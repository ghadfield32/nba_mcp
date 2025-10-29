"""
Test for get_player_game_stats tool implementation.
Tests the critical gap fix for individual game statistics.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.client import NBAApiClient


async def test_player_game_stats():
    """Test get_player_game_log client method."""
    client = NBAApiClient()

    print("=" * 80)
    print("TEST 1: Get LeBron James' last 5 games")
    print("=" * 80)

    result = await client.get_player_game_log(
        player_name="LeBron James",
        season="2023-24",
        last_n_games=5
    )

    if isinstance(result, dict) and "error" in result:
        print(f"[FAIL] ERROR: {result['error']}")
        return False
    else:
        print(f"[PASS] SUCCESS: Retrieved {len(result)} games")
        print(f"\nColumns: {list(result.columns)[:10]}...")  # Show first 10 columns
        if len(result) > 0:
            first_game = result.iloc[0]
            print(f"\nMost Recent Game:")
            print(f"  Date: {first_game.get('GAME_DATE')}")
            print(f"  Matchup: {first_game.get('MATCHUP')}")
            print(f"  Points: {first_game.get('PTS')}")
            print(f"  Rebounds: {first_game.get('REB')}")
            print(f"  Assists: {first_game.get('AST')}")

    print("\n" + "=" * 80)
    print("TEST 2: Get Stephen Curry's last game")
    print("=" * 80)

    result2 = await client.get_player_game_log(
        player_name="Stephen Curry",
        season="2023-24",
        last_n_games=1
    )

    if isinstance(result2, dict) and "error" in result2:
        print(f"[FAIL] ERROR: {result2['error']}")
        return False
    else:
        print(f"[PASS] SUCCESS: Retrieved {len(result2)} game")
        if len(result2) > 0:
            game = result2.iloc[0]
            print(f"\nLast Game:")
            print(f"  Date: {game.get('GAME_DATE')}")
            print(f"  Matchup: {game.get('MATCHUP')}")
            print(f"  W/L: {game.get('WL')}")
            print(f"  Stats: {game.get('PTS')} PTS, {game.get('REB')} REB, {game.get('AST')} AST")

    print("\n" + "=" * 80)
    print("TEST 3: Get full season game log")
    print("=" * 80)

    result3 = await client.get_player_game_log(
        player_name="Giannis",
        season="2023-24"
    )

    if isinstance(result3, dict) and "error" in result3:
        print(f"[FAIL] ERROR: {result3['error']}")
        return False
    else:
        print(f"[PASS] SUCCESS: Retrieved {len(result3)} games for full season")
        avg_pts = result3['PTS'].mean() if len(result3) > 0 else 0
        print(f"  Season Average: {avg_pts:.1f} PPG")

    print("\n" + "=" * 80)
    print("ALL TESTS PASSED [SUCCESS]")
    print("=" * 80)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_player_game_stats())
    sys.exit(0 if success else 1)
