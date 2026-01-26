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
    "popular": 86400,      # 24 hours
    "new_releases": 86400, # 24 hours
    "search": 1800,        # 30 minutes
    "book_details": 86400, # 24 hours
    "series": 604800,      # 7 days
    "popular_series": 86400, # 24 hours
    "similar_books": 604800, # 7 days - recommendations don't change often
    "book_prompts": None, # never expire - prompt summaries are stable
    "author": 86400, # 24 hours
    "search_grouped": 1800, # 30 minutes
    "requests_by_hardcover": 300, # 5 minutes
    "requests_by_hardcover_batch": 300, # 5 minutes
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
                namespace="bookkeep",
            )
            # Test connection
            await cache_instance.get("test")
            logger.info("cache_backend", backend="redis", url=REDIS_URL)
        except Exception as e:
            logger.warning("redis_init_failed", error=str(e), fallback="memory")
            cache_instance = Cache(Cache.MEMORY, serializer=JsonSerializer(), namespace="bookkeep")
            logger.info("cache_backend", backend="memory")
    else:
        # No Redis URL, use in-memory cache
        cache_instance = Cache(Cache.MEMORY, serializer=JsonSerializer(), namespace="bookkeep")
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

async def clear_cache_pattern(pattern: str) -> int:
    """
    Clear all cache keys matching a pattern.
    For Redis, uses SCAN to find matching keys.
    For in-memory cache, iterates through all keys.

    Pattern examples: "requests_by_hardcover_batch:*"
    Returns: Number of keys deleted
    """
    if not cache_instance:
        return 0

    deleted_count = 0
    try:
        import fnmatch

        # Get the namespace (used by both backends)
        namespace = getattr(cache_instance, 'namespace', '')

        # Check if this is a Redis backend by looking at the class name
        cache_class = cache_instance.__class__.__name__
        is_redis = 'Redis' in cache_class

        if is_redis:
            # Redis backend - use redis-py directly to scan and delete keys
            # Build the full pattern with namespace
            if namespace:
                full_pattern = f"{namespace}:{pattern}"
            else:
                full_pattern = pattern

            # aiocache's RedisCache doesn't expose the client directly,
            # so we need to create our own Redis connection for pattern deletion
            try:
                import redis.asyncio as aioredis

                # Parse the Redis URL to get connection info
                redis_url = REDIS_URL
                if redis_url:
                    # Create a direct Redis connection for SCAN/DELETE operations
                    redis_client = aioredis.from_url(redis_url, decode_responses=True)

                    logger.info("redis_scan_starting", pattern=full_pattern)
                    cursor = 0
                    while True:
                        cursor, keys = await redis_client.scan(cursor, match=full_pattern, count=100)
                        if keys:
                            logger.info("redis_scan_found_keys", cursor=cursor, keys_found=len(keys), sample_keys=keys[:5])
                        for key in keys:
                            await redis_client.delete(key)
                            deleted_count += 1
                        if cursor == 0:
                            break

                    logger.info("redis_scan_complete", pattern=full_pattern, total_deleted=deleted_count)
                    await redis_client.aclose()
                else:
                    logger.warning("redis_url_not_set")
            except ImportError:
                logger.warning("redis_asyncio_not_available")
            except Exception as e:
                logger.warning("redis_direct_connection_failed", error=str(e))
        else:
            # In-memory backend (SimpleMemoryCache)
            # Try multiple ways to access the internal cache dict
            cache_dict = None

            # Method 1: Direct _cache attribute (some aiocache versions)
            if hasattr(cache_instance, '_cache') and isinstance(cache_instance._cache, dict):
                cache_dict = cache_instance._cache
                logger.debug("cache_found_via_direct_cache")

            # Method 2: _backend._cache (newer aiocache)
            if cache_dict is None:
                backend = getattr(cache_instance, '_backend', None)
                if backend and hasattr(backend, '_cache'):
                    cache_dict = backend._cache
                    logger.debug("cache_found_via_backend")

            # Method 3: _cache._cache (wrapped backend)
            if cache_dict is None:
                inner_cache = getattr(cache_instance, '_cache', None)
                if inner_cache and hasattr(inner_cache, '_cache'):
                    cache_dict = inner_cache._cache
                    logger.debug("cache_found_via_inner_cache")

            # Method 4: Try to introspect the object
            if cache_dict is None:
                # Log available attributes for debugging
                attrs = [a for a in dir(cache_instance) if not a.startswith('__')]
                logger.warning(
                    "cache_dict_not_found",
                    cache_class=cache_class,
                    available_attrs=attrs[:20]  # Limit to first 20
                )

            if cache_dict is not None:
                keys_to_delete = []

                # Build full pattern with namespace for matching
                if namespace:
                    full_pattern = f"{namespace}:{pattern}"
                else:
                    full_pattern = pattern

                # Log all keys for debugging (limit to avoid huge logs)
                all_keys = list(cache_dict.keys())
                logger.info(
                    "cache_memory_keys",
                    pattern=full_pattern,
                    total_keys=len(all_keys),
                    sample_keys=all_keys[:5] if all_keys else []
                )

                # Find keys matching pattern (glob-style matching)
                for key in all_keys:
                    if fnmatch.fnmatch(key, full_pattern):
                        keys_to_delete.append(key)

                # Delete matching keys directly from the backend
                for key in keys_to_delete:
                    if key in cache_dict:
                        del cache_dict[key]
                        deleted_count += 1

                logger.debug(
                    "cache_pattern_memory_clear",
                    pattern=full_pattern,
                    matched_keys=len(keys_to_delete)
                )

        logger.info("cache_pattern_cleared", pattern=pattern, deleted_count=deleted_count)
        return deleted_count
    except Exception as e:
        logger.warning("cache_pattern_clear_error", pattern=pattern, error=str(e))
        return deleted_count

