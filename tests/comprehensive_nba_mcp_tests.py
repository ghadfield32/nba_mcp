"""
Comprehensive NBA MCP Test Suite

This test suite provides extensive coverage of all NBA MCP tools with real-world
scenarios for NBA teams and betting companies. Tests are parameterized and automated
for easy adjustment and continuous validation.

Test Categories:
1. Entity Resolution
2. Player Analytics
3. Team Analytics
4. Comparative Analysis
5. League-Wide Data
6. Game Intelligence
7. Shot Analytics
8. Natural Language Queries
9. Dataset Operations
10. System & Configuration

Usage:
    python tests/comprehensive_nba_mcp_tests.py
    python tests/comprehensive_nba_mcp_tests.py --category player_analytics
    python tests/comprehensive_nba_mcp_tests.py --scenario betting_company
"""

import sys
import asyncio
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import argparse

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.nba_server import (
    resolve_nba_entity,
    get_player_career_information,
    get_player_advanced_stats,
    get_team_standings,
    get_team_advanced_stats,
    compare_players,
    compare_players_era_adjusted,
    get_league_leaders_info,
    get_live_scores,
    get_date_range_game_log_or_team_game_log,
    play_by_play,
    get_game_context,
    get_shot_chart,
    answer_nba_question,
    save_nba_data,
    get_metrics_info,
)


class TestConfig:
    """Configurable test parameters for easy adjustment"""

    # Test Players (mix of current stars, legends, role players)
    PLAYERS = {
        "superstar_current": "LeBron James",
        "superstar_young": "Luka Doncic",
        "star_guard": "Stephen Curry",
        "star_forward": "Kevin Durant",
        "star_center": "Joel Embiid",
        "legend_90s": "Michael Jordan",
        "legend_80s": "Magic Johnson",
        "role_player": "Draymond Green",
    }

    # Test Teams
    TEAMS = {
        "western_top": "Golden State Warriors",
        "western_mid": "Los Angeles Lakers",
        "eastern_top": "Boston Celtics",
        "eastern_mid": "Miami Heat",
        "small_market": "Memphis Grizzlies",
    }

    # Seasons for testing
    SEASONS = {
        "current": "2025-26",
        "recent": "2024-25",
        "historic_jordan": "1995-96",
        "historic_magic": "1986-87",
    }

    # Stat categories for league leaders
    STAT_CATEGORIES = ["PTS", "AST", "REB", "STL", "BLK", "FG_PCT", "FG3_PCT"]

    # Test dates (use recent dates for live data)
    @staticmethod
    def get_test_dates():
        today = datetime.now()
        return {
            "today": today.strftime("%Y-%m-%d"),
            "yesterday": (today - timedelta(days=1)).strftime("%Y-%m-%d"),
            "week_ago": (today - timedelta(days=7)).strftime("%Y-%m-%d"),
            "month_ago": (today - timedelta(days=30)).strftime("%Y-%m-%d"),
        }


class TestResults:
    """Track test results for reporting"""

    def __init__(self):
        self.passed = []
        self.failed = []
        self.skipped = []
        self.start_time = datetime.now()

    def add_pass(self, test_name: str, duration_ms: float):
        self.passed.append({"test": test_name, "duration_ms": duration_ms})

    def add_fail(self, test_name: str, error: str):
        self.failed.append({"test": test_name, "error": error})

    def add_skip(self, test_name: str, reason: str):
        self.skipped.append({"test": test_name, "reason": reason})

    def summary(self):
        total = len(self.passed) + len(self.failed) + len(self.skipped)
        duration = (datetime.now() - self.start_time).total_seconds()

        return {
            "total_tests": total,
            "passed": len(self.passed),
            "failed": len(self.failed),
            "skipped": len(self.skipped),
            "pass_rate": f"{(len(self.passed)/total*100):.1f}%" if total > 0 else "0%",
            "total_duration_seconds": round(duration, 2),
        }

    def print_report(self):
        summary = self.summary()
        print("\n" + "="*80)
        print("NBA MCP TEST SUITE - RESULTS")
        print("="*80)
        print(f"Total Tests: {summary['total_tests']}")
        print(f"Passed: {summary['passed']} ({summary['pass_rate']})")
        print(f"Failed: {summary['failed']}")
        print(f"Skipped: {summary['skipped']}")
        print(f"Duration: {summary['total_duration_seconds']}s")
        print("="*80)

        if self.failed:
            print("\nFAILED TESTS:")
            for fail in self.failed:
                print(f"  - {fail['test']}: {fail['error']}")

        if self.skipped:
            print("\nSKIPPED TESTS:")
            for skip in self.skipped:
                print(f"  - {skip['test']}: {skip['reason']}")

        print("\n")


