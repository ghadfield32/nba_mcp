"""
Comprehensive Test Suite for NBA MCP Data Groupings

Tests all grouping levels with various parameters and granularities:
- player/game, player/team/game
- player/season, player/team/season
- team/game, team/season
- play-by-play with lineup tracking
- shot charts (player and team)

Validates:
- Data retrieval for each grouping level
- Proper granularity (second, day, season)
- Column presence and correctness
- Parameter validation
- Error handling
"""

import asyncio
import logging
from datetime import date, datetime
from typing import Any, Dict, List

import pandas as pd
import pytest

# Test configuration
TEST_SEASON = "2023-24"
TEST_PLAYER_ID = 2544  # LeBron James
TEST_PLAYER_NAME = "LeBron James"
TEST_TEAM_ID = 1610612747  # Lakers
TEST_TEAM_NAME = "Lakers"
TEST_GAME_ID = "0022300001"  # Example game ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# TEST DATA GROUPINGS
# ============================================================================

class TestDataGroupings:
    """Test all data grouping levels"""

    @pytest.mark.asyncio
    async def test_player_game_grouping(self):
        """Test player/game grouping - day granularity"""
        from nba_mcp.api.data_groupings import GroupingFactory, GroupingLevel

        grouping = GroupingFactory.create(GroupingLevel.PLAYER_GAME)

        # Fetch player game logs
        df = await grouping.fetch(season=TEST_SEASON, player_id=TEST_PLAYER_ID)

        # Validate
        assert not df.empty, "Should return game logs"
        assert "GAME_DATE" in df.columns, "Should have GAME_DATE column"
        assert "_granularity" in df.columns, "Should have granularity metadata"
        assert df.iloc[0]["_granularity"] == "day", "Granularity should be 'day'"

        logger.info(f"✅ player/game grouping: {len(df)} games found")

    @pytest.mark.asyncio
    async def test_player_team_game_grouping(self):
        """Test player/team/game grouping - filtered by team"""
        from nba_mcp.api.data_groupings import GroupingFactory, GroupingLevel

        grouping = GroupingFactory.create(GroupingLevel.PLAYER_TEAM_GAME)

        # Fetch player game logs for specific team
        df = await grouping.fetch(
            season=TEST_SEASON,
            team_id=TEST_TEAM_ID,
            player_id=TEST_PLAYER_ID
        )

        # Validate
        assert not df.empty, "Should return game logs"
        assert all(df["TEAM_ID"] == TEST_TEAM_ID), "All games should be for specified team"
        assert "_grouping_level" in df.columns, "Should have grouping level metadata"

        logger.info(f"✅ player/team/game grouping: {len(df)} games found")

    @pytest.mark.asyncio
    async def test_team_game_grouping(self):
        """Test team/game grouping - day granularity"""
        from nba_mcp.api.data_groupings import GroupingFactory, GroupingLevel

        grouping = GroupingFactory.create(GroupingLevel.TEAM_GAME)

        # Fetch team game logs
        df = await grouping.fetch(season=TEST_SEASON, team_id=TEST_TEAM_ID)

        # Validate
        assert not df.empty, "Should return game logs"
        assert "GAME_DATE" in df.columns, "Should have GAME_DATE column"
        assert all(df["TEAM_ID"] == TEST_TEAM_ID), "All games should be for specified team"

        logger.info(f"✅ team/game grouping: {len(df)} games found")

    @pytest.mark.asyncio
    async def test_player_season_aggregation(self):
        """Test player/season grouping - season granularity"""
        from nba_mcp.api.season_aggregator import get_player_season_stats

        # Fetch season stats
        stats = await get_player_season_stats(
            season=TEST_SEASON,
            player_id=TEST_PLAYER_ID
        )

        # Validate
        assert stats, "Should return season stats"
        assert "SEASON_YEAR" in stats, "Should have SEASON_YEAR"
        assert "PTS" in stats, "Should have points total"
        assert "PPG" in stats, "Should have per-game average"
        assert "_granularity" in stats, "Should have granularity metadata"
        assert stats["_granularity"] == "season", "Granularity should be 'season'"

        logger.info(
            f"✅ player/season aggregation: "
            f"GP={stats.get('GP')}, PPG={stats.get('PPG'):.1f}"
        )

    @pytest.mark.asyncio
    async def test_team_season_aggregation(self):
        """Test team/season grouping - season granularity"""
        from nba_mcp.api.season_aggregator import get_team_season_stats

        # Fetch team season stats
        stats = await get_team_season_stats(
            season=TEST_SEASON,
            team_id=TEST_TEAM_ID
        )

        # Validate
        assert stats, "Should return season stats"
        assert "SEASON_YEAR" in stats, "Should have SEASON_YEAR"
        assert "PTS" in stats, "Should have points total"
        assert "W" in stats, "Should have wins"
        assert "L" in stats, "Should have losses"

        logger.info(
            f"✅ team/season aggregation: "
            f"Record={stats.get('W')}-{stats.get('L')}, PPG={stats.get('PPG'):.1f}"
        )

    @pytest.mark.asyncio
    async def test_player_team_season_aggregation(self):
        """Test player/team/season grouping - season granularity with team filter"""
        from nba_mcp.api.season_aggregator import get_player_season_stats

        # Get player stats filtered by team
        stats = await get_player_season_stats(
            season=TEST_SEASON,
            player_id=TEST_PLAYER_ID,
            team_id=TEST_TEAM_ID
        )

        # Validate
        assert stats is not None, "Should return season stats"
        assert stats.get("GP", 0) > 0, "Should have games played"
        assert stats.get("_grouping_level") == "player/team/season"
        assert stats.get("_granularity") == "season"

        logger.info(
            f"✅ player/team/season aggregation: "
            f"GP={stats.get('GP')}, PPG={stats.get('PPG'):.1f}"
        )

    @pytest.mark.asyncio
    async def test_play_by_play_with_lineups(self):
        """Test play-by-play with lineup tracking - second granularity"""
        from nba_mcp.api.lineup_tracker import get_play_by_play_with_lineups

        # Fetch play-by-play with lineups
        df = await get_play_by_play_with_lineups(TEST_GAME_ID, start_period=1, end_period=1)

        # Validate
        assert not df.empty, "Should return play-by-play events"
        assert "period" in df.columns, "Should have period column"
        assert "clock" in df.columns, "Should have clock column"

        # Check lineup columns
        lineup_cols = [
            "CURRENT_LINEUP_HOME",
            "CURRENT_LINEUP_AWAY",
            "CURRENT_LINEUP_HOME_IDS",
            "CURRENT_LINEUP_AWAY_IDS",
            "LINEUP_ID_HOME",
            "LINEUP_ID_AWAY"
        ]
        for col in lineup_cols:
            assert col in df.columns, f"Should have {col} column"

        logger.info(
            f"✅ play-by-play with lineups: {len(df)} events, "
            f"granularity=second"
        )

    @pytest.mark.asyncio
    async def test_granularity_constraints(self):
        """Test that granularity constraints are enforced"""
        from nba_mcp.api.data_groupings import get_grouping_info, GroupingLevel

        # Check player/game granularity
        player_game_info = get_grouping_info(GroupingLevel.PLAYER_GAME)
        assert player_game_info.granularity.value == "day", "player/game should be day granularity"

        # Check player/season granularity
        player_season_info = get_grouping_info(GroupingLevel.PLAYER_SEASON)
        assert player_season_info.granularity.value == "season", "player/season should be season granularity"

        # Check play-by-play granularity
        pbp_info = get_grouping_info(GroupingLevel.PLAY_BY_PLAY_TEAM)
        assert pbp_info.granularity.value == "second", "play-by-play should be second granularity"

        logger.info("✅ Granularity constraints validated")

    @pytest.mark.asyncio
    async def test_parameter_validation(self):
        """Test parameter validation for each grouping"""
        from nba_mcp.api.data_groupings import GroupingFactory, GroupingLevel

        # Test player/game requires season
        grouping = GroupingFactory.create(GroupingLevel.PLAYER_GAME)
        assert not grouping.validate_params({}), "Should fail without season"
        assert grouping.validate_params({"season": TEST_SEASON}), "Should pass with season"

        # Test player/team/game requires season and team
        grouping = GroupingFactory.create(GroupingLevel.PLAYER_TEAM_GAME)
        assert not grouping.validate_params({"season": TEST_SEASON}), "Should fail without team_id"
        assert grouping.validate_params({
            "season": TEST_SEASON,
            "team_id": TEST_TEAM_ID
        }), "Should pass with season and team"

        logger.info("✅ Parameter validation working correctly")


