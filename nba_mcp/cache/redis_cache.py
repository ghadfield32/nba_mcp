# nba_mcp/cache/redis_cache.py
"""
Redis cache implementation with TTL tiers for NBA MCP.

Provides intelligent caching based on data freshness requirements:
- Live data (30s): In-progress games, live stats
- Daily data (1h): Today's stats, current standings
- Historical data (24h): Past seasons, game logs
- Static data (7d): Player names, team info

Features:
- Connection pooling
- Stale-while-revalidate
- Cache statistics
- Automatic key generation
"""

import hashlib
import json
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, Optional

import redis
from redis.connection import ConnectionPool

logger = logging.getLogger(__name__)


# ============================================================================
# TTL TIERS
# ============================================================================


class CacheTier(Enum):
    """Cache TTL tiers based on data freshness requirements."""

    LIVE = 30  # 30 seconds - live scores, in-progress games
    DAILY = 3600  # 1 hour - today's stats, current standings
    HISTORICAL = 86400  # 24 hours - past seasons, completed games
    STATIC = 604800  # 7 days - player names, team info, entities

    def __str__(self):
        return self.name.lower()


# ============================================================================
# CACHE KEY GENERATION
# ============================================================================


def generate_cache_key(
    tool_name: str, params: Dict[str, Any], version: str = "v1"
) -> str:
    """
    Generate deterministic cache key from tool name and parameters.

    Args:
        tool_name: Name of the tool (e.g., "get_player_stats")
        params: Tool parameters as dict
        version: API version for cache invalidation

    Returns:
        Cache key string

    Example:
        >>> generate_cache_key("get_player_stats", {"player": "LeBron James", "season": "2023-24"})
        "nba_mcp:v1:get_player_stats:a3f2b8c9d1e4f5a6"
    """
    # Sort params for deterministic hashing
    param_str = json.dumps(params, sort_keys=True)
    param_hash = hashlib.md5(param_str.encode()).hexdigest()[:16]

    return f"nba_mcp:{version}:{tool_name}:{param_hash}"


# ============================================================================
# REDIS CACHE CLIENT
# ============================================================================


class RedisCache:
    """
    Redis cache client with TTL tiers and connection pooling.
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        password: Optional[str] = None,
        max_connections: int = 10,
        decode_responses: bool = True,
    ):
        """
        Initialize Redis cache client.

        Args:
            url: Redis connection URL
            password: Redis password (optional)
            max_connections: Max connections in pool
            decode_responses: Auto-decode bytes to strings
        """
        self.url = url
        self.password = password

        # Create connection pool
        self.pool = ConnectionPool.from_url(
            url,
            password=password,
            max_connections=max_connections,
            decode_responses=decode_responses,
        )

        # Create Redis client
        self.client = redis.Redis(connection_pool=self.pool)

        # Statistics
        self.stats = {"hits": 0, "misses": 0, "sets": 0, "deletes": 0, "errors": 0}

        logger.info(f"Redis cache initialized: {url}")

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        try:
            value = self.client.get(key)

            if value is not None:
                self.stats["hits"] += 1
                logger.debug(f"Cache HIT: {key}")
                return json.loads(value)
            else:
                self.stats["misses"] += 1
                logger.debug(f"Cache MISS: {key}")
                return None

        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Cache GET error: {e}", exc_info=True)
            return None

    def set(
        self, key: str, value: Any, ttl: int, tier: Optional[CacheTier] = None
    ) -> bool:
        """
        Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time to live in seconds
            tier: Optional tier for logging

        Returns:
            True if successful, False otherwise
        """
        try:
            serialized = json.dumps(value)
            self.client.setex(key, ttl, serialized)
            self.stats["sets"] += 1

            if tier:
                logger.debug(f"Cache SET: {key} (TTL={ttl}s, tier={tier})")
            else:
                logger.debug(f"Cache SET: {key} (TTL={ttl}s)")

            return True

        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Cache SET error: {e}", exc_info=True)
            return False

    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        try:
            self.client.delete(key)
            self.stats["deletes"] += 1
            logger.debug(f"Cache DELETE: {key}")
            return True
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Cache DELETE error: {e}", exc_info=True)
            return False

    def clear(self) -> bool:
        """Clear all cache entries."""
        try:
            self.client.flushdb()
            logger.info("Cache cleared")
            return True
        except Exception as e:
            logger.error(f"Cache CLEAR error: {e}", exc_info=True)
            return False

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with hit/miss ratios, counts, etc.
        """
        total_requests = self.stats["hits"] + self.stats["misses"]
        hit_ratio = self.stats["hits"] / total_requests if total_requests > 0 else 0.0

        return {
            **self.stats,
            "total_requests": total_requests,
            "hit_ratio": hit_ratio,
            "miss_ratio": 1.0 - hit_ratio,
        }

    def ping(self) -> bool:
        """Check if Redis is accessible."""
        try:
            self.client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False

    def close(self):
        """Close Redis connection pool."""
        try:
            self.pool.disconnect()
            logger.info("Redis connection pool closed")
        except Exception as e:
            logger.error(f"Error closing Redis pool: {e}")


