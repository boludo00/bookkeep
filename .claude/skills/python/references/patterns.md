# Python Patterns Reference

## Contents
- Async Patterns
- Dependency Injection
- Database Session Management
- Graceful Degradation
- Background Jobs
- Caching

---

## Async Patterns

### Async Context Managers for Resources

```python
# GOOD - Resource cleanup with async context manager
async with readarr_client.session(timeout=10.0) as client:
    result = await client.find_book(hardcover_id)

# GOOD - Lifespan for app startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    await cache.init_cache()
    yield
    await cache.close_cache()

app = FastAPI(lifespan=lifespan)
```

### WARNING: Sync Code in Async Context

**The Problem:**

```python
# BAD - Blocking call in async function
async def get_book_details(isbn: str):
    response = requests.get(f"https://api.example.com/{isbn}")  # BLOCKS!
    return response.json()
```

**Why This Breaks:**
1. Blocks the entire event loop, stalling all concurrent requests
2. Defeats the purpose of async—one slow call blocks everything
3. Can cause request timeouts across the entire application

**The Fix:**

```python
# GOOD - Use async HTTP client
import httpx

async def get_book_details(isbn: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.example.com/{isbn}")
        return response.json()
```

---

## Dependency Injection

### Database Session Pattern

```python
# database.py
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Usage in router
@router.post("/", response_model=schemas.BookResponse)
def create_book(book: schemas.BookCreate, db: Session = Depends(get_db)):
    db_book = models.Book(**book.model_dump())
    db.add(db_book)
    db.commit()
    return db_book
```

### Auth Dependency Chain

```python
# auth.py
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> models.User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token_data = verify_access_token(credentials.credentials)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(models.User).filter(models.User.id == token_data.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user

# Usage
@router.delete("/{user_id}")
def delete_user(user_id: int, admin: models.User = Depends(require_admin)):
    ...
```

---

## Graceful Degradation

### Multi-Source Fallback Pattern

```python
# Check multiple sources, continue on failure
async def check_book_availability(book: models.Book, db: Session) -> dict:
    ebook_available = book.ebook_available
    checked_sources = []
    
    for server in db.query(models.ReadarrServer).all():
        try:
            client = ReadarrClient.from_server(server)
            async with client.session(timeout=10.0) as session:
                result = await client.find_book(session, book.hardcover_id)
                if result:
                    ebook_available = True
                    checked_sources.append(server.name)
        except Exception as e:
            logger.warning("readarr_check_failed", 
                          server_id=server.id, 
                          book_id=book.id, 
                          error=str(e))
            # Continue to next server instead of failing
    
    return {"ebook_available": ebook_available, "sources": checked_sources}
```

### Cache Fallback Pattern

```python
# Try Redis, fall back to memory cache
async def init_cache():
    global cache_instance
    if REDIS_URL:
        try:
            cache_instance = Cache(Cache.REDIS, endpoint=redis_host, port=redis_port)
            await cache_instance.get("test")  # Verify connection
            logger.info("cache_backend", backend="redis")
        except Exception as e:
            logger.warning("redis_init_failed", error=str(e), fallback="memory")
            cache_instance = Cache(Cache.MEMORY)
    else:
        cache_instance = Cache(Cache.MEMORY)
```

---

## Background Jobs

### APScheduler Job Pattern

```python
# scheduler.py
JOB_DEFINITIONS = {
    "sync_download_states": {
        "default_interval": 2 * 60,  # 2 minutes
        "description": "Poll download clients for status",
        "type": "PROCESS",
    },
}

async def initialize_jobs():
    job_functions = {
        "sync_download_states": sync_download_states,
    }
    for job_name, definition in JOB_DEFINITIONS.items():
        schedule = db.query(JobSchedule).filter(JobSchedule.job_name == job_name).first()
        interval = schedule.interval_seconds if schedule else definition["default_interval"]
        scheduler.add_job(job_functions[job_name], "interval", seconds=interval, id=job_name)
```

---

## Environment Configuration

```python
# GOOD - Fallback with type conversion
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("BOOKKEEP_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# GOOD - Optional with None default
REDIS_URL = os.getenv("REDIS_URL")  # None if not set

# GOOD - Database URL with fallback path
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{Path(__file__).parent / 'data/bookkeep.db'}"