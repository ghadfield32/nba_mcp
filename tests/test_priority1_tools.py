"""
Comprehensive test suite for Priority 1 implementations:
- get_player_game_stats
- get_box_score
- get_clutch_stats

Tests all features, error handling, and edge cases.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.client import NBAApiClient


class TestResults:
    """Track test results"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def record_pass(self, test_name):
        self.passed += 1
        print(f"[PASS] {test_name}")

    def record_fail(self, test_name, error):
        self.failed += 1
        self.errors.append((test_name, str(error)))
        print(f"[FAIL] {test_name}: {error}")

    def summary(self):
        total = self.passed + self.failed
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"Total Tests: {total}")
        print(f"Passed: {self.passed}")
        print(f"Failed: {self.failed}")
        print(f"Success Rate: {(self.passed/total*100):.1f}%")

        if self.errors:
            print("\nFailed Tests:")
            for test_name, error in self.errors:
                print(f"  - {test_name}: {error}")

        return self.failed == 0


async def test_player_game_stats(client, results):
    """Test get_player_game_stats tool"""
    print("\n" + "=" * 80)
    print("TEST SUITE 1: get_player_game_stats()")
    print("=" * 80)

    # Test 1: Last N games
    try:
        print("\nTest 1.1: Last 5 games for LeBron James...")
        result = await client.get_player_game_log(
            player_name="LeBron James",
            season="2023-24",
            last_n_games=5
        )
        if isinstance(result, dict) and "error" in result:
            results.record_fail("Player Game Stats - Last N games", result["error"])
        elif len(result) == 5:
            results.record_pass("Player Game Stats - Last N games")
            print(f"  Retrieved {len(result)} games")
        else:
            results.record_fail("Player Game Stats - Last N games",
                              f"Expected 5 games, got {len(result)}")
    except Exception as e:
        results.record_fail("Player Game Stats - Last N games", str(e))

    # Test 2: Single game
    try:
        print("\nTest 1.2: Last game for Stephen Curry...")
        result = await client.get_player_game_log(
            player_name="Stephen Curry",
            season="2023-24",
            last_n_games=1
        )
        if isinstance(result, dict) and "error" in result:
            results.record_fail("Player Game Stats - Single game", result["error"])
        elif len(result) == 1:
            results.record_pass("Player Game Stats - Single game")
            print(f"  Game: {result.iloc[0]['MATCHUP']}, {result.iloc[0]['PTS']} PTS")
        else:
            results.record_fail("Player Game Stats - Single game",
                              f"Expected 1 game, got {len(result)}")
    except Exception as e:
        results.record_fail("Player Game Stats - Single game", str(e))

    # Test 3: Full season
    try:
        print("\nTest 1.3: Full season for Giannis...")
        result = await client.get_player_game_log(
            player_name="Giannis",
            season="2023-24"
        )
        if isinstance(result, dict) and "error" in result:
            results.record_fail("Player Game Stats - Full season", result["error"])
        elif len(result) > 50:  # Expect at least 50 games
            results.record_pass("Player Game Stats - Full season")
            avg_pts = result['PTS'].mean()
            print(f"  Retrieved {len(result)} games, {avg_pts:.1f} PPG")
        else:
            results.record_fail("Player Game Stats - Full season",
                              f"Expected >50 games, got {len(result)}")
    except Exception as e:
        results.record_fail("Player Game Stats - Full season", str(e))

    # Test 4: Invalid player
    try:
        print("\nTest 1.4: Invalid player name...")
        result = await client.get_player_game_log(
            player_name="NonexistentPlayer12345",
            season="2023-24"
        )
        if isinstance(result, dict) and "error" in result:
            results.record_pass("Player Game Stats - Invalid player error handling")
            print(f"  Correctly returned error: {result['error']}")
        else:
            results.record_fail("Player Game Stats - Invalid player error handling",
                              "Should return error for invalid player")
    except Exception as e:
        results.record_fail("Player Game Stats - Invalid player error handling", str(e))


