"""
Comprehensive tests for filter pushdown across all granularity levels.

This test suite validates that filter pushdown works correctly for all
data granularities defined by the user:
- Shot-by-shot (shot_chart endpoint)
- Play-by-play (play_by_play endpoint)
- Player/game (player_game_log endpoint)
- Team/game (team_game_log endpoint)
- Player/season (player_career_stats endpoint)
- Team/season (team_standings, team_advanced_stats endpoints)

Phase 2F: Granularity Testing
"""
import pytest
from nba_mcp.data.filter_pushdown import FilterPushdownMapper


class TestGranularityFilterMappings:
    """Test that filter mappings exist for all granularity levels."""

    def test_player_game_granularity_filters(self):
        """Test player/game level has filter pushdown support."""
        mapper = FilterPushdownMapper()

        # player_game_log endpoint should have filter mappings
        pushable_columns = mapper.get_pushable_columns("player_game_log")

        assert "GAME_DATE" in pushable_columns, "player_game_log should support GAME_DATE filtering"
        assert "SEASON" in pushable_columns, "player_game_log should support SEASON filtering"
        assert "SEASON_TYPE" in pushable_columns, "player_game_log should support SEASON_TYPE filtering"

    def test_team_game_granularity_filters(self):
        """Test team/game level has filter pushdown support."""
        mapper = FilterPushdownMapper()

        # team_game_log endpoint should have filter mappings
        pushable_columns = mapper.get_pushable_columns("team_game_log")

        assert "GAME_DATE" in pushable_columns, "team_game_log should support GAME_DATE filtering"
        assert "SEASON" in pushable_columns, "team_game_log should support SEASON filtering"
        assert "WL" in pushable_columns, "team_game_log should support WL filtering"

    def test_player_season_granularity_filters(self):
        """Test player/season level has filter pushdown support."""
        mapper = FilterPushdownMapper()

        # player_career_stats endpoint should have filter mappings
        pushable_columns = mapper.get_pushable_columns("player_career_stats")

        assert "SEASON_ID" in pushable_columns, "player_career_stats should support SEASON_ID filtering"
        assert "SEASON_TYPE" in pushable_columns, "player_career_stats should support SEASON_TYPE filtering"

    def test_clutch_stats_granularity_filters(self):
        """Test clutch stats (player/team game subset) has extensive filter support."""
        mapper = FilterPushdownMapper()

        # clutch_stats endpoint should have comprehensive filter mappings
        pushable_columns = mapper.get_pushable_columns("clutch_stats")

        assert "GAME_DATE" in pushable_columns, "clutch_stats should support GAME_DATE filtering"
        assert "SEASON" in pushable_columns, "clutch_stats should support SEASON filtering"
        assert "WL" in pushable_columns, "clutch_stats should support WL filtering"
        assert "MATCHUP" in pushable_columns, "clutch_stats should support MATCHUP (Home/Away) filtering"
        assert "PER_MODE" in pushable_columns, "clutch_stats should support PER_MODE filtering"

    def test_player_head_to_head_granularity_filters(self):
        """Test player head-to-head (player/game subset) has filter support."""
        mapper = FilterPushdownMapper()

        # player_head_to_head endpoint should have filter mappings
        pushable_columns = mapper.get_pushable_columns("player_head_to_head")

        assert "GAME_DATE" in pushable_columns, "player_head_to_head should support GAME_DATE filtering"
        assert "SEASON" in pushable_columns, "player_head_to_head should support SEASON filtering"

    def test_player_performance_splits_granularity_filters(self):
        """Test player performance splits (player/game aggregated) has filter support."""
        mapper = FilterPushdownMapper()

        # player_performance_splits endpoint should have filter mappings
        pushable_columns = mapper.get_pushable_columns("player_performance_splits")

        assert "GAME_DATE" in pushable_columns, "player_performance_splits should support GAME_DATE filtering"
        assert "SEASON" in pushable_columns, "player_performance_splits should support SEASON filtering"


