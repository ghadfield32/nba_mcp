"""
Cache integration for unified dataset fetching.

Integrates 3-tier caching system:
- Tier 1: In-memory LRU (fastest, volatile)
- Tier 2: Redis (fast, volatile)
- Tier 3: Parquet files (persistent, survives restarts) ← Phase 2H-D

Features:
- Intelligent caching based on endpoint type
- Automatic TTL selection
- Cache key generation
- Persistent Parquet cache layer (Phase 2H-D)
- Cache statistics

Integration with unified_fetch:
    from nba_mcp.data.cache_integration import get_cache_manager

    cache_mgr = get_cache_manager()
    cached_data = await cache_mgr.get_or_fetch(endpoint, params, fetch_func)
"""

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from datetime import datetime
import pyarrow as pa

from nba_mcp.cache.redis_cache import RedisCache, CacheTier, LRUCache
from nba_mcp.data.dataset_manager import ProvenanceInfo
from nba_mcp.data.parquet_cache import ParquetCacheBackend, ParquetCacheConfig

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Manages caching for unified dataset fetching.

    Features:
    - Automatic TTL selection based on endpoint
    - Cache key generation from endpoint + params
    - Integration with existing Redis cache
    - In-memory fallback
    - Cache statistics
    """

    def __init__(self, enable_cache: bool = True):
        """
        Initialize cache manager.

        Args:
            enable_cache: Whether to enable caching (default: True)
        """
        self.enable_cache = enable_cache

        # Try to initialize Redis cache
        try:
            self.redis_cache = RedisCache()
            self.cache_backend = "redis"
            logger.info("Cache manager initialized with Redis backend")
        except Exception as e:
            logger.warning(f"Redis unavailable, using in-memory cache: {e}")
            self.lru_cache = LRUCache(max_size=1000)
            self.cache_backend = "memory"

        # Tier 3: Parquet cache backend (Phase 2H-D)
        self.parquet_backend: Optional[ParquetCacheBackend] = None
        self._parquet_enabled = False

        # Cache statistics
        self.stats = {
            "hits": 0,
            "misses": 0,
            "errors": 0,
            "bypassed": 0
        }

        # Endpoint → TTL tier mapping
        self.endpoint_ttl_map = {
            # Live data (30s) - frequently changing
            "live_scores": CacheTier.LIVE,
            "play_by_play": CacheTier.LIVE,

            # Daily data (1h) - changes daily
            "team_standings": CacheTier.DAILY,
            "league_leaders": CacheTier.DAILY,

            # Historical data (24h) - rarely changes
            "player_career_stats": CacheTier.HISTORICAL,
            "player_advanced_stats": CacheTier.HISTORICAL,
            "team_advanced_stats": CacheTier.HISTORICAL,
            "team_game_log": CacheTier.HISTORICAL,
            "shot_chart": CacheTier.HISTORICAL,

            # Static data (7d) - almost never changes
            # (we can add entity lookups here later)
        }

    def generate_cache_key(self, endpoint: str, params: Dict[str, Any]) -> str:
        """
        Generate a deterministic cache key from endpoint and params.

        Args:
            endpoint: Endpoint name
            params: Parameter dictionary

        Returns:
            Cache key string

        Example:
            >>> manager.generate_cache_key("player_career_stats", {"player_name": "LeBron James"})
            "nba_mcp:player_career_stats:e3b0c44298..."
        """
        # Sort params for deterministic key generation
        sorted_params = json.dumps(params, sort_keys=True)

        # Hash params for compact key
        param_hash = hashlib.md5(sorted_params.encode()).hexdigest()[:12]

        # Format: nba_mcp:endpoint:param_hash
        return f"nba_mcp:{endpoint}:{param_hash}"

    def get_ttl_for_endpoint(self, endpoint: str, params: Dict[str, Any]) -> int:
        """
        Get appropriate TTL for an endpoint.

        Args:
            endpoint: Endpoint name
            params: Parameters (can affect TTL)

        Returns:
            TTL in seconds
        """
        # Check if endpoint has specific TTL mapping
        tier = self.endpoint_ttl_map.get(endpoint)

        if tier:
            return tier.value

        # Smart defaults based on parameters
        if "season" in params:
            # Historical seasons get longer cache
            season = params.get("season", "")
            current_season = self._get_current_season()

            if season and season != current_season:
                return CacheTier.HISTORICAL.value  # 24 hours for past seasons
            else:
                return CacheTier.DAILY.value  # 1 hour for current season

        # Default to daily cache
        return CacheTier.DAILY.value

    def _get_current_season(self) -> str:
        """Get current NBA season string (e.g., '2024-25')."""
        now = datetime.now()
        year = now.year
        month = now.month

        # Season starts in October
        if month >= 10:
            return f"{year}-{str(year + 1)[-2:]}"
        else:
            return f"{year - 1}-{str(year)[-2:]}"

    def enable_parquet_cache(
        self,
        cache_dir: Path = Path("mcp_data/parquet_cache"),
        compression: str = "SNAPPY",
        max_size_mb: int = 5000,
        background_writes: bool = True
    ) -> None:
        """
        Enable Tier 3 Parquet cache for persistent storage.

        Args:
            cache_dir: Directory for Parquet cache files
            compression: Compression algorithm (SNAPPY, GZIP, etc.)
            max_size_mb: Maximum cache size in MB (default: 5GB)
            background_writes: Enable background writes (default: True)

        Example:
            >>> cache_mgr = get_cache_manager()
            >>> cache_mgr.enable_parquet_cache(
            ...     cache_dir=Path("mcp_data/parquet_cache"),
            ...     compression="SNAPPY",
            ...     max_size_mb=5000
            ... )
        """
        config = ParquetCacheConfig(
            enabled=True,
            cache_dir=cache_dir,
            compression=compression,
            max_size_mb=max_size_mb,
            background_writes=background_writes
        )
        self.parquet_backend = ParquetCacheBackend(config)
        self._parquet_enabled = True
        logger.info(f"✅ Parquet cache enabled at {cache_dir} (max: {max_size_mb}MB, compression: {compression})")

    async def get_or_fetch(
        self,
        endpoint: str,
        params: Dict[str, Any],
        fetch_func: Callable,
        force_refresh: bool = False
    ) -> Tuple[Optional[pa.Table], bool]:
        """
        Get data from cache or fetch if not cached.

        Args:
            endpoint: Endpoint name
            params: Parameters
            fetch_func: Async function to call if cache miss (should return pa.Table)
            force_refresh: Force cache refresh (default: False)

        Returns:
            Tuple of (data, from_cache)
            - data: PyArrow Table or None if error
            - from_cache: True if from cache, False if freshly fetched

        Example:
            data, from_cache = await cache_mgr.get_or_fetch(
                "player_career_stats",
                {"player_name": "LeBron James"},
                lambda: fetch_endpoint("player_career_stats", {...})
            )
        """
        # If caching disabled, always fetch
        if not self.enable_cache or force_refresh:
            self.stats["bypassed"] += 1
            try:
                data = await fetch_func()
                return data, False
            except Exception as e:
                logger.error(f"Fetch failed: {e}")
                return None, False

        # Generate cache key
        cache_key = self.generate_cache_key(endpoint, params)

        # Tier 1/2: Check LRU and Redis
        try:
            cached_data = await self._get_from_cache(cache_key)

            if cached_data is not None:
                self.stats["hits"] += 1
                logger.debug(f"Cache HIT (Tier 1/2) for {endpoint} (key: {cache_key[:20]}...)")
                return cached_data, True
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            self.stats["errors"] += 1

        # Tier 3: Check Parquet cache (persistent layer)
        if self._parquet_enabled and self.parquet_backend:
            try:
                parquet_data = await self.parquet_backend.get(endpoint, params)
                if parquet_data is not None:
                    self.stats["hits"] += 1
                    logger.info(f"✅ Cache HIT (Tier 3 Parquet) for {endpoint} - loaded {len(parquet_data)} rows from persistent cache")

                    # Populate higher tiers (Tier 1/2) for faster future access
                    ttl = self.get_ttl_for_endpoint(endpoint, params)
                    await self._set_in_cache(cache_key, parquet_data, ttl)

                    return parquet_data, True
            except Exception as e:
                logger.warning(f"Parquet cache read failed: {e}, falling back to API")
                self.stats["errors"] += 1

        # Cache miss (all tiers) - fetch data
        self.stats["misses"] += 1
        logger.debug(f"Cache MISS (all tiers) for {endpoint} (key: {cache_key[:20]}...)")

        try:
            data = await fetch_func()

            if data is not None:
                # Store in Tier 1/2 cache
                ttl = self.get_ttl_for_endpoint(endpoint, params)
                await self._set_in_cache(cache_key, data, ttl)

                # Store in Tier 3 Parquet cache (background, non-blocking)
                if self._parquet_enabled and self.parquet_backend:
                    asyncio.create_task(
                        self.parquet_backend.set(
                            endpoint=endpoint,
                            params=params,
                            data=data,
                            metadata={
                                "row_count": len(data),
                                "timestamp": datetime.now().isoformat(),
                                "ttl": ttl
                            }
                        )
                    )

            return data, False
        except Exception as e:
            logger.error(f"Fetch failed: {e}")
            self.stats["errors"] += 1
            return None, False

    async def _get_from_cache(self, key: str) -> Optional[pa.Table]:
        """Get data from cache backend."""
        if self.cache_backend == "redis":
            # Redis stores serialized Arrow tables
            cached_bytes = self.redis_cache.get(key)
            if cached_bytes:
                # Deserialize Arrow table
                import pyarrow as pa
                return pa.ipc.open_stream(cached_bytes).read_all()
            return None
        else:
            # In-memory LRU cache
            return self.lru_cache.get(key)

    async def _set_in_cache(self, key: str, data: pa.Table, ttl: int):
        """Set data in cache backend."""
        try:
            if self.cache_backend == "redis":
                # Serialize Arrow table to bytes
                import pyarrow as pa
                import io

                sink = io.BytesIO()
                writer = pa.ipc.RecordBatchStreamWriter(sink, data.schema)
                writer.write_table(data)
                writer.close()

                self.redis_cache.set(key, sink.getvalue(), ttl)
            else:
                # In-memory LRU cache
                self.lru_cache.set(key, data, ttl)
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

    async def invalidate(self, endpoint: str, params: Optional[Dict[str, Any]] = None):
        """
        Invalidate cache for an endpoint.

        Args:
            endpoint: Endpoint name
            params: Specific params to invalidate (if None, invalidates all)
        """
        if params:
            # Invalidate specific key
            cache_key = self.generate_cache_key(endpoint, params)
            try:
                if self.cache_backend == "redis":
                    self.redis_cache.delete(cache_key)
                else:
                    self.lru_cache.cache.pop(cache_key, None)
                    self.lru_cache.ttls.pop(cache_key, None)
                logger.info(f"Invalidated cache for {endpoint}")
            except Exception as e:
                logger.warning(f"Cache invalidation error: {e}")
        else:
            # Invalidate all keys for endpoint (requires pattern matching)
            logger.warning("Bulk invalidation not yet implemented")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        total_requests = self.stats["hits"] + self.stats["misses"]
        hit_rate = (self.stats["hits"] / total_requests * 100) if total_requests > 0 else 0

        return {
            "backend": self.cache_backend,
            "enabled": self.enable_cache,
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "errors": self.stats["errors"],
            "bypassed": self.stats["bypassed"],
            "total_requests": total_requests,
            "hit_rate_percent": round(hit_rate, 2)
        }

    def reset_stats(self):
        """Reset cache statistics."""
        self.stats = {
            "hits": 0,
            "misses": 0,
            "errors": 0,
            "bypassed": 0
        }


# Global cache manager instance (singleton)
_cache_manager = None


def get_cache_manager(enable_cache: bool = True) -> CacheManager:
    """
    Get the global cache manager instance.

    Args:
        enable_cache: Whether to enable caching

    Returns:
        CacheManager singleton
    """
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager(enable_cache=enable_cache)
    return _cache_manager


def reset_cache_manager():
    """Reset the global cache manager (useful for testing)."""
    global _cache_manager
    _cache_manager = None
