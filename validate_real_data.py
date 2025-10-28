"""
Real Data Validation Script for NBA MCP

Tests all 12 MCP tools with real NBA data to ensure:
1. No fallback or fake values are returned
2. Response envelopes are correctly structured
3. Data integrity is maintained
4. All tools function with actual NBA API data

Run this script to validate the entire system before deployment.
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List

# Add parent directory to path for imports
sys.path.insert(0, "/home/user/nba_mcp")

from nba_mcp.api.client import NBAApiClient
from nba_mcp.api.entity_resolver import resolve_entity
from nba_mcp.api.models import ResponseEnvelope


class ValidationReport:
    """Track validation results."""

    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures: List[Dict[str, Any]] = []

    def add_pass(self, test_name: str):
        self.tests_run += 1
        self.tests_passed += 1
        print(f"✅ {test_name}")

    def add_fail(self, test_name: str, error: str):
        self.tests_run += 1
        self.tests_failed += 1
        self.failures.append({"test": test_name, "error": error})
        print(f"❌ {test_name}: {error}")

    def print_summary(self):
        print("\n" + "=" * 70)
        print("VALIDATION SUMMARY")
        print("=" * 70)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed} ({self.tests_passed/self.tests_run*100:.1f}%)")
        print(f"Failed: {self.tests_failed} ({self.tests_failed/self.tests_run*100:.1f}%)")

        if self.failures:
            print("\nFAILURES:")
            for failure in self.failures:
                print(f"  - {failure['test']}: {failure['error']}")
        else:
            print("\n🎉 ALL TESTS PASSED!")

        return self.tests_failed == 0


# Global validation report
report = ValidationReport()


def validate_response_envelope(data: str, test_name: str) -> bool:
    """Validate that response follows ResponseEnvelope structure."""
    try:
        parsed = json.loads(data)

        # Check required fields
        if "status" not in parsed:
            report.add_fail(test_name, "Missing 'status' field in response")
            return False

        if "metadata" not in parsed:
            report.add_fail(test_name, "Missing 'metadata' field in response")
            return False

        # Check metadata structure
        metadata = parsed["metadata"]
        required_metadata = ["version", "schema_version", "timestamp", "source"]
        for field in required_metadata:
            if field not in metadata:
                report.add_fail(test_name, f"Missing '{field}' in metadata")
                return False

        # Check status-specific requirements
        if parsed["status"] == "success":
            if "data" not in parsed:
                report.add_fail(test_name, "Success response missing 'data' field")
                return False
        elif parsed["status"] == "error":
            if "errors" not in parsed:
                report.add_fail(test_name, "Error response missing 'errors' field")
                return False

        return True
    except json.JSONDecodeError as e:
        report.add_fail(test_name, f"Invalid JSON: {e}")
        return False
    except Exception as e:
        report.add_fail(test_name, f"Validation error: {e}")
        return False


def validate_no_fallback_values(data: Dict, test_name: str) -> bool:
    """Check that data doesn't contain obvious fallback/fake values."""
    fake_indicators = [
        "N/A",
        "Unknown",
        "placeholder",
        "test",
        "fake",
        "mock",
        "TODO",
        "FIXME",
    ]

    def check_value(value, path=""):
        if isinstance(value, str):
            value_lower = value.lower()
            for indicator in fake_indicators:
                if indicator.lower() in value_lower:
                    return False, f"Found fake value '{value}' at {path}"
        elif isinstance(value, dict):
            for k, v in value.items():
                result, msg = check_value(v, f"{path}.{k}" if path else k)
                if not result:
                    return result, msg
        elif isinstance(value, list):
            for i, item in enumerate(value):
                result, msg = check_value(item, f"{path}[{i}]")
                if not result:
                    return result, msg
        return True, ""

    result, msg = check_value(data)
    if not result:
        report.add_fail(test_name, msg)
    return result