async def test_box_score(client, results):
    """Test get_box_score tool"""
    print("\n" + "=" * 80)
    print("TEST SUITE 2: get_box_score()")
    print("=" * 80)

    # Test 1: Valid game ID
    try:
        print("\nTest 2.1: Box score with valid game ID...")
        # Using a known game ID from 2023-24 season
        result = await client.get_box_score(
            game_id="0022300500",
            as_dataframe=True
        )
        if isinstance(result, dict) and "error" in result:
            results.record_fail("Box Score - Valid game ID", result["error"])
        elif "player_stats" in result and not result["player_stats"].empty:
            results.record_pass("Box Score - Valid game ID")
            player_count = len(result["player_stats"])
            team_count = len(result["team_stats"]) if "team_stats" in result else 0
            print(f"  Retrieved {player_count} player stats, {team_count} team stats")

            # Check for quarter scores
            if "line_score" in result and not result["line_score"].empty:
                print(f"  Quarter breakdown available: {len(result['line_score'])} teams")
        else:
            results.record_fail("Box Score - Valid game ID", "No player stats returned")
    except Exception as e:
        results.record_fail("Box Score - Valid game ID", str(e))

    # Test 2: Invalid game ID
    try:
        print("\nTest 2.2: Box score with invalid game ID...")
        result = await client.get_box_score(
            game_id="0000000000",
            as_dataframe=True
        )
        if isinstance(result, dict) and "error" in result:
            results.record_pass("Box Score - Invalid game ID error handling")
            print(f"  Correctly returned error")
        else:
            results.record_fail("Box Score - Invalid game ID error handling",
                              "Should return error for invalid game ID")
    except Exception as e:
        # Expected to fail, that's good
        results.record_pass("Box Score - Invalid game ID error handling")
        print(f"  Correctly raised exception for invalid game")

    # Test 3: Check data completeness
    try:
        print("\nTest 2.3: Box score data completeness...")
        result = await client.get_box_score(
            game_id="0022300500",
            as_dataframe=True
        )

        if isinstance(result, dict) and "error" not in result:
            player_stats = result.get("player_stats")

            # Check required columns
            required_cols = ["PLAYER_NAME", "MIN", "PTS", "REB", "AST", "FG_PCT"]
            has_all_cols = all(col in player_stats.columns for col in required_cols)

            if has_all_cols:
                results.record_pass("Box Score - Data completeness")
                print(f"  All required columns present")
            else:
                missing = [col for col in required_cols if col not in player_stats.columns]
                results.record_fail("Box Score - Data completeness",
                                  f"Missing columns: {missing}")
        else:
            results.record_fail("Box Score - Data completeness", "No data returned")
    except Exception as e:
        results.record_fail("Box Score - Data completeness", str(e))


async def test_clutch_stats(client, results):
    """Test get_clutch_stats tool"""
    print("\n" + "=" * 80)
    print("TEST SUITE 3: get_clutch_stats()")
    print("=" * 80)

    # Test 1: Player clutch stats
    try:
        print("\nTest 3.1: Player clutch stats - LeBron James...")
        result = await client.get_clutch_stats(
            entity_name="LeBron James",
            entity_type="player",
            season="2023-24",
            per_mode="PerGame"
        )
        if isinstance(result, dict) and "error" in result:
            results.record_fail("Clutch Stats - Player", result["error"])
        elif not result.empty:
            results.record_pass("Clutch Stats - Player")
            row = result.iloc[0]
            pts = row.get("PTS", 0)
            games = row.get("GP", 0)
            print(f"  Games: {games}, Points: {pts:.1f} per game in clutch")
        else:
            results.record_fail("Clutch Stats - Player", "Empty result")
    except Exception as e:
        results.record_fail("Clutch Stats - Player", str(e))

    # Test 2: Team clutch stats
    try:
        print("\nTest 3.2: Team clutch stats - Lakers...")
        result = await client.get_clutch_stats(
            entity_name="Lakers",
            entity_type="team",
            season="2023-24",
            per_mode="PerGame"
        )
        if isinstance(result, dict) and "error" in result:
            results.record_fail("Clutch Stats - Team", result["error"])
        elif not result.empty:
            results.record_pass("Clutch Stats - Team")
            row = result.iloc[0]
            wins = row.get("W", 0)
            losses = row.get("L", 0)
            print(f"  Clutch record: {wins}W-{losses}L")
        else:
            results.record_fail("Clutch Stats - Team", "Empty result")
    except Exception as e:
        results.record_fail("Clutch Stats - Team", str(e))

    # Test 3: Different per_mode
    try:
        print("\nTest 3.3: Clutch stats with Totals mode...")
        result = await client.get_clutch_stats(
            entity_name="Stephen Curry",
            entity_type="player",
            season="2023-24",
            per_mode="Totals"
        )
        if isinstance(result, dict) and "error" in result:
            results.record_fail("Clutch Stats - Totals mode", result["error"])
        elif not result.empty:
            results.record_pass("Clutch Stats - Totals mode")
            row = result.iloc[0]
            pts = row.get("PTS", 0)
            print(f"  Total clutch points: {pts:.0f}")
        else:
            results.record_fail("Clutch Stats - Totals mode", "Empty result")
    except Exception as e:
        results.record_fail("Clutch Stats - Totals mode", str(e))

    # Test 4: Invalid entity
    try:
        print("\nTest 3.4: Invalid entity name...")
        result = await client.get_clutch_stats(
            entity_name="NonexistentPlayer12345",
            entity_type="player",
            season="2023-24"
        )
        if isinstance(result, dict) and "error" in result:
            results.record_pass("Clutch Stats - Invalid entity error handling")
            print(f"  Correctly returned error")
        else:
            results.record_fail("Clutch Stats - Invalid entity error handling",
                              "Should return error for invalid entity")
    except Exception as e:
        results.record_fail("Clutch Stats - Invalid entity error handling", str(e))

    # Test 5: Data completeness
    try:
        print("\nTest 3.5: Clutch stats data completeness...")
        # Use a different player to avoid duplicate API calls
        result = await client.get_clutch_stats(
            entity_name="Damian Lillard",
            entity_type="player",
            season="2023-24"
        )

        if isinstance(result, dict) and "error" not in result and not result.empty:
            row = result.iloc[0]

            # Check required columns
            required_cols = ["GP", "W", "L", "PTS", "FG_PCT", "AST", "REB"]
            has_all_cols = all(col in result.columns for col in required_cols)

            if has_all_cols:
                results.record_pass("Clutch Stats - Data completeness")
                print(f"  All required columns present")
            else:
                missing = [col for col in required_cols if col not in result.columns]
                results.record_fail("Clutch Stats - Data completeness",
                                  f"Missing columns: {missing}")
        else:
            results.record_fail("Clutch Stats - Data completeness", "No data returned")
    except Exception as e:
        results.record_fail("Clutch Stats - Data completeness", str(e))