async def run_test(test_func, test_name: str, results: TestResults, *args, **kwargs):
    """Run a single test and track results"""
    start_time = datetime.now()
    try:
        await test_func(*args, **kwargs)
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        results.add_pass(test_name, duration_ms)
        print(f"[PASS] {test_name} ({duration_ms:.0f}ms)")
    except Exception as e:
        results.add_fail(test_name, str(e))
        print(f"[FAIL] {test_name}: {str(e)}")


# ============================================================================
# CATEGORY 1: ENTITY RESOLUTION TESTS
# ============================================================================

async def test_resolve_player_full_name():
    """Test resolving player by full name"""
    result = await resolve_nba_entity("LeBron James", entity_type="player")
    data = json.loads(result)
    assert data["status"] == "success"
    assert "LeBron" in data["data"]["name"]


async def test_resolve_player_partial_name():
    """Test resolving player by partial name (first name only)"""
    result = await resolve_nba_entity("LeBron", entity_type="player")
    data = json.loads(result)
    assert data["status"] == "success"


async def test_resolve_team_full_name():
    """Test resolving team by full name"""
    result = await resolve_nba_entity("Golden State Warriors", entity_type="team")
    data = json.loads(result)
    assert data["status"] == "success"
    assert "Warriors" in data["data"]["name"]


async def test_resolve_team_abbreviation():
    """Test resolving team by abbreviation"""
    result = await resolve_nba_entity("GSW", entity_type="team")
    data = json.loads(result)
    assert data["status"] == "success"


async def test_resolve_team_city():
    """Test resolving team by city name"""
    result = await resolve_nba_entity("Los Angeles", entity_type="team")
    data = json.loads(result)
    assert data["status"] == "success"


# ============================================================================
# CATEGORY 2: PLAYER ANALYTICS TESTS
# ============================================================================

async def test_player_career_info_current_season():
    """Test getting current player career information"""
    result = await get_player_career_information(
        TestConfig.PLAYERS["superstar_current"]
    )
    assert "LeBron" in result


async def test_player_career_info_specific_season():
    """Test getting player career info for specific season"""
    result = await get_player_career_information(
        TestConfig.PLAYERS["star_guard"],
        season=TestConfig.SEASONS["recent"]
    )
    assert "Curry" in result


async def test_player_advanced_stats_current():
    """Test getting player advanced stats for current season"""
    result = await get_player_advanced_stats(
        TestConfig.PLAYERS["star_forward"]
    )
    data = json.loads(result)
    assert data["status"] == "success"


async def test_player_advanced_stats_historical():
    """Test getting historical player advanced stats"""
    result = await get_player_advanced_stats(
        TestConfig.PLAYERS["legend_90s"],
        season=TestConfig.SEASONS["historic_jordan"]
    )
    data = json.loads(result)
    assert data["status"] == "success"


async def test_player_stats_multiple_seasons():
    """Test getting player stats across multiple seasons for trend analysis"""
    seasons = ["2023-24", "2024-25", "2025-26"]
    results = []
    for season in seasons:
        result = await get_player_advanced_stats(
            TestConfig.PLAYERS["superstar_young"],
            season=season
        )
        results.append(json.loads(result))

    # Verify we got data for all seasons
    assert len(results) == 3
    assert all(r["status"] == "success" for r in results)


# ============================================================================
# CATEGORY 3: TEAM ANALYTICS TESTS
# ============================================================================

async def test_team_standings_current_all():
    """Test getting current standings for all teams"""
    result = await get_team_standings()
    data = json.loads(result)
    assert data["status"] == "success"


async def test_team_standings_eastern_conference():
    """Test getting Eastern Conference standings"""
    result = await get_team_standings(conference="East")
    data = json.loads(result)
    assert data["status"] == "success"


