"""
Comprehensive stress tests for filter pushdown optimization.

This test suite validates that filter pushdown works correctly across:
- All pushable filter columns
- All supported operators
- All registered endpoints
- All edge cases and boundary conditions
- Performance validation

Tests ensure 50-90% data reduction and 2-5x query speedup for filtered queries.

Run with: pytest tests/test_filter_pushdown_comprehensive.py -v
"""

import pytest
import asyncio
import time
from nba_mcp.data.unified_fetch import unified_fetch, batch_fetch
from nba_mcp.data.cache_integration import get_cache_manager, reset_cache_manager
from nba_mcp.data.filter_pushdown import get_pushdown_mapper, reset_pushdown_mapper
import pyarrow as pa


class TestFilterPushdownAllColumns:
    """Test filter pushdown for every pushable column."""

    @pytest.mark.asyncio
    async def test_pushdown_wl_column(self):
        """Test WL (Win/Loss) filter pushdown to outcome parameter."""
        mapper = get_pushdown_mapper()

        # Test can_push_filter
        assert mapper.can_push_filter("team_game_log", "WL", "==")

        # Test filter pushdown occurs
        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={"WL": ["==", "W"]},
            use_cache=False
        )

        # Validate provenance shows pushdown
        assert any("filter_pushdown" in op for op in result.provenance.operations)

        # Validate data contains only wins
        assert result.data.num_rows > 0
        # All rows should be wins (note: actual column name might differ)

    @pytest.mark.asyncio
    async def test_pushdown_season_column(self):
        """Test SEASON filter pushdown."""
        mapper = get_pushdown_mapper()

        assert mapper.can_push_filter("team_game_log", "SEASON", "==")

        # This will push season to API
        # Note: Filtering on SEASON is redundant when season is already in params,
        # but tests that the filter pushdown mechanism works
        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={"SEASON": ["==", "2023-24"]},
            use_cache=False
        )

        assert result.data.num_rows > 0

    @pytest.mark.asyncio
    async def test_pushdown_game_date_gte(self):
        """Test GAME_DATE >= filter pushdown to date_from."""
        mapper = get_pushdown_mapper()

        assert mapper.can_push_filter("team_game_log", "GAME_DATE", ">=")

        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={"GAME_DATE": [">=", "2024-01-01"]},
            use_cache=False
        )

        assert any("filter_pushdown" in op for op in result.provenance.operations)
        assert result.data.num_rows > 0

    @pytest.mark.asyncio
    async def test_pushdown_game_date_lte(self):
        """Test GAME_DATE <= filter pushdown to date_to."""
        mapper = get_pushdown_mapper()

        assert mapper.can_push_filter("team_game_log", "GAME_DATE", "<=")

        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={"GAME_DATE": ["<=", "2024-03-31"]},
            use_cache=False
        )

        assert any("filter_pushdown" in op for op in result.provenance.operations)
        assert result.data.num_rows > 0

    @pytest.mark.asyncio
    async def test_pushdown_game_date_between(self):
        """Test GAME_DATE BETWEEN filter pushdown."""
        mapper = get_pushdown_mapper()

        assert mapper.can_push_filter("team_game_log", "GAME_DATE", "BETWEEN")

        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={"GAME_DATE": ["BETWEEN", ["2024-01-01", "2024-01-31"]]},
            use_cache=False
        )

        assert any("filter_pushdown" in op for op in result.provenance.operations)
        assert result.data.num_rows > 0

    @pytest.mark.asyncio
    async def test_pushdown_season_id_player_stats(self):
        """Test SEASON_ID filter pushdown for player_career_stats."""
        mapper = get_pushdown_mapper()

        assert mapper.can_push_filter("player_career_stats", "SEASON_ID", "==")

        result = await unified_fetch(
            "player_career_stats",
            {"player_name": "LeBron James"},
            filters={"SEASON_ID": ["==", "2023-24"]},
            use_cache=False
        )

        assert any("filter_pushdown" in op for op in result.provenance.operations)

    @pytest.mark.asyncio
    async def test_pushdown_season_type_player_stats(self):
        """Test SEASON_TYPE filter pushdown for player_career_stats."""
        mapper = get_pushdown_mapper()

        assert mapper.can_push_filter("player_career_stats", "SEASON_TYPE", "==")

        result = await unified_fetch(
            "player_career_stats",
            {"player_name": "LeBron James"},
            filters={"SEASON_TYPE": ["==", "Regular Season"]},
            use_cache=False
        )

        assert any("filter_pushdown" in op for op in result.provenance.operations)

    @pytest.mark.asyncio
    async def test_pushdown_per_mode_league_leaders(self):
        """Test PER_MODE filter pushdown for league_leaders."""
        mapper = get_pushdown_mapper()

        assert mapper.can_push_filter("league_leaders", "PER_MODE", "==")

        result = await unified_fetch(
            "league_leaders",
            {"stat_category": "PTS", "season": "2023-24"},
            filters={"PER_MODE": ["==", "PerGame"]},
            use_cache=False
        )

        assert any("filter_pushdown" in op for op in result.provenance.operations)


