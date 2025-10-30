# FIXED TEST FUNCTIONS FOR test_cache_and_rate_limit.py
# These are the corrected versions that match the actual API implementation

import pytest
import time
import asyncio
from nba_mcp.rate_limit.token_bucket import (
    TokenBucket, RateLimiter, QuotaTracker, rate_limited,
    initialize_rate_limiter, get_rate_limiter
)
from nba_mcp.api.errors import RateLimitError


# ==============================================================================
# FIX 1: test_token_bucket_basic - Use pytest.approx() for float comparisons
# ==============================================================================
def test_token_bucket_basic():
    """Test basic token bucket operations."""
    bucket = TokenBucket(capacity=10.0, refill_rate=1.0)

    # Should allow consuming available tokens
    assert bucket.consume(5) is True
    assert bucket.tokens == pytest.approx(5.0, abs=0.01)  # FIX: Use approx for float comparison

    # Should reject consuming more than available
    assert bucket.consume(10) is False
    # FIX: Tokens may have refilled slightly due to time passing
    assert bucket.tokens == pytest.approx(5.0, abs=0.01)

    # Should allow consuming remaining tokens (approximately 5)
    remaining = bucket.get_remaining()
    assert bucket.consume(int(remaining)) is True
    assert bucket.tokens == pytest.approx(0.0, abs=0.01)


# ==============================================================================
# FIX 2: test_rate_limiter_multiple_buckets - Unpack tuples from check_limit()
# ==============================================================================
def test_rate_limiter_multiple_buckets():
    """Test rate limiter with multiple buckets."""
    limiter = RateLimiter()

    limiter.add_limit("api1", capacity=10.0, refill_rate=1.0)
    limiter.add_limit("api2", capacity=5.0, refill_rate=0.5)

    # FIX: check_limit returns (allowed, retry_after) tuple
    allowed1, retry1 = limiter.check_limit("api1", tokens=5)
    assert allowed1 is True
    assert retry1 is None

    allowed2, retry2 = limiter.check_limit("api2", tokens=3)
    assert allowed2 is True
    assert retry2 is None

    # Should track separately
    allowed3, retry3 = limiter.check_limit("api1", tokens=6)  # Only 5 left
    assert allowed3 is False
    assert retry3 > 0

    allowed4, retry4 = limiter.check_limit("api2", tokens=3)  # Only 2 left
    assert allowed4 is False
    assert retry4 > 0


# ==============================================================================
# FIX 3: test_rate_limiter_status - Use get_stats() instead of get_status()
# ==============================================================================
def test_rate_limiter_status():
    """Test rate limiter status reporting."""
    limiter = RateLimiter()
    limiter.add_limit("test_api", capacity=10.0, refill_rate=1.0)

    # FIX: Method is get_stats(), not get_status()
    # FIX: Stats are organized by tool name
    # FIX: Key is "remaining", not "tokens_available"
    all_stats = limiter.get_stats()
    status = all_stats["test_api"]
    assert status["capacity"] == 10.0
    assert status["refill_rate"] == 1.0
    assert status["remaining"] == pytest.approx(10.0, abs=0.01)

    # Consume some tokens
    limiter.check_limit("test_api", tokens=5)
    all_stats = limiter.get_stats()
    status = all_stats["test_api"]
    assert status["remaining"] == pytest.approx(5.0, abs=0.01)


# ==============================================================================
# FIX 4: test_quota_tracker - Use check() and increment() instead of consume()
# ==============================================================================
def test_quota_tracker():
    """Test daily quota tracking."""
    tracker = QuotaTracker(daily_limit=100)

    # FIX: QuotaTracker doesn't have consume(), use check() + increment()
    # Should allow increments under limit
    for i in range(50):
        assert tracker.check() is True
        tracker.increment()

    # FIX: Check count instead of .used attribute
    assert tracker.count == 50

    # Should allow up to limit
    for i in range(50):
        assert tracker.check() is True
        tracker.increment()

    assert tracker.count == 100

    # Should reject over limit
    assert tracker.check() is False


