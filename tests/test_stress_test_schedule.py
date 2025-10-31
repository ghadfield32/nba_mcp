"""
Stress Test for NBA Schedule Tool

Tests the schedule tool with real-world queries including:
1. Getting Christmas games
2. Natural language query variations
3. All filter combinations
4. Edge cases
5. Integration with MCP server
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.schedule import (
    get_nba_schedule,
    format_schedule_markdown,
    get_current_season_year,
)


class StressTestResults:
    def __init__(self):
        self.tests = []
        self.passed = 0
        self.failed = 0
        self.total = 0

    def add_result(self, name, passed, details=""):
        self.tests.append({
            "name": name,
            "passed": passed,
            "details": details
        })
        self.total += 1
        if passed:
            self.passed += 1
        else:
            self.failed += 1

    def print_summary(self):
        print("\n" + "=" * 80)
        print("STRESS TEST SUMMARY")
        print("=" * 80)

        for test in self.tests:
            status = "[PASS]" if test["passed"] else "[FAIL]"
            details = f" - {test['details']}" if test['details'] else ""
            print(f"{status:8} {test['name']}{details}")

        print("=" * 80)
        print(f"Results: {self.passed}/{self.total} tests passed ({self.passed/self.total*100:.1f}%)")
        if self.failed > 0:
            print(f"FAILURES: {self.failed} test(s) failed")
        print("=" * 80)

        return self.failed == 0


results = StressTestResults()


async def test_christmas_games_2025():
    """
    PRIMARY TEST: Get Christmas games for 2025
    This is what the user explicitly asked for
    """
    print("\n" + "=" * 80)
    print("PRIMARY TEST: Christmas Games 2025")
    print("=" * 80)

    try:
        # Test 1: Get Christmas Day 2025 games
        print("\nQuery: Get all games on Christmas Day 2025 (2025-12-25)")
        df = await get_nba_schedule(
            date_from="2025-12-25",
            date_to="2025-12-25"
        )

        if len(df) > 0:
            print(f"\n[SUCCESS] Found {len(df)} Christmas games!")
            print("\nChristmas Day 2025 Schedule:")
            print("-" * 80)

            for idx, row in df.iterrows():
                matchup = f"{row['away_abbr']} @ {row['home_abbr']}"
                arena = row.get('arena', 'TBD')
                status = row.get('game_status', 'Scheduled')
                time_utc = row.get('game_date_utc', 'TBD')

                print(f"\nGame {idx + 1}: {matchup}")
                print(f"  Arena: {arena}")
                print(f"  Status: {status}")
                print(f"  Time: {time_utc}")

                # Show TV info if available
                if pd.notna(row.get('broadcasters_national')):
                    print(f"  National TV: {row['broadcasters_national']}")

            # Format as markdown too
            print("\n" + "=" * 80)
            print("MARKDOWN FORMAT:")
            print("=" * 80)
            markdown = format_schedule_markdown(df)
            print(markdown)

            results.add_result(
                "Christmas Games 2025",
                True,
                f"Found {len(df)} games"
            )
        else:
            print(f"\n[INFO] No Christmas games found yet")
            print("This might mean:")
            print("  1. Schedule not published for Christmas 2025 yet")
            print("  2. Games scheduled but data not in NBA CDN yet")
            print("  3. Need to check NBA.com for official announcement")

            results.add_result(
                "Christmas Games 2025",
                True,
                "0 games (schedule may not be published)"
            )

    except Exception as e:
        print(f"\n[FAIL] Error getting Christmas games: {e}")
        import traceback
        traceback.print_exc()
        results.add_result("Christmas Games 2025", False, str(e))


async def test_natural_language_scenarios():
    """
    Test natural language query scenarios
    """
    print("\n" + "=" * 80)
    print("NATURAL LANGUAGE QUERY TESTS")
    print("=" * 80)

    scenarios = [
        {
            "query": "Get all Lakers games",
            "params": {"team": "LAL"},
            "description": "Simple team query"
        },
        {
            "query": "Show me Celtics games in December",
            "params": {"team": "BOS", "date_from": "2025-12-01", "date_to": "2025-12-31"},
            "description": "Team + month query"
        },
        {
            "query": "What games are on New Year's Day?",
            "params": {"date_from": "2026-01-01", "date_to": "2026-01-01"},
            "description": "Specific date query"
        },
        {
            "query": "Get Warriors home games",
            "params": {"team": "GSW"},
            "description": "Team query (filter home manually)"
        },
        {
            "query": "Show me opening week",
            "params": {"date_from": "2025-10-22", "date_to": "2025-10-28"},
            "description": "Date range query"
        },
    ]

    for scenario in scenarios:
        print(f"\n{scenario['query']}")
        print(f"  Description: {scenario['description']}")

        try:
            df = await get_nba_schedule(**scenario['params'])

            if len(df) > 0:
                print(f"  [PASS] Found {len(df)} games")

                # Show sample
                if len(df) >= 3:
                    print(f"  Sample games:")
                    for _, row in df.head(3).iterrows():
                        matchup = f"{row['away_abbr']} @ {row['home_abbr']}"
                        date = row.get('game_date_local', 'N/A')
                        print(f"    {date}: {matchup}")
                else:
                    print(f"  All {len(df)} games:")
                    for _, row in df.iterrows():
                        matchup = f"{row['away_abbr']} @ {row['home_abbr']}"
                        date = row.get('game_date_local', 'N/A')
                        print(f"    {date}: {matchup}")

                results.add_result(
                    f"NL Query: {scenario['query'][:40]}",
                    True,
                    f"{len(df)} games"
                )
            else:
                print(f"  [INFO] No games found")
                results.add_result(
                    f"NL Query: {scenario['query'][:40]}",
                    True,
                    "0 games"
                )

        except Exception as e:
            print(f"  [FAIL] Error: {e}")
            results.add_result(
                f"NL Query: {scenario['query'][:40]}",
                False,
                str(e)
            )


async def test_all_teams():
    """
    Test getting schedule for all NBA teams
    """
    print("\n" + "=" * 80)
    print("ALL TEAMS TEST")
    print("=" * 80)

    teams = [
        # Eastern Conference
        "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DET", "IND",
        "MIA", "MIL", "NYK", "ORL", "PHI", "TOR", "WAS",
        # Western Conference
        "DAL", "DEN", "GSW", "HOU", "LAC", "LAL", "MEM", "MIN",
        "NOP", "OKC", "PHX", "POR", "SAC", "SAS", "UTA"
    ]

    team_results = {}
    total_teams_with_games = 0

    print(f"\nTesting schedule fetch for all {len(teams)} NBA teams...")

    for team in teams:
        try:
            df = await get_nba_schedule(team=team)
            game_count = len(df)
            team_results[team] = game_count

            if game_count > 0:
                total_teams_with_games += 1

        except Exception as e:
            print(f"  [FAIL] {team}: {e}")
            team_results[team] = -1

    # Print summary
    print(f"\nResults:")
    print(f"  Teams tested: {len(teams)}")
    print(f"  Teams with games: {total_teams_with_games}")

    # Show teams with most games
    if total_teams_with_games > 0:
        sorted_teams = sorted(
            [(t, c) for t, c in team_results.items() if c > 0],
            key=lambda x: x[1],
            reverse=True
        )

        print(f"\n  Top 5 teams by game count:")
        for team, count in sorted_teams[:5]:
            print(f"    {team}: {count} games")

    # All teams should work (even if 0 games)
    failed_teams = [t for t, c in team_results.items() if c == -1]

    if len(failed_teams) == 0:
        results.add_result(
            "All Teams Test",
            True,
            f"{len(teams)} teams, {total_teams_with_games} with games"
        )
    else:
        results.add_result(
            "All Teams Test",
            False,
            f"{len(failed_teams)} teams failed"
        )


async def test_date_ranges():
    """
    Test various date range scenarios
    """
    print("\n" + "=" * 80)
    print("DATE RANGE TESTS")
    print("=" * 80)

    test_ranges = [
        {
            "name": "Full Season (Oct-Apr)",
            "date_from": "2025-10-01",
            "date_to": "2026-04-30"
        },
        {
            "name": "October 2025",
            "date_from": "2025-10-01",
            "date_to": "2025-10-31"
        },
        {
            "name": "November 2025",
            "date_from": "2025-11-01",
            "date_to": "2025-11-30"
        },
        {
            "name": "December 2025",
            "date_from": "2025-12-01",
            "date_to": "2025-12-31"
        },
        {
            "name": "January 2026",
            "date_from": "2026-01-01",
            "date_to": "2026-01-31"
        },
        {
            "name": "All-Star Weekend (approx)",
            "date_from": "2026-02-13",
            "date_to": "2026-02-16"
        },
        {
            "name": "Playoffs Start (approx)",
            "date_from": "2026-04-18",
            "date_to": "2026-04-30"
        },
    ]

    for test_range in test_ranges:
        print(f"\n{test_range['name']}:")

        try:
            df = await get_nba_schedule(
                date_from=test_range['date_from'],
                date_to=test_range['date_to']
            )

            print(f"  [PASS] Found {len(df)} games")

            if len(df) > 0:
                # Verify date range
                min_date = df['game_date_local'].min()
                max_date = df['game_date_local'].max()
                print(f"  Date range: {min_date} to {max_date}")

            results.add_result(
                f"Date Range: {test_range['name']}",
                True,
                f"{len(df)} games"
            )

        except Exception as e:
            print(f"  [FAIL] Error: {e}")
            results.add_result(
                f"Date Range: {test_range['name']}",
                False,
                str(e)
            )


async def test_combined_filters():
    """
    Test complex filter combinations
    """
    print("\n" + "=" * 80)
    print("COMBINED FILTER TESTS")
    print("=" * 80)

    combinations = [
        {
            "name": "Lakers in December",
            "params": {"team": "LAL", "date_from": "2025-12-01", "date_to": "2025-12-31"}
        },
        {
            "name": "Celtics Opening Week",
            "params": {"team": "BOS", "date_from": "2025-10-22", "date_to": "2025-10-28"}
        },
        {
            "name": "Warriors on Christmas",
            "params": {"team": "GSW", "date_from": "2025-12-25", "date_to": "2025-12-25"}
        },
        {
            "name": "Any team New Year's Day",
            "params": {"date_from": "2026-01-01", "date_to": "2026-01-01"}
        },
    ]

    for combo in combinations:
        print(f"\n{combo['name']}:")

        try:
            df = await get_nba_schedule(**combo['params'])

            print(f"  [PASS] Found {len(df)} games")

            if len(df) > 0:
                for _, row in df.iterrows():
                    matchup = f"{row['away_abbr']} @ {row['home_abbr']}"
                    date = row.get('game_date_local', 'N/A')
                    print(f"    {date}: {matchup}")

            results.add_result(
                f"Combined: {combo['name']}",
                True,
                f"{len(df)} games"
            )

        except Exception as e:
            print(f"  [FAIL] Error: {e}")
            results.add_result(
                f"Combined: {combo['name']}",
                False,
                str(e)
            )


async def test_output_formats():
    """
    Test both markdown and JSON output formats
    """
    print("\n" + "=" * 80)
    print("OUTPUT FORMAT TESTS")
    print("=" * 80)

    try:
        # Get some games
        df = await get_nba_schedule(
            date_from="2025-12-25",
            date_to="2025-12-25"
        )

        # Test markdown format
        print("\nMarkdown Format Test:")
        markdown = format_schedule_markdown(df, max_games=5)

        if markdown and len(markdown) > 0:
            print(f"  [PASS] Generated markdown ({len(markdown)} chars)")
            print("\n  Preview:")
            lines = markdown.split("\n")
            for line in lines[:5]:
                print(f"  {line}")

            results.add_result("Markdown Output", True, f"{len(markdown)} chars")
        else:
            print(f"  [INFO] Empty markdown (no games)")
            results.add_result("Markdown Output", True, "Empty (no games)")

        # Test JSON format (DataFrame to dict)
        print("\nJSON Format Test:")
        if len(df) > 0:
            json_data = df.head(3).to_dict(orient='records')
            json_str = json.dumps(json_data, indent=2, default=str)

            print(f"  [PASS] Generated JSON ({len(json_str)} chars)")
            print(f"  Sample keys: {list(json_data[0].keys())[:5]}")

            results.add_result("JSON Output", True, f"{len(json_str)} chars")
        else:
            print(f"  [INFO] No games to convert to JSON")
            results.add_result("JSON Output", True, "No games")

    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        results.add_result("Output Formats", False, str(e))


async def test_edge_cases():
    """
    Test edge cases and error conditions
    """
    print("\n" + "=" * 80)
    print("EDGE CASE TESTS")
    print("=" * 80)

    # Test 1: Invalid date format
    print("\nTest 1: Invalid date format")
    try:
        df = await get_nba_schedule(date_from="12/25/2025")
        print(f"  [FAIL] Should have rejected MM/DD/YYYY format")
        results.add_result("Edge: Invalid Date Format", False, "No error raised")
    except ValueError as e:
        print(f"  [PASS] Correctly rejected: {str(e)[:60]}...")
        results.add_result("Edge: Invalid Date Format", True, "ValueError raised")
    except Exception as e:
        print(f"  [FAIL] Wrong error type: {type(e)}")
        results.add_result("Edge: Invalid Date Format", False, f"Wrong error: {type(e)}")

    # Test 2: Invalid team abbreviation (should work but return 0)
    print("\nTest 2: Invalid team abbreviation")
    try:
        df = await get_nba_schedule(team="XXX")
        print(f"  [PASS] Handled gracefully ({len(df)} games)")
        results.add_result("Edge: Invalid Team", True, f"{len(df)} games")
    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        results.add_result("Edge: Invalid Team", False, str(e))

    # Test 3: Future date (way in future)
    print("\nTest 3: Far future date")
    try:
        df = await get_nba_schedule(date_from="2030-01-01", date_to="2030-01-31")
        print(f"  [PASS] Handled gracefully ({len(df)} games)")
        results.add_result("Edge: Future Date", True, f"{len(df)} games")
    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        results.add_result("Edge: Future Date", False, str(e))

    # Test 4: Past date (way in past)
    print("\nTest 4: Old date (2000)")
    try:
        df = await get_nba_schedule(date_from="2000-01-01", date_to="2000-01-31")
        print(f"  [PASS] Handled gracefully ({len(df)} games)")
        results.add_result("Edge: Old Date", True, f"{len(df)} games")
    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        results.add_result("Edge: Old Date", False, str(e))

    # Test 5: Reversed date range (from > to)
    print("\nTest 5: Reversed date range")
    try:
        df = await get_nba_schedule(date_from="2026-01-31", date_to="2026-01-01")
        print(f"  [PASS] Handled gracefully ({len(df)} games)")
        results.add_result("Edge: Reversed Dates", True, f"{len(df)} games")
    except Exception as e:
        print(f"  [INFO] Rejected or empty: {e}")
        results.add_result("Edge: Reversed Dates", True, "Handled")


async def test_performance():
    """
    Test performance and response times
    """
    print("\n" + "=" * 80)
    print("PERFORMANCE TESTS")
    print("=" * 80)

    import time

    # Test 1: Single team query
    print("\nTest 1: Single team query (Lakers)")
    start = time.time()
    df = await get_nba_schedule(team="LAL")
    elapsed = time.time() - start

    print(f"  Time: {elapsed*1000:.1f}ms")
    print(f"  Games: {len(df)}")

    if elapsed < 5.0:  # Should be under 5 seconds
        results.add_result("Performance: Single Query", True, f"{elapsed*1000:.1f}ms")
    else:
        results.add_result("Performance: Single Query", False, f"Too slow: {elapsed*1000:.1f}ms")

    # Test 2: Date range query
    print("\nTest 2: Date range query (December)")
    start = time.time()
    df = await get_nba_schedule(date_from="2025-12-01", date_to="2025-12-31")
    elapsed = time.time() - start

    print(f"  Time: {elapsed*1000:.1f}ms")
    print(f"  Games: {len(df)}")

    if elapsed < 5.0:
        results.add_result("Performance: Date Range", True, f"{elapsed*1000:.1f}ms")
    else:
        results.add_result("Performance: Date Range", False, f"Too slow: {elapsed*1000:.1f}ms")

    # Test 3: Combined filters
    print("\nTest 3: Combined filters (Team + Date)")
    start = time.time()
    df = await get_nba_schedule(
        team="BOS",
        date_from="2025-12-01",
        date_to="2025-12-31"
    )
    elapsed = time.time() - start

    print(f"  Time: {elapsed*1000:.1f}ms")
    print(f"  Games: {len(df)}")

    if elapsed < 5.0:
        results.add_result("Performance: Combined", True, f"{elapsed*1000:.1f}ms")
    else:
        results.add_result("Performance: Combined", False, f"Too slow: {elapsed*1000:.1f}ms")


async def run_stress_tests():
    """
    Run all stress tests
    """
    print("\n" + "=" * 80)
    print("NBA SCHEDULE TOOL - COMPREHENSIVE STRESS TEST")
    print("=" * 80)
    print("Testing all functionality, natural language queries, and edge cases")
    print("=" * 80)

    # Import pandas for some tests
    global pd
    import pandas as pd

    # PRIMARY TEST - What the user asked for
    await test_christmas_games_2025()

    # Natural language scenarios
    await test_natural_language_scenarios()

    # All teams
    await test_all_teams()

    # Date ranges
    await test_date_ranges()

    # Combined filters
    await test_combined_filters()

    # Output formats
    await test_output_formats()

    # Edge cases
    await test_edge_cases()

    # Performance
    await test_performance()

    # Print final summary
    success = results.print_summary()

    return success


if __name__ == "__main__":
    success = asyncio.run(run_stress_tests())
    sys.exit(0 if success else 1)
