# nba_mcp/cache/__init__.py
"""
Caching layer for NBA MCP.

Provides Redis-based caching with TTL tiers, fallback cache, and compression.

Features:
- Redis cache with connection pooling
- In-memory LRU fallback cache
- Automatic compression for large payloads
- Smart TTL selection based on season
- Cache statistics and monitoring
"""

from .redis_cache import (
    CacheTier,
    LRUCache,
    RedisCache,
    cached,
    close_cache,
    compress_value,
    decompress_value,
    generate_cache_key,
    get_cache,
    get_smart_tier,
    initialize_cache,
    with_cache,
)

__all__ = [
    "RedisCache",
    "LRUCache",
    "CacheTier",
    "cached",
    "with_cache",
    "generate_cache_key",
    "get_smart_tier",
    "compress_value",
    "decompress_value",
    "initialize_cache",
    "get_cache",
    "close_cache",
]