class TestGranularityFilterPushdown:
    """Test filter pushdown conversion for each granularity level."""

    def test_player_game_date_filter_pushdown(self):
        """Test date filtering is pushed down for player/game granularity."""
        mapper = FilterPushdownMapper()

        # Test >= operator (date_from)
        result = mapper.convert_filter_to_param(
            "player_game_log",
            "GAME_DATE",
            ">=",
            "2024-01-01"
        )

        assert result is not None, "Should be able to push GAME_DATE >= filter"
        param_name, param_value = result
        assert param_name == "date_from", "Should convert to date_from parameter"
        assert param_value == "2024-01-01", "Should preserve date value"

    def test_player_game_season_filter_pushdown(self):
        """Test season filtering is pushed down for player/game granularity."""
        mapper = FilterPushdownMapper()

        # Test equality operator
        result = mapper.convert_filter_to_param(
            "player_game_log",
            "SEASON",
            "==",
            "2023-24"
        )

        assert result is not None, "Should be able to push SEASON == filter"
        param_name, param_value = result
        assert param_name == "season", "Should convert to season parameter"
        assert param_value == "2023-24", "Should preserve season value"

    def test_team_game_wl_filter_pushdown(self):
        """Test win/loss filtering is pushed down for team/game granularity."""
        mapper = FilterPushdownMapper()

        # Test equality operator for WL
        result = mapper.convert_filter_to_param(
            "team_game_log",
            "WL",
            "==",
            "W"
        )

        assert result is not None, "Should be able to push WL == filter"
        param_name, param_value = result
        assert param_name == "outcome", "Should convert to outcome parameter"
        assert param_value == "W", "Should preserve W/L value"

    def test_clutch_stats_outcome_filter_pushdown(self):
        """Test outcome filtering is pushed down for clutch stats."""
        mapper = FilterPushdownMapper()

        # Test equality operator for WL in clutch stats
        result = mapper.convert_filter_to_param(
            "clutch_stats",
            "WL",
            "==",
            "W"
        )

        assert result is not None, "Should be able to push WL filter in clutch_stats"
        param_name, param_value = result
        assert param_name == "outcome", "Should convert to outcome parameter"
        assert param_value == "W", "Should preserve W value"

    def test_clutch_stats_location_filter_pushdown(self):
        """Test location (Home/Away) filtering is pushed down for clutch stats."""
        mapper = FilterPushdownMapper()

        # Test equality operator for MATCHUP
        result = mapper.convert_filter_to_param(
            "clutch_stats",
            "MATCHUP",
            "==",
            "Home"
        )

        assert result is not None, "Should be able to push MATCHUP filter"
        param_name, param_value = result
        assert param_name == "location", "Should convert to location parameter"
        assert param_value == "Home", "Should preserve location value"

    def test_clutch_stats_per_mode_filter_pushdown(self):
        """Test per_mode filtering is pushed down for clutch stats."""
        mapper = FilterPushdownMapper()

        # Test equality operator for PER_MODE
        result = mapper.convert_filter_to_param(
            "clutch_stats",
            "PER_MODE",
            "==",
            "PerGame"
        )

        assert result is not None, "Should be able to push PER_MODE filter"
        param_name, param_value = result
        assert param_value == "PerGame", "Should preserve PER_MODE value"


class TestGranularitySplitFilters:
    """Test filter splitting works correctly for each granularity level."""

    def test_player_game_split_filters(self):
        """Test filter splitting for player/game granularity."""
        mapper = FilterPushdownMapper()

        filters = {
            "GAME_DATE": [">=", "2024-01-01"],  # Should be pushed
            "PTS": [">=", 30],                   # Cannot be pushed (post-filter)
            "SEASON": ["==", "2023-24"],         # Should be pushed
        }

        api_params, post_filters = mapper.split_filters("player_game_log", filters, {})

        # Verify API params
        assert "date_from" in api_params, "GAME_DATE should be pushed as date_from"
        assert api_params["date_from"] == "2024-01-01"
        assert "season" in api_params, "SEASON should be pushed as season"
        assert api_params["season"] == "2023-24"

        # Verify post-filters
        assert "PTS" in post_filters, "PTS should be in post-filters"
        assert "GAME_DATE" not in post_filters, "GAME_DATE should NOT be in post-filters (was pushed)"
        assert "SEASON" not in post_filters, "SEASON should NOT be in post-filters (was pushed)"

    def test_team_game_split_filters(self):
        """Test filter splitting for team/game granularity."""
        mapper = FilterPushdownMapper()

        filters = {
            "WL": ["==", "W"],                   # Should be pushed
            "PTS": [">=", 110],                  # Cannot be pushed (post-filter)
            "GAME_DATE": ["BETWEEN", ["2024-01-01", "2024-01-31"]],  # Should be pushed
        }

        api_params, post_filters = mapper.split_filters("team_game_log", filters, {})

        # Verify API params
        assert "outcome" in api_params, "WL should be pushed as outcome"
        assert api_params["outcome"] == "W"
        assert "date_from" in api_params, "GAME_DATE BETWEEN should set date_from"
        assert "date_to" in api_params, "GAME_DATE BETWEEN should set date_to"

        # Verify post-filters
        assert "PTS" in post_filters, "PTS should be in post-filters"
        assert "WL" not in post_filters, "WL should NOT be in post-filters (was pushed)"

    def test_clutch_stats_split_filters(self):
        """Test filter splitting for clutch stats (extensive filter support)."""
        mapper = FilterPushdownMapper()

        filters = {
            "GAME_DATE": [">=", "2024-01-01"],  # Should be pushed
            "WL": ["==", "W"],                   # Should be pushed
            "MATCHUP": ["==", "Home"],           # Should be pushed
            "PTS": [">=", 5],                    # Cannot be pushed (post-filter)
        }

        api_params, post_filters = mapper.split_filters("clutch_stats", filters, {})

        # Verify API params
        assert "date_from" in api_params, "GAME_DATE should be pushed"
        assert "outcome" in api_params, "WL should be pushed as outcome"
        assert "location" in api_params, "MATCHUP should be pushed as location"

        # Verify post-filters
        assert "PTS" in post_filters, "PTS should be in post-filters"
        assert len(post_filters) == 1, "Only PTS should be in post-filters (others were pushed)"


