# Redis Workflows Reference

## Contents
- Adding Cache to a New Endpoint
- Cache Debugging Workflow
- Cache Clear Operations
- Testing Cache Behavior
- Environment Configuration

## Adding Cache to a New Endpoint

Copy this checklist and track progress:
- [ ] Step 1: Define TTL in `CACHE_TTL` dict if new resource type
- [ ] Step 2: Implement cache-aside pattern in endpoint
- [ ] Step 3: Add invalidation to related mutation endpoints
- [ ] Step 4: Add resource to `CACHE_RESOURCES` for admin UI (if applicable)
- [ ] Step 5: Test with Redis running and with fallback

### Step 1: Define TTL

```python
# backend/app/cache.py:18
CACHE_TTL = {
    # ... existing entries
    "my_new_resource": 3600,  # 1 hour
}
```

### Step 2: Cache-Aside Implementation

```python
from app import cache

@router.get("/my-endpoint/{id}")
async def get_my_resource(id: int):
    cache_key = cache.make_cache_key("my_new_resource", id=id)
    cached = await cache.get_cached(cache_key)
    if cached is not None:
        return cached
    
    result = await expensive_operation(id)
    await cache.set_cached(cache_key, result, ttl=cache.CACHE_TTL["my_new_resource"])
    return result
```

### Step 3: Add Invalidation

```python
@router.put("/my-endpoint/{id}")
async def update_my_resource(id: int, data: UpdateSchema):
    # ... mutation logic
    await cache.delete_cached(cache.make_cache_key("my_new_resource", id=id))
    return result
```

### Step 4: Register for Admin UI

```python
# backend/app/cache.py:275
CACHE_RESOURCES = {
    # ... existing entries
    "my_resources": {
        "name": "My Resources",
        "description": "Description for admin UI",
        "patterns": ["my_new_resource:*"],
    },
}
```

---

## Cache Debugging Workflow

### Check Cache Backend Type

```bash
# In Docker logs
docker-compose logs app | grep cache_backend
# Output: cache_backend backend=redis url=redis://redis:6379/0
# Or:     cache_backend backend=memory
```

### Inspect Redis Keys (Admin Endpoint)

```bash
curl -X GET "http://localhost:8000/api/settings/cache/debug" \
  -H "Authorization: Bearer $TOKEN"
# Returns: {"total_keys": 42, "sample_keys": [...], "namespace": "bookkeep"}
```

### Direct Redis Inspection

```bash
# Connect to Redis container
docker exec -it book-hound-redis redis-cli

# List all bookkeep keys
KEYS bookkeep:*

# Get specific key value
GET bookkeep:book_details:book_id:123

# Check TTL
TTL bookkeep:book_details:book_id:123
```

### Clear Specific Resource Cache

```bash
curl -X POST "http://localhost:8000/api/settings/cache/clear/books" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
# Returns: {"message": "Cleared Books cache", "deleted_count": 15}
```

---

## Cache Clear Operations

### Via Admin API

```python
# List available resources
GET /api/settings/cache/resources

# Clear specific resource
POST /api/settings/cache/clear/{resource}
# Resources: books, series, authors, discovery, requests

# Clear all caches
POST /api/settings/cache/clear-all
```

### Programmatic Clear

```python
from app.cache import clear_cache_by_resource, clear_all_cache

# Clear single resource
result = await clear_cache_by_resource("books")
# {"resource": "books", "deleted_count": 15, "patterns": ["book_details:*", ...]}

# Clear everything
result = await clear_all_cache()
# {"total_deleted": 150, "by_resource": {"books": 15, "series": 20, ...}}
```

---

## Testing Cache Behavior

### Test Cache Hit

```python
import pytest
from app.cache import get_cached, set_cached, make_cache_key

@pytest.mark.asyncio
async def test_cache_hit():
    key = make_cache_key("test", id=1)
    await set_cached(key, {"data": "value"}, ttl=60)
    
    result = await get_cached(key)
    assert result == {"data": "value"}
```

### Test Fallback to Memory

```bash
# Stop Redis and verify app still works
docker-compose stop redis
curl http://localhost:8000/api/hardcover/trending?limit=10
# Should work but logs show: cache_backend backend=memory
```

---

## Environment Configuration

### Docker Compose (Production)

```yaml
# docker-compose.yml
services:
  app:
    environment:
      REDIS_URL: redis://redis:6379/0
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
```

### Local Development (No Redis)

```bash
# Omit REDIS_URL - falls back to memory cache
export DATABASE_URL=postgresql://...
uvicorn main:app --reload
# Log shows: cache_backend backend=memory
```

### Custom Redis Configuration

```bash
# Custom Redis with password
export REDIS_URL=redis://:password@redis-host:6379/1

# TLS connection (if supported)
export REDIS_URL=rediss://redis-host:6380/0
```

---

## WARNING: Using Memory Cache in Production

**The Problem:**
Running production without Redis (`REDIS_URL` unset) uses in-memory cache.

**Why This Breaks:**
1. Cache lost on every restart
2. No cache sharing between multiple app instances
3. Memory usage grows unbounded (no LRU eviction)

**The Fix:**
Always configure `REDIS_URL` in production deployments. The fallback is only for local development.