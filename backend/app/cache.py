"""
Cache configuration and utilities for the Book Hound API.

Uses Redis for distributed caching, falls back to in-memory cache if Redis unavailable.
"""
import os
from typing import Optional, Any
from aiocache import Cache
from aiocache.serializers import JsonSerializer
import structlog

logger = structlog.get_logger()

# Redis configuration from environment (optional)
REDIS_URL = os.getenv("REDIS_URL", "")

# Cache TTLs (in seconds)
CACHE_TTL = {
    "trending": 86400,     # 24 hours
    "popular": 21600,      # 6 hours
    "new_releases": 86400, # 24 hours
    "search": 1800,        # 30 minutes
    "book_details": 86400, # 24 hours
    "series": 86400,       # 24 hours
    "popular_series": 86400, # 24 hours
    "similar_books": 604800, # 7 days - recommendations don't change often
    "book_prompts": 86400, # 24 hours - prompt summaries are stable
    "author": 86400, # 24 hours
    "search_grouped": 1800, # 30 minutes
    "readarr_library": 60, # 1 minute
    "requests_by_hardcover": 30, # 30 seconds
}

# Initialize cache - try Redis first, fallback to memory
cache_instance: Optional[Cache] = None

async def init_cache():
    """Initialize cache connection"""
    global cache_instance
    if REDIS_URL:
        try:
            # Parse Redis URL
            def _parse_redis_url(url: str) -> dict:
                if url.startswith("redis://"):
                    url = url[8:]
                parts = url.split("/")
                host_port = parts[0]
                db = int(parts[1]) if len(parts) > 1 else 0
                
                if ":" in host_port:
                    host, port = host_port.split(":")
                    port = int(port)
                else:
                    host = host_port
                    port = 6379
                
                return {"endpoint": host, "port": port, "db": db}
            
            redis_config = _parse_redis_url(REDIS_URL)
            cache_instance = Cache(
                Cache.REDIS,
                endpoint=redis_config["endpoint"],
                port=redis_config["port"],
                db=redis_config["db"],
                serializer=JsonSerializer(),
                namespace="bookhound",
            )
            # Test connection
            await cache_instance.get("test")
            logger.info("cache_backend", backend="redis", url=REDIS_URL)
        except Exception as e:
            logger.warning("redis_init_failed", error=str(e), fallback="memory")
            cache_instance = Cache(Cache.MEMORY, serializer=JsonSerializer(), namespace="bookhound")
            logger.info("cache_backend", backend="memory")
    else:
        # No Redis URL, use in-memory cache
        cache_instance = Cache(Cache.MEMORY, serializer=JsonSerializer(), namespace="bookhound")
        logger.info("cache_backend", backend="memory")

async def close_cache():
    """Close cache connection"""
    global cache_instance
    if cache_instance:
        try:
            await cache_instance.close()
            logger.info("cache_closed")
        except Exception as e:
            logger.warning("cache_close_error", error=str(e))
        finally:
            cache_instance = None

async def get_cached(key: str) -> Optional[Any]:
    """Get a value from cache"""
    if not cache_instance:
        return None
    try:
        value = await cache_instance.get(key)
        if value is not None:
            logger.debug("cache_hit", key=key)
        return value
    except Exception as e:
        logger.debug("cache_get_error", key=key, error=str(e))
        return None

async def set_cached(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """Set a value in cache with optional TTL"""
    if not cache_instance:
        return False
    try:
        await cache_instance.set(key, value, ttl=ttl)
        logger.debug("cache_set", key=key, ttl=ttl)
        return True
    except Exception as e:
        logger.debug("cache_set_error", key=key, error=str(e))
        return False

async def delete_cached(key: str) -> bool:
    """Delete a value from cache"""
    if not cache_instance:
        return False
    try:
        await cache_instance.delete(key)
        logger.debug("cache_delete", key=key)
        return True
    except Exception as e:
        logger.debug("cache_delete_error", key=key, error=str(e))
        return False

def make_cache_key(prefix: str, **kwargs) -> str:
    """Create a cache key from prefix and keyword arguments"""
    parts = [prefix]
    for key, value in sorted(kwargs.items()):
        parts.append(f"{key}:{value}")
    return ":".join(parts)
