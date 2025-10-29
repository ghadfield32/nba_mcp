"""
Test script for extended NBA Awards (All-NBA, All-Defensive, All-Rookie teams).
Tests the 7 new team selection award types.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.client import NBAApiClient
import nba_mcp.nba_server as server


def safe_print(text):
    """Print with ASCII fallback for Windows console"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'replace').decode('ascii'))


async def test_extended_awards():
    """Test all extended award types (team selections)"""
    print("=" * 80)
    print("TESTING EXTENDED NBA AWARDS (TEAM SELECTIONS)")
    print("=" * 80)

    client = NBAApiClient()
    test_count = 0
    passed = 0

    # Test team selection award types
    team_selections = [
        ("all_nba_first", "All-NBA First Team"),
        ("all_nba_second", "All-NBA Second Team"),
        ("all_nba_third", "All-NBA Third Team"),
        ("all_defensive_first", "All-Defensive First Team"),
        ("all_defensive_second", "All-Defensive Second Team"),
        ("all_rookie_first", "All-Rookie First Team"),
        ("all_rookie_second", "All-Rookie Second Team")
    ]

    # ═══════════════════════════════════════════════════════════════════════════════
    # PART 1: Test Data Loading
    # ═══════════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("PART 1: DATA LOADING TEST")
    print("=" * 80)

    test_count += 1
    print(f"\n[Test {test_count}] Load extended awards data...")
    try:
        awards_data = client.load_historical_awards()

        # Check all new award types exist
        for award_type, _ in team_selections:
            assert award_type in awards_data, f"Missing award type: {award_type}"

        print(f"[PASS] All 7 team selection award types loaded")
        print(f"  Total award types: {len([k for k in awards_data.keys() if k != 'metadata'])}")

        # Check data structure
        first_team = awards_data['all_nba_first'][0]
        assert 'players' in first_team, "Missing 'players' array"
        assert len(first_team['players']) == 5, "Should have 5 players per team"
        print(f"  Data structure validated: 5 players per team selection")

        passed += 1
    except Exception as e:
        print(f"[FAIL] {e}")

    # ═══════════════════════════════════════════════════════════════════════════════
    # PART 2: Test Each Award Type via Client
    # ═══════════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("PART 2: CLIENT METHOD TESTS")
    print("=" * 80)

    for award_type, award_name in team_selections:
        test_count += 1
        print(f"\n[Test {test_count}] Get {award_name} via client...")
        try:
            winners = client.get_award_winners(award_type, last_n=1)
            assert len(winners) == 1, f"Expected 1 selection, got {len(winners)}"

            # Verify structure
            latest = winners[0]
            assert 'season' in latest, "Missing season"
            assert 'players' in latest, "Missing players array"
            assert len(latest['players']) == 5, f"Expected 5 players, got {len(latest['players'])}"

            season = latest['season']
            player_names = [p['player_name'] for p in latest['players']]

            print(f"[PASS] {award_name} ({season}):")
            for i, player in enumerate(latest['players'][:3], 1):
                name = player['player_name']
                team = player['team']
                safe_print(f"  {i}. {name} ({team})")
            print(f"  ... and 2 more players")

            passed += 1
        except Exception as e:
            print(f"[FAIL] {e}")

    # ═══════════════════════════════════════════════════════════════════════════════
    # PART 3: Test Each Award Type via MCP Tool
    # ═══════════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("PART 3: MCP TOOL TESTS")
    print("=" * 80)

    for award_type, award_name in team_selections:
        test_count += 1
        print(f"\n[Test {test_count}] Get {award_name} via MCP tool...")
        try:
            result = await server.get_nba_awards(award_type=award_type, last_n=1)

            # Verify output contains expected content
            assert award_name in result, f"Award name missing from output"
            assert "2023-24" in result or "2022-23" in result, "Recent season missing"

            # Count players mentioned (should be 5)
            # Each player line starts with a number followed by a dot
            player_lines = [line for line in result.split('\n') if line.strip() and line.strip()[0].isdigit()]

            print(f"[PASS] {award_name} retrieved via MCP tool")
            print(f"  Players listed: {len(player_lines)}")

            # Show first few lines
            lines = result.split('\n')
            for line in lines[:8]:
                if line.strip():
                    safe_print(f"  {line}")

            passed += 1
        except Exception as e:
            print(f"[FAIL] {e}")

    # ═══════════════════════════════════════════════════════════════════════════════
    # PART 4: Specific Test Cases
    # ═══════════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("PART 4: SPECIFIC TEST CASES")
    print("=" * 80)

    # Test 4.1: Get 2023-24 All-NBA First Team
    test_count += 1
    print(f"\n[Test {test_count}] Get 2023-24 All-NBA First Team...")
    try:
        result = await server.get_nba_awards(award_type="all_nba_first", season="2023-24")

        # Known players on 2023-24 All-NBA First Team
        expected_players = ["Gilgeous-Alexander", "Dončić", "Antetokounmpo", "Tatum", "Jokić"]

        found = 0
        for player in expected_players:
            if player in result:
                found += 1

        assert found >= 3, f"Expected at least 3 known players, found {found}"

        print(f"[PASS] 2023-24 All-NBA First Team retrieved")
        print(f"  Known players found: {found}/{len(expected_players)}")
        safe_print(result[:300])

        passed += 1
    except Exception as e:
        print(f"[FAIL] {e}")

    # Test 4.2: Get All-Defensive teams from last 2 seasons
    test_count += 1
    print(f"\n[Test {test_count}] Get All-Defensive First Team (last 2)...")
    try:
        result = await server.get_nba_awards(award_type="all_defensive_first", last_n=2)

        assert "2023-24" in result, "2023-24 season missing"
        assert "2022-23" in result, "2022-23 season missing"

        # Count seasons (should be 2)
        season_count = result.count("2023-24") + result.count("2022-23")

        print(f"[PASS] Last 2 All-Defensive First Team selections retrieved")
        print(f"  Seasons found: {season_count}")

        passed += 1
    except Exception as e:
        print(f"[FAIL] {e}")

    # Test 4.3: Get All-Rookie First Team (Wembanyama should be there)
    test_count += 1
    print(f"\n[Test {test_count}] Get 2023-24 All-Rookie First Team (Wembanyama)...")
    try:
        result = await server.get_nba_awards(award_type="all_rookie_first", season="2023-24")

        assert "Wembanyama" in result, "Wembanyama not found"
        assert "Holmgren" in result, "Chet Holmgren not found"

        print(f"[PASS] 2023-24 All-Rookie First Team retrieved")
        print(f"  Confirmed: Wembanyama and Holmgren present")

        passed += 1
    except Exception as e:
        print(f"[FAIL] {e}")

    # Test 4.4: JSON format for team selections
    test_count += 1
    print(f"\n[Test {test_count}] Test JSON format for team selections...")
    try:
        result = await server.get_nba_awards(award_type="all_nba_second", last_n=1, format="json")

        import json
        data = json.loads(result)

        assert isinstance(data, list), "Expected JSON list"
        assert len(data) == 1, f"Expected 1 selection, got {len(data)}"
        assert 'players' in data[0], "Missing players array in JSON"
        assert len(data[0]['players']) == 5, "Expected 5 players"

        print(f"[PASS] JSON format working for team selections")
        print(f"  Season: {data[0]['season']}")
        print(f"  Players: {len(data[0]['players'])}")

        passed += 1
    except Exception as e:
        print(f"[FAIL] {e}")

    # Test 4.5: Verify usage help includes new awards
    test_count += 1
    print(f"\n[Test {test_count}] Test usage help includes new award types...")
    try:
        result = await server.get_nba_awards()

        assert "all_nba_first" in result, "all_nba_first missing from help"
        assert "all_defensive_first" in result, "all_defensive_first missing from help"
        assert "all_rookie_first" in result, "all_rookie_first missing from help"
        assert "Team Selections" in result, "Team Selections section missing"

        print(f"[PASS] Usage help includes all new award types")
        print(f"  Help text length: {len(result)} characters")

        passed += 1
    except Exception as e:
        print(f"[FAIL] {e}")

    # ═══════════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total Tests: {test_count}")
    print(f"Passed: {passed}")
    print(f"Failed: {test_count - passed}")
    print(f"Success Rate: {(passed/test_count)*100:.1f}%")

    if passed == test_count:
        print("\n[SUCCESS] ALL EXTENDED AWARDS TESTS PASSED!")
        print("\nNew Award Types Working:")
        for award_type, award_name in team_selections:
            print(f"  [OK] {award_name}")
        return True
    else:
        print(f"\n[PARTIAL] {test_count - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_extended_awards())
    sys.exit(0 if success else 1)