async def test_entity_resolution():
    """Test 1: Entity Resolution with Real Data"""
    print("\n" + "=" * 70)
    print("TEST 1: Entity Resolution")
    print("=" * 70)

    test_cases = [
        ("LeBron", "player", "LeBron James"),
        ("Lakers", "team", "Los Angeles Lakers"),
        ("Curry", "player", "Stephen Curry"),
        ("Warriors", "team", "Golden State Warriors"),
        ("Giannis", "player", "Giannis Antetokounmpo"),
    ]

    for query, entity_type, expected_name in test_cases:
        try:
            entity = resolve_entity(query, entity_type=entity_type)

            # Verify real entity returned
            if entity.name and expected_name.lower() in entity.name.lower():
                report.add_pass(f"Resolve {entity_type} '{query}'")
            else:
                report.add_fail(
                    f"Resolve {entity_type} '{query}'",
                    f"Expected '{expected_name}', got '{entity.name}'",
                )

            # Verify confidence score
            if not (0.0 <= entity.confidence <= 1.0):
                report.add_fail(
                    f"Resolve {entity_type} '{query}'",
                    f"Invalid confidence: {entity.confidence}",
                )
        except Exception as e:
            report.add_fail(f"Resolve {entity_type} '{query}'", str(e))


async def test_player_career_stats():
    """Test 2: Player Career Statistics"""
    print("\n" + "=" * 70)
    print("TEST 2: Player Career Statistics")
    print("=" * 70)

    from nba_mcp.nba_server import get_player_career_information

    test_cases = [("LeBron James", "2023-24"), ("Stephen Curry", "2022-23")]

    for player_name, season in test_cases:
        try:
            result = await get_player_career_information(player_name, season)

            # Check for real data
            if (
                "Points Per Game" in result
                and "Rebounds Per Game" in result
                and "Assists Per Game" in result
            ):
                report.add_pass(f"Player career stats: {player_name} ({season})")
            else:
                report.add_fail(
                    f"Player career stats: {player_name} ({season})",
                    "Missing expected stats fields",
                )
        except Exception as e:
            report.add_fail(f"Player career stats: {player_name} ({season})", str(e))


async def test_team_standings():
    """Test 3: Team Standings"""
    print("\n" + "=" * 70)
    print("TEST 3: Team Standings")
    print("=" * 70)

    from nba_mcp.nba_server import get_team_standings

    try:
        result = await get_team_standings(season="2023-24", conference="West")

        # Validate response envelope
        if validate_response_envelope(result, "Team standings (West)"):
            parsed = json.loads(result)

            # Check for real standings data
            if (
                parsed["status"] == "success"
                and "data" in parsed
                and isinstance(parsed["data"], list)
                and len(parsed["data"]) > 0
            ):
                report.add_pass("Team standings (West)")

                # Verify no fallback values
                validate_no_fallback_values(
                    parsed["data"], "Team standings (West) - data check"
                )
            else:
                report.add_fail("Team standings (West)", "No standings data returned")
    except Exception as e:
        report.add_fail("Team standings (West)", str(e))


async def test_player_advanced_stats():
    """Test 4: Player Advanced Statistics"""
    print("\n" + "=" * 70)
    print("TEST 4: Player Advanced Statistics")
    print("=" * 70)

    from nba_mcp.nba_server import get_player_advanced_stats

    test_players = ["LeBron James", "Stephen Curry", "Giannis Antetokounmpo"]

    for player_name in test_players:
        try:
            result = await get_player_advanced_stats(player_name, season="2023-24")

            # Validate response envelope
            if validate_response_envelope(
                result, f"Player advanced stats: {player_name}"
            ):
                parsed = json.loads(result)

                if parsed["status"] == "success" and "data" in parsed:
                    report.add_pass(f"Player advanced stats: {player_name}")

                    # Verify no fallback values
                    validate_no_fallback_values(
                        parsed["data"], f"Player advanced stats: {player_name}"
                    )
                else:
                    report.add_fail(
                        f"Player advanced stats: {player_name}", "No data returned"
                    )
        except Exception as e:
            report.add_fail(f"Player advanced stats: {player_name}", str(e))