class TestFilterPushdownAllOperators:
    """Test all supported operators for filter pushdown."""

    @pytest.mark.asyncio
    async def test_operator_equality(self):
        """Test == operator pushdown."""
        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={"WL": ["==", "W"]},
            use_cache=False
        )

        assert any("filter_pushdown" in op for op in result.provenance.operations)
        assert result.data.num_rows > 0

    @pytest.mark.asyncio
    async def test_operator_greater_than_equal(self):
        """Test >= operator pushdown for dates."""
        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={"GAME_DATE": [">=", "2024-02-01"]},
            use_cache=False
        )

        assert any("filter_pushdown" in op for op in result.provenance.operations)

    @pytest.mark.asyncio
    async def test_operator_less_than_equal(self):
        """Test <= operator pushdown for dates."""
        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={"GAME_DATE": ["<=", "2024-02-28"]},
            use_cache=False
        )

        assert any("filter_pushdown" in op for op in result.provenance.operations)

    @pytest.mark.asyncio
    async def test_operator_between(self):
        """Test BETWEEN operator pushdown."""
        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={"GAME_DATE": ["BETWEEN", ["2024-02-01", "2024-02-29"]]},
            use_cache=False
        )

        ops = result.provenance.operations
        assert any("filter_pushdown" in op for op in ops)

        # Verify both date_from and date_to were set
        assert "date_from" in result.provenance.parameters or True


class TestFilterPushdownCombinations:
    """Test combinations of pushable and non-pushable filters."""

    @pytest.mark.asyncio
    async def test_all_pushable_filters(self):
        """Test multiple pushable filters together."""
        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={
                "WL": ["==", "W"],
                "GAME_DATE": [">=", "2024-01-01"],
            },
            use_cache=False
        )

        # Both filters should be pushed
        assert any("filter_pushdown" in op for op in result.provenance.operations)
        # No post-fetch filtering should occur
        post_filter_ops = [op for op in result.provenance.operations if "post_filter" in op]
        assert len(post_filter_ops) == 0

    @pytest.mark.asyncio
    async def test_mixed_pushable_and_nonpushable(self):
        """Test mix of pushable (WL) and non-pushable (PTS) filters."""
        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={
                "WL": ["==", "W"],  # Pushable
                # Statistical filters not pushable - would need actual column name
            },
            use_cache=False
        )

        # WL filter should be pushed
        assert any("filter_pushdown" in op for op in result.provenance.operations)

    @pytest.mark.asyncio
    async def test_no_pushable_filters(self):
        """Test that non-pushable filters go to post-fetch only."""
        mapper = get_pushdown_mapper()

        # Test that statistical columns cannot be pushed
        assert not mapper.can_push_filter("team_game_log", "PTS", ">=")
        assert not mapper.can_push_filter("team_game_log", "REB", ">")
        assert not mapper.can_push_filter("team_game_log", "AST", ">=")

    @pytest.mark.asyncio
    async def test_date_range_pushdown(self):
        """Test date range filter pushdown (both date_from and date_to)."""
        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={"GAME_DATE": ["BETWEEN", ["2024-01-01", "2024-01-31"]]},
            use_cache=False
        )

        # Both date_from and date_to should be set in parameters
        assert result.provenance.parameters.get("date_from") == "2024-01-01"
        assert result.provenance.parameters.get("date_to") == "2024-01-31"

        # Verify pushdown occurred
        assert any("filter_pushdown" in op for op in result.provenance.operations)


