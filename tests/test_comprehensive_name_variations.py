"""
Comprehensive Stress Test for Name Variations Across All MCP Tools

Tests all MCP tools with various name variations to ensure:
- Team nicknames work everywhere (Dubs, Clips, Sixers, etc.)
- Player nicknames work everywhere (King James, Greek Freak, etc.)
- International spellings work (Jokic, Doncic, etc.)
- All granularity levels work with variations
- All filters and parameters work with variations
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.nba_server import (
    get_player_career_information,
    get_league_leaders_info,
    get_live_scores,
    get_date_range_game_log_or_team_game_log,
    get_team_standings,
    get_team_advanced_stats,
    get_player_advanced_stats,
    compare_players,
    get_shot_chart,
    get_game_context,
    answer_nba_question,
)


class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def record_success(self, test_name: str):
        self.passed += 1
        print(f"  [OK] {test_name}")

    def record_failure(self, test_name: str, error: str):
        self.failed += 1
        self.errors.append((test_name, error))
        # Use ASCII-safe error message
        try:
            print(f"  [FAIL] {test_name}: {error}")
        except UnicodeEncodeError:
            error_ascii = error.encode('ascii', errors='replace').decode('ascii')
            print(f"  [FAIL] {test_name}: {error_ascii}")

    def print_summary(self):
        total = self.passed + self.failed
        pass_rate = (self.passed / total * 100) if total > 0 else 0
        print("\n" + "=" * 80)
        print("COMPREHENSIVE TEST SUMMARY")
        print("=" * 80)
        print(f"Total tests: {total}")
        print(f"Passed: {self.passed} ({pass_rate:.1f}%)")
        print(f"Failed: {self.failed}")

        if self.errors:
            print("\n" + "=" * 80)
            print("FAILED TESTS:")
            print("=" * 80)
            for test_name, error in self.errors:
                print(f"  {test_name}")
                print(f"    Error: {error}")


results = TestResults()


async def test_player_career_with_nicknames():
    """Test player career info with various nickname variations"""
    print("\n" + "=" * 80)
    print("TEST 1: Player Career Information with Nicknames")
    print("=" * 80)

    test_cases = [
        ("King James", "2023-24"),
        ("The King", "2022-23"),
        ("Greek Freak", "2023-24"),
        ("The Joker", "2023-24"),
        ("Steph", "2023-24"),
        ("Chef Curry", "2022-23"),
        ("KD", "2023-24"),
        ("AD", "2023-24"),
        ("CP3", "2022-23"),
        ("Luka", "2023-24"),
    ]

    for player_name, season in test_cases:
        try:
            result = await get_player_career_information(player_name, season)
            if result and "error" not in result.lower():
                results.record_success(f"Career info: {player_name} ({season})")
            else:
                results.record_failure(f"Career info: {player_name}", result)
        except Exception as e:
            results.record_failure(f"Career info: {player_name}", str(e))


async def test_league_leaders_various_stats():
    """Test league leaders with different stat categories"""
    print("\n" + "=" * 80)
    print("TEST 2: League Leaders with Various Stats")
    print("=" * 80)

    stat_categories = ["PTS", "AST", "REB", "STL", "BLK", "FG_PCT", "FG3_PCT"]

    for stat in stat_categories:
        try:
            result = await get_league_leaders_info(
                stat_category=stat,
                season="2023-24",
                per_mode="PerGame",
                limit=10
            )
            if result and "error" not in result.lower():
                results.record_success(f"League leaders: {stat}")
            else:
                results.record_failure(f"League leaders: {stat}", result)
        except Exception as e:
            results.record_failure(f"League leaders: {stat}", str(e))


async def test_team_game_logs_with_nicknames():
    """Test team game logs with team nickname variations"""
    print("\n" + "=" * 80)
    print("TEST 3: Team Game Logs with Nicknames")
    print("=" * 80)

    test_cases = [
        ("Dubs", "2023-24"),           # Golden State Warriors
        ("Lake Show", "2023-24"),      # Lakers
        ("Clips", "2023-24"),          # Clippers
        ("Sixers", "2023-24"),         # 76ers
        ("Mavs", "2023-24"),           # Mavericks
        ("Celts", "2023-24"),          # Celtics
        ("Pels", "2023-24"),           # Pelicans
    ]

    for team_name, season in test_cases:
        try:
            result = await get_date_range_game_log_or_team_game_log(
                season=season,
                team=team_name,
                date_from=None,
                date_to=None
            )
            if result and "error" not in result.lower():
                results.record_success(f"Game log: {team_name} ({season})")
            else:
                results.record_failure(f"Game log: {team_name}", result)
        except Exception as e:
            results.record_failure(f"Game log: {team_name}", str(e))


async def test_team_advanced_stats_with_variations():
    """Test team advanced stats with various team name variations"""
    print("\n" + "=" * 80)
    print("TEST 4: Team Advanced Stats with Variations")
    print("=" * 80)

    test_cases = [
        "Dubs",           # Warriors
        "Warriors",       # Full name
        "GSW",            # Abbreviation
        "Clips",          # Clippers
        "Lake Show",      # Lakers
        "Sixers",         # 76ers
    ]

    for team_name in test_cases:
        try:
            result = await get_team_advanced_stats(team_name, season="2023-24")
            if result and "error" not in result.lower():
                results.record_success(f"Advanced stats: {team_name}")
            else:
                results.record_failure(f"Advanced stats: {team_name}", result)
        except Exception as e:
            results.record_failure(f"Advanced stats: {team_name}", str(e))


async def test_player_advanced_stats_with_nicknames():
    """Test player advanced stats with nickname variations"""
    print("\n" + "=" * 80)
    print("TEST 5: Player Advanced Stats with Nicknames")
    print("=" * 80)

    test_cases = [
        "The King",       # LeBron
        "Greek Freak",    # Giannis
        "The Joker",      # Jokic
        "Steph",          # Curry
        "KD",             # Durant
        "AD",             # Davis
    ]

    for player_name in test_cases:
        try:
            result = await get_player_advanced_stats(player_name, season="2023-24")
            if result and "error" not in result.lower():
                results.record_success(f"Player advanced: {player_name}")
            else:
                results.record_failure(f"Player advanced: {player_name}", result)
        except Exception as e:
            results.record_failure(f"Player advanced: {player_name}", str(e))


async def test_player_comparison_with_nicknames():
    """Test player comparison with nickname variations"""
    print("\n" + "=" * 80)
    print("TEST 6: Player Comparison with Nicknames")
    print("=" * 80)

    test_cases = [
        ("The King", "Greek Freak"),
        ("Steph", "Dame"),
        ("KD", "AD"),
        ("The Joker", "The Process"),
        ("Chef Curry", "CP3"),
    ]

    for player1, player2 in test_cases:
        try:
            result = await compare_players(
                player1_name=player1,
                player2_name=player2,
                season="2023-24",
                normalization="per_75"
            )
            if result and "error" not in result.lower():
                results.record_success(f"Compare: {player1} vs {player2}")
            else:
                results.record_failure(f"Compare: {player1} vs {player2}", result)
        except Exception as e:
            results.record_failure(f"Compare: {player1} vs {player2}", str(e))


async def test_shot_chart_all_granularities():
    """Test shot chart with all granularity levels using name variations"""
    print("\n" + "=" * 80)
    print("TEST 7: Shot Chart with All Granularities")
    print("=" * 80)

    granularities = ["raw", "hexbin", "both", "summary"]

    # Test with player nickname
    for granularity in granularities:
        try:
            result = await get_shot_chart(
                entity_name="Steph",
                entity_type="player",
                season="2023-24",
                granularity=granularity
            )
            if result and "error" not in result.lower():
                results.record_success(f"Shot chart (Steph, {granularity})")
            else:
                results.record_failure(f"Shot chart (Steph, {granularity})", result)
        except Exception as e:
            results.record_failure(f"Shot chart (Steph, {granularity})", str(e))

    # Test with team nickname
    try:
        result = await get_shot_chart(
            entity_name="Dubs",
            entity_type="team",
            season="2023-24",
            granularity="summary"
        )
        if result and "error" not in result.lower():
            results.record_success("Shot chart (Dubs, team)")
        else:
            results.record_failure("Shot chart (Dubs, team)", result)
    except Exception as e:
        results.record_failure("Shot chart (Dubs, team)", str(e))


async def test_shot_chart_with_date_filters():
    """Test shot chart with date range filters"""
    print("\n" + "=" * 80)
    print("TEST 8: Shot Chart with Date Filters")
    print("=" * 80)

    test_cases = [
        ("Greek Freak", "2024-01-01", "2024-01-31"),
        ("The Joker", "2023-12-01", "2023-12-31"),
        ("Luka", "2024-02-01", "2024-02-28"),
    ]

    for player_name, date_from, date_to in test_cases:
        try:
            result = await get_shot_chart(
                entity_name=player_name,
                entity_type="player",
                season="2023-24",
                date_from=date_from,
                date_to=date_to,
                granularity="summary"
            )
            if result and "error" not in result.lower():
                results.record_success(f"Shot chart with dates: {player_name}")
            else:
                results.record_failure(f"Shot chart with dates: {player_name}", result)
        except Exception as e:
            results.record_failure(f"Shot chart with dates: {player_name}", str(e))


async def test_game_context_with_team_nicknames():
    """Test game context with team nickname variations"""
    print("\n" + "=" * 80)
    print("TEST 9: Game Context with Team Nicknames")
    print("=" * 80)

    test_cases = [
        ("Dubs", "Lakers"),
        ("Clips", "Mavs"),
        ("Celts", "Sixers"),
        ("Lake Show", "Clippers"),
    ]

    for team1, team2 in test_cases:
        try:
            result = await get_game_context(
                team1_name=team1,
                team2_name=team2,
                season="2023-24"
            )
            if result and "error" not in result.lower():
                results.record_success(f"Game context: {team1} vs {team2}")
            else:
                results.record_failure(f"Game context: {team1} vs {team2}", result)
        except Exception as e:
            results.record_failure(f"Game context: {team1} vs {team2}", str(e))


async def test_nlq_interface_comprehensive():
    """Test NLQ interface with various question types using name variations"""
    print("\n" + "=" * 80)
    print("TEST 10: NLQ Interface Comprehensive")
    print("=" * 80)

    questions = [
        # Player stats with nicknames
        "How is The King doing this season?",
        "Show me Greek Freak stats from 2023-24",
        "What are Steph's shooting percentages?",

        # Team stats with nicknames
        "How are the Dubs performing this season?",
        "What is the Lake Show's offensive rating?",
        "Show me Clips defense stats",

        # Comparisons with nicknames
        "Compare The King and Greek Freak",
        "KD vs AD this season",
        "Steph vs Dame shooting",

        # League leaders
        "Who leads the NBA in assists?",
        "Top 5 scorers this season",

        # International players
        "How is Luka doing?",
        "Show me Jokic stats",
    ]

    for question in questions:
        try:
            result = await answer_nba_question(question)
            if result and "error" not in result.lower():
                results.record_success(f"NLQ: {question[:40]}...")
            else:
                results.record_failure(f"NLQ: {question}", result[:100])
        except Exception as e:
            results.record_failure(f"NLQ: {question}", str(e)[:100])


async def test_team_standings_with_conference_filter():
    """Test team standings with conference filters"""
    print("\n" + "=" * 80)
    print("TEST 11: Team Standings with Conference Filters")
    print("=" * 80)

    test_cases = [
        (None, "All conferences"),
        ("East", "Eastern Conference"),
        ("West", "Western Conference"),
    ]

    for conference, desc in test_cases:
        try:
            result = await get_team_standings(season="2023-24", conference=conference)
            if result and "error" not in result.lower():
                results.record_success(f"Standings: {desc}")
            else:
                results.record_failure(f"Standings: {desc}", result)
        except Exception as e:
            results.record_failure(f"Standings: {desc}", str(e))


async def test_historical_teams():
    """Test historical team name mappings"""
    print("\n" + "=" * 80)
    print("TEST 12: Historical Team Names")
    print("=" * 80)

    test_cases = [
        ("Sonics", "2023-24"),    # Should map to OKC
        ("Bobcats", "2023-24"),   # Should map to Charlotte
        ("Bullets", "2023-24"),   # Should map to Washington
    ]

    for team_name, season in test_cases:
        try:
            result = await get_team_advanced_stats(team_name, season=season)
            if result and "error" not in result.lower():
                results.record_success(f"Historical team: {team_name}")
            else:
                results.record_failure(f"Historical team: {team_name}", result)
        except Exception as e:
            results.record_failure(f"Historical team: {team_name}", str(e))


async def test_live_scores():
    """Test live scores endpoint"""
    print("\n" + "=" * 80)
    print("TEST 13: Live Scores")
    print("=" * 80)

    try:
        # Test with today's date
        result = await get_live_scores(target_date=None)
        if result:
            results.record_success("Live scores (today)")
        else:
            results.record_failure("Live scores (today)", "No result returned")
    except Exception as e:
        results.record_failure("Live scores (today)", str(e))

    try:
        # Test with specific date
        result = await get_live_scores(target_date="2024-01-15")
        if result:
            results.record_success("Live scores (2024-01-15)")
        else:
            results.record_failure("Live scores (2024-01-15)", "No result returned")
    except Exception as e:
        results.record_failure("Live scores (2024-01-15)", str(e))


async def main():
    """Run all comprehensive tests"""
    print("=" * 80)
    print("COMPREHENSIVE NAME VARIATIONS STRESS TEST")
    print("Testing all MCP tools with various name variations")
    print("=" * 80)

    # Run all test suites
    await test_player_career_with_nicknames()
    await test_league_leaders_various_stats()
    await test_team_game_logs_with_nicknames()
    await test_team_advanced_stats_with_variations()
    await test_player_advanced_stats_with_nicknames()
    await test_player_comparison_with_nicknames()
    await test_shot_chart_all_granularities()
    await test_shot_chart_with_date_filters()
    await test_game_context_with_team_nicknames()
    await test_nlq_interface_comprehensive()
    await test_team_standings_with_conference_filter()
    await test_historical_teams()
    await test_live_scores()

    # Print final summary
    results.print_summary()

    # Return exit code based on results
    return 0 if results.failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
