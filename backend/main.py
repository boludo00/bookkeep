from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import structlog
import logging
import sys
import os

from app.database import engine, Base
from app.routers import users, books, hardcover, requests, settings, readarr, jobs, booklore, auth, download_settings, downloads
from app import cache

# Configure Python's standard logging to emit structlog-style console output.
shared_processors = [
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
]
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(
    structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(),
        foreign_pre_chain=shared_processors,
    )
)
root_logger = logging.getLogger()
root_logger.handlers = [handler]
root_logger.setLevel(logging.INFO)

# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Create database tables and run migrations on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # Alembic migrations are handled by entrypoint.sh
    # Always ensure tables exist (migrations may have skipped if tables didn't exist)
    # This is safe because migrations are idempotent and will add missing columns
    Base.metadata.create_all(bind=engine)
    logger.info("database_tables_ensured")
    
    # Initialize cache
    await cache.init_cache()
    logger.info("cache_initialized")
    
    # Start APScheduler for background jobs
    try:
        from app.scheduler import start_scheduler, initialize_jobs
        start_scheduler()
        await initialize_jobs()
        logger.info("scheduler_initialized")
    except Exception as e:
        logger.warning("scheduler_failed", error=str(e))
    
    yield
    
    # Shutdown
    await cache.close_cache()
    logger.info("cache_closed")

app = FastAPI(
    title="Book Hound API",
    description="Backend API for Book Hound application",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS - allow all origins when serving static files
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers FIRST (before static files) so API routes take precedence
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(books.router, prefix="/api/books", tags=["books"])
app.include_router(hardcover.router, prefix="/api/hardcover", tags=["hardcover"])
app.include_router(requests.router, prefix="/api/requests", tags=["requests"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(readarr.router, prefix="/api/readarr", tags=["readarr"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(booklore.router, prefix="/api/booklore", tags=["booklore"])
app.include_router(download_settings.router, prefix="/api/download-settings", tags=["download-settings"])
app.include_router(downloads.router, prefix="/api/downloads", tags=["downloads"])
app.include_router(auth.router)  # No prefix, it's already in the router

enable_debug_routes = os.getenv("BOOKHOUND_DEBUG_ROUTES", "").lower() in {"1", "true", "yes"}
if enable_debug_routes:
    # Log jobs router registration for debugging
    logger.info("jobs_router_registered", prefix="/api/jobs", routes_count=len(jobs.router.routes))
    for route in jobs.router.routes:
        if hasattr(route, "path"):
            logger.info("jobs_route_registered", path=route.path, methods=getattr(route, "methods", None))

# Health check route (before static files mount)
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if enable_debug_routes:
    # Debug endpoint to list all routes (temporary, for debugging)
    @app.get("/debug/routes")
    async def debug_routes():
        """Debug endpoint to list all registered routes"""
        routes = []
        for route in app.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                routes.append({
                    "path": route.path,
                    "methods": list(route.methods) if route.methods else [],
                    "name": getattr(route, "name", None)
                })
        return {"routes": routes, "total": len(routes)}

# Serve static files (frontend build)
static_dir = os.path.join(os.path.dirname(__file__), "..", "frontend_dist")
if os.path.exists(static_dir):
    # Mount static files for assets (JS, CSS, images, etc.)
    assets_dir = os.path.join(static_dir, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    
    # Catch-all route for SPA routing - serves index.html for all non-API routes
    # This must be registered LAST so API routes take precedence
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        # Skip API routes and health check (these are handled by routes above)
        if full_path.startswith("api/") or full_path == "health":
            raise HTTPException(status_code=404, detail="Not Found")
        
        # Check if it's a static file that exists (like favicon.ico, robots.txt, etc.)
        file_full_path = os.path.join(static_dir, full_path)
        if os.path.isfile(file_full_path):
            # Security check: ensure the file is within static_dir
            try:
                if os.path.commonpath([static_dir, file_full_path]) == static_dir:
                    return FileResponse(file_full_path)
            except ValueError:
                # Paths don't share a common base, reject
                pass
        
        # For all SPA routes (like /series, /book/123, etc.), serve index.html
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        
        raise HTTPException(status_code=404, detail="Not Found")
