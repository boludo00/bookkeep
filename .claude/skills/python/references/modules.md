# Python Modules Reference

## Contents
- Project Structure
- Router Organization
- Service Layer
- Download System
- Background Tasks

---

## Project Structure

```
backend/
├── main.py                 # FastAPI app, lifespan, router includes
├── app/
│   ├── models.py           # SQLAlchemy ORM models
│   ├── schemas.py          # Pydantic request/response schemas
│   ├── database.py         # Engine, SessionLocal, get_db dependency
│   ├── cache.py            # Redis/memory cache abstraction
│   ├── auth.py             # Password hashing, current_user dependency
│   ├── jwt.py              # Token creation/verification
│   ├── scheduler.py        # APScheduler configuration
│   ├── tasks.py            # Background job implementations
│   ├── routers/            # API route handlers
│   │   ├── auth.py         # /api/auth/login, /api/auth/refresh
│   │   ├── books.py        # /api/books CRUD
│   │   ├── requests.py     # /api/requests management
│   │   ├── downloads.py    # /api/downloads search and trigger
│   │   └── ...
│   ├── downloads/          # Download orchestration
│   │   ├── orchestrator.py
│   │   ├── prowlarr/       # Indexer integration
│   │   ├── clients/        # qBittorrent, NZBGet, SABnzbd
│   │   └── handlers/       # Protocol handlers
│   └── services/           # Business logic
```

---

## Router Organization

### Router File Template

```python
# backend/app/routers/books.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas, database
from app.auth import get_current_user
import structlog

logger = structlog.get_logger()
router = APIRouter()  # No prefix here - added in main.py

@router.get("/", response_model=list[schemas.BookResponse])
def list_books(db: Session = Depends(database.get_db)):
    return db.query(models.Book).all()

@router.post("/", response_model=schemas.BookResponse, status_code=status.HTTP_201_CREATED)
def create_book(book: schemas.BookCreate, db: Session = Depends(database.get_db)):
    db_book = models.Book(**book.model_dump())
    db.add(db_book)
    db.commit()
    db.refresh(db_book)
    return db_book
```

### Main App Router Registration

```python
# backend/main.py
from app.routers import auth, books, requests, downloads

app.include_router(auth.router)  # prefix in router: /api/auth
app.include_router(books.router, prefix="/api/books", tags=["books"])
app.include_router(requests.router, prefix="/api/requests", tags=["requests"])
app.include_router(downloads.router, prefix="/api/downloads", tags=["downloads"])
```

---

## Service Layer Pattern

### When to Extract Services

Extract to `services/` when:
- Logic is reused across multiple routers
- Complex business rules need isolation
- External API integration is involved

```python
# backend/app/services/readarr_service.py
import structlog
from app import models

logger = structlog.get_logger()

class ReadarrClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key
    
    @classmethod
    def from_server(cls, server: models.ReadarrServer) -> "ReadarrClient":
        return cls(base_url=server.url, api_key=server.api_key)
    
    async def find_book_in_library(self, client, hardcover_id: str) -> Optional[dict]:
        try:
            response = await self._get(client, "/book/lookup", params={"term": hardcover_id})
            return response.json()[0] if response.json() else None
        except Exception as e:
            logger.debug("readarr_lookup_failed", hardcover_id=hardcover_id, error=str(e))
            return None
```

---

## Download System Architecture

```
downloads/
├── orchestrator.py      # Coordinates search → download flow
├── prowlarr/
│   ├── api.py           # Prowlarr REST API client
│   └── source.py        # Release source abstraction
├── clients/
│   ├── qbittorrent.py   # qBittorrent WebUI client
│   ├── nzbget.py        # NZBGet JSON-RPC client
│   └── sabnzbd.py       # SABnzbd REST client
└── handlers/
    ├── torrent.py       # Torrent protocol handler
    └── usenet.py        # Usenet protocol handler
```

### Orchestrator Pattern

```python
# backend/app/downloads/orchestrator.py
class DownloadOrchestrator:
    async def search(self, book: models.Book, format_type: str, db: Session) -> list[dict]:
        """Search all configured sources for releases."""
        releases = []
        for source in self._get_sources(db):
            try:
                results = await source.search(book.title, book.author, format_type)
                releases.extend(results)
            except Exception as e:
                logger.warning("source_search_failed", source=source.name, error=str(e))
        return self._rank_releases(releases)
    
    async def download(self, release: dict, book: models.Book, db: Session) -> models.DownloadTask:
        """Start download via appropriate handler."""
        handler = self._get_handler(release["protocol"])
        task = await handler.start_download(release, book)
        db.add(task)
        db.commit()
        return task
```

---

## Background Tasks

### Task Implementation

```python
# backend/app/tasks.py
import structlog
from app.database import SessionLocal
from app import models

logger = structlog.get_logger()

async def sync_download_states():
    """Poll download clients for status updates."""
    db = SessionLocal()
    try:
        active_tasks = db.query(models.DownloadTask).filter(
            models.DownloadTask.state.in_(["downloading", "queued"])
        ).all()
        
        for task in active_tasks:
            try:
                handler = get_handler(task.protocol)
                status = await handler.get_status(task.external_id)
                task.progress = status.progress
                task.state = status.state
                db.commit()
                logger.info("task_synced", task_id=task.id, state=task.state)
            except Exception as e:
                logger.warning("task_sync_failed", task_id=task.id, error=str(e))
    finally:
        db.close()
```

### Registering Jobs

```python
# backend/app/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

def add_job(name: str, func, interval_seconds: int):
    scheduler.add_job(
        func,
        trigger="interval",
        seconds=interval_seconds,
        id=name,
        replace_existing=True,
    )