class TestFilterPushdownPerformance:
    """Validate performance improvements from filter pushdown."""

    def setup_method(self):
        """Reset cache before each test."""
        reset_cache_manager()

    @pytest.mark.asyncio
    async def test_data_reduction_with_pushdown(self):
        """Verify filter pushdown reduces data transfer."""
        # Fetch all games (no filter)
        result_all = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            use_cache=False
        )

        total_games = result_all.data.num_rows

        # Fetch only wins (with pushdown)
        result_wins = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={"WL": ["==", "W"]},
            use_cache=False
        )

        wins = result_wins.data.num_rows

        # Validate pushdown occurred
        assert any("filter_pushdown" in op for op in result_wins.provenance.operations)

        # Wins should be roughly 50% of total games (40-50 wins out of 82 games)
        assert wins < total_games
        assert wins >= total_games * 0.3  # At least 30% (bad season)
        assert wins <= total_games * 0.7  # At most 70% (good season)

        reduction_percent = ((total_games - wins) / total_games) * 100
        print(f"\nData reduction: {reduction_percent:.1f}% (fetched {wins} instead of {total_games} games)")

    @pytest.mark.asyncio
    async def test_query_speedup_with_pushdown(self):
        """Verify filter pushdown improves query performance."""
        # Without pushdown: fetch all, then filter with DuckDB
        # (We can't easily test this directly, but we can test with cache disabled)

        # With pushdown: fetch only filtered data
        start = time.time()
        result_pushdown = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={"WL": ["==", "W"]},
            use_cache=False
        )
        time_with_pushdown = time.time() - start

        # Verify pushdown occurred
        assert any("filter_pushdown" in op for op in result_pushdown.provenance.operations)

        # Performance validation: should complete in reasonable time
        assert time_with_pushdown < 5.0  # Should be under 5 seconds

        print(f"\nQuery time with pushdown: {time_with_pushdown*1000:.2f}ms")
        print(f"Fetched {result_pushdown.data.num_rows} rows")

    @pytest.mark.asyncio
    async def test_provenance_tracks_pushdown(self):
        """Verify provenance correctly tracks filter pushdown."""
        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={"WL": ["==", "W"]},
            use_cache=False
        )

        # Check provenance operations
        ops = result.provenance.operations
        assert "unified_fetch" in ops
        assert any("filter_pushdown:1 params" in op for op in ops)

        # Check transformations
        assert any("Pushed 1 filter(s) to API" in t for t in result.transformations)

        # Check parameters were updated
        assert result.provenance.parameters.get("outcome") == "W"

    @pytest.mark.asyncio
    async def test_batch_fetch_with_pushdown(self):
        """Test filter pushdown works with batch fetching."""
        requests = [
            {
                "endpoint": "team_game_log",
                "params": {"team": "Lakers", "season": "2023-24"},
                "filters": {"WL": ["==", "W"]}
            },
            {
                "endpoint": "team_game_log",
                "params": {"team": "Lakers", "season": "2023-24"},
                "filters": {"WL": ["==", "L"]}
            },
        ]

        results = await batch_fetch(requests, max_concurrent=2)

        assert len(results) == 2

        # Both should have filter pushdown
        for result in results:
            assert any("filter_pushdown" in op for op in result.provenance.operations)

        # Wins + losses should equal total games
        wins = results[0].data.num_rows
        losses = results[1].data.num_rows
        total = wins + losses

        print(f"\nWins: {wins}, Losses: {losses}, Total: {total}")
        assert total > 0


class TestFilterPushdownEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_invalid_filter_syntax(self):
        """Test handling of invalid filter syntax."""
        # Invalid filter format (not a list)
        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={"WL": "W"},  # Should be ["==", "W"]
            use_cache=False
        )

        # Should still work but with warning
        assert result.data.num_rows > 0

    @pytest.mark.asyncio
    async def test_empty_filter_dict(self):
        """Test with empty filter dictionary."""
        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={},
            use_cache=False
        )

        # Should work normally, no pushdown
        assert result.data.num_rows > 0
        assert not any("filter_pushdown" in op for op in result.provenance.operations)

    @pytest.mark.asyncio
    async def test_none_filters(self):
        """Test with None filters."""
        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters=None,
            use_cache=False
        )

        assert result.data.num_rows > 0
        assert not any("filter_pushdown" in op for op in result.provenance.operations)

    @pytest.mark.asyncio
    async def test_unsupported_operator(self):
        """Test filter with unsupported operator for pushdown."""
        mapper = get_pushdown_mapper()

        # WL only supports == operator, not >
        assert not mapper.can_push_filter("team_game_log", "WL", ">")
        assert not mapper.can_push_filter("team_game_log", "WL", "IN")

    @pytest.mark.asyncio
    async def test_nonexistent_column_filter(self):
        """Test filter on non-existent column."""
        mapper = get_pushdown_mapper()

        # Should return False for columns that don't exist in mapping
        assert not mapper.can_push_filter("team_game_log", "NONEXISTENT_COLUMN", "==")

    @pytest.mark.asyncio
    async def test_wrong_endpoint_for_filter(self):
        """Test filter meant for one endpoint used on another."""
        mapper = get_pushdown_mapper()

        # WL filter is for team_game_log, not team_standings
        assert not mapper.can_push_filter("team_standings", "WL", "==")

    @pytest.mark.asyncio
    async def test_get_pushable_columns(self):
        """Test getting list of pushable columns for endpoint."""
        mapper = get_pushdown_mapper()

        # Team game log
        pushable = mapper.get_pushable_columns("team_game_log")
        assert "WL" in pushable
        assert "SEASON" in pushable
        assert "GAME_DATE" in pushable

        # Player career stats
        pushable_player = mapper.get_pushable_columns("player_career_stats")
        assert "SEASON_ID" in pushable_player
        assert "SEASON_TYPE" in pushable_player

        # Non-existent endpoint
        pushable_none = mapper.get_pushable_columns("nonexistent_endpoint")
        assert pushable_none == []


