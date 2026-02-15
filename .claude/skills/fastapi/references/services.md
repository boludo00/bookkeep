# Services Reference

## Contents
- Service Layer Pattern
- External API Integration
- Background Tasks
- Caching Integration
- Anti-Patterns

---

## Service Layer Pattern

Extract business logic from routes into service classes for testability and reuse.

### Service Class Structure

```python
# backend/app/services/book_service.py
from sqlalchemy.orm import Session
from app import models, schemas
from app.cache import get_cached, set_cached, CACHE_TTL

class BookService:
    def __init__(self, db: Session):
        self.db = db

    def get_book(self, book_id: int) -> models.Book | None:
        return self.db.query(models.Book).filter(models.Book.id == book_id).first()

    def create_book(self, book_data: schemas.BookCreate) -> models.Book:
        db_book = models.Book(**book_data.model_dump())
        self.db.add(db_book)
        self.db.commit()
        self.db.refresh(db_book)
        return db_book

    async def get_book_with_cache(self, book_id: int) -> models.Book | None:
        cache_key = f"book_details:{book_id}"
        cached = await get_cached(cache_key)
        if cached:
            return cached
        book = self.get_book(book_id)
        if book:
            await set_cached(cache_key, book, ttl=CACHE_TTL["book_details"])
        return book
```

### Using Service in Routes

```python
# backend/app/routers/books.py
from app.services.book_service import BookService

@router.get("/{book_id}", response_model=schemas.BookResponse)
async def get_book(book_id: int, db: Session = Depends(get_db)):
    service = BookService(db)
    book = await service.get_book_with_cache(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book
```

---

## External API Integration

### Async HTTP Client Pattern

```python
# backend/app/services/hardcover_client.py
import httpx
import structlog

logger = structlog.get_logger(__name__)

class HardcoverClient:
    BASE_URL = "https://api.hardcover.app/v1/graphql"

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    async def search_books(self, query: str, limit: int = 20) -> list[dict]:
        graphql_query = {
            "query": """
                query SearchBooks($query: String!, $limit: Int!) {
                    books(where: {title: {_ilike: $query}}, limit: $limit) {
                        id
                        title
                        slug
                    }
                }
            """,
            "variables": {"query": f"%{query}%", "limit": limit}
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    self.BASE_URL,
                    json=graphql_query,
                    headers=self.headers
                )
                response.raise_for_status()
                data = response.json()
                return data.get("data", {}).get("books", [])
            except httpx.TimeoutException:
                logger.error("hardcover_timeout", query=query)
                raise
            except httpx.HTTPStatusError as e:
                logger.error("hardcover_error", status=e.response.status_code)
                raise
```

### Usage in Routes

```python
@router.get("/search")
async def search_books(
    query: str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    token, _ = get_hardcover_token(db)
    if not token:
        raise HTTPException(status_code=503, detail="Hardcover not configured")

    client = HardcoverClient(token)
    return await client.search_books(query, limit)
```

---

## Background Tasks

### Task Implementation Pattern

See the **apscheduler** skill for scheduler configuration.

```python
# backend/app/tasks.py
import structlog
from app.database import SessionLocal
from app import models

logger = structlog.get_logger(__name__)

async def sync_download_states():
    """Background task to sync download client states"""
    db = SessionLocal()
    try:
        # Get all active download tasks
        tasks = db.query(models.DownloadTask).filter(
            models.DownloadTask.state.in_(["downloading", "queued"])
        ).all()

        for task in tasks:
            try:
                # Check with download client
                client = get_download_client(db, task.client_id)
                status = await client.get_status(task.external_id)

                # Update task state
                task.progress = status.get("progress", 0)
                task.state = status.get("state", task.state)

                if status.get("state") == "completed":
                    task.state = "completed"
                    logger.info("download_completed", task_id=task.id)

            except Exception as e:
                logger.error("sync_task_error", task_id=task.id, error=str(e))

        db.commit()
        logger.info("sync_download_states_complete", count=len(tasks))
    finally:
        db.close()
```

### One-Off Background Task (FastAPI)

```python
from fastapi import BackgroundTasks

@router.post("/downloads/start")
async def start_download(
    request: schemas.DownloadRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    # Create download task record
    task = models.DownloadTask(...)
    db.add(task)
    db.commit()

    # Queue actual download in background
    background_tasks.add_task(execute_download, task.id)

    return {"task_id": task.id, "status": "queued"}
```

---

## Caching Integration

### Cache-Aside Pattern

```python
# backend/app/cache.py usage
from app.cache import get_cached, set_cached, delete_cached, make_cache_key, CACHE_TTL

async def get_trending_books(db: Session) -> list[dict]:
    cache_key = make_cache_key("trending", page=1, limit=50)

    # Check cache
    cached = await get_cached(cache_key)
    if cached:
        return cached

    # Fetch from database
    books = db.query(models.Book).filter(
        models.Book.is_seed_data == True
    ).order_by(models.Book.created_at.desc()).limit(50).all()

    result = [schemas.BookResponse.model_validate(b).model_dump() for b in books]

    # Cache result
    await set_cached(cache_key, result, ttl=CACHE_TTL["trending"])

    return result
```

### Cache Invalidation

```python
async def update_book(book_id: int, data: schemas.BookUpdate, db: Session):
    book = db.query(models.Book).filter(models.Book.id == book_id).first()
    # ... update logic

    # Invalidate related caches
    await delete_cached(f"book_details:{book_id}")
    await delete_cached(make_cache_key("search", query=book.title))

    db.commit()
    return book
```

---

## WARNING: Service Anti-Patterns

### Mixing Sync and Async

**The Problem:**

```python
# BAD - Blocking sync call inside async function
async def fetch_book_data(book_id: int):
    import requests
    response = requests.get(f"https://api.example.com/books/{book_id}")  # BLOCKS!
    return response.json()
```

**Why This Breaks:**
1. Blocks the entire event loop
2. Other requests cannot be processed
3. Defeats the purpose of async

**The Fix:**

```python
# GOOD - Use async HTTP client
async def fetch_book_data(book_id: int):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.example.com/books/{book_id}")
        return response.json()
```

### Leaking Database Sessions

**The Problem:**

```python
# BAD - Session not closed on error
async def process_books():
    db = SessionLocal()
    books = db.query(models.Book).all()
    for book in books:
        await external_api_call(book)  # If this raises, db leaks!
    db.close()
```

**The Fix:**

```python
# GOOD - Always use try/finally
async def process_books():
    db = SessionLocal()
    try:
        books = db.query(models.Book).all()
        for book in books:
            await external_api_call(book)
    finally:
        db.close()
```

### Hardcoded Configuration

**The Problem:**

```python
# BAD - Secrets in code
class APIClient:
    API_KEY = "sk-12345-hardcoded-key"
    BASE_URL = "https://api.example.com"
```

**The Fix:**

```python
# GOOD - Environment variables
import os

class APIClient:
    def __init__(self):
        self.api_key = os.getenv("API_KEY")
        self.base_url = os.getenv("API_BASE_URL", "https://api.example.com")
        if not self.api_key:
            raise ValueError("API_KEY environment variable required")
```
