"""
Test the new fetch_player_games functionality

Tests the comprehensive filtering exposed via the new MCP tool.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.data_groupings import fetch_grouping


async def test_basic_fetch():
    """Test basic player game fetch"""
    print("\n" + "="*80)
    print("TEST 1: Basic Fetch - LeBron 2023-24 Playoffs")
    print("="*80)

    df = await fetch_grouping(
        "player/game",
        season="2023-24",
        player_id=2544,
        season_type="Playoffs"
    )

    print(f"[OK] Found {len(df)} games")
    print(f"  Player: {df['PLAYER_NAME'].iloc[0] if len(df) > 0 else 'N/A'}")
    print(f"  Date range: {df['GAME_DATE'].min()} to {df['GAME_DATE'].max()}")
    print(f"  Avg PPG: {df['PTS'].mean():.1f}")

    return df


async def test_stat_filtering():
    """Test statistical filtering (MIN >= 20)"""
    print("\n" + "="*80)
    print("TEST 2: Statistical Filtering - LeBron games with 20+ minutes")
    print("="*80)

    df = await fetch_grouping(
        "player/game",
        season="2023-24",
        player_id=2544,
        MIN=(">=", 20)  # DuckDB filter
    )

    print(f"[OK] Found {len(df)} games with MIN >= 20")
    print(f"  Min minutes: {df['MIN'].min():.1f}")
    print(f"  Max minutes: {df['MIN'].max():.1f}")
    print(f"  Avg minutes: {df['MIN'].mean():.1f}")

    assert df['MIN'].min() >= 20, "All games should have MIN >= 20"

    return df


async def test_combined_filtering():
    """Test combined API + stat filtering"""
    print("\n" + "="*80)
    print("TEST 3: Combined - Home playoff wins with 15+ points")
    print("="*80)

    df = await fetch_grouping(
        "player/game",
        season="2023-24",
        player_id=2544,
        location="Home",  # API filter
        outcome="W",      # API filter
        season_type="Playoffs",  # API filter
        PTS=(">=", 15)    # DuckDB filter
    )

    print(f"[OK] Found {len(df)} home playoff wins with 15+ points")
    if len(df) > 0:
        print(f"  Min points: {df['PTS'].min()}")
        print(f"  Max points: {df['PTS'].max()}")
        print(f"  Avg points: {df['PTS'].mean():.1f}")

    return df


async def test_all_players_with_filter():
    """Test fetching all players with statistical filter"""
    print("\n" + "="*80)
    print("TEST 4: All Players - 2023-24 Playoffs with 10+ minutes")
    print("="*80)

    df = await fetch_grouping(
        "player/game",
        season="2023-24",
        season_type="Playoffs",
        MIN=(">=", 10)  # DuckDB filter
    )

    print(f"[OK] Found {len(df)} games from {df['PLAYER_ID'].nunique()} players")
    print(f"  Top scorers:")
    top_scorers = df.nlargest(5, 'PTS')[['PLAYER_NAME', 'GAME_DATE', 'PTS', 'MIN']]
    for _, row in top_scorers.iterrows():
        print(f"    {row['PLAYER_NAME']}: {row['PTS']} pts in {row['MIN']:.1f} min ({row['GAME_DATE']})")

    return df


async def test_multiple_stat_filters():
    """Test multiple statistical filters"""
    print("\n" + "="*80)
    print("TEST 5: Multiple Filters - 25+ pts, 50%+ FG, 10+ reb")
    print("="*80)

    df = await fetch_grouping(
        "player/game",
        season="2023-24",
        season_type="Playoffs",
        PTS=(">=", 25),       # DuckDB filter
        FG_PCT=(">=", 0.5),  # DuckDB filter
        REB=(">=", 10)        # DuckDB filter
    )

    print(f"[OK] Found {len(df)} elite performances")
    print(f"  Players: {df['PLAYER_ID'].nunique()}")
    if len(df) > 0:
        print(f"  Top performances:")
        top = df.nlargest(5, 'PTS')[['PLAYER_NAME', 'GAME_DATE', 'PTS', 'REB', 'FG_PCT', 'MIN']]
        for _, row in top.iterrows():
            print(f"    {row['PLAYER_NAME']} ({row['GAME_DATE']}): {row['PTS']} pts, {row['REB']} reb, {row['FG_PCT']:.1%} FG")

    return df


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("FETCH_PLAYER_GAMES FUNCTIONALITY TEST")
    print("Testing Three-Tier Filtering System")
    print("="*80)

    try:
        # Run all tests
        await test_basic_fetch()
        await test_stat_filtering()
        await test_combined_filtering()
        await test_all_players_with_filter()
        await test_multiple_stat_filters()

        print("\n" + "="*80)
        print("ALL TESTS PASSED [OK]")
        print("="*80)
        print("\nThe fetch_player_games MCP tool is ready to use!")
        print("Restart the MCP server to access it.")
        print("="*80)

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