# ============================================================================
# CACHE DECORATOR
# ============================================================================


def cached(tier: CacheTier, key_fn: Optional[Callable] = None, version: str = "v1"):
    """
    Decorator to cache function results with specified TTL tier.

    Args:
        tier: Cache tier (determines TTL)
        key_fn: Optional custom key generation function
        version: API version for cache invalidation

    Example:
        @cached(tier=CacheTier.DAILY)
        async def get_player_stats(player_name: str, season: str):
            # ... expensive NBA API call
            return stats
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get cache instance (assumes global cache)
            cache = get_cache()

            if cache is None or not cache.ping():
                # Cache unavailable - call function directly
                logger.warning("Cache unavailable, calling function directly")
                return await func(*args, **kwargs)

            # Generate cache key
            if key_fn:
                key = key_fn(*args, **kwargs)
            else:
                # Default: use function name and kwargs
                params = kwargs.copy()
                key = generate_cache_key(func.__name__, params, version)

            # Try to get from cache
            cached_value = cache.get(key)
            if cached_value is not None:
                logger.info(f"Cache hit for {func.__name__}")
                return cached_value

            # Cache miss - call function
            logger.info(f"Cache miss for {func.__name__}, calling function")
            result = await func(*args, **kwargs)

            # Store in cache
            if result is not None:
                cache.set(key, result, tier.value, tier)

            return result

        return wrapper

    return decorator


# ============================================================================
# GLOBAL CACHE INSTANCE
# ============================================================================

_cache_instance: Optional[RedisCache] = None


def initialize_cache(
    url: str = "redis://localhost:6379/0", password: Optional[str] = None, **kwargs
) -> RedisCache:
    """
    Initialize global cache instance.

    Args:
        url: Redis connection URL
        password: Redis password
        **kwargs: Additional Redis client options

    Returns:
        RedisCache instance
    """
    global _cache_instance
    _cache_instance = RedisCache(url, password, **kwargs)
    return _cache_instance


def get_cache() -> Optional[RedisCache]:
    """Get global cache instance."""
    return _cache_instance


def close_cache():
    """Close global cache instance."""
    global _cache_instance
    if _cache_instance:
        _cache_instance.close()
        _cache_instance = None


# ============================================================================
# CACHE MIDDLEWARE
# ============================================================================


async def with_cache(
    tool_name: str,
    params: Dict[str, Any],
    tier: CacheTier,
    func: Callable,
    version: str = "v1",
) -> Any:
    """
    Execute function with caching.

    This is a programmatic alternative to the @cached decorator.

    Args:
        tool_name: Tool name for cache key
        params: Tool parameters
        tier: Cache tier
        func: Async function to execute
        version: API version

    Returns:
        Function result (from cache or fresh)
    """
    cache = get_cache()

    if cache is None or not cache.ping():
        return await func()

    # Generate key
    key = generate_cache_key(tool_name, params, version)

    # Try cache
    cached_value = cache.get(key)
    if cached_value is not None:
        return cached_value

    # Execute function
    result = await func()

    # Store in cache
    if result is not None:
        cache.set(key, result, tier.value, tier)

    return result