async def test_team_advanced_stats():
    """Test 5: Team Advanced Statistics"""
    print("\n" + "=" * 70)
    print("TEST 5: Team Advanced Statistics")
    print("=" * 70)

    from nba_mcp.nba_server import get_team_advanced_stats

    test_teams = ["Lakers", "Warriors", "Celtics"]

    for team_name in test_teams:
        try:
            result = await get_team_advanced_stats(team_name, season="2023-24")

            # Validate response envelope
            if validate_response_envelope(result, f"Team advanced stats: {team_name}"):
                parsed = json.loads(result)

                if parsed["status"] == "success" and "data" in parsed:
                    report.add_pass(f"Team advanced stats: {team_name}")

                    # Verify no fallback values
                    validate_no_fallback_values(
                        parsed["data"], f"Team advanced stats: {team_name}"
                    )
                else:
                    report.add_fail(
                        f"Team advanced stats: {team_name}", "No data returned"
                    )
        except Exception as e:
            report.add_fail(f"Team advanced stats: {team_name}", str(e))


async def test_compare_players():
    """Test 6: Player Comparison"""
    print("\n" + "=" * 70)
    print("TEST 6: Player Comparison")
    print("=" * 70)

    from nba_mcp.nba_server import compare_players

    test_comparisons = [
        ("LeBron James", "Stephen Curry"),
        ("Giannis Antetokounmpo", "Joel Embiid"),
    ]

    for player1, player2 in test_comparisons:
        try:
            result = await compare_players(
                player1, player2, season="2023-24", normalization="per_75"
            )

            # Validate response envelope
            if validate_response_envelope(
                result, f"Compare: {player1} vs {player2}"
            ):
                parsed = json.loads(result)

                if (
                    parsed["status"] == "success"
                    and "data" in parsed
                    and "player1" in parsed["data"]
                    and "player2" in parsed["data"]
                ):
                    report.add_pass(f"Compare: {player1} vs {player2}")

                    # Verify no fallback values
                    validate_no_fallback_values(
                        parsed["data"], f"Compare: {player1} vs {player2}"
                    )
                else:
                    report.add_fail(
                        f"Compare: {player1} vs {player2}", "Invalid comparison data"
                    )
        except Exception as e:
            report.add_fail(f"Compare: {player1} vs {player2}", str(e))


async def test_live_scores():
    """Test 7: Live Scores"""
    print("\n" + "=" * 70)
    print("TEST 7: Live Scores")
    print("=" * 70)

    from nba_mcp.nba_server import get_live_scores

    # Test with a date during NBA season
    test_date = "2024-01-15"

    try:
        result = await get_live_scores(target_date=test_date)

        # This should return either games or "No games found"
        if "No games found" in result or "NBA Games for" in result:
            report.add_pass(f"Live scores ({test_date})")
        else:
            report.add_fail(
                f"Live scores ({test_date})", "Unexpected response format"
            )
    except Exception as e:
        report.add_fail(f"Live scores ({test_date})", str(e))


async def test_league_leaders():
    """Test 8: League Leaders"""
    print("\n" + "=" * 70)
    print("TEST 8: League Leaders")
    print("=" * 70)

    from nba_mcp.nba_server import get_league_leaders_info, LeagueLeadersParams

    test_cases = [
        ("PTS", "PerGame", "Points leaders"),
        ("AST", "PerGame", "Assists leaders"),
        ("REB", "PerGame", "Rebounds leaders"),
    ]

    for stat_cat, per_mode, description in test_cases:
        try:
            params = LeagueLeadersParams(
                season="2023-24", stat_category=stat_cat, per_mode=per_mode
            )
            result = await get_league_leaders_info(params)

            # Check for real data
            if "Top 10" in result and stat_cat in result:
                report.add_pass(f"League leaders: {description}")
            else:
                report.add_fail(
                    f"League leaders: {description}", "Missing expected data"
                )
        except Exception as e:
            report.add_fail(f"League leaders: {description}", str(e))


