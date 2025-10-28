#!/usr/bin/env python3
"""
Week 4 Integration Example: Cache + Rate Limiting

This example demonstrates how to use Redis caching and token bucket rate limiting
together to build high-performance, sustainable NBA API tools.

Run this example:
    python examples/week4_integration_example.py
"""

import asyncio
import time
from typing import Dict, Any, Optional
import sys
sys.path.insert(0, '/home/user/nba_mcp')

from nba_mcp.cache.redis_cache import (
    RedisCache,
    CacheTier,
    cached,
    get_cache_key,
    initialize_cache,
    get_cache
)
from nba_mcp.rate_limit.token_bucket import (
    RateLimiter,
    rate_limited,
    initialize_rate_limiter,
    get_rate_limiter
)


# ============================================================================
# EXAMPLE 1: BASIC CACHE USAGE
# ============================================================================

async def example_basic_cache():
    """Example: Basic cache operations."""
    print("\n" + "="*70)
    print("EXAMPLE 1: Basic Cache Usage")
    print("="*70)

    cache = get_cache()

    # Set a value with 60 second TTL
    cache.set("player:lebron:stats", {"ppg": 25.7, "rpg": 7.3}, ttl=60)
    print("✓ Set player stats in cache (60s TTL)")

    # Get the value
    stats = cache.get("player:lebron:stats")
    print(f"✓ Retrieved from cache: {stats}")

    # Check non-existent key
    missing = cache.get("player:notfound")
    print(f"✓ Non-existent key returns: {missing}")

    # View cache statistics
    print(f"\n📊 Cache Stats: {cache.get_stats()}")


# ============================================================================
# EXAMPLE 2: CACHE DECORATOR WITH TTL TIERS
# ============================================================================

@cached(tier=CacheTier.LIVE)
async def get_live_score(game_id: str) -> Dict[str, Any]:
    """Simulated live score fetch (cached 30s)."""
    await asyncio.sleep(0.5)  # Simulate API call
    return {
        "game_id": game_id,
        "home_score": 105,
        "away_score": 98,
        "quarter": 4,
        "time_remaining": "2:45"
    }


@cached(tier=CacheTier.DAILY)
async def get_player_stats(player_name: str, season: str) -> Dict[str, Any]:
    """Simulated player stats fetch (cached 1 hour)."""
    await asyncio.sleep(0.8)  # Simulate API call
    return {
        "player": player_name,
        "season": season,
        "ppg": 27.5,
        "rpg": 8.2,
        "apg": 6.1
    }


@cached(tier=CacheTier.HISTORICAL)
async def get_historical_game(game_id: str) -> Dict[str, Any]:
    """Simulated historical game fetch (cached 24 hours)."""
    await asyncio.sleep(0.6)  # Simulate API call
    return {
        "game_id": game_id,
        "date": "2023-06-12",
        "final_score": {"home": 95, "away": 88}
    }


async def example_cache_decorator():
    """Example: Using @cached decorator with TTL tiers."""
    print("\n" + "="*70)
    print("EXAMPLE 2: Cache Decorator with TTL Tiers")
    print("="*70)

    # First call - cache miss
    print("\n1️⃣ First call (cache miss):")
    start = time.time()
    score = await get_live_score("game123")
    elapsed = (time.time() - start) * 1000
    print(f"   Live score: {score['home_score']}-{score['away_score']}")
    print(f"   Time: {elapsed:.0f}ms")

    # Second call - cache hit
    print("\n2️⃣ Second call (cache hit):")
    start = time.time()
    score = await get_live_score("game123")
    elapsed = (time.time() - start) * 1000
    print(f"   Live score: {score['home_score']}-{score['away_score']}")
    print(f"   Time: {elapsed:.0f}ms (should be ~1-2ms)")

    # Different tiers
    print("\n3️⃣ Testing different cache tiers:")

    start = time.time()
    stats = await get_player_stats("LeBron James", "2023-24")
    elapsed = (time.time() - start) * 1000
    print(f"   Player stats (DAILY tier): {elapsed:.0f}ms")

    start = time.time()
    stats = await get_player_stats("LeBron James", "2023-24")
    elapsed = (time.time() - start) * 1000
    print(f"   Player stats (cached): {elapsed:.0f}ms")

    start = time.time()
    game = await get_historical_game("game456")
    elapsed = (time.time() - start) * 1000
    print(f"   Historical game (HISTORICAL tier): {elapsed:.0f}ms")

    start = time.time()
    game = await get_historical_game("game456")
    elapsed = (time.time() - start) * 1000
    print(f"   Historical game (cached): {elapsed:.0f}ms")

    # Show cache stats
    cache = get_cache()
    stats = cache.get_stats()
    print(f"\n📊 Cache Stats:")
    print(f"   Hits: {stats['hits']}, Misses: {stats['misses']}")
    print(f"   Hit Rate: {stats['hit_rate']:.1%}")
    print(f"   Stored Items: {stats['stored_items']}")