def make_cache_key(prefix: str, **kwargs) -> str:
    """Create a cache key from prefix and keyword arguments"""
    parts = [prefix]
    for key, value in sorted(kwargs.items()):
        parts.append(f"{key}:{value}")
    return ":".join(parts)


# Cache resource definitions for UI
CACHE_RESOURCES = {
    "books": {
        "name": "Books",
        "description": "Book details, search results, and metadata",
        "patterns": ["book_details:*", "search:*", "search_grouped:*", "similar_books:*", "book_prompts:*"],
    },
    "series": {
        "name": "Series",
        "description": "Series information and popular series lists",
        "patterns": ["series:*", "popular_series:*"],
    },
    "authors": {
        "name": "Authors",
        "description": "Author information and metadata",
        "patterns": ["author:*"],
    },
    "discovery": {
        "name": "Discovery",
        "description": "Trending, popular, and new release lists",
        "patterns": ["trending:*", "popular:*", "new_releases:*"],
    },
    "requests": {
        "name": "Requests",
        "description": "Request status cache",
        "patterns": ["requests_by_hardcover:*", "requests_by_hardcover_batch:*"],
    },
}


async def clear_cache_by_resource(resource: str) -> dict:
    """
    Clear cache for a specific resource type.

    Args:
        resource: Resource key from CACHE_RESOURCES

    Returns:
        Dict with deleted count and patterns cleared
    """
    if resource not in CACHE_RESOURCES:
        raise ValueError(f"Unknown cache resource: {resource}")

    resource_info = CACHE_RESOURCES[resource]
    total_deleted = 0

    for pattern in resource_info["patterns"]:
        deleted = await clear_cache_pattern(pattern)
        total_deleted += deleted

    logger.info(
        "cache_resource_cleared",
        resource=resource,
        patterns=resource_info["patterns"],
        deleted_count=total_deleted
    )

    return {
        "resource": resource,
        "name": resource_info["name"],
        "deleted_count": total_deleted,
        "patterns": resource_info["patterns"],
    }


async def clear_all_cache() -> dict:
    """
    Clear all cache entries.

    Returns:
        Dict with total deleted count and per-resource counts
    """
    results = {}
    total_deleted = 0

    for resource in CACHE_RESOURCES:
        result = await clear_cache_by_resource(resource)
        results[resource] = result["deleted_count"]
        total_deleted += result["deleted_count"]

    logger.info("cache_all_cleared", total_deleted=total_deleted, by_resource=results)

    return {
        "total_deleted": total_deleted,
        "by_resource": results,
    }