async def test_team_standings_western_conference():
    """Test getting Western Conference standings"""
    result = await get_team_standings(conference="West")
    data = json.loads(result)
    assert data["status"] == "success"


async def test_team_standings_historical():
    """Test getting historical season standings"""
    result = await get_team_standings(
        season=TestConfig.SEASONS["historic_jordan"]
    )
    data = json.loads(result)
    assert data["status"] == "success"


async def test_team_advanced_stats_current():
    """Test getting team advanced stats for current season"""
    result = await get_team_advanced_stats(TestConfig.TEAMS["western_top"])
    data = json.loads(result)
    assert data["status"] == "success"


async def test_team_advanced_stats_comparison():
    """Test comparing advanced stats across multiple teams"""
    teams = [TestConfig.TEAMS["western_top"], TestConfig.TEAMS["eastern_top"]]
    results = []
    for team in teams:
        result = await get_team_advanced_stats(team)
        results.append(json.loads(result))

    assert len(results) == 2
    assert all(r["status"] == "success" for r in results)


# ============================================================================
# CATEGORY 4: COMPARATIVE ANALYSIS TESTS
# ============================================================================

async def test_compare_players_same_era():
    """Test comparing two players from same era"""
    result = await compare_players(
        TestConfig.PLAYERS["star_guard"],
        TestConfig.PLAYERS["star_forward"]
    )
    data = json.loads(result)
    assert data["status"] == "success"


async def test_compare_players_different_positions():
    """Test comparing players at different positions"""
    result = await compare_players(
        TestConfig.PLAYERS["star_guard"],
        TestConfig.PLAYERS["star_center"]
    )
    data = json.loads(result)
    assert data["status"] == "success"


async def test_compare_players_era_adjusted_cross_generation():
    """Test era-adjusted comparison across generations"""
    result = await compare_players_era_adjusted(
        TestConfig.PLAYERS["legend_90s"],
        TestConfig.PLAYERS["superstar_current"],
        TestConfig.SEASONS["historic_jordan"],
        "2023-24"
    )
    assert "Jordan" in result or "LeBron" in result


async def test_compare_players_era_adjusted_80s_vs_90s():
    """Test era-adjusted comparison 80s vs 90s"""
    result = await compare_players_era_adjusted(
        TestConfig.PLAYERS["legend_80s"],
        TestConfig.PLAYERS["legend_90s"],
        TestConfig.SEASONS["historic_magic"],
        TestConfig.SEASONS["historic_jordan"]
    )
    assert "Magic" in result or "Jordan" in result


# ============================================================================
# CATEGORY 5: LEAGUE-WIDE DATA TESTS
# ============================================================================

async def test_league_leaders_points():
    """Test getting league leaders in points"""
    result = await get_league_leaders_info(stat_category="PTS")
    data = json.loads(result)
    assert data["status"] == "success"


async def test_league_leaders_assists():
    """Test getting league leaders in assists"""
    result = await get_league_leaders_info(stat_category="AST")
    data = json.loads(result)
    assert data["status"] == "success"


async def test_league_leaders_multiple_categories():
    """Test getting league leaders across multiple stat categories"""
    categories = TestConfig.STAT_CATEGORIES
    results = []
    for cat in categories:
        result = await get_league_leaders_info(stat_category=cat)
        results.append(json.loads(result))

    assert len(results) == len(categories)
    assert all(r["status"] == "success" for r in results)


async def test_league_leaders_per_game_vs_totals():
    """Test different aggregation modes for league leaders"""
    result_per_game = await get_league_leaders_info(
        stat_category="PTS",
        per_mode="PerGame"
    )
    result_totals = await get_league_leaders_info(
        stat_category="PTS",
        per_mode="Totals"
    )

    assert "PerGame" in result_per_game or "Per Game" in result_per_game
    assert result_per_game != result_totals  # Results should be different


async def test_live_scores_today():
    """Test getting live scores for today"""
    dates = TestConfig.get_test_dates()
    result = await get_live_scores(dates["today"])
    # Note: May return no games if no games today
    assert isinstance(result, str)


async def test_live_scores_historical():
    """Test getting scores for historical date"""
    result = await get_live_scores("2024-12-25")  # Christmas Day games
    assert isinstance(result, str)