async def test_integration(client, results):
    """Test integration between tools"""
    print("\n" + "=" * 80)
    print("TEST SUITE 4: Integration Tests")
    print("=" * 80)

    # Test 1: Get player game stats, then use game ID for box score
    try:
        print("\nTest 4.1: Integration - Player games to box score...")

        # Get recent games for LeBron
        games = await client.get_player_game_log(
            player_name="LeBron James",
            season="2023-24",
            last_n_games=1
        )

        if not isinstance(games, dict) and not games.empty:
            # Extract game ID from the GAME_ID column
            game_id = games.iloc[0]["Game_ID"]

            # Get box score for that game
            box_score = await client.get_box_score(
                game_id=game_id,
                as_dataframe=True
            )

            if isinstance(box_score, dict) and "error" not in box_score:
                results.record_pass("Integration - Player games to box score")
                print(f"  Successfully linked game {game_id} to box score")
            else:
                results.record_fail("Integration - Player games to box score",
                                  "Could not get box score")
        else:
            results.record_fail("Integration - Player games to box score",
                              "Could not get player games")
    except Exception as e:
        results.record_fail("Integration - Player games to box score", str(e))

    # Test 2: Compare player game stats with clutch stats
    try:
        print("\nTest 4.2: Integration - Game stats vs clutch stats...")

        # Get full season stats
        games = await client.get_player_game_log(
            player_name="Stephen Curry",
            season="2023-24"
        )

        # Get clutch stats
        clutch = await client.get_clutch_stats(
            entity_name="Stephen Curry",
            entity_type="player",
            season="2023-24"
        )

        if not isinstance(games, dict) and not isinstance(clutch, dict):
            if not games.empty and not clutch.empty:
                regular_ppg = games["PTS"].mean()
                clutch_ppg = clutch.iloc[0]["PTS"]

                results.record_pass("Integration - Game stats vs clutch stats")
                print(f"  Regular PPG: {regular_ppg:.1f}, Clutch PPG: {clutch_ppg:.1f}")
            else:
                results.record_fail("Integration - Game stats vs clutch stats",
                                  "Empty data")
        else:
            results.record_fail("Integration - Game stats vs clutch stats",
                              "Data retrieval failed")
    except Exception as e:
        results.record_fail("Integration - Game stats vs clutch stats", str(e))


async def run_all_tests():
    """Run all test suites"""
    print("=" * 80)
    print("PRIORITY 1 TOOLS - COMPREHENSIVE TEST SUITE")
    print("=" * 80)
    print("\nTesting:")
    print("1. get_player_game_stats()")
    print("2. get_box_score()")
    print("3. get_clutch_stats()")
    print("4. Integration tests")

    client = NBAApiClient()
    results = TestResults()

    # Run all test suites
    await test_player_game_stats(client, results)
    await test_box_score(client, results)
    await test_clutch_stats(client, results)
    await test_integration(client, results)

    # Print summary
    success = results.summary()

    return success


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