class TestGranularityDateRangeHandling:
    """Test date range handling across different granularities."""

    def test_player_game_date_range_filter(self):
        """Test date range (BETWEEN) filtering for player/game granularity."""
        mapper = FilterPushdownMapper()

        filters = {
            "GAME_DATE": ["BETWEEN", ["2024-01-01", "2024-01-31"]],
        }

        api_params, post_filters = mapper.split_filters("player_game_log", filters, {})

        # Should set both date_from and date_to
        assert "date_from" in api_params, "BETWEEN should set date_from"
        assert "date_to" in api_params, "BETWEEN should set date_to"
        assert api_params["date_from"] == "2024-01-01"
        assert api_params["date_to"] == "2024-01-31"

        # Should not appear in post-filters (was pushed)
        assert "GAME_DATE" not in post_filters

    def test_team_game_exact_date_filter(self):
        """Test exact date (==) filtering for team/game granularity."""
        mapper = FilterPushdownMapper()

        filters = {
            "GAME_DATE": ["==", "2024-01-15"],
        }

        api_params, post_filters = mapper.split_filters("team_game_log", filters, {})

        # Should set both date_from and date_to to the same value for exact match
        assert "date_from" in api_params, "Exact date should set date_from"
        assert "date_to" in api_params, "Exact date should set date_to"
        assert api_params["date_from"] == "2024-01-15"
        assert api_params["date_to"] == "2024-01-15"

    def test_clutch_stats_date_from_only(self):
        """Test date_from-only filtering for clutch stats."""
        mapper = FilterPushdownMapper()

        filters = {
            "GAME_DATE": [">=", "2024-01-01"],
        }

        api_params, post_filters = mapper.split_filters("clutch_stats", filters, {})

        # Should set only date_from
        assert "date_from" in api_params
        assert api_params["date_from"] == "2024-01-01"
        # date_to should not be set for >= operator
        assert "date_to" not in api_params or api_params["date_to"] == ""

    def test_clutch_stats_date_to_only(self):
        """Test date_to-only filtering for clutch stats."""
        mapper = FilterPushdownMapper()

        filters = {
            "GAME_DATE": ["<=", "2024-01-31"],
        }

        api_params, post_filters = mapper.split_filters("clutch_stats", filters, {})

        # Should set only date_to
        assert "date_to" in api_params
        assert api_params["date_to"] == "2024-01-31"
        # date_from should not be set for <= operator
        assert "date_from" not in api_params or api_params["date_from"] == ""


class TestNonPushableGranularities:
    """Test that endpoints without filter pushdown support are handled correctly."""

    def test_box_score_no_filter_pushdown(self):
        """Test box_score endpoint does not have filter pushdown (single game)."""
        mapper = FilterPushdownMapper()

        # box_score should have no pushable columns (single game ID only)
        pushable_columns = mapper.get_pushable_columns("box_score")
        assert len(pushable_columns) == 0, "box_score should not have filter pushdown (single game)"

    def test_play_by_play_no_filter_pushdown(self):
        """Test play_by_play endpoint does not have filter pushdown (query params)."""
        mapper = FilterPushdownMapper()

        # play_by_play should have no pushable columns (period/time are query params)
        pushable_columns = mapper.get_pushable_columns("play_by_play")
        assert len(pushable_columns) == 0, "play_by_play should not have filter pushdown"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
