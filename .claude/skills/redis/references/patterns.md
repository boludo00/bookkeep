# Redis Patterns Reference

## Contents
- Cache Module Architecture
- Cache-Aside Implementation
- Cache Key Generation
- Cache Invalidation Patterns
- Anti-Patterns

## Cache Module Architecture

The cache abstraction in `backend/app/cache.py` provides:

```python
# Core exports
from app.cache import (
    get_cached,           # async (key) -> Optional[Any]
    set_cached,           # async (key, value, ttl) -> bool
    delete_cached,        # async (key) -> bool
    clear_cache_pattern,  # async (pattern) -> int (deleted count)
    make_cache_key,       # (prefix, **kwargs) -> str
    CACHE_TTL,           # Dict[str, int] - TTLs by resource
    CACHE_RESOURCES,     # Dict - Admin UI resource definitions
)
```

## Cache-Aside Implementation

Standard pattern used throughout `backend/app/routers/hardcover.py`:

```python
# From hardcover.py:1676-1680
cache_key = cache.make_cache_key("trending", limit=limit, date=current_date)
cached_result = await cache.get_cached(cache_key)
if cached_result is not None:
    return cached_result

# Expensive API call
result = await fetch_from_hardcover()

# Cache for next request
await cache.set_cached(
    cache_key,
    result.model_dump(),  # Pydantic model to dict
    ttl=cache.CACHE_TTL["trending"]
)
```

## Cache Key Generation

`make_cache_key` creates deterministic keys by sorting kwargs:

```python
# backend/app/cache.py:266-271
def make_cache_key(prefix: str, **kwargs) -> str:
    parts = [prefix]
    for key, value in sorted(kwargs.items()):
        parts.append(f"{key}:{value}")
    return ":".join(parts)

# Examples:
make_cache_key("search", query="python", limit=10)
# → "search:limit:10:query:python"

make_cache_key("requests_by_hardcover_batch", ids="1,2,3")
# → "requests_by_hardcover_batch:ids:1,2,3"
```

## Cache Invalidation Patterns

### Single Key Invalidation

Use after mutations that affect a specific entity:

```python
# From requests.py:394-396
await delete_cached(make_cache_key("requests_by_hardcover", hardcover_id=hardcover_id))
```

### Pattern-Based Invalidation

Use when mutation affects multiple cache entries:

```python
# From requests.py:183
await clear_cache_pattern("requests_by_hardcover_batch:*")

# Clear all series caches
await clear_cache_pattern("series:*")
```

### Write-Through Invalidation

```python
# After creating/updating request
await delete_cached(make_cache_key("requests_by_hardcover", hardcover_id=book.hardcover_id))
await clear_cache_pattern("requests_by_hardcover_batch:*")
```

---

## WARNING: Forgetting Cache Invalidation

**The Problem:**

```python
# BAD - Mutation without invalidation
@router.put("/books/{book_id}")
async def update_book(book_id: int, data: BookUpdate, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    book.title = data.title
    db.commit()
    return book  # Cache still has old data!
```

**Why This Breaks:**
1. Users see stale data until TTL expires
2. Inconsistent state between cache and database
3. Hard to debug - "sometimes it shows old data"

**The Fix:**

```python
# GOOD - Invalidate after mutation
@router.put("/books/{book_id}")
async def update_book(book_id: int, data: BookUpdate, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    book.title = data.title
    db.commit()
    
    # Invalidate affected caches
    await cache.delete_cached(cache.make_cache_key("book_details", book_id=book_id))
    if book.series_id:
        await cache.delete_cached(cache.make_cache_key("series", series_id=book.series_id))
    
    return book
```

---

## WARNING: Cache Keys Without Namespace

**The Problem:**

```python
# BAD - Generic key that could collide
cache_key = f"book:{book_id}"
```

**Why This Breaks:**
1. No namespace prefix - collides with other apps sharing Redis
2. No sorted parameter ordering - `book:1:limit:10` ≠ `book:limit:10:1`

**The Fix:**

```python
# GOOD - Use make_cache_key with resource prefix
cache_key = make_cache_key("book_details", book_id=book_id, limit=limit)
# aiocache adds "bookkeep:" namespace automatically
```

---

## WARNING: Caching Mutable Objects

**The Problem:**

```python
# BAD - Caching Pydantic model directly
await cache.set_cached(key, pydantic_response)  # May not serialize correctly
```

**Why This Breaks:**
1. aiocache uses JsonSerializer - complex objects may fail
2. Pydantic models need explicit serialization

**The Fix:**

```python
# GOOD - Serialize to dict first
await cache.set_cached(key, response.model_dump(), ttl=ttl)

# When reading, reconstruct if needed
cached = await cache.get_cached(key)
if cached:
    return ResponseModel(**cached)