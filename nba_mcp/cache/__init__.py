# nba_mcp/cache/__init__.py
"""
Caching layer for NBA MCP.

Provides Redis-based caching with TTL tiers for different data types.
"""

from .redis_cache import (
    RedisCache,
    CacheTier,
    cached,
    with_cache,
    generate_cache_key,
    initialize_cache,
    get_cache,
    close_cache,
)

__all__ = [
    "RedisCache",
    "CacheTier",
    "cached",
    "with_cache",
    "generate_cache_key",
    "initialize_cache",
    "get_cache",
    "close_cache",
]
