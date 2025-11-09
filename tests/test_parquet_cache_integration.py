"""
Phase 2H-D Integration Tests: Parquet Cache Layer

Tests the 3-tier cache hierarchy with Parquet persistent storage:
- Tier 1: In-Memory LRU
- Tier 2: Redis
- Tier 3: Parquet (persistent)

Validates:
1. Cache tier hierarchy (Tier 1 → Tier 2 → Tier 3 → API)
2. Tier population on cache miss
3. Persistence across "restarts" (clear Tier 1/2)
4. Background writes don't block queries
5. Graceful degradation on Parquet failures
"""
import asyncio
import shutil
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow as pa
import pytest

from nba_mcp.data.cache_integration import CacheManager, get_cache_manager, reset_cache_manager
from nba_mcp.data.parquet_cache import ParquetCacheConfig


@pytest.fixture
def test_cache_dir(tmp_path):
    """Create temporary cache directory for testing."""
    cache_dir = tmp_path / "test_parquet_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    yield cache_dir
    # Cleanup
    if cache_dir.exists():
        shutil.rmtree(cache_dir)


@pytest.fixture
def sample_data():
    """Create sample NBA-like data for testing."""
    df = pd.DataFrame({
        "PLAYER_ID": [2544, 2544, 2544, 2544, 2544],
        "PLAYER_NAME": ["LeBron James"] * 5,
        "GAME_DATE": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
        "PTS": [28, 32, 25, 30, 27],
        "REB": [7, 8, 6, 7, 9],
        "AST": [9, 11, 8, 10, 12]
    })
    return pa.Table.from_pandas(df)


@pytest.fixture
def cache_manager(test_cache_dir):
    """Create CacheManager with Parquet cache enabled."""
    reset_cache_manager()  # Clear any existing singleton

    manager = CacheManager(enable_cache=True)

    # Enable Parquet cache
    manager.enable_parquet_cache(
        cache_dir=test_cache_dir,
        compression="SNAPPY",
        max_size_mb=100,  # Small for testing
        background_writes=True
    )

    yield manager

    # Cleanup
    reset_cache_manager()


@pytest.mark.asyncio
async def test_parquet_cache_basic_read_write(cache_manager, sample_data, test_cache_dir):
    """Test basic Parquet cache read/write operations."""
    endpoint = "player_game_log"
    params = {"player_name": "LeBron James", "season": "2023-24"}

    # Write to Parquet cache
    await cache_manager.parquet_backend.set(endpoint, params, sample_data, metadata={"row_count": len(sample_data)})

    # Wait for background write to complete
    await asyncio.sleep(0.5)

    # Verify file was created
    cache_key = cache_manager.parquet_backend._generate_cache_key(endpoint, params)
    cache_path = cache_manager.parquet_backend._get_cache_path(endpoint, cache_key)
    assert cache_path.exists(), "Parquet file should exist"

    # Read from Parquet cache
    retrieved_data = await cache_manager.parquet_backend.get(endpoint, params)

    assert retrieved_data is not None, "Should retrieve data from Parquet cache"
    assert len(retrieved_data) == len(sample_data), "Row count should match"
    assert retrieved_data.schema == sample_data.schema, "Schema should match"


@pytest.mark.asyncio
async def test_three_tier_hierarchy(cache_manager, sample_data):
    """Test that cache checks Tier 1 → Tier 2 → Tier 3 → API."""
    endpoint = "player_game_log"
    params = {"player_name": "LeBron James", "season": "2023-24"}

    api_call_count = 0

    async def mock_fetch_func():
        """Mock API fetch that tracks calls."""
        nonlocal api_call_count
        api_call_count += 1
        await asyncio.sleep(0.1)  # Simulate API latency
        return sample_data

    # First call: Should miss all tiers and call API
    data1, from_cache1 = await cache_manager.get_or_fetch(endpoint, params, mock_fetch_func)
    assert data1 is not None, "Should fetch data"
    assert from_cache1 is False, "Should not be from cache (first fetch)"
    assert api_call_count == 1, "Should call API once"

    # Wait for background Parquet write
    await asyncio.sleep(0.5)

    # Second call: Should hit Tier 1 (LRU/Redis)
    data2, from_cache2 = await cache_manager.get_or_fetch(endpoint, params, mock_fetch_func)
    assert data2 is not None, "Should retrieve data"
    assert from_cache2 is True, "Should be from cache (Tier 1/2)"
    assert api_call_count == 1, "Should NOT call API again"

    # Simulate "server restart": Clear Tier 1/2 but keep Tier 3
    cache_manager.lru_cache = None
    cache_manager.redis_cache = None
    cache_manager.cache_backend = "memory"

    # Third call: Should hit Tier 3 (Parquet)
    data3, from_cache3 = await cache_manager.get_or_fetch(endpoint, params, mock_fetch_func)
    assert data3 is not None, "Should retrieve data from Parquet"
    assert from_cache3 is True, "Should be from cache (Tier 3 Parquet)"
    assert api_call_count == 1, "Should NOT call API (Parquet cache hit)"