# ============================================================================
# TEST ADVANCED METRICS
# ============================================================================

class TestAdvancedMetrics:
    """Test advanced metrics calculations"""

    @pytest.mark.asyncio
    async def test_game_score_calculation(self):
        """Test Game Score per 36 calculation"""
        from nba_mcp.api.advanced_metrics_calculator import calculate_game_score, calculate_game_score_per_36

        # Sample stats
        stats = {
            "PTS": 25,
            "FGM": 10,
            "FGA": 20,
            "FTM": 4,
            "FTA": 5,
            "OREB": 2,
            "DREB": 6,
            "STL": 1,
            "AST": 7,
            "BLK": 1,
            "PF": 2,
            "TOV": 3,
            "MIN": 36
        }

        gs = calculate_game_score(stats)
        gs_per_36 = calculate_game_score_per_36(stats)

        assert gs > 0, "Game Score should be positive"
        assert gs_per_36 == gs, "GS/36 should equal GS when MIN=36"

        logger.info(f"✅ Game Score calculation: GS={gs:.2f}, GS/36={gs_per_36:.2f}")

    @pytest.mark.asyncio
    async def test_efficiency_metrics(self):
        """Test TS% and eFG% calculations"""
        from nba_mcp.api.advanced_metrics_calculator import (
            calculate_true_shooting_pct,
            calculate_effective_fg_pct
        )

        # Test data
        pts, fga, fta = 25, 20, 5
        fgm, fg3m = 10, 2

        ts_pct = calculate_true_shooting_pct(pts, fga, fta)
        efg_pct = calculate_effective_fg_pct(fgm, fg3m, fga)

        assert 0 <= ts_pct <= 1, "TS% should be between 0 and 1"
        assert 0 <= efg_pct <= 1, "eFG% should be between 0 and 1"

        logger.info(f"✅ Efficiency metrics: TS%={ts_pct:.3f}, eFG%={efg_pct:.3f}")

    @pytest.mark.asyncio
    async def test_win_shares_calculation(self):
        """Test Win Shares calculation"""
        from nba_mcp.api.advanced_metrics_calculator import WinSharesCalculator

        player_stats = {
            "PTS": 2000,
            "FGM": 800,
            "FGA": 1600,
            "FG3M": 100,
            "FTM": 400,
            "FTA": 500,
            "OREB": 80,
            "DREB": 400,
            "AST": 600,
            "STL": 100,
            "BLK": 50,
            "TOV": 200,
            "MIN": 2800,
            "GP": 70
        }

        ws_calc = WinSharesCalculator()
        ows, dws, ws = ws_calc.calculate_win_shares(player_stats, {}, TEST_SEASON)

        assert ows >= 0, "OWS should be non-negative"
        assert dws >= 0, "DWS should be non-negative"
        assert ws == ows + dws, "WS should equal OWS + DWS"

        logger.info(f"✅ Win Shares: OWS={ows:.2f}, DWS={dws:.2f}, WS={ws:.2f}")

    @pytest.mark.asyncio
    async def test_ewa_calculation(self):
        """Test Estimated Wins Added calculation"""
        from nba_mcp.api.advanced_metrics_calculator import calculate_ewa

        player_stats = {
            "PTS": 2000,
            "FGM": 800,
            "FGA": 1600,
            "FTM": 400,
            "FTA": 500,
            "OREB": 80,
            "DREB": 400,
            "AST": 600,
            "STL": 100,
            "BLK": 50,
            "TOV": 200,
            "PF": 150,
            "MIN": 2800
        }

        ewa = calculate_ewa(player_stats, TEST_SEASON)

        assert isinstance(ewa, float), "EWA should be a float"
        # EWA can be negative for below-replacement players
        assert -5 <= ewa <= 20, "EWA should be in reasonable range"

        logger.info(f"✅ Estimated Wins Added: EWA={ewa:.2f}")


