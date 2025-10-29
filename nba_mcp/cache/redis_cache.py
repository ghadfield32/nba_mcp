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
- In-memory fallback cache (LRU)
- Response compression (gzip)
- Stale-while-revalidate
- Cache statistics
- Automatic key generation
"""

import gzip
import hashlib
import json
import logging
import time
from collections import OrderedDict
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
# IN-MEMORY FALLBACK CACHE (LRU)
# ============================================================================


class LRUCache:
    """
    In-memory LRU cache with TTL support.

    Used as fallback when Redis is unavailable. Provides basic caching
    functionality with automatic eviction of least recently used items.
    """

    def __init__(self, max_size: int = 1000):
        """
        Initialize LRU cache.

        Args:
            max_size: Maximum number of items to store
        """
        self.cache: OrderedDict = OrderedDict()
        self.max_size = max_size
        self.ttls: Dict[str, float] = {}  # key -> expiration timestamp
        logger.info(f"In-memory LRU cache initialized (max_size={max_size})")

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        if key not in self.cache:
            return None

        # Check if expired
        if key in self.ttls and time.time() > self.ttls[key]:
            self.cache.pop(key)
            self.ttls.pop(key, None)
            return None

        # Move to end (mark as recently used)
        self.cache.move_to_end(key)
        return self.cache[key]

    def set(self, key: str, value: Any, ttl: int):
        """
        Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
        """
        # Remove if already exists
        if key in self.cache:
            self.cache.pop(key)

        # Add to cache
        self.cache[key] = value
        self.ttls[key] = time.time() + ttl

        # Evict oldest if over max size
        if len(self.cache) > self.max_size:
            oldest_key = next(iter(self.cache))
            self.cache.pop(oldest_key)
            self.ttls.pop(oldest_key, None)

    def delete(self, key: str):
        """Delete key from cache."""
        self.cache.pop(key, None)
        self.ttls.pop(key, None)

    def clear(self):
        """Clear all cache entries."""
        self.cache.clear()
        self.ttls.clear()

    def size(self) -> int:
        """Get current cache size."""
        return len(self.cache)


# ============================================================================
# COMPRESSION HELPERS
# ============================================================================


def compress_value(value: Any, threshold: int = 1024) -> tuple[bytes, bool]:
    """
    Compress value if larger than threshold.

    Args:
        value: Value to compress (will be JSON serialized)
        threshold: Size threshold in bytes for compression

    Returns:
        Tuple of (compressed_data, was_compressed)
    """
    serialized = json.dumps(value).encode('utf-8')

    if len(serialized) > threshold:
        compressed = gzip.compress(serialized)
        return compressed, True

    return serialized, False


def decompress_value(data: bytes, was_compressed: bool) -> Any:
    """
    Decompress value if needed.

    Args:
        data: Compressed or uncompressed data
        was_compressed: Whether data was compressed

    Returns:
        Decompressed value
    """
    if was_compressed:
        decompressed = gzip.decompress(data)
        return json.loads(decompressed.decode('utf-8'))

    return json.loads(data.decode('utf-8'))


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
    Redis cache client with TTL tiers, fallback cache, and compression.
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        password: Optional[str] = None,
        max_connections: int = 10,
        decode_responses: bool = False,  # Changed to False for compression support
        enable_compression: bool = True,
        compression_threshold: int = 1024,
        fallback_cache_size: int = 1000,
    ):
        """
        Initialize Redis cache client with fallback and compression.

        Args:
            url: Redis connection URL
            password: Redis password (optional)
            max_connections: Max connections in pool
            decode_responses: Auto-decode bytes to strings (must be False for compression)
            enable_compression: Enable gzip compression for large payloads
            compression_threshold: Size threshold for compression (bytes)
            fallback_cache_size: Size of in-memory fallback cache
        """
        self.url = url
        self.password = password
        self.enable_compression = enable_compression
        self.compression_threshold = compression_threshold

        # Create Redis client
        try:
            self.pool = ConnectionPool.from_url(
                url,
                password=password,
                max_connections=max_connections,
                decode_responses=decode_responses,
            )
            self.client = redis.Redis(connection_pool=self.pool)
            self.redis_available = self.client.ping()
            logger.info(f"Redis cache initialized: {url}")
        except Exception as e:
            logger.warning(f"Redis unavailable: {e}. Using fallback cache only.")
            self.client = None
            self.redis_available = False

        # Create fallback cache
        self.fallback = LRUCache(max_size=fallback_cache_size)

        # Statistics
        self.stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0,
            "redis_hits": 0,
            "fallback_hits": 0,
            "compression_saves": 0,
        }

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache (Redis with fallback).

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        # Try Redis first if available
        if self.redis_available and self.client:
            try:
                value = self.client.get(key)

                if value is not None:
                    self.stats["hits"] += 1
                    self.stats["redis_hits"] += 1
                    logger.debug(f"Cache HIT (Redis): {key}")

                    # Decompress if needed
                    if self.enable_compression and value.startswith(b'\x1f\x8b'):  # gzip magic number
                        return decompress_value(value, was_compressed=True)
                    else:
                        return json.loads(value)

            except Exception as e:
                self.stats["errors"] += 1
                logger.error(f"Redis GET error: {e}, falling back to memory cache")
                self.redis_available = False

        # Try fallback cache
        value = self.fallback.get(key)
        if value is not None:
            self.stats["hits"] += 1
            self.stats["fallback_hits"] += 1
            logger.debug(f"Cache HIT (fallback): {key}")
            return value

        # Cache miss
        self.stats["misses"] += 1
        logger.debug(f"Cache MISS: {key}")
        return None

    def set(
        self, key: str, value: Any, ttl: int, tier: Optional[CacheTier] = None
    ) -> bool:
        """
        Set value in cache with TTL (Redis + fallback).

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time to live in seconds
            tier: Optional tier for logging

        Returns:
            True if successful, False otherwise
        """
        # Always set in fallback cache for resilience
        try:
            self.fallback.set(key, value, ttl)
        except Exception as e:
            logger.warning(f"Fallback cache SET error: {e}")

        # Try Redis if available
        if self.redis_available and self.client:
            try:
                # Compress if enabled and value is large
                if self.enable_compression:
                    data, was_compressed = compress_value(value, self.compression_threshold)
                    if was_compressed:
                        self.stats["compression_saves"] += 1
                else:
                    data = json.dumps(value).encode('utf-8')
                    was_compressed = False

                self.client.setex(key, ttl, data)
                self.stats["sets"] += 1

                if tier:
                    comp_str = " [compressed]" if was_compressed else ""
                    logger.debug(f"Cache SET (Redis): {key} (TTL={ttl}s, tier={tier}){comp_str}")
                else:
                    logger.debug(f"Cache SET (Redis): {key} (TTL={ttl}s)")

                return True

            except Exception as e:
                self.stats["errors"] += 1
                logger.error(f"Redis SET error: {e}, using fallback only")
                self.redis_available = False
                return False

        # Redis unavailable, fallback already set
        if tier:
            logger.debug(f"Cache SET (fallback only): {key} (TTL={ttl}s, tier={tier})")
        return True

    def delete(self, key: str) -> bool:
        """Delete key from cache (Redis + fallback)."""
        # Delete from fallback
        self.fallback.delete(key)

        # Delete from Redis if available
        if self.redis_available and self.client:
            try:
                self.client.delete(key)
                self.stats["deletes"] += 1
                logger.debug(f"Cache DELETE: {key}")
                return True
            except Exception as e:
                self.stats["errors"] += 1
                logger.error(f"Redis DELETE error: {e}", exc_info=True)
                self.redis_available = False
                return False
        return True

    def clear(self) -> bool:
        """Clear all cache entries (Redis + fallback)."""
        # Clear fallback
        self.fallback.clear()

        # Clear Redis if available
        if self.redis_available and self.client:
            try:
                self.client.flushdb()
                logger.info("Cache cleared (Redis + fallback)")
                return True
            except Exception as e:
                logger.error(f"Redis CLEAR error: {e}", exc_info=True)
                self.redis_available = False
                return False

        logger.info("Cache cleared (fallback only)")
        return True

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics including fallback and compression metrics.

        Returns:
            Dictionary with hit/miss ratios, fallback usage, compression stats, etc.
        """
        total_requests = self.stats["hits"] + self.stats["misses"]
        hit_ratio = self.stats["hits"] / total_requests if total_requests > 0 else 0.0

        # Calculate fallback usage percentage
        fallback_ratio = (
            self.stats["fallback_hits"] / self.stats["hits"]
            if self.stats["hits"] > 0
            else 0.0
        )

        return {
            **self.stats,
            "total_requests": total_requests,
            "hit_ratio": hit_ratio,
            "miss_ratio": 1.0 - hit_ratio,
            "fallback_ratio": fallback_ratio,
            "fallback_cache_size": self.fallback.size(),
            "redis_available": self.redis_available,
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
# SMART TTL SELECTION
# ============================================================================


def get_smart_tier(season: Optional[str] = None) -> CacheTier:
    """
    Select appropriate cache tier based on season (current vs historical).

    Args:
        season: Season string in 'YYYY-YY' format (e.g., "2023-24")
                If None, assumes current season data

    Returns:
        CacheTier.DAILY for current season, CacheTier.HISTORICAL for past seasons

    Example:
        >>> get_smart_tier("2023-24")  # If current season is 2024-25
        CacheTier.HISTORICAL
        >>> get_smart_tier("2024-25")  # Current season
        CacheTier.DAILY
        >>> get_smart_tier(None)  # Assume current season
        CacheTier.DAILY
    """
    if season is None:
        # No season specified, assume current data (changes frequently)
        return CacheTier.DAILY

    try:
        # Parse season year
        season_year = int(season.split("-")[0])
        current_year = datetime.now().year

        # Determine current NBA season (starts in October)
        current_month = datetime.now().month
        if current_month >= 10:  # October-December
            current_season_year = current_year
        else:  # January-September
            current_season_year = current_year - 1

        # If season is current or future, use DAILY (data changes after games)
        if season_year >= current_season_year:
            return CacheTier.DAILY

        # Historical season, use longer TTL
        return CacheTier.HISTORICAL

    except (ValueError, IndexError):
        # Invalid season format, default to DAILY for safety
        logger.warning(f"Invalid season format: {season}, defaulting to DAILY tier")
        return CacheTier.DAILY


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