@pytest.mark.asyncio
async def test_parquet_persistence_across_restarts(cache_manager, sample_data, test_cache_dir):
    """Test that Parquet cache survives simulated server restarts."""
    endpoint = "team_game_log"
    params = {"team": "Lakers", "season": "2023-24"}

    # Store data in Parquet
    await cache_manager.parquet_backend.set(endpoint, params, sample_data, metadata={"row_count": len(sample_data)})
    await asyncio.sleep(0.5)  # Wait for background write

    # Simulate server restart: Create NEW cache manager
    reset_cache_manager()
    new_manager = CacheManager(enable_cache=True)
    new_manager.enable_parquet_cache(
        cache_dir=test_cache_dir,
        compression="SNAPPY",
        max_size_mb=100
    )

    # Verify data is still accessible
    retrieved_data = await new_manager.parquet_backend.get(endpoint, params)
    assert retrieved_data is not None, "Data should persist across restarts"
    assert len(retrieved_data) == len(sample_data), "Row count should match after restart"


@pytest.mark.asyncio
async def test_tier_population_on_parquet_hit(cache_manager, sample_data):
    """Test that Tier 3 hit populates Tier 1/2 for faster future access."""
    endpoint = "player_game_log"
    params = {"player_name": "Stephen Curry", "season": "2023-24"}

    # Manually write to Tier 3 (Parquet) only
    await cache_manager.parquet_backend.set(endpoint, params, sample_data, metadata={"row_count": len(sample_data)})
    await asyncio.sleep(0.5)

    # Verify Tier 1/2 is empty
    cache_key = cache_manager.generate_cache_key(endpoint, params)
    tier1_data = await cache_manager._get_from_cache(cache_key)
    assert tier1_data is None, "Tier 1/2 should be empty initially"

    # Fetch data (should hit Tier 3)
    async def mock_fetch():
        raise Exception("Should not call API if Parquet cache hit")

    data, from_cache = await cache_manager.get_or_fetch(endpoint, params, mock_fetch)
    assert data is not None, "Should retrieve from Tier 3"
    assert from_cache is True, "Should be from cache"

    # Verify Tier 1/2 is now populated
    tier1_data_after = await cache_manager._get_from_cache(cache_key)
    assert tier1_data_after is not None, "Tier 1/2 should be populated after Tier 3 hit"


@pytest.mark.asyncio
async def test_background_writes_dont_block(cache_manager, sample_data):
    """Test that Parquet writes happen in background without blocking queries."""
    endpoint = "player_game_log"
    params = {"player_name": "Giannis Antetokounmpo", "season": "2023-24"}

    async def mock_fetch_func():
        return sample_data

    # Measure time for fetch + cache write
    start = time.time()
    data, from_cache = await cache_manager.get_or_fetch(endpoint, params, mock_fetch_func)
    elapsed = time.time() - start

    assert data is not None, "Should fetch data"
    assert from_cache is False, "Should be fresh fetch"

    # Fetch should complete quickly (< 200ms) even with Parquet write
    # Background write doesn't block the response
    assert elapsed < 0.2, f"Fetch should be fast ({elapsed:.3f}s), Parquet write is background"

    # Wait for background write to complete
    await asyncio.sleep(0.5)

    # Verify data was written to Parquet
    retrieved = await cache_manager.parquet_backend.get(endpoint, params)
    assert retrieved is not None, "Background write should have completed"


@pytest.mark.asyncio
async def test_graceful_degradation_on_parquet_failure(cache_manager, sample_data):
    """Test that Parquet failures don't break the cache system."""
    endpoint = "player_game_log"
    params = {"player_name": "Kevin Durant", "season": "2023-24"}

    # Simulate Parquet failure by disabling it
    cache_manager._parquet_enabled = False

    api_call_count = 0

    async def mock_fetch_func():
        nonlocal api_call_count
        api_call_count += 1
        return sample_data

    # Should still work, falling back to Tier 1/2 only
    data, from_cache = await cache_manager.get_or_fetch(endpoint, params, mock_fetch_func)
    assert data is not None, "Should work even without Parquet"
    assert api_call_count == 1, "Should call API"

    # Re-enable Parquet
    cache_manager._parquet_enabled = True


@pytest.mark.asyncio
async def test_cache_statistics_tracking(cache_manager, sample_data):
    """Test that cache statistics correctly track Parquet hits/misses."""
    endpoint = "player_game_log"
    params = {"player_name": "Luka Doncic", "season": "2023-24"}

    # Reset stats
    cache_manager.reset_stats()

    async def mock_fetch_func():
        return sample_data

    # First call: Cache miss, API fetch
    await cache_manager.get_or_fetch(endpoint, params, mock_fetch_func)
    stats1 = cache_manager.get_stats()
    assert stats1["misses"] == 1, "Should record cache miss"
    assert stats1["hits"] == 0, "No cache hits yet"

    # Wait for background write
    await asyncio.sleep(0.5)

    # Second call: Cache hit (Tier 1/2)
    await cache_manager.get_or_fetch(endpoint, params, mock_fetch_func)
    stats2 = cache_manager.get_stats()
    assert stats2["hits"] == 1, "Should record cache hit"
    assert stats2["misses"] == 1, "Miss count unchanged"


if __name__ == "__main__":
    # Run with: pytest tests/test_parquet_cache_integration.py -v
    pytest.main([__file__, "-v", "--tb=short"])