# ============================================================================
# EXAMPLE 3: RATE LIMITING
# ============================================================================

@rate_limited("example_api")
async def call_rate_limited_api(endpoint: str) -> str:
    """Simulated API call with rate limiting."""
    await asyncio.sleep(0.1)
    return f"Response from {endpoint}"


async def example_rate_limiting():
    """Example: Rate limiting with token bucket."""
    print("\n" + "="*70)
    print("EXAMPLE 3: Rate Limiting")
    print("="*70)

    limiter = get_rate_limiter()

    # Configure rate limit: 5 requests per 10 seconds (0.5/sec refill)
    limiter.add_limit("example_api", capacity=5.0, refill_rate=0.5)
    print("✓ Configured rate limit: 5 requests burst, 0.5/sec refill")

    # Make rapid requests
    print("\n1️⃣ Making 7 rapid requests:")
    for i in range(7):
        try:
            result = await call_rate_limited_api(f"/endpoint/{i+1}")
            print(f"   Request {i+1}: ✓ {result}")
        except Exception as e:
            print(f"   Request {i+1}: ✗ Rate limited ({e})")

    # Check available tokens
    stats = limiter.get_status("example_api")
    print(f"\n📊 Rate Limit Status:")
    print(f"   Available tokens: {stats['tokens_available']:.2f}")
    print(f"   Capacity: {stats['capacity']}")
    print(f"   Refill rate: {stats['refill_rate']}/sec")

    # Wait for refill
    print("\n⏳ Waiting 3 seconds for token refill...")
    await asyncio.sleep(3)

    stats = limiter.get_status("example_api")
    print(f"   Available tokens after 3s: {stats['tokens_available']:.2f}")

    # Try again
    print("\n2️⃣ Making 2 more requests after refill:")
    for i in range(2):
        try:
            result = await call_rate_limited_api(f"/endpoint/{i+8}")
            print(f"   Request {i+8}: ✓ {result}")
        except Exception as e:
            print(f"   Request {i+8}: ✗ Rate limited ({e})")


# ============================================================================
# EXAMPLE 4: COMBINED CACHE + RATE LIMITING
# ============================================================================

@cached(tier=CacheTier.DAILY)
@rate_limited("combined_api")
async def fetch_player_data(player_name: str) -> Dict[str, Any]:
    """
    Combined example: Cache + Rate Limiting.

    - First call: Rate limited + API call (slow)
    - Subsequent calls within 1 hour: Cached (fast, no rate limit hit)
    - After cache expires: Rate limited + API call again
    """
    print(f"      🌐 Making real API call for {player_name}")
    await asyncio.sleep(0.8)  # Simulate API latency
    return {
        "name": player_name,
        "ppg": 28.5,
        "rpg": 9.1,
        "apg": 7.8
    }


