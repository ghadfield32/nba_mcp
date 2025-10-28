"""
Tests for Week 4 infrastructure: Cache and Rate Limiting.
"""

import pytest
import asyncio
import time
import sys
sys.path.insert(0, '/home/user/nba_mcp')

from nba_mcp.cache.redis_cache import (
    RedisCache, CacheTier, cached, get_cache_key, initialize_cache, get_cache
)
from nba_mcp.rate_limit.token_bucket import (
    TokenBucket, RateLimiter, QuotaTracker, rate_limited,
    initialize_rate_limiter, get_rate_limiter, RateLimitError
)


# ============================================================================
# CACHE TESTS
# ============================================================================

@pytest.fixture(scope="module")
def redis_cache():
    """Initialize Redis cache for testing."""
    try:
        initialize_cache(redis_url="redis://localhost:6379", db=15)  # Use test DB
        cache = get_cache()
        cache.client.flushdb()  # Clear test DB
        yield cache
        cache.client.flushdb()  # Cleanup
    except Exception as e:
        pytest.skip(f"Redis not available: {e}")


def test_cache_basic_operations(redis_cache):
    """Test basic cache set/get operations."""
    # Set value
    redis_cache.set("test_key", {"data": "test_value"}, ttl=60)

    # Get value
    result = redis_cache.get("test_key")
    assert result == {"data": "test_value"}

    # Get non-existent key
    result = redis_cache.get("non_existent")
    assert result is None


def test_cache_ttl_expiration(redis_cache):
    """Test cache TTL expiration."""
    # Set value with 1 second TTL
    redis_cache.set("expire_key", {"data": "temp"}, ttl=1)

    # Should exist immediately
    result = redis_cache.get("expire_key")
    assert result == {"data": "temp"}

    # Wait for expiration
    time.sleep(1.1)

    # Should be gone
    result = redis_cache.get("expire_key")
    assert result is None


def test_cache_statistics(redis_cache):
    """Test cache statistics tracking."""
    redis_cache.client.flushdb()  # Reset stats

    # Generate hits and misses
    redis_cache.set("stats_key", {"data": "value"}, ttl=60)

    redis_cache.get("stats_key")  # Hit
    redis_cache.get("stats_key")  # Hit
    redis_cache.get("missing1")   # Miss
    redis_cache.get("missing2")   # Miss

    stats = redis_cache.get_stats()
    assert stats["hits"] == 2
    assert stats["misses"] == 2
    assert stats["hit_rate"] == 0.5


def test_cache_key_generation():
    """Test cache key generation."""
    # Same inputs should generate same key
    key1 = get_cache_key("test_func", {"param": "value", "num": 42})
    key2 = get_cache_key("test_func", {"param": "value", "num": 42})
    assert key1 == key2

    # Different inputs should generate different keys
    key3 = get_cache_key("test_func", {"param": "different", "num": 42})
    assert key1 != key3

    # Different function names should generate different keys
    key4 = get_cache_key("other_func", {"param": "value", "num": 42})
    assert key1 != key4


@pytest.mark.asyncio
async def test_cached_decorator(redis_cache):
    """Test @cached decorator."""
    call_count = 0

    @cached(tier=CacheTier.DAILY)
    async def expensive_function(param: str) -> dict:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.1)  # Simulate work
        return {"result": param, "call": call_count}

    # First call - should execute function
    result1 = await expensive_function("test")
    assert result1["call"] == 1
    assert call_count == 1

    # Second call - should use cache
    result2 = await expensive_function("test")
    assert result2["call"] == 1  # Same result as before
    assert call_count == 1  # Function not called again

    # Different parameter - should execute function
    result3 = await expensive_function("other")
    assert result3["call"] == 2
    assert call_count == 2


def test_cache_tier_ttls():
    """Test cache tier TTL values."""
    assert CacheTier.LIVE.value == 30
    assert CacheTier.DAILY.value == 3600
    assert CacheTier.HISTORICAL.value == 86400
    assert CacheTier.STATIC.value == 604800


# ============================================================================
# RATE LIMITING TESTS
# ============================================================================

def test_token_bucket_basic():
    """Test basic token bucket operations."""
    bucket = TokenBucket(capacity=10.0, refill_rate=1.0)

    # Should allow consuming available tokens
    assert bucket.consume(5) is True
    assert bucket.tokens == 5.0

    # Should reject consuming more than available
    assert bucket.consume(10) is False
    assert bucket.tokens == 5.0  # Tokens unchanged

    # Should allow consuming remaining tokens
    assert bucket.consume(5) is True
    assert bucket.tokens == 0.0


def test_token_bucket_refill():
    """Test token bucket refill over time."""
    bucket = TokenBucket(capacity=10.0, refill_rate=5.0)  # 5 tokens/sec

    # Consume all tokens
    bucket.consume(10)
    assert bucket.tokens == 0.0

    # Wait 1 second - should refill 5 tokens
    time.sleep(1.1)
    assert bucket.consume(5) is True

    # Should not have more than refilled amount
    assert bucket.consume(1) is False


def test_token_bucket_max_capacity():
    """Test token bucket doesn't exceed capacity."""
    bucket = TokenBucket(capacity=10.0, refill_rate=1.0)

    # Wait to ensure full refill
    time.sleep(2)

    # Try to consume - should only have capacity amount
    assert bucket.consume(10) is True
    assert bucket.consume(1) is False  # Can't exceed capacity


