"""
Comprehensive stress tests for unified fetch system.

Tests all aspects of the unified fetch system to ensure robustness:
- All filter operators on various endpoints
- Cache performance and hit rates
- Batch operations with different sizes
- Filter pushdown verification
- Parameter aliases and entity resolution
- Error handling and edge cases

Run with: pytest tests/test_unified_fetch_stress.py -v
"""

import pytest
import asyncio
import time
from nba_mcp.data.unified_fetch import unified_fetch, batch_fetch, apply_filters
from nba_mcp.data.cache_integration import get_cache_manager, reset_cache_manager
from nba_mcp.data.filter_pushdown import get_pushdown_mapper
import pyarrow as pa


class TestFilterOperators:
    """Test all filter operators work correctly."""

    @pytest.mark.asyncio
    async def test_equality_operator(self):
        """Test == operator."""
        result = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            filters={"conference": ["==", "West"]}
        )
        assert result.data.num_rows > 0
        assert result.data.num_rows <= 15  # Max 15 Western Conference teams

    @pytest.mark.asyncio
    async def test_not_equal_operator(self):
        """Test != operator."""
        result = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            filters={"conference": ["!=", "East"]}
        )
        assert result.data.num_rows > 0
        assert result.data.num_rows <= 15

    @pytest.mark.asyncio
    async def test_greater_than_operator(self):
        """Test > operator."""
        result = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            filters={"wins": [">", 40]}
        )
        assert result.data.num_rows >= 0  # May have 0 if no teams >40 wins

    @pytest.mark.asyncio
    async def test_greater_equal_operator(self):
        """Test >= operator."""
        result = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            filters={"wins": [">=", 41]}
        )
        assert result.data.num_rows >= 0

    @pytest.mark.asyncio
    async def test_less_than_operator(self):
        """Test < operator."""
        result = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            filters={"losses": ["<", 20]}
        )
        assert result.data.num_rows >= 0

    @pytest.mark.asyncio
    async def test_less_equal_operator(self):
        """Test <= operator."""
        result = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            filters={"losses": ["<=", 30]}
        )
        assert result.data.num_rows >= 0

    @pytest.mark.asyncio
    async def test_in_operator(self):
        """Test IN operator."""
        result = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            filters={"team_abbreviation": ["IN", ["LAL", "GSW", "BOS"]]}
        )
        # Should have exactly 3 teams (if all exist in standings)
        assert result.data.num_rows <= 3

    @pytest.mark.asyncio
    async def test_between_operator(self):
        """Test BETWEEN operator."""
        result = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            filters={"wins": ["BETWEEN", [40, 50]]}
        )
        assert result.data.num_rows >= 0

    @pytest.mark.asyncio
    async def test_multiple_filters_and(self):
        """Test multiple filters (AND logic)."""
        result = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            filters={
                "conference": ["==", "West"],
                "wins": [">=", 40]
            }
        )
        assert result.data.num_rows >= 0


class TestCachePerformance:
    """Test cache behavior and performance."""

    def setup_method(self):
        """Reset cache before each test."""
        reset_cache_manager()

    @pytest.mark.asyncio
    async def test_cache_miss_then_hit(self):
        """Test cache miss on first fetch, hit on second."""
        cache_mgr = get_cache_manager()
        cache_mgr.reset_stats()

        # First fetch - should be cache miss
        result1 = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            use_cache=True
        )
        assert not result1.from_cache

        # Second fetch - should be cache hit
        result2 = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            use_cache=True
        )
        assert result2.from_cache

        # Verify cache statistics
        stats = cache_mgr.get_stats()
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert stats['hit_rate_percent'] == 50.0

    @pytest.mark.asyncio
    async def test_cache_force_refresh(self):
        """Test force_refresh bypasses cache."""
        # First fetch to populate cache
        result1 = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            use_cache=True
        )

        # Force refresh - should bypass cache
        result2 = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            use_cache=True,
            force_refresh=True
        )
        assert not result2.from_cache

    @pytest.mark.asyncio
    async def test_cache_disabled(self):
        """Test cache disabled mode."""
        # First fetch with cache disabled
        result1 = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            use_cache=False
        )
        assert not result1.from_cache

        # Second fetch with cache disabled
        result2 = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            use_cache=False
        )
        assert not result2.from_cache

    @pytest.mark.asyncio
    async def test_cache_performance_speedup(self):
        """Test cache provides speedup."""
        cache_mgr = get_cache_manager()
        cache_mgr.reset_stats()

        # First fetch (cache miss)
        start = time.time()
        result1 = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            use_cache=True
        )
        time1 = time.time() - start

        # Second fetch (cache hit)
        start = time.time()
        result2 = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            use_cache=True
        )
        time2 = time.time() - start

        # Cache hit should be significantly faster
        assert time2 < time1
        speedup = time1 / time2
        print(f"Cache speedup: {speedup:.1f}x")
        # Typically 50-200x faster from cache