class TestShotCharts:
    """Test shot chart groupings (spatial granularity)"""

    @pytest.mark.asyncio
    async def test_player_shot_chart(self):
        """Test player shot chart - spatial granularity"""
        from nba_mcp.api.shot_charts import get_shot_chart

        # Fetch player shot chart
        data = await get_shot_chart(
            entity_name=TEST_PLAYER_NAME,
            entity_type="player",
            season=TEST_SEASON,
            granularity="summary"
        )

        # Validate
        assert data is not None, "Should return shot chart data"
        assert "entity" in data, "Should have entity info"
        assert data["entity"]["type"] == "player", "Entity should be player"

        # Should have summary data
        if "summary" in data:
            assert isinstance(data["summary"], dict), "Summary should be dict"

        logger.info(f"✅ player shot chart: entity={data['entity']['name']}, granularity=spatial")

    @pytest.mark.asyncio
    async def test_team_shot_chart(self):
        """Test team shot chart - spatial granularity"""
        from nba_mcp.api.shot_charts import get_shot_chart

        # Fetch team shot chart
        data = await get_shot_chart(
            entity_name=TEST_TEAM_NAME,
            entity_type="team",
            season=TEST_SEASON,
            granularity="summary"
        )

        # Validate
        assert data is not None, "Should return shot chart data"
        assert "entity" in data, "Should have entity info"
        assert data["entity"]["type"] == "team", "Entity should be team"

        logger.info(f"✅ team shot chart: entity={data['entity']['name']}, granularity=spatial")