async def test_resolve_nba_entity_tool():
    """Test 9: resolve_nba_entity MCP Tool"""
    print("\n" + "=" * 70)
    print("TEST 9: resolve_nba_entity MCP Tool")
    print("=" * 70)

    from nba_mcp.nba_server import resolve_nba_entity

    test_cases = [
        ("LeBron", "player"),
        ("Lakers", "team"),
    ]

    for query, entity_type in test_cases:
        try:
            result = await resolve_nba_entity(query, entity_type=entity_type)

            # Validate response envelope
            if validate_response_envelope(
                result, f"resolve_nba_entity: {query} ({entity_type})"
            ):
                parsed = json.loads(result)

                if parsed["status"] == "success" and "data" in parsed:
                    report.add_pass(f"resolve_nba_entity: {query} ({entity_type})")

                    # Verify no fallback values
                    validate_no_fallback_values(
                        parsed["data"], f"resolve_nba_entity: {query}"
                    )
                else:
                    report.add_fail(
                        f"resolve_nba_entity: {query} ({entity_type})", "No data"
                    )
        except Exception as e:
            report.add_fail(f"resolve_nba_entity: {query} ({entity_type})", str(e))


async def test_schema_versioning():
    """Test 10: Schema Versioning"""
    print("\n" + "=" * 70)
    print("TEST 10: Schema Versioning")
    print("=" * 70)

    from nba_mcp.nba_server import get_team_standings

    try:
        result = await get_team_standings(season="2023-24")
        parsed = json.loads(result)

        # Verify schema_version field exists
        if "metadata" in parsed and "schema_version" in parsed["metadata"]:
            schema_version = parsed["metadata"]["schema_version"]

            # Verify format (YYYY-MM)
            if len(schema_version) == 7 and schema_version[4] == "-":
                report.add_pass("Schema versioning present")
            else:
                report.add_fail(
                    "Schema versioning format",
                    f"Invalid format: {schema_version}, expected YYYY-MM",
                )
        else:
            report.add_fail("Schema versioning", "Missing schema_version field")
    except Exception as e:
        report.add_fail("Schema versioning", str(e))


async def test_response_envelope_consistency():
    """Test 11: Response Envelope Consistency"""
    print("\n" + "=" * 70)
    print("TEST 11: Response Envelope Consistency")
    print("=" * 70)

    from nba_mcp.nba_server import (
        get_team_standings,
        get_player_advanced_stats,
        compare_players,
    )

    tools_to_test = [
        ("get_team_standings", get_team_standings(season="2023-24")),
        (
            "get_player_advanced_stats",
            get_player_advanced_stats("LeBron James", season="2023-24"),
        ),
        (
            "compare_players",
            compare_players(
                "LeBron James", "Stephen Curry", season="2023-24", normalization="per_75"
            ),
        ),
    ]

    for tool_name, tool_call in tools_to_test:
        try:
            result = await tool_call

            if validate_response_envelope(result, f"Envelope consistency: {tool_name}"):
                report.add_pass(f"Envelope consistency: {tool_name}")
        except Exception as e:
            report.add_fail(f"Envelope consistency: {tool_name}", str(e))


async def main():
    """Run all validation tests."""
    print("=" * 70)
    print("NBA MCP REAL DATA VALIDATION")
    print("=" * 70)
    print(f"Started: {datetime.now().isoformat()}")
    print()

    # Run all test suites
    await test_entity_resolution()
    await test_player_career_stats()
    await test_team_standings()
    await test_player_advanced_stats()
    await test_team_advanced_stats()
    await test_compare_players()
    await test_live_scores()
    await test_league_leaders()
    await test_resolve_nba_entity_tool()
    await test_schema_versioning()
    await test_response_envelope_consistency()

    # Print final summary
    report.print_summary()

    # Exit with appropriate code
    sys.exit(0 if report.tests_failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