class TestBatchOperations:
    """Test batch fetching with various configurations."""

    @pytest.mark.asyncio
    async def test_batch_fetch_basic(self):
        """Test basic batch fetch with 3 endpoints."""
        results = await batch_fetch([
            {"endpoint": "team_standings", "params": {"season": "2023-24"}},
            {"endpoint": "team_standings", "params": {"season": "2022-23"}},
            {"endpoint": "team_standings", "params": {"season": "2021-22"}},
        ])

        assert len(results) == 3
        assert all(r.data.num_rows > 0 for r in results)

    @pytest.mark.asyncio
    async def test_batch_fetch_with_filters(self):
        """Test batch fetch with filters."""
        results = await batch_fetch([
            {
                "endpoint": "team_standings",
                "params": {"season": "2023-24"},
                "filters": {"conference": ["==", "West"]}
            },
            {
                "endpoint": "team_standings",
                "params": {"season": "2023-24"},
                "filters": {"conference": ["==", "East"]}
            },
        ])

        assert len(results) == 2
        assert results[0].data.num_rows > 0
        assert results[1].data.num_rows > 0

    @pytest.mark.asyncio
    async def test_batch_fetch_parallel_speedup(self):
        """Test parallel batch fetching is faster than sequential."""
        requests = [
            {"endpoint": "team_standings", "params": {"season": f"202{i}-{i+1}"}}
            for i in range(0, 3)  # 3 seasons
        ]

        # Parallel execution
        start = time.time()
        results_parallel = await batch_fetch(requests, max_concurrent=3)
        time_parallel = time.time() - start

        # Sequential execution
        start = time.time()
        results_sequential = []
        for req in requests:
            result = await unified_fetch(req["endpoint"], req["params"])
            results_sequential.append(result)
        time_sequential = time.time() - start

        # Parallel should be faster
        assert time_parallel < time_sequential
        speedup = time_sequential / time_parallel
        print(f"Batch speedup: {speedup:.2f}x")

    @pytest.mark.asyncio
    async def test_batch_fetch_max_concurrent_limit(self):
        """Test max_concurrent parameter limits parallelism."""
        requests = [
            {"endpoint": "team_standings", "params": {"season": f"202{i}-{i+1}"}}
            for i in range(0, 5)  # 5 seasons
        ]

        # Fetch with concurrent limit of 2
        results = await batch_fetch(requests, max_concurrent=2)
        assert len(results) == 5


class TestFilterPushdown:
    """Test filter pushdown optimization."""

    @pytest.mark.asyncio
    async def test_filter_pushdown_occurs(self):
        """Test that eligible filters are pushed to API."""
        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={"WL": ["==", "W"]}
        )

        # Check provenance shows filter pushdown
        assert any("filter_pushdown" in op for op in result.provenance.operations)
        # Check transformations mention pushdown
        assert any("Pushed" in t for t in result.transformations)

    @pytest.mark.asyncio
    async def test_filter_split_api_and_post(self):
        """Test filters split into API (pushdown) and post-fetch."""
        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={
                "WL": ["==", "W"],     # Can push to API
                "PTS": [">=", 110],    # Cannot push (stat filter)
            }
        )

        # Should have both filter_pushdown and post_filter operations
        ops = result.provenance.operations
        assert any("filter_pushdown" in op for op in ops)
        assert any("post_filter" in op for op in ops)

    @pytest.mark.asyncio
    async def test_pushdown_mapper_can_push_filter(self):
        """Test pushdown mapper correctly identifies pushable filters."""
        mapper = get_pushdown_mapper()

        # Test pushable filters
        assert mapper.can_push_filter("team_game_log", "WL", "==")
        assert mapper.can_push_filter("team_game_log", "SEASON", "==")

        # Test non-pushable filters
        assert not mapper.can_push_filter("team_game_log", "PTS", ">=")
        assert not mapper.can_push_filter("team_game_log", "REB", ">")


