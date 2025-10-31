"""
Test NBA Schedule Fetcher

Quick validation script for the get_nba_schedule tool.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.schedule import (
    get_current_season_year,
    fetch_nba_schedule_raw,
    parse_schedule_to_dataframe,
    get_nba_schedule,
    format_schedule_markdown,
)


async def test_season_detection():
    """Test automatic season detection"""
    print("\n" + "=" * 80)
    print("TEST 1: Season Auto-Detection")
    print("=" * 80)

    season_year = get_current_season_year()
    print(f"[PASS] Current season ending year: {season_year}")
    print(f"[PASS] Season string: {season_year-1}-{str(season_year)[2:]}")


async def test_raw_fetch():
    """Test fetching raw schedule data"""
    print("\n" + "=" * 80)
    print("TEST 2: Raw Schedule Fetch")
    print("=" * 80)

    try:
        raw_data = fetch_nba_schedule_raw()
        league_schedule = raw_data.get("leagueSchedule", {})
        game_dates = league_schedule.get("gameDates", [])

        print(f"[PASS] Successfully fetched schedule data")
        print(f"[PASS] Number of game dates: {len(game_dates)}")

        if game_dates:
            first_date = game_dates[0]
            print(f"[PASS] First game date: {first_date.get('gameDate')}")
            games = first_date.get("games", [])
            print(f"[PASS] Games on first date: {len(games)}")

            if games:
                game = games[0]
                print(f"[PASS] Sample game: {game.get('awayTeam', {}).get('teamTricode')} @ "
                      f"{game.get('homeTeam', {}).get('teamTricode')}")

        return True
    except Exception as e:
        print(f"[FAIL] Error fetching schedule: {e}")
        return False


async def test_parse_schedule():
    """Test parsing schedule data"""
    print("\n" + "=" * 80)
    print("TEST 3: Schedule Parsing")
    print("=" * 80)

    try:
        raw_data = fetch_nba_schedule_raw()
        df = parse_schedule_to_dataframe(raw_data)

        print(f"[PASS] Parsed {len(df)} games")
        print(f"[PASS] Columns: {', '.join(df.columns.tolist()[:10])}...")

        if not df.empty:
            # Show sample game
            sample = df.iloc[0]
            print(f"[PASS] Sample game:")
            print(f"  - Date: {sample['game_date_local']}")
            print(f"  - Matchup: {sample['away_abbr']} @ {sample['home_abbr']}")
            print(f"  - Arena: {sample['arena']}")
            print(f"  - Status: {sample['game_status']}")

        return True
    except Exception as e:
        print(f"[FAIL] Error parsing schedule: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_current_season():
    """Test fetching current season schedule"""
    print("\n" + "=" * 80)
    print("TEST 4: Current Season Schedule (Auto-Detect)")
    print("=" * 80)

    try:
        df = await get_nba_schedule()

        print(f"[PASS] Fetched {len(df)} games for current season")

        if not df.empty:
            season_year = df['season_year'].iloc[0]
            print(f"[PASS] Season: {season_year-1}-{str(season_year)[2:]}")

            # Count by stage
            stage_counts = df.groupby('season_stage_id').size()
            stage_map = {1: "Preseason", 2: "Regular Season", 4: "Playoffs"}
            for stage_id, count in stage_counts.items():
                print(f"[PASS] {stage_map.get(stage_id, f'Stage {stage_id}')}: {count} games")

        return True
    except Exception as e:
        print(f"[FAIL] Error fetching current season: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_filter_by_team():
    """Test filtering by team"""
    print("\n" + "=" * 80)
    print("TEST 5: Filter by Team (Lakers)")
    print("=" * 80)

    try:
        df = await get_nba_schedule(team="LAL")

        print(f"[PASS] Fetched {len(df)} Lakers games")

        if not df.empty:
            # Show first 5 games
            print(f"[PASS] First 5 games:")
            for idx, row in df.head(5).iterrows():
                print(f"  {row['game_date_local']}: {row['away_abbr']} @ {row['home_abbr']} - {row['game_status']}")

        return True
    except Exception as e:
        print(f"[FAIL] Error filtering by team: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_filter_by_stage():
    """Test filtering by season stage"""
    print("\n" + "=" * 80)
    print("TEST 6: Filter by Season Stage (Regular Season)")
    print("=" * 80)

    try:
        df = await get_nba_schedule(season_stage="regular")

        print(f"[PASS] Fetched {len(df)} regular season games")

        if not df.empty:
            # Verify all games are regular season
            unique_stages = df['season_stage_id'].unique()
            print(f"[PASS] Stage IDs: {unique_stages.tolist()}")
            assert all(stage == 2 for stage in unique_stages), "Non-regular season games found!"

        return True
    except Exception as e:
        print(f"[FAIL] Error filtering by stage: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_markdown_formatting():
    """Test markdown output"""
    print("\n" + "=" * 80)
    print("TEST 7: Markdown Formatting")
    print("=" * 80)

    try:
        df = await get_nba_schedule(team="LAL", season_stage="regular")
        markdown = format_schedule_markdown(df, max_games=10)

        print(f"[PASS] Generated markdown output:")
        print()
        print(markdown)

        return True
    except Exception as e:
        print(f"[FAIL] Error generating markdown: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("NBA SCHEDULE TOOL - TEST SUITE")
    print("=" * 80)

    results = []

    # Test 1: Season detection (sync)
    try:
        await test_season_detection()
        results.append(("Season Detection", True))
    except Exception as e:
        print(f"[FAIL] Season detection failed: {e}")
        results.append(("Season Detection", False))

    # Test 2: Raw fetch
    try:
        success = await test_raw_fetch()
        results.append(("Raw Fetch", success))
    except Exception as e:
        print(f"[FAIL] Raw fetch test failed: {e}")
        results.append(("Raw Fetch", False))

    # Test 3: Parse schedule
    try:
        success = await test_parse_schedule()
        results.append(("Parse Schedule", success))
    except Exception as e:
        print(f"[FAIL] Parse schedule test failed: {e}")
        results.append(("Parse Schedule", False))

    # Test 4: Current season
    try:
        success = await test_current_season()
        results.append(("Current Season", success))
    except Exception as e:
        print(f"[FAIL] Current season test failed: {e}")
        results.append(("Current Season", False))

    # Test 5: Filter by team
    try:
        success = await test_filter_by_team()
        results.append(("Filter by Team", success))
    except Exception as e:
        print(f"[FAIL] Filter by team test failed: {e}")
        results.append(("Filter by Team", False))

    # Test 6: Filter by stage
    try:
        success = await test_filter_by_stage()
        results.append(("Filter by Stage", success))
    except Exception as e:
        print(f"[FAIL] Filter by stage test failed: {e}")
        results.append(("Filter by Stage", False))

    # Test 7: Markdown formatting
    try:
        success = await test_markdown_formatting()
        results.append(("Markdown Formatting", success))
    except Exception as e:
        print(f"[FAIL] Markdown formatting test failed: {e}")
        results.append(("Markdown Formatting", False))

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for test_name, success in results:
        status = "[PASS] PASS" if success else "[FAIL] FAIL"
        print(f"{status:8} {test_name}")

    print("=" * 80)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 80)

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