# ==============================================================================
# FIX 5: test_quota_tracker_status - Use correct API and keys
# ==============================================================================
def test_quota_tracker_status():
    """Test quota tracker status."""
    tracker = QuotaTracker(daily_limit=100)

    # FIX: Use check() + increment() instead of consume()
    for i in range(75):
        tracker.increment()

    # FIX: Method is get_stats(), and keys match implementation
    status = tracker.get_stats()
    assert status["count"] == 75  # Key is "count", not "used"
    assert status["daily_limit"] == 100  # Key is "daily_limit", not "limit"
    assert status["remaining"] == 25
    assert status["usage_pct"] == pytest.approx(75.0, abs=0.1)  # Key is "usage_pct", not "usage_percent"


# ==============================================================================
# FIX 6: test_rate_limiter_global_quota - Use check_limit() with tool name
# ==============================================================================
def test_rate_limiter_global_quota():
    """Test rate limiter with global quota."""
    limiter = RateLimiter()
    limiter.set_global_quota(daily_limit=100)
    limiter.add_limit("test_tool", capacity=1000.0, refill_rate=1000.0)  # High limit so quota is the constraint

    # FIX: Use check_limit() instead of consume_quota()
    # Global quota is tracked automatically by check_limit()
    for i in range(50):
        allowed, retry_after = limiter.check_limit("test_tool", tokens=1)
        assert allowed is True

    # FIX: Use get_stats() to access global_quota
    all_stats = limiter.get_stats()
    quota_stats = all_stats.get("global_quota", {})
    assert quota_stats["count"] == 50  # Key is "count", not "used"
    assert quota_stats["remaining"] == 50


# ==============================================================================
# FIX 7: test_rate_limited_decorator - Initialize rate limiter first
# ==============================================================================
@pytest.mark.asyncio
async def test_rate_limited_decorator():
    """Test @rate_limited decorator."""
    # FIX: Must initialize rate limiter before use
    limiter = initialize_rate_limiter()
    limiter.reset_all()  # Reset any existing state
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


# ==============================================================================
# FIX 8: test_rate_limited_decorator_refill - Initialize rate limiter first
# ==============================================================================
@pytest.mark.asyncio
async def test_rate_limited_decorator_refill():
    """Test @rate_limited decorator with refill."""
    # FIX: Must initialize rate limiter before use
    limiter = initialize_rate_limiter()
    limiter.reset_all()  # Reset any existing state
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


# ==============================================================================
# SUMMARY OF FIXES
# ==============================================================================
"""
Fix 1: test_token_bucket_basic
    - Use pytest.approx() for float comparisons
    - Account for time passing between operations
    - Use get_remaining() to handle slight refills

Fix 2: test_rate_limiter_multiple_buckets
    - Unpack (allowed, retry_after) tuple from check_limit()
    - Assert on tuple elements instead of whole tuple

Fix 3: test_rate_limiter_status
    - Change get_status() → get_stats()
    - Access stats by tool name: stats["test_api"]
    - Key is "remaining", not "tokens_available"

Fix 4: test_quota_tracker
    - Replace consume() with check() + increment()
    - Check tracker.count instead of tracker.used
    - QuotaTracker.check() returns bool, doesn't raise

Fix 5: test_quota_tracker_status
    - Use check() + increment() instead of consume()
    - Keys: "count" (not "used"), "daily_limit" (not "limit"), "usage_pct" (not "usage_percent")

Fix 6: test_rate_limiter_global_quota
    - Use check_limit() instead of consume_quota()
    - Access quota via get_stats()["global_quota"]
    - Keys: "count" (not "used")

Fix 7: test_rate_limited_decorator
    - Call initialize_rate_limiter() before using decorator
    - Reset state before test

Fix 8: test_rate_limited_decorator_refill
    - Same as Fix 7 - initialize before use
    - Reset state before test
"""
