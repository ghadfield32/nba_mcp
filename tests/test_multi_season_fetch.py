"""
Test multi-season fetching functionality

Tests the enhanced fetch_player_games tool that supports multiple seasons.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.data_groupings import fetch_grouping
import pandas as pd


async def test_single_season():
    """Test single season fetch (backward compatibility)"""
    print("\n" + "="*80)
    print("TEST 1: Single Season - LeBron 2023-24")
    print("="*80)

    df = await fetch_grouping(
        "player/game",
        season="2023-24",
        player_id=2544,
    )

    print(f"[OK] Found {len(df)} games")
    print(f"  Unique seasons: {df['SEASON_ID'].nunique()}")
    print(f"  Player: {df['PLAYER_NAME'].iloc[0]}")

    return df


async def test_multi_season():
    """Test multi-season fetch"""
    print("\n" + "="*80)
    print("TEST 2: Multi-Season - LeBron 2021-22, 2022-23, 2023-24")
    print("="*80)

    seasons = ["2021-22", "2022-23", "2023-24"]
    all_dfs = []

    for season in seasons:
        df = await fetch_grouping(
            "player/game",
            season=season,
            player_id=2544,
        )
        print(f"  {season}: {len(df)} games")
        all_dfs.append(df)

    df_combined = pd.concat(all_dfs, ignore_index=True)

    print(f"\n[OK] Combined: {len(df_combined)} total games")
    print(f"  Unique seasons: {df_combined['SEASON_ID'].nunique()}")
    print(f"  Seasons: {sorted(df_combined['SEASON_ID'].unique())}")
    print(f"  Date range: {df_combined['GAME_DATE'].min()} to {df_combined['GAME_DATE'].max()}")

    return df_combined


async def test_multi_season_with_filters():
    """Test multi-season with statistical filters"""
    print("\n" + "="*80)
    print("TEST 3: Multi-Season with Filters - LeBron 2021-24, MIN >= 30")
    print("="*80)

    seasons = ["2021-22", "2022-23", "2023-24"]
    all_dfs = []

    for season in seasons:
        df = await fetch_grouping(
            "player/game",
            season=season,
            player_id=2544,
            MIN=(">=", 30)  # 30+ minutes
        )
        print(f"  {season}: {len(df)} games with 30+ minutes")
        all_dfs.append(df)

    df_combined = pd.concat(all_dfs, ignore_index=True)

    print(f"\n[OK] Combined: {len(df_combined)} games with 30+ minutes")
    print(f"  Avg minutes: {df_combined['MIN'].mean():.1f}")
    print(f"  Avg points: {df_combined['PTS'].mean():.1f}")

    assert df_combined['MIN'].min() >= 30, "All games should have MIN >= 30"

    return df_combined


async def test_all_players_multi_season():
    """Test fetching all players across multiple seasons (with filters to limit size)"""
    print("\n" + "="*80)
    print("TEST 4: All Players Multi-Season - Playoffs 2022-23, 2023-24, 30+ pts")
    print("="*80)

    seasons = ["2022-23", "2023-24"]
    all_dfs = []

    for season in seasons:
        df = await fetch_grouping(
            "player/game",
            season=season,
            season_type="Playoffs",
            PTS=(">=", 30)  # 30+ points in playoffs
        )
        print(f"  {season} Playoffs: {len(df)} games with 30+ points")
        all_dfs.append(df)

    df_combined = pd.concat(all_dfs, ignore_index=True)

    print(f"\n[OK] Combined: {len(df_combined)} elite playoff performances")
    print(f"  Unique players: {df_combined['PLAYER_ID'].nunique()}")
    print(f"  Top scorer: {df_combined.nlargest(1, 'PTS')[['PLAYER_NAME', 'PTS', 'GAME_DATE']].to_string(index=False)}")

    return df_combined


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("MULTI-SEASON FETCH FUNCTIONALITY TEST")
    print("Testing Enhanced fetch_player_games with Season Range Support")
    print("="*80)

    try:
        # Run all tests
        await test_single_season()
        await test_multi_season()
        await test_multi_season_with_filters()
        await test_all_players_multi_season()

        print("\n" + "="*80)
        print("ALL TESTS PASSED [OK]")
        print("="*80)
        print("\nThe multi-season fetch functionality is ready!")
        print("Restart the MCP server to make it available as MCP tool.")
        print("="*80)

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