# ============================================================================
# CATEGORY 6: GAME INTELLIGENCE TESTS
# ============================================================================

async def test_game_log_current_season():
    """Test getting game logs for current season"""
    result = await get_date_range_game_log_or_team_game_log(
        season=TestConfig.SEASONS["current"]
    )
    assert isinstance(result, str)


async def test_game_log_date_range():
    """Test getting game logs for specific date range"""
    dates = TestConfig.get_test_dates()
    result = await get_date_range_game_log_or_team_game_log(
        season=TestConfig.SEASONS["current"],
        date_from=dates["month_ago"],
        date_to=dates["today"]
    )
    assert isinstance(result, str)


async def test_game_log_specific_team():
    """Test getting game logs for specific team"""
    result = await get_date_range_game_log_or_team_game_log(
        season=TestConfig.SEASONS["current"],
        team=TestConfig.TEAMS["western_top"]
    )
    assert isinstance(result, str)


async def test_play_by_play_today():
    """Test getting play-by-play for today's games"""
    result = await play_by_play()
    assert isinstance(result, str)


async def test_play_by_play_specific_game():
    """Test getting play-by-play for specific game"""
    dates = TestConfig.get_test_dates()
    result = await play_by_play(
        game_date=dates["yesterday"],
        team=TestConfig.TEAMS["western_top"]
    )
    assert isinstance(result, str)


async def test_game_context_rivalry_matchup():
    """Test getting game context for rivalry matchup"""
    result = await get_game_context(
        TestConfig.TEAMS["western_top"],
        TestConfig.TEAMS["western_mid"]
    )
    data = json.loads(result)
    assert data["status"] == "success"


async def test_game_context_cross_conference():
    """Test getting game context for cross-conference matchup"""
    result = await get_game_context(
        TestConfig.TEAMS["western_top"],
        TestConfig.TEAMS["eastern_top"]
    )
    data = json.loads(result)
    assert data["status"] == "success"


async def test_game_context_historical_season():
    """Test getting game context for historical season"""
    result = await get_game_context(
        "Los Angeles Lakers",
        "Boston Celtics",
        season="2010-11"  # Classic rivalry season
    )
    data = json.loads(result)
    assert data["status"] == "success"


# ============================================================================
# CATEGORY 7: SHOT ANALYTICS TESTS
# ============================================================================

async def test_shot_chart_player_current_season():
    """Test getting shot chart for player - current season"""
    result = await get_shot_chart(
        entity_name=TestConfig.PLAYERS["star_guard"],
        entity_type="player"
    )
    data = json.loads(result)
    assert data["status"] == "success"


async def test_shot_chart_player_specific_dates():
    """Test getting shot chart for player - specific date range"""
    dates = TestConfig.get_test_dates()
    result = await get_shot_chart(
        entity_name=TestConfig.PLAYERS["star_guard"],
        entity_type="player",
        date_from=dates["month_ago"],
        date_to=dates["today"]
    )
    data = json.loads(result)
    assert data["status"] == "success"


async def test_shot_chart_team_full_season():
    """Test getting shot chart for team - full season"""
    result = await get_shot_chart(
        entity_name=TestConfig.TEAMS["western_top"],
        entity_type="team"
    )
    data = json.loads(result)
    assert data["status"] == "success"


async def test_shot_chart_granularity_raw():
    """Test shot chart with raw data granularity"""
    result = await get_shot_chart(
        entity_name=TestConfig.PLAYERS["star_guard"],
        entity_type="player",
        granularity="raw"
    )
    data = json.loads(result)
    assert data["status"] == "success"


async def test_shot_chart_granularity_summary():
    """Test shot chart with summary granularity"""
    result = await get_shot_chart(
        entity_name=TestConfig.TEAMS["western_top"],
        entity_type="team",
        granularity="summary"
    )
    data = json.loads(result)
    assert data["status"] == "success"


async def test_shot_chart_playoffs():
    """Test getting shot chart for playoffs"""
    result = await get_shot_chart(
        entity_name=TestConfig.PLAYERS["star_forward"],
        entity_type="player",
        season="2023-24",
        season_type="Playoffs"
    )
    data = json.loads(result)
    assert data["status"] == "success"