async def example_combined():
    """Example: Combined cache + rate limiting."""
    print("\n" + "="*70)
    print("EXAMPLE 4: Combined Cache + Rate Limiting")
    print("="*70)

    limiter = get_rate_limiter()
    limiter.add_limit("combined_api", capacity=3.0, refill_rate=0.3)
    print("✓ Configured: 3 request burst, 0.3/sec refill, 1 hour cache")

    # First call: Rate limited + cache miss
    print("\n1️⃣ First call (rate limited + cache miss):")
    start = time.time()
    data = await fetch_player_data("Giannis")
    elapsed = (time.time() - start) * 1000
    print(f"   Result: {data['ppg']} PPG")
    print(f"   Time: {elapsed:.0f}ms")
    print(f"   Rate limit tokens used: 1")

    # Second call: Cached (no rate limit hit)
    print("\n2️⃣ Second call (cached, no rate limit):")
    start = time.time()
    data = await fetch_player_data("Giannis")
    elapsed = (time.time() - start) * 1000
    print(f"   Result: {data['ppg']} PPG")
    print(f"   Time: {elapsed:.0f}ms (cached!)")
    print(f"   Rate limit tokens used: 0 (cache hit)")

    # Multiple players
    print("\n3️⃣ Fetching 4 different players:")
    players = ["LeBron", "Durant", "Curry", "Jokic"]

    for i, player in enumerate(players):
        try:
            start = time.time()
            data = await fetch_player_data(player)
            elapsed = (time.time() - start) * 1000
            print(f"   {player}: ✓ {elapsed:.0f}ms")
        except Exception as e:
            print(f"   {player}: ✗ Rate limited")

    # Show final stats
    limiter_stats = limiter.get_status("combined_api")
    cache_stats = get_cache().get_stats()

    print(f"\n📊 Final Statistics:")
    print(f"   Rate Limiter:")
    print(f"     - Tokens remaining: {limiter_stats['tokens_available']:.2f}/{limiter_stats['capacity']}")
    print(f"   Cache:")
    print(f"     - Hit rate: {cache_stats['hit_rate']:.1%}")
    print(f"     - Total hits: {cache_stats['hits']}")
    print(f"     - Total misses: {cache_stats['misses']}")


# ============================================================================
# EXAMPLE 5: QUOTA TRACKING
# ============================================================================

async def example_quota_tracking():
    """Example: Daily quota tracking."""
    print("\n" + "="*70)
    print("EXAMPLE 5: Daily Quota Tracking")
    print("="*70)

    limiter = get_rate_limiter()

    # Set daily quota: 100 requests per day
    limiter.set_global_quota(daily_limit=100)
    print("✓ Configured daily quota: 100 requests/day")

    # Simulate some usage
    print("\n1️⃣ Simulating 45 requests:")
    for i in range(45):
        limiter.consume_quota(1)

    quota_info = limiter.get_quota_status()
    print(f"   Used: {quota_info['used']}/{quota_info['limit']}")
    print(f"   Remaining: {quota_info['remaining']}")
    print(f"   Usage: {quota_info['usage_percent']:.1f}%")

    # Simulate more usage
    print("\n2️⃣ Simulating 40 more requests:")
    for i in range(40):
        limiter.consume_quota(1)

    quota_info = limiter.get_quota_status()
    print(f"   Used: {quota_info['used']}/{quota_info['limit']}")
    print(f"   Remaining: {quota_info['remaining']}")
    print(f"   Usage: {quota_info['usage_percent']:.1f}%")

    if quota_info['usage_percent'] > 80:
        print(f"   ⚠️  WARNING: Over 80% quota used!")

    # Try to exceed quota
    print("\n3️⃣ Attempting to exceed quota:")
    try:
        for i in range(20):
            limiter.consume_quota(1)
        quota_info = limiter.get_quota_status()
        print(f"   Used: {quota_info['used']}/{quota_info['limit']}")
    except Exception as e:
        print(f"   ✗ Quota exceeded: {e}")


# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Run all examples."""
    print("\n" + "="*70)
    print("Week 4 Integration Examples: Cache + Rate Limiting")
    print("="*70)
    print("\nThese examples demonstrate:")
    print("  • Redis caching with TTL tiers")
    print("  • Token bucket rate limiting")
    print("  • Combined cache + rate limiting")
    print("  • Daily quota tracking")
    print("="*70)

    # Initialize infrastructure
    print("\n🔧 Initializing infrastructure...")
    initialize_cache(redis_url="redis://localhost:6379", db=0)
    initialize_rate_limiter()
    print("✓ Cache and rate limiter initialized")

    try:
        # Run examples
        await example_basic_cache()
        await example_cache_decorator()
        await example_rate_limiting()
        await example_combined()
        await example_quota_tracking()

        print("\n" + "="*70)
        print("✅ All examples completed successfully!")
        print("="*70)

    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run examples
    asyncio.run(main())
