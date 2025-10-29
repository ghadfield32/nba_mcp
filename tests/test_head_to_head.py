"""
Test the new get_player_head_to_head tool
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.client import NBAApiClient


async def test_head_to_head():
    """Test head-to-head functionality"""
    print("=" * 80)
    print("TESTING: get_player_head_to_head()")
    print("=" * 80)

    client = NBAApiClient()

    # Test 1: LeBron vs Durant (known rivalry)
    print("\nTest 1: LeBron James vs Kevin Durant (2023-24)...")
    try:
        result = await client.get_player_head_to_head(
            player1_name="LeBron James",
            player2_name="Kevin Durant",
            season="2023-24"
        )

        if isinstance(result, dict) and "error" in result:
            print(f"  [INFO] {result['error']}")
            if result.get("matchup_count", 0) == 0:
                print("  [NOTE] No matchups found - players may not have faced each other")
        else:
            print(f"  [SUCCESS] Found {result['matchup_count']} matchups")
            print(f"  Player 1 Record: {result['player1_record']}")
            print(f"  Player 2 Record: {result['player2_record']}")

            # Show average stats
            p1_stats = result["player1_stats"]
            p2_stats = result["player2_stats"]

            print(f"\n  {p1_stats.iloc[0]['PLAYER_NAME']} averages:")
            print(f"    PPG: {p1_stats['PTS'].mean():.1f}")
            print(f"    RPG: {p1_stats['REB'].mean():.1f}")
            print(f"    APG: {p1_stats['AST'].mean():.1f}")

            print(f"\n  {p2_stats.iloc[0]['PLAYER_NAME']} averages:")
            print(f"    PPG: {p2_stats['PTS'].mean():.1f}")
            print(f"    RPG: {p2_stats['REB'].mean():.1f}")
            print(f"    APG: {p2_stats['AST'].mean():.1f}")

    except Exception as e:
        print(f"  [ERROR] {str(e)}")
        return False

    # Test 2: Giannis vs Embiid
    print("\nTest 2: Giannis Antetokounmpo vs Joel Embiid (2023-24)...")
    try:
        result = await client.get_player_head_to_head(
            player1_name="Giannis",
            player2_name="Embiid",
            season="2023-24"
        )

        if isinstance(result, dict) and "error" in result:
            print(f"  [INFO] {result['error']}")
            if result.get("matchup_count", 0) == 0:
                print("  [NOTE] No matchups found - players may not have faced each other")
        else:
            print(f"  [SUCCESS] Found {result['matchup_count']} matchups")
            print(f"  Player 1 Record: {result['player1_record']}")
            print(f"  Player 2 Record: {result['player2_record']}")

    except Exception as e:
        print(f"  [ERROR] {str(e)}")
        return False

    # Test 3: Invalid player
    print("\nTest 3: Invalid player name...")
    try:
        result = await client.get_player_head_to_head(
            player1_name="NonexistentPlayer123",
            player2_name="LeBron James",
            season="2023-24"
        )

        if isinstance(result, dict) and "error" in result:
            print(f"  [SUCCESS] Correctly returned error: {result['error']}")
        else:
            print(f"  [FAIL] Should have returned error for invalid player")
            return False

    except Exception as e:
        print(f"  [SUCCESS] Correctly raised exception: {str(e)}")

    print("\n" + "=" * 80)
    print("ALL TESTS COMPLETED")
    print("=" * 80)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_head_to_head())
    sys.exit(0 if success else 1)