# ============================================================================
# TEST RUNNER
# ============================================================================

async def run_all_tests():
    """Run all data grouping tests"""
    logger.info("=" * 80)
    logger.info("RUNNING DATA GROUPINGS TEST SUITE")
    logger.info("=" * 80)

    # Create test instances
    grouping_tests = TestDataGroupings()
    metrics_tests = TestAdvancedMetrics()
    shot_chart_tests = TestShotCharts()

    test_results = {
        "passed": [],
        "failed": [],
        "skipped": []
    }

    # Test data groupings
    tests = [
        ("player/game grouping", grouping_tests.test_player_game_grouping),
        ("player/team/game grouping", grouping_tests.test_player_team_game_grouping),
        ("team/game grouping", grouping_tests.test_team_game_grouping),
        ("player/season aggregation", grouping_tests.test_player_season_aggregation),
        ("team/season aggregation", grouping_tests.test_team_season_aggregation),
        ("player/team/season aggregation", grouping_tests.test_player_team_season_aggregation),
        ("play-by-play with lineups", grouping_tests.test_play_by_play_with_lineups),
        ("player shot chart", shot_chart_tests.test_player_shot_chart),
        ("team shot chart", shot_chart_tests.test_team_shot_chart),
        ("granularity constraints", grouping_tests.test_granularity_constraints),
        ("parameter validation", grouping_tests.test_parameter_validation),
        ("game score calculation", metrics_tests.test_game_score_calculation),
        ("efficiency metrics", metrics_tests.test_efficiency_metrics),
        ("win shares calculation", metrics_tests.test_win_shares_calculation),
        ("EWA calculation", metrics_tests.test_ewa_calculation),
    ]

    for test_name, test_func in tests:
        try:
            logger.info(f"\n▶️  Running: {test_name}")
            await test_func()
            test_results["passed"].append(test_name)
        except Exception as e:
            logger.error(f"❌ Failed: {test_name} - {str(e)}")
            test_results["failed"].append((test_name, str(e)))

    # Print summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    logger.info(f"✅ Passed: {len(test_results['passed'])}")
    logger.info(f"❌ Failed: {len(test_results['failed'])}")
    logger.info(f"⏭️  Skipped: {len(test_results['skipped'])}")

    if test_results["failed"]:
        logger.info("\nFailed tests:")
        for test_name, error in test_results["failed"]:
            logger.info(f"  - {test_name}: {error}")

    return test_results


if __name__ == "__main__":
    asyncio.run(run_all_tests())