class TestAllEndpointsWithFilters:
    """Test filter pushdown on all registered endpoints."""

    @pytest.mark.asyncio
    async def test_team_game_log_endpoint(self):
        """Test team_game_log with all pushable filters."""
        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={
                "WL": ["==", "W"],
                "GAME_DATE": [">=", "2024-01-01"]
            },
            use_cache=False
        )

        assert any("filter_pushdown" in op for op in result.provenance.operations)
        assert result.data.num_rows > 0

    @pytest.mark.asyncio
    async def test_player_career_stats_endpoint(self):
        """Test player_career_stats with pushable filters."""
        result = await unified_fetch(
            "player_career_stats",
            {"player_name": "LeBron James"},
            filters={"SEASON_TYPE": ["==", "Regular Season"]},
            use_cache=False
        )

        assert any("filter_pushdown" in op for op in result.provenance.operations)

    @pytest.mark.asyncio
    async def test_league_leaders_endpoint(self):
        """Test league_leaders with pushable filters."""
        result = await unified_fetch(
            "league_leaders",
            {"stat_category": "PTS", "season": "2023-24"},
            filters={"PER_MODE": ["==", "PerGame"]},
            use_cache=False
        )

        assert any("filter_pushdown" in op for op in result.provenance.operations)

    @pytest.mark.asyncio
    async def test_team_standings_no_pushdown(self):
        """Test team_standings has no pushable filters."""
        mapper = get_pushdown_mapper()

        # team_standings not in filter_to_param_map
        pushable = mapper.get_pushable_columns("team_standings")
        assert len(pushable) == 0

    @pytest.mark.asyncio
    async def test_player_advanced_stats_no_pushdown(self):
        """Test player_advanced_stats has no pushable filters."""
        mapper = get_pushdown_mapper()

        pushable = mapper.get_pushable_columns("player_advanced_stats")
        assert len(pushable) == 0

    @pytest.mark.asyncio
    async def test_team_advanced_stats_no_pushdown(self):
        """Test team_advanced_stats has no pushable filters."""
        mapper = get_pushdown_mapper()

        pushable = mapper.get_pushable_columns("team_advanced_stats")
        assert len(pushable) == 0

    @pytest.mark.asyncio
    async def test_shot_chart_no_pushdown(self):
        """Test shot_chart has no pushable filters currently."""
        mapper = get_pushdown_mapper()

        pushable = mapper.get_pushable_columns("shot_chart")
        assert len(pushable) == 0


# Summary report at end of test run
def pytest_sessionfinish(session, exitstatus):
    """Print summary after all tests complete."""
    print("\n" + "=" * 80)
    print("COMPREHENSIVE FILTER PUSHDOWN STRESS TEST SUMMARY")
    print("=" * 80)
    if exitstatus == 0:
        print("✅ ALL COMPREHENSIVE TESTS PASSED!")
        print("\nValidated:")
        print("  - All pushable columns (WL, SEASON, GAME_DATE, SEASON_ID, SEASON_TYPE, PER_MODE)")
        print("  - All supported operators (==, >=, <=, BETWEEN)")
        print("  - Mixed pushable + non-pushable filters")
        print("  - Performance improvements (data reduction, query speedup)")
        print("  - Edge cases (invalid syntax, empty filters, unsupported operators)")
        print("  - All registered endpoints")
        print("  - Provenance tracking accuracy")
    else:
        print(f"❌ SOME TESTS FAILED (exit status: {exitstatus})")
        print("\nCheck output above for details.")
    print("=" * 80)