# ============================================================================
# CATEGORY 8: NATURAL LANGUAGE QUERY TESTS
# ============================================================================

async def test_nlq_who_leads_scoring():
    """Test NLQ: Who leads the NBA in scoring?"""
    result = await answer_nba_question("Who leads the NBA in scoring?")
    data = json.loads(result)
    assert data["status"] == "success"


async def test_nlq_player_comparison():
    """Test NLQ: Compare two players"""
    result = await answer_nba_question(
        f"Compare {TestConfig.PLAYERS['star_guard']} and {TestConfig.PLAYERS['star_forward']}"
    )
    data = json.loads(result)
    assert data["status"] == "success"


async def test_nlq_team_stats():
    """Test NLQ: Team statistics query"""
    result = await answer_nba_question(
        f"What are the {TestConfig.TEAMS['western_top']} stats this season?"
    )
    data = json.loads(result)
    assert data["status"] == "success"


async def test_nlq_standings():
    """Test NLQ: Standings query"""
    result = await answer_nba_question("Show me the Eastern Conference standings")
    data = json.loads(result)
    assert data["status"] == "success"


# ============================================================================
# CATEGORY 9: DATA PERSISTENCE TESTS
# ============================================================================

async def test_save_shot_chart_auto_filename():
    """Test saving shot chart data with auto-generated filename"""
    # First get data
    shot_data = await get_shot_chart(
        entity_name=TestConfig.TEAMS["western_top"],
        entity_type="team",
        granularity="summary"
    )

    # Then save it
    result = await save_nba_data(shot_data)
    data = json.loads(result)
    assert data["status"] == "success"
    assert "file_info" in data
    assert "warriors" in data["file_info"]["filename"].lower() or "golden_state" in data["file_info"]["filename"].lower()


async def test_save_game_context_auto_filename():
    """Test saving game context with auto-generated filename"""
    # First get data
    context_data = await get_game_context(
        TestConfig.TEAMS["western_top"],
        TestConfig.TEAMS["eastern_top"]
    )

    # Then save it
    result = await save_nba_data(context_data)
    data = json.loads(result)
    assert data["status"] == "success"
    assert "vs" in data["file_info"]["filename"]


async def test_save_custom_filename():
    """Test saving data with custom filename"""
    # Get any data
    standings_data = await get_team_standings()

    # Save with custom filename
    result = await save_nba_data(
        standings_data,
        custom_filename="test_standings_data"
    )
    data = json.loads(result)
    assert data["status"] == "success"
    assert "test_standings_data" in data["file_info"]["filename"]


# ============================================================================
# CATEGORY 10: SYSTEM & CONFIGURATION TESTS
# ============================================================================

async def test_get_metrics():
    """Test getting system metrics"""
    result = await get_metrics_info()
    assert isinstance(result, str)
    assert len(result) > 0


# ============================================================================
# INTEGRATION TESTS: REAL-WORLD SCENARIOS
# ============================================================================

async def integration_test_pregame_scouting_report():
    """
    Integration Test: Pre-Game Scouting Report

    Scenario: NBA team wants complete scouting report for upcoming opponent
    Steps:
        1. Get opponent team standings (record, form)
        2. Get opponent advanced stats (offensive/defensive ratings)
        3. Get game context (head-to-head, recent matchups)
        4. Get shot chart (offensive tendencies)
        5. Get top players' advanced stats
        6. Save all data for coaching staff review
    """
    print("\n[INTEGRATION] Pre-Game Scouting Report")

    opponent = TestConfig.TEAMS["eastern_top"]
    our_team = TestConfig.TEAMS["western_top"]

    # 1. Team standings
    standings = await get_team_standings()
    print("  ✓ Retrieved league standings")

    # 2. Advanced stats
    adv_stats = await get_team_advanced_stats(opponent)
    print("  ✓ Retrieved opponent advanced stats")

    # 3. Game context
    game_context = await get_game_context(our_team, opponent)
    print("  ✓ Retrieved game context and matchup history")

    # 4. Shot chart
    shot_chart = await get_shot_chart(
        entity_name=opponent,
        entity_type="team",
        granularity="summary"
    )
    print("  ✓ Retrieved opponent shot chart")

    # 5. Save scouting report
    save_result = await save_nba_data(
        game_context,
        custom_filename=f"scouting_report_{opponent.replace(' ', '_').lower()}"
    )
    print("  ✓ Saved scouting report")

    print("[INTEGRATION] Pre-Game Scouting Report: COMPLETED")