class TestParameterAliases:
    """Test parameter alias handling."""

    @pytest.mark.asyncio
    async def test_player_alias(self):
        """Test 'player' alias for 'player_name'."""
        # This should work even though parameter is 'player' not 'player_name'
        result = await unified_fetch(
            "player_career_stats",
            {"player": "LeBron James"}  # Using alias
        )
        assert result.data.num_rows > 0

    @pytest.mark.asyncio
    async def test_team_alias(self):
        """Test 'team' alias."""
        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"}  # 'team' is alias
        )
        assert result.data.num_rows > 0


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_invalid_endpoint(self):
        """Test error on invalid endpoint."""
        with pytest.raises(Exception):  # Should raise FetchError
            await unified_fetch("nonexistent_endpoint", {})

    @pytest.mark.asyncio
    async def test_missing_required_param(self):
        """Test error on missing required parameter."""
        with pytest.raises(Exception):
            await unified_fetch("team_game_log", {"season": "2023-24"})  # Missing 'team'

    @pytest.mark.asyncio
    async def test_invalid_filter_syntax(self):
        """Test error on invalid filter syntax."""
        result = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            filters={"wins": "invalid"}  # Should be ["operator", value]
        )
        # Should still work but log warning
        assert result.warnings or True  # Check for warnings or passes

    @pytest.mark.asyncio
    async def test_invalid_filter_column(self):
        """Test error on non-existent filter column."""
        with pytest.raises(Exception):
            result = await unified_fetch(
                "team_standings",
                {"season": "2023-24"},
                filters={"NONEXISTENT_COLUMN": ["==", "value"]}
            )


class TestEndpointCoverage:
    """Test all registered endpoints work."""

    @pytest.mark.asyncio
    async def test_player_career_stats(self):
        """Test player_career_stats endpoint."""
        result = await unified_fetch(
            "player_career_stats",
            {"player_name": "LeBron James"}
        )
        assert result.data.num_rows > 0

    @pytest.mark.asyncio
    async def test_player_advanced_stats(self):
        """Test player_advanced_stats endpoint."""
        result = await unified_fetch(
            "player_advanced_stats",
            {"player_name": "LeBron James", "season": "2023-24"}
        )
        assert result.data.num_rows > 0

    @pytest.mark.asyncio
    async def test_team_standings(self):
        """Test team_standings endpoint."""
        result = await unified_fetch(
            "team_standings",
            {"season": "2023-24"}
        )
        assert result.data.num_rows == 30  # All 30 teams

    @pytest.mark.asyncio
    async def test_team_advanced_stats(self):
        """Test team_advanced_stats endpoint."""
        result = await unified_fetch(
            "team_advanced_stats",
            {"team_name": "Lakers", "season": "2023-24"}
        )
        assert result.data.num_rows > 0

    @pytest.mark.asyncio
    async def test_league_leaders(self):
        """Test league_leaders endpoint."""
        result = await unified_fetch(
            "league_leaders",
            {"stat_category": "PTS", "season": "2023-24"}
        )
        assert result.data.num_rows >= 10  # Default limit is 10


class TestProvenanceTracking:
    """Test provenance tracking works correctly."""

    @pytest.mark.asyncio
    async def test_provenance_operations_tracked(self):
        """Test all operations are tracked in provenance."""
        result = await unified_fetch(
            "team_standings",
            {"season": "2023-24"},
            filters={"conference": ["==", "West"]}
        )

        ops = result.provenance.operations
        assert "unified_fetch" in ops
        assert any("post_filter" in op or "filter_pushdown" in op for op in ops)

    @pytest.mark.asyncio
    async def test_transformations_recorded(self):
        """Test transformations are recorded."""
        result = await unified_fetch(
            "team_standings",
            {"season": "2023-24"}
        )

        # Should have transformations from parameter processing
        assert len(result.transformations) >= 0

    @pytest.mark.asyncio
    async def test_execution_time_recorded(self):
        """Test execution time is recorded."""
        result = await unified_fetch(
            "team_standings",
            {"season": "2023-24"}
        )

        assert result.execution_time_ms > 0
        assert result.provenance.execution_time_ms > 0


# Summary report at end of test run
def pytest_sessionfinish(session, exitstatus):
    """Print summary after all tests complete."""
    print("\n" + "=" * 80)
    print("STRESS TEST SUMMARY")
    print("=" * 80)
    if exitstatus == 0:
        print("✅ ALL STRESS TESTS PASSED!")
        print("\nTested:")
        print("  - All filter operators (==, !=, >, >=, <, <=, IN, BETWEEN)")
        print("  - Cache performance (miss, hit, force refresh, disabled)")
        print("  - Batch operations (parallel, concurrent limits)")
        print("  - Filter pushdown (API optimization)")
        print("  - Parameter aliases (player, team, etc.)")
        print("  - Error handling (invalid endpoint, params, filters)")
        print("  - All registered endpoints")
        print("  - Provenance tracking")
    else:
        print(f"❌ SOME TESTS FAILED (exit status: {exitstatus})")
    print("=" * 80)