def test_rate_limiter_multiple_buckets():
    """Test rate limiter with multiple buckets."""
    limiter = RateLimiter()

    limiter.add_limit("api1", capacity=10.0, refill_rate=1.0)
    limiter.add_limit("api2", capacity=5.0, refill_rate=0.5)

    # Each limit should be independent
    assert limiter.check_limit("api1", tokens=5) is True
    assert limiter.check_limit("api2", tokens=3) is True

    # Should track separately
    assert limiter.check_limit("api1", tokens=6) is False  # Only 5 left
    assert limiter.check_limit("api2", tokens=3) is False  # Only 2 left


def test_rate_limiter_status():
    """Test rate limiter status reporting."""
    limiter = RateLimiter()
    limiter.add_limit("test_api", capacity=10.0, refill_rate=1.0)

    # Get status
    status = limiter.get_status("test_api")
    assert status["capacity"] == 10.0
    assert status["refill_rate"] == 1.0
    assert status["tokens_available"] == 10.0

    # Consume some tokens
    limiter.check_limit("test_api", tokens=5)
    status = limiter.get_status("test_api")
    assert status["tokens_available"] == 5.0


def test_quota_tracker():
    """Test daily quota tracking."""
    tracker = QuotaTracker(daily_limit=100)

    # Should allow consumption under limit
    assert tracker.consume(50) is True
    assert tracker.used == 50

    # Should allow up to limit
    assert tracker.consume(50) is True
    assert tracker.used == 100

    # Should reject over limit
    with pytest.raises(RateLimitError):
        tracker.consume(1)


def test_quota_tracker_status():
    """Test quota tracker status."""
    tracker = QuotaTracker(daily_limit=100)
    tracker.consume(75)

    status = tracker.get_status()
    assert status["used"] == 75
    assert status["limit"] == 100
    assert status["remaining"] == 25
    assert status["usage_percent"] == 75.0


def test_rate_limiter_global_quota():
    """Test rate limiter with global quota."""
    limiter = RateLimiter()
    limiter.set_global_quota(daily_limit=100)

    # Consume quota
    for i in range(50):
        limiter.consume_quota(1)

    status = limiter.get_quota_status()
    assert status["used"] == 50
    assert status["remaining"] == 50


@pytest.mark.asyncio
async def test_rate_limited_decorator():
    """Test @rate_limited decorator."""
    limiter = get_rate_limiter()
    limiter.add_limit("test_func", capacity=3.0, refill_rate=1.0)

    @rate_limited("test_func")
    async def limited_function(value: int) -> int:
        return value * 2

    # Should allow first 3 calls
    assert await limited_function(1) == 2
    assert await limited_function(2) == 4
    assert await limited_function(3) == 6

    # Should reject 4th call
    with pytest.raises(RateLimitError):
        await limited_function(4)


@pytest.mark.asyncio
async def test_rate_limited_decorator_refill():
    """Test @rate_limited decorator with refill."""
    limiter = get_rate_limiter()
    limiter.add_limit("refill_func", capacity=2.0, refill_rate=2.0)  # 2 tokens/sec

    @rate_limited("refill_func")
    async def limited_function() -> str:
        return "success"

    # Consume all tokens
    await limited_function()
    await limited_function()

    # Should reject
    with pytest.raises(RateLimitError):
        await limited_function()

    # Wait for refill
    await asyncio.sleep(1.1)

    # Should allow again
    result = await limited_function()
    assert result == "success"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_cache_and_rate_limit_together(redis_cache):
    """Test cache and rate limiting working together."""
    limiter = get_rate_limiter()
    limiter.add_limit("integrated_func", capacity=2.0, refill_rate=0.5)

    call_count = 0

    @cached(tier=CacheTier.DAILY)
    @rate_limited("integrated_func")
    async def integrated_function(param: str) -> dict:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.1)
        return {"param": param, "call": call_count}

    # First call - rate limited + cache miss
    result1 = await integrated_function("test")
    assert result1["call"] == 1
    assert call_count == 1

    # Second call - cache hit (no rate limit)
    result2 = await integrated_function("test")
    assert result2["call"] == 1  # Same cached result
    assert call_count == 1  # Function not called

    # Third call with different param - rate limited + cache miss
    result3 = await integrated_function("other")
    assert result3["call"] == 2
    assert call_count == 2

    # Fourth call - should be rate limited
    with pytest.raises(RateLimitError):
        await integrated_function("third")


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_cache_performance_improvement(redis_cache):
    """Test cache provides significant performance improvement."""

    @cached(tier=CacheTier.DAILY)
    async def slow_function(param: str) -> str:
        await asyncio.sleep(0.5)  # Simulate slow operation
        return f"result_{param}"

    # First call - should be slow
    start = time.time()
    result1 = await slow_function("test")
    uncached_time = time.time() - start
    assert uncached_time > 0.5

    # Second call - should be fast
    start = time.time()
    result2 = await slow_function("test")
    cached_time = time.time() - start
    assert cached_time < 0.1  # Should be much faster

    # Verify speedup
    speedup = uncached_time / cached_time
    assert speedup > 10  # At least 10x faster


def test_rate_limiter_performance():
    """Test rate limiter has minimal overhead."""
    limiter = RateLimiter()
    limiter.add_limit("perf_test", capacity=10000.0, refill_rate=1000.0)

    # Measure 1000 checks
    start = time.time()
    for i in range(1000):
        limiter.check_limit("perf_test", tokens=1)
    elapsed = time.time() - start

    # Should be very fast (< 100ms for 1000 checks)
    assert elapsed < 0.1
    print(f"Rate limiter overhead: {elapsed*1000/1000:.3f}ms per check")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