async def integration_test_betting_odds_calculation():
    """
    Integration Test: Betting Odds Calculation

    Scenario: Betting company needs data to calculate game odds
    Steps:
        1. Get both teams' standings and records
        2. Get advanced stats for both teams
        3. Get head-to-head history
        4. Get recent form (last 10 games)
        5. Get key players' current performance
        6. Compile data for odds algorithm
    """
    print("\n[INTEGRATION] Betting Odds Calculation")

    team1 = TestConfig.TEAMS["western_top"]
    team2 = TestConfig.TEAMS["eastern_top"]

    # 1 & 2: Team data
    team1_stats = await get_team_advanced_stats(team1)
    team2_stats = await get_team_advanced_stats(team2)
    print("  ✓ Retrieved both teams' advanced stats")

    # 3 & 4: Game context (includes head-to-head and recent form)
    matchup = await get_game_context(team1, team2)
    print("  ✓ Retrieved matchup context and history")

    # 5: Key player stats
    player1 = TestConfig.PLAYERS["star_guard"]
    player2 = TestConfig.PLAYERS["star_forward"]
    player1_stats = await get_player_advanced_stats(player1)
    player2_stats = await get_player_advanced_stats(player2)
    print("  ✓ Retrieved key players' stats")

    # 6: Standings for current form
    standings = await get_team_standings()
    print("  ✓ Retrieved league standings")

    print("[INTEGRATION] Betting Odds Calculation: COMPLETED")


async def integration_test_live_game_tracking():
    """
    Integration Test: Live Game Tracking

    Scenario: Real-time monitoring during active game
    Steps:
        1. Get live scores
        2. Get play-by-play updates
        3. Track key player performance
        4. Monitor betting lines changes (via stats)
    """
    print("\n[INTEGRATION] Live Game Tracking")

    dates = TestConfig.get_test_dates()

    # 1. Live scores
    scores = await get_live_scores(dates["yesterday"])
    print("  ✓ Retrieved live scores")

    # 2. Play-by-play
    pbp = await play_by_play(game_date=dates["yesterday"])
    print("  ✓ Retrieved play-by-play data")

    print("[INTEGRATION] Live Game Tracking: COMPLETED")


async def integration_test_player_trade_analysis():
    """
    Integration Test: Player Trade Analysis

    Scenario: NBA team evaluating potential trade targets
    Steps:
        1. Compare target player with current roster player
        2. Get advanced stats for both players
        3. Get career trajectory data
        4. Era-adjusted comparison if needed
        5. Generate comprehensive report
    """
    print("\n[INTEGRATION] Player Trade Analysis")

    current_player = TestConfig.PLAYERS["role_player"]
    target_player = TestConfig.PLAYERS["star_center"]

    # 1. Direct comparison
    comparison = await compare_players(current_player, target_player)
    print("  ✓ Compared players")

    # 2. Advanced stats
    current_adv = await get_player_advanced_stats(current_player)
    target_adv = await get_player_advanced_stats(target_player)
    print("  ✓ Retrieved advanced stats for both players")

    # 3. Career information
    current_career = await get_player_career_information(current_player)
    target_career = await get_player_career_information(target_player)
    print("  ✓ Retrieved career information")

    # 4. Save analysis
    save_result = await save_nba_data(
        comparison,
        custom_filename="trade_analysis_comparison"
    )
    print("  ✓ Saved trade analysis")

    print("[INTEGRATION] Player Trade Analysis: COMPLETED")


