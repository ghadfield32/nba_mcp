"""
Test improved caching layer with fallback and compression
"""
import time

from nba_mcp.cache import (
    CacheTier,
    LRUCache,
    RedisCache,
    compress_value,
    decompress_value,
    get_smart_tier,
)


def test_lru_cache():
    """Test in-memory LRU cache"""
    print("\n=== Testing LRU Cache ===")

    cache = LRUCache(max_size=3)

    # Test set and get
    cache.set("key1", {"data": "value1"}, ttl=60)
    cache.set("key2", {"data": "value2"}, ttl=60)
    cache.set("key3", {"data": "value3"}, ttl=60)

    assert cache.get("key1") == {"data": "value1"}
    assert cache.size() == 3
    print("[PASS] LRU cache set/get works")

    # Test eviction (key1 was just accessed, so it's most recent)
    cache.set("key4", {"data": "value4"}, ttl=60)
    assert cache.size() == 3
    assert cache.get("key2") is None  # Evicted (oldest since key1 was accessed)
    assert cache.get("key1") is not None  # Still in cache
    assert cache.get("key4") == {"data": "value4"}
    print("[PASS] LRU eviction works")

    # Test TTL expiration
    cache.set("short_ttl", {"data": "expires"}, ttl=1)
    time.sleep(1.1)
    assert cache.get("short_ttl") is None
    print("[PASS] TTL expiration works")

    print("[SUCCESS] LRU cache: ALL TESTS PASSED\n")


def test_compression():
    """Test compression helpers"""
    print("=== Testing Compression ===")

    # Small value (should not compress)
    small_data = {"key": "value"}
    compressed, was_compressed = compress_value(small_data, threshold=1024)
    assert not was_compressed
    print("[PASS] Small values not compressed")

    # Large value (should compress)
    large_data = {"key": "x" * 10000}
    compressed, was_compressed = compress_value(large_data, threshold=1024)
    assert was_compressed
    assert len(compressed) < len(str(large_data))
    print(f"[PASS] Large values compressed (saved {len(str(large_data)) - len(compressed)} bytes)")

    # Test decompression
    decompressed = decompress_value(compressed, was_compressed=True)
    assert decompressed == large_data
    print("[PASS] Decompression works correctly")

    print("[SUCCESS] Compression: ALL TESTS PASSED\n")


def test_smart_tier():
    """Test smart TTL tier selection"""
    print("=== Testing Smart Tier Selection ===")

    # Current season should be DAILY (2025-26 since we're in October 2025)
    tier_current = get_smart_tier("2025-26")
    assert tier_current == CacheTier.DAILY
    print(f"[PASS] Current season (2025-26): {tier_current}")

    # Historical season should be HISTORICAL
    tier_historical = get_smart_tier("2020-21")
    assert tier_historical == CacheTier.HISTORICAL
    print(f"[PASS] Historical season (2020-21): {tier_historical}")

    # None should default to DAILY
    tier_none = get_smart_tier(None)
    assert tier_none == CacheTier.DAILY
    print(f"[PASS] No season (None): {tier_none}")

    print("[SUCCESS] Smart tier selection: ALL TESTS PASSED\n")


def test_redis_fallback():
    """Test Redis cache with fallback"""
    print("=== Testing Redis Cache with Fallback ===")

    # Initialize with invalid Redis URL (will use fallback)
    cache = RedisCache(
        url="redis://invalid-host:6379/0",
        enable_compression=True,
        fallback_cache_size=100
    )

    assert not cache.redis_available
    print("[PASS] Fallback activated when Redis unavailable")

    # Test set/get with fallback
    cache.set("test_key", {"data": "test_value"}, ttl=60, tier=CacheTier.DAILY)
    result = cache.get("test_key")
    assert result == {"data": "test_value"}
    print("[PASS] Fallback cache works for set/get")

    # Check stats
    stats = cache.get_stats()
    assert stats["fallback_hits"] > 0
    assert stats["fallback_cache_size"] > 0
    print(f"[PASS] Stats: {stats['fallback_hits']} fallback hits, {stats['fallback_cache_size']} items cached")

    print("[SUCCESS] Redis fallback: ALL TESTS PASSED\n")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("IMPROVED CACHE TESTS")
    print("="*60)

    test_lru_cache()
    test_compression()
    test_smart_tier()
    test_redis_fallback()

    print("="*60)
    print("[SUCCESS] ALL IMPROVED CACHE TESTS PASSED!")
    print("="*60)