async def integration_test_season_performance_tracking():
    """
    Integration Test: Season Performance Tracking

    Scenario: Track team performance throughout season
    Steps:
        1. Get team standings progression
        2. Get team advanced stats trends
        3. Get game logs for the season
        4. Identify patterns and trends
        5. Generate season report
    """
    print("\n[INTEGRATION] Season Performance Tracking")

    team = TestConfig.TEAMS["western_top"]
    season = TestConfig.SEASONS["current"]

    # 1. Current standings
    standings = await get_team_standings(season=season)
    print("  ✓ Retrieved current standings")

    # 2. Advanced stats
    adv_stats = await get_team_advanced_stats(team, season=season)
    print("  ✓ Retrieved team advanced stats")

    # 3. Game logs
    dates = TestConfig.get_test_dates()
    game_logs = await get_date_range_game_log_or_team_game_log(
        season=season,
        team=team,
        date_from=dates["month_ago"],
        date_to=dates["today"]
    )
    print("  ✓ Retrieved game logs")

    print("[INTEGRATION] Season Performance Tracking: COMPLETED")


# ============================================================================
# TEST RUNNER
# ============================================================================

async def run_all_tests(category: Optional[str] = None, scenario: Optional[str] = None):
    """Run all tests or filtered by category/scenario"""
    results = TestResults()

    print("\n" + "="*80)
    print("NBA MCP COMPREHENSIVE TEST SUITE")
    print("="*80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Filter - Category: {category or 'ALL'}, Scenario: {scenario or 'ALL'}")
    print("="*80 + "\n")

    # Category 1: Entity Resolution
    if not category or category == "entity_resolution":
        print("\n[CATEGORY 1] Entity Resolution Tests")
        print("-" * 80)
        await run_test(test_resolve_player_full_name, "Entity: Player Full Name", results)
        await run_test(test_resolve_player_partial_name, "Entity: Player Partial Name", results)
        await run_test(test_resolve_team_full_name, "Entity: Team Full Name", results)
        await run_test(test_resolve_team_abbreviation, "Entity: Team Abbreviation", results)
        await run_test(test_resolve_team_city, "Entity: Team City", results)

    # Category 2: Player Analytics
    if not category or category == "player_analytics":
        print("\n[CATEGORY 2] Player Analytics Tests")
        print("-" * 80)
        await run_test(test_player_career_info_current_season, "Player: Career Info Current", results)
        await run_test(test_player_career_info_specific_season, "Player: Career Info Specific Season", results)
        await run_test(test_player_advanced_stats_current, "Player: Advanced Stats Current", results)
        await run_test(test_player_advanced_stats_historical, "Player: Advanced Stats Historical", results)
        await run_test(test_player_stats_multiple_seasons, "Player: Multi-Season Trend", results)

    # Category 3: Team Analytics
    if not category or category == "team_analytics":
        print("\n[CATEGORY 3] Team Analytics Tests")
        print("-" * 80)
        await run_test(test_team_standings_current_all, "Team: Standings All Teams", results)
        await run_test(test_team_standings_eastern_conference, "Team: Standings East", results)
        await run_test(test_team_standings_western_conference, "Team: Standings West", results)
        await run_test(test_team_standings_historical, "Team: Standings Historical", results)
        await run_test(test_team_advanced_stats_current, "Team: Advanced Stats Current", results)
        await run_test(test_team_advanced_stats_comparison, "Team: Multi-Team Comparison", results)

    # Category 4: Comparative Analysis
    if not category or category == "comparative":
        print("\n[CATEGORY 4] Comparative Analysis Tests")
        print("-" * 80)
        await run_test(test_compare_players_same_era, "Compare: Same Era Players", results)
        await run_test(test_compare_players_different_positions, "Compare: Different Positions", results)
        await run_test(test_compare_players_era_adjusted_cross_generation, "Compare: Cross-Generation Era-Adjusted", results)
        await run_test(test_compare_players_era_adjusted_80s_vs_90s, "Compare: 80s vs 90s Era-Adjusted", results)

    # Category 5: League-Wide Data
    if not category or category == "league_data":
        print("\n[CATEGORY 5] League-Wide Data Tests")
        print("-" * 80)
        await run_test(test_league_leaders_points, "League: Leaders Points", results)
        await run_test(test_league_leaders_assists, "League: Leaders Assists", results)
        await run_test(test_league_leaders_multiple_categories, "League: Leaders Multiple Categories", results)
        await run_test(test_league_leaders_per_game_vs_totals, "League: Leaders Aggregation Modes", results)
        await run_test(test_live_scores_today, "League: Live Scores Today", results)
        await run_test(test_live_scores_historical, "League: Live Scores Historical", results)

    # Category 6: Game Intelligence
    if not category or category == "game_intelligence":
        print("\n[CATEGORY 6] Game Intelligence Tests")
        print("-" * 80)
        await run_test(test_game_log_current_season, "Game: Logs Current Season", results)
        await run_test(test_game_log_date_range, "Game: Logs Date Range", results)
        await run_test(test_game_log_specific_team, "Game: Logs Specific Team", results)
        await run_test(test_play_by_play_today, "Game: Play-by-Play Today", results)
        await run_test(test_play_by_play_specific_game, "Game: Play-by-Play Specific", results)
        await run_test(test_game_context_rivalry_matchup, "Game: Context Rivalry", results)
        await run_test(test_game_context_cross_conference, "Game: Context Cross-Conference", results)
        await run_test(test_game_context_historical_season, "Game: Context Historical", results)

    # Category 7: Shot Analytics
    if not category or category == "shot_analytics":
        print("\n[CATEGORY 7] Shot Analytics Tests")
        print("-" * 80)
        await run_test(test_shot_chart_player_current_season, "Shot: Player Current Season", results)
        await run_test(test_shot_chart_player_specific_dates, "Shot: Player Date Range", results)
        await run_test(test_shot_chart_team_full_season, "Shot: Team Full Season", results)
        await run_test(test_shot_chart_granularity_raw, "Shot: Granularity Raw", results)
        await run_test(test_shot_chart_granularity_summary, "Shot: Granularity Summary", results)
        await run_test(test_shot_chart_playoffs, "Shot: Playoffs Data", results)

    # Category 8: Natural Language
    if not category or category == "nlq":
        print("\n[CATEGORY 8] Natural Language Query Tests")
        print("-" * 80)
        await run_test(test_nlq_who_leads_scoring, "NLQ: League Leaders", results)
        await run_test(test_nlq_player_comparison, "NLQ: Player Comparison", results)
        await run_test(test_nlq_team_stats, "NLQ: Team Stats", results)
        await run_test(test_nlq_standings, "NLQ: Standings", results)

    # Category 9: Data Persistence
    if not category or category == "data_persistence":
        print("\n[CATEGORY 9] Data Persistence Tests")
        print("-" * 80)
        await run_test(test_save_shot_chart_auto_filename, "Save: Shot Chart Auto-Filename", results)
        await run_test(test_save_game_context_auto_filename, "Save: Game Context Auto-Filename", results)
        await run_test(test_save_custom_filename, "Save: Custom Filename", results)

    # Category 10: System
    if not category or category == "system":
        print("\n[CATEGORY 10] System & Configuration Tests")
        print("-" * 80)
        await run_test(test_get_metrics, "System: Get Metrics", results)

    # Integration Tests / Scenarios
    if not scenario or scenario == "nba_team":
        print("\n[INTEGRATION] NBA Team Scenarios")
        print("-" * 80)
        await run_test(integration_test_pregame_scouting_report, "Scenario: Pre-Game Scouting", results)
        await run_test(integration_test_player_trade_analysis, "Scenario: Trade Analysis", results)
        await run_test(integration_test_season_performance_tracking, "Scenario: Season Tracking", results)

    if not scenario or scenario == "betting_company":
        print("\n[INTEGRATION] Betting Company Scenarios")
        print("-" * 80)
        await run_test(integration_test_betting_odds_calculation, "Scenario: Odds Calculation", results)
        await run_test(integration_test_live_game_tracking, "Scenario: Live Tracking", results)

    # Print results
    results.print_report()

    # Return exit code based on results
    return 0 if len(results.failed) == 0 else 1


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point with CLI argument parsing"""
    parser = argparse.ArgumentParser(
        description="NBA MCP Comprehensive Test Suite"
    )
    parser.add_argument(
        "--category",
        choices=[
            "entity_resolution", "player_analytics", "team_analytics",
            "comparative", "league_data", "game_intelligence",
            "shot_analytics", "nlq", "data_persistence", "system"
        ],
        help="Run tests for specific category only"
    )
    parser.add_argument(
        "--scenario",
        choices=["nba_team", "betting_company"],
        help="Run specific integration scenario"
    )

    args = parser.parse_args()

    # Run tests
    exit_code = asyncio.run(run_all_tests(
        category=args.category,
        scenario=args.scenario
    ))

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
