"""
Comprehensive NBA Schedule Fetcher Tests

Tests the schedule tool across multiple seasons, all filter combinations,
data integrity checks, edge cases, and real-world scenarios.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.schedule import (
    get_current_season_year,
    fetch_nba_schedule_raw,
    parse_schedule_to_dataframe,
    get_nba_schedule,
    format_schedule_markdown,
)


class TestResults:
    """Track test results for summary reporting"""
    def __init__(self):
        self.tests = []
        self.passed = 0
        self.failed = 0
        self.warnings = []

    def add_test(self, name, passed, message=""):
        self.tests.append({
            "name": name,
            "passed": passed,
            "message": message
        })
        if passed:
            self.passed += 1
        else:
            self.failed += 1

    def add_warning(self, message):
        self.warnings.append(message)

    def print_summary(self):
        print("\n" + "=" * 80)
        print("COMPREHENSIVE TEST SUMMARY")
        print("=" * 80)

        for test in self.tests:
            status = "[PASS]" if test["passed"] else "[FAIL]"
            msg = f" - {test['message']}" if test["message"] else ""
            print(f"{status:8} {test['name']}{msg}")

        if self.warnings:
            print("\nWarnings:")
            for warning in self.warnings:
                print(f"  [WARN] {warning}")

        print("=" * 80)
        print(f"Results: {self.passed}/{len(self.tests)} tests passed")
        if self.failed > 0:
            print(f"FAILURES: {self.failed} test(s) failed")
        print("=" * 80)

        return self.failed == 0


results = TestResults()


async def test_1_season_auto_detection():
    """Test 1: Verify automatic season detection logic"""
    print("\n" + "=" * 80)
    print("TEST 1: Season Auto-Detection Logic")
    print("=" * 80)

    try:
        season_year = get_current_season_year()
        current_month = datetime.now().month
        current_year = datetime.now().year

        print(f"Current date: {datetime.now().strftime('%Y-%m-%d')}")
        print(f"Current month: {current_month}")
        print(f"Detected season year: {season_year}")
        print(f"Season string: {season_year-1}-{str(season_year)[2:]}")

        # Verify logic
        if current_month >= 8:
            expected = current_year + 1
        else:
            expected = current_year

        if season_year == expected:
            print(f"[PASS] Season detection correct (month {current_month} -> season year {season_year})")
            results.add_test("Season Auto-Detection", True, f"Correctly detected {season_year-1}-{str(season_year)[2:]}")
        else:
            print(f"[FAIL] Expected {expected}, got {season_year}")
            results.add_test("Season Auto-Detection", False, f"Expected {expected}, got {season_year}")

    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        results.add_test("Season Auto-Detection", False, str(e))


async def test_2_fetch_multiple_seasons():
    """Test 2: Fetch schedules for multiple historical seasons"""
    print("\n" + "=" * 80)
    print("TEST 2: Multiple Season Fetching")
    print("=" * 80)

    # Test seasons: 2023-24, 2024-25, 2025-26
    test_seasons = ["2023-24", "2024-25", "2025-26"]
    season_results = {}

    for season in test_seasons:
        try:
            print(f"\nFetching {season} season...")
            df = await get_nba_schedule(season=season)

            game_count = len(df)
            season_results[season] = {
                "success": True,
                "games": game_count,
                "error": None
            }

            if game_count > 0:
                # Verify season year
                if 'season_year' in df.columns:
                    season_years = df['season_year'].unique()
                    print(f"  [PASS] Found {game_count} games")
                    print(f"  Season years in data: {season_years.tolist()}")

                    # Count by stage
                    if 'season_stage_id' in df.columns:
                        stage_counts = df.groupby('season_stage_id').size()
                        stage_map = {1: "Preseason", 2: "Regular", 4: "Playoffs"}
                        for stage_id, count in stage_counts.items():
                            print(f"    - {stage_map.get(stage_id, f'Stage {stage_id}')}: {count} games")
                else:
                    print(f"  [WARN] Found {game_count} games but no season_year column")
                    results.add_warning(f"{season}: Missing season_year column")
            else:
                print(f"  [INFO] No games found for {season} (may not be published yet)")
                results.add_warning(f"{season}: No games found (schedule may not be published)")

        except Exception as e:
            print(f"  [FAIL] Error fetching {season}: {e}")
            season_results[season] = {
                "success": False,
                "games": 0,
                "error": str(e)
            }

    # Evaluate results
    successful_seasons = [s for s, r in season_results.items() if r["success"]]
    total_games = sum(r["games"] for r in season_results.values())

    if len(successful_seasons) >= 1:  # At least one season should work
        results.add_test(
            "Multiple Season Fetching",
            True,
            f"{len(successful_seasons)}/3 seasons, {total_games} total games"
        )
    else:
        results.add_test(
            "Multiple Season Fetching",
            False,
            "No seasons fetched successfully"
        )

    return season_results


async def test_3_all_season_stages():
    """Test 3: Verify all season stages can be fetched"""
    print("\n" + "=" * 80)
    print("TEST 3: Season Stage Filtering")
    print("=" * 80)

    stages = {
        "preseason": 1,
        "regular": 2,
        "playoffs": 4
    }

    stage_results = {}

    for stage_name, expected_id in stages.items():
        try:
            print(f"\nFetching {stage_name} games...")
            df = await get_nba_schedule(season_stage=stage_name)

            game_count = len(df)
            stage_results[stage_name] = game_count

            if game_count > 0:
                # Verify all games are correct stage
                actual_stages = df['season_stage_id'].unique()
                if len(actual_stages) == 1 and actual_stages[0] == expected_id:
                    print(f"  [PASS] {game_count} {stage_name} games (stage_id={expected_id})")
                else:
                    print(f"  [FAIL] Expected stage_id {expected_id}, got {actual_stages.tolist()}")
                    results.add_test(
                        f"Stage Filter: {stage_name}",
                        False,
                        f"Wrong stage IDs: {actual_stages.tolist()}"
                    )
                    continue
            else:
                print(f"  [INFO] No {stage_name} games found")

            results.add_test(
                f"Stage Filter: {stage_name}",
                True,
                f"{game_count} games"
            )

        except Exception as e:
            print(f"  [FAIL] Error: {e}")
            results.add_test(f"Stage Filter: {stage_name}", False, str(e))
            stage_results[stage_name] = 0

    # Test aliases
    print(f"\nTesting stage aliases...")
    try:
        df1 = await get_nba_schedule(season_stage="pre")
        df2 = await get_nba_schedule(season_stage="preseason")

        if len(df1) == len(df2):
            print(f"  [PASS] Alias 'pre' = 'preseason' ({len(df1)} games)")
            results.add_test("Stage Aliases", True, "'pre' and 'preseason' match")
        else:
            print(f"  [FAIL] Alias mismatch: pre={len(df1)}, preseason={len(df2)}")
            results.add_test("Stage Aliases", False, "Alias counts don't match")
    except Exception as e:
        print(f"  [FAIL] Error testing aliases: {e}")
        results.add_test("Stage Aliases", False, str(e))


async def test_4_team_filtering():
    """Test 4: Verify team filtering works for multiple teams"""
    print("\n" + "=" * 80)
    print("TEST 4: Team Filtering")
    print("=" * 80)

    # Test teams from different conferences
    test_teams = ["LAL", "BOS", "GSW", "MIA", "CHI"]
    team_results = {}

    for team_abbr in test_teams:
        try:
            print(f"\nFetching {team_abbr} schedule...")
            df = await get_nba_schedule(team=team_abbr)

            game_count = len(df)
            team_results[team_abbr] = game_count

            if game_count > 0:
                # Verify team appears in all games
                home_matches = (df['home_abbr'] == team_abbr).sum()
                away_matches = (df['away_abbr'] == team_abbr).sum()
                total_matches = home_matches + away_matches

                if total_matches == game_count:
                    print(f"  [PASS] {game_count} games ({home_matches} home, {away_matches} away)")
                else:
                    print(f"  [FAIL] Team filter leak: {total_matches}/{game_count} games have {team_abbr}")
                    results.add_test(
                        f"Team Filter: {team_abbr}",
                        False,
                        f"Filter leak: {total_matches}/{game_count}"
                    )
                    continue

                # Show first few games
                print(f"  Sample games:")
                for _, row in df.head(3).iterrows():
                    matchup = f"{row['away_abbr']} @ {row['home_abbr']}"
                    date = row['game_date_local']
                    print(f"    {date}: {matchup}")

                results.add_test(
                    f"Team Filter: {team_abbr}",
                    True,
                    f"{game_count} games ({home_matches}H/{away_matches}A)"
                )
            else:
                print(f"  [INFO] No games found for {team_abbr}")
                results.add_warning(f"{team_abbr}: No games found")
                results.add_test(f"Team Filter: {team_abbr}", True, "0 games (may be off-season)")

        except Exception as e:
            print(f"  [FAIL] Error: {e}")
            results.add_test(f"Team Filter: {team_abbr}", False, str(e))


async def test_5_date_range_filtering():
    """Test 5: Test date range filtering"""
    print("\n" + "=" * 80)
    print("TEST 5: Date Range Filtering")
    print("=" * 80)

    # Test case 1: Single month (December 2024)
    print("\nTest 5a: December 2024 games")
    try:
        df = await get_nba_schedule(
            season="2024-25",
            date_from="2024-12-01",
            date_to="2024-12-31"
        )

        if len(df) > 0:
            dates = df['game_date_local'].unique()
            print(f"  [PASS] Found {len(df)} games in December 2024")
            print(f"  Date range: {dates.min()} to {dates.max()}")

            # Verify all dates in range
            min_date = df['game_date_local'].min()
            max_date = df['game_date_local'].max()

            if min_date >= "2024-12-01" and max_date <= "2024-12-31":
                results.add_test("Date Range: December 2024", True, f"{len(df)} games")
            else:
                results.add_test("Date Range: December 2024", False, f"Dates outside range: {min_date} - {max_date}")
        else:
            print(f"  [INFO] No games in December 2024")
            results.add_test("Date Range: December 2024", True, "0 games")

    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        results.add_test("Date Range: December 2024", False, str(e))

    # Test case 2: Opening week (October 2024)
    print("\nTest 5b: Opening week October 2024")
    try:
        df = await get_nba_schedule(
            season="2024-25",
            date_from="2024-10-22",
            date_to="2024-10-28"
        )

        if len(df) > 0:
            print(f"  [PASS] Found {len(df)} games in opening week")
            print(f"  Games per day:")

            # Count by date
            daily_counts = df.groupby('game_date_local').size()
            for date, count in daily_counts.items():
                print(f"    {date}: {count} games")

            results.add_test("Date Range: Opening Week", True, f"{len(df)} games")
        else:
            print(f"  [INFO] No games in opening week")
            results.add_test("Date Range: Opening Week", True, "0 games")

    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        results.add_test("Date Range: Opening Week", False, str(e))


async def test_6_combined_filters():
    """Test 6: Test combinations of multiple filters"""
    print("\n" + "=" * 80)
    print("TEST 6: Combined Filter Scenarios")
    print("=" * 80)

    test_cases = [
        {
            "name": "Lakers Regular Season 2024-25",
            "params": {
                "season": "2024-25",
                "season_stage": "regular",
                "team": "LAL"
            }
        },
        {
            "name": "Lakers December 2024 Regular Season",
            "params": {
                "season": "2024-25",
                "season_stage": "regular",
                "team": "LAL",
                "date_from": "2024-12-01",
                "date_to": "2024-12-31"
            }
        },
        {
            "name": "Celtics vs Lakers matchups 2024-25",
            "params": {
                "season": "2024-25",
                "team": "LAL"  # Will manually filter for BOS opponent
            }
        }
    ]

    for test_case in test_cases:
        print(f"\nTest: {test_case['name']}")
        try:
            df = await get_nba_schedule(**test_case['params'])

            if len(df) > 0:
                print(f"  [PASS] Found {len(df)} games")

                # Additional filtering for Celtics matchups
                if "Celtics vs Lakers" in test_case['name']:
                    # Filter for games against BOS
                    bos_games = df[
                        ((df['home_abbr'] == 'LAL') & (df['away_abbr'] == 'BOS')) |
                        ((df['home_abbr'] == 'BOS') & (df['away_abbr'] == 'LAL'))
                    ]
                    print(f"  Found {len(bos_games)} LAL vs BOS matchups")

                    if len(bos_games) > 0:
                        for _, row in bos_games.iterrows():
                            matchup = f"{row['away_abbr']} @ {row['home_abbr']}"
                            date = row['game_date_local']
                            print(f"    {date}: {matchup}")

                # Show date range if applicable
                if 'game_date_local' in df.columns:
                    date_range = f"{df['game_date_local'].min()} to {df['game_date_local'].max()}"
                    print(f"  Date range: {date_range}")

                results.add_test(f"Combined: {test_case['name']}", True, f"{len(df)} games")
            else:
                print(f"  [INFO] No games found")
                results.add_test(f"Combined: {test_case['name']}", True, "0 games")

        except Exception as e:
            print(f"  [FAIL] Error: {e}")
            import traceback
            traceback.print_exc()
            results.add_test(f"Combined: {test_case['name']}", False, str(e))


async def test_7_data_integrity():
    """Test 7: Verify data integrity and completeness"""
    print("\n" + "=" * 80)
    print("TEST 7: Data Integrity Checks")
    print("=" * 80)

    try:
        # Fetch a season with data
        df = await get_nba_schedule(season="2024-25")

        if len(df) == 0:
            print("  [WARN] No data to validate")
            results.add_warning("No 2024-25 schedule data available for integrity checks")
            results.add_test("Data Integrity", True, "No data to validate")
            return

        print(f"\nValidating {len(df)} games from 2024-25 season...")

        # Check required columns
        required_columns = [
            'game_id', 'season_year', 'season_stage_id', 'game_status',
            'game_date_utc', 'game_date_local', 'arena',
            'home_id', 'home_name', 'home_abbr',
            'away_id', 'away_name', 'away_abbr'
        ]

        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            print(f"  [FAIL] Missing columns: {missing_columns}")
            results.add_test("Data Integrity: Columns", False, f"Missing: {missing_columns}")
        else:
            print(f"  [PASS] All required columns present")
            results.add_test("Data Integrity: Columns", True, f"{len(df.columns)} columns")

        # Check for null values in critical fields
        print(f"\nChecking for null values...")
        critical_fields = ['game_id', 'home_abbr', 'away_abbr', 'game_date_local']
        null_counts = {}

        for field in critical_fields:
            if field in df.columns:
                null_count = df[field].isnull().sum()
                null_counts[field] = null_count
                if null_count > 0:
                    print(f"  [WARN] {field}: {null_count} null values")
                else:
                    print(f"  [PASS] {field}: No null values")

        total_nulls = sum(null_counts.values())
        if total_nulls == 0:
            results.add_test("Data Integrity: Null Values", True, "No nulls in critical fields")
        else:
            results.add_test("Data Integrity: Null Values", False, f"{total_nulls} nulls found")

        # Check game_id uniqueness
        print(f"\nChecking game_id uniqueness...")
        duplicate_game_ids = df['game_id'].duplicated().sum()

        if duplicate_game_ids == 0:
            print(f"  [PASS] All game_ids unique ({len(df)} games)")
            results.add_test("Data Integrity: Unique IDs", True, f"{len(df)} unique game IDs")
        else:
            print(f"  [FAIL] {duplicate_game_ids} duplicate game_ids")
            results.add_test("Data Integrity: Unique IDs", False, f"{duplicate_game_ids} duplicates")

        # Check team abbreviations are valid (3 letters)
        print(f"\nValidating team abbreviations...")
        invalid_abbrs = []

        for col in ['home_abbr', 'away_abbr']:
            if col in df.columns:
                # Check length
                invalid = df[~df[col].str.match(r'^[A-Z]{3}$', na=False)]
                if len(invalid) > 0:
                    invalid_abbrs.extend(invalid[col].unique().tolist())

        if len(invalid_abbrs) == 0:
            print(f"  [PASS] All team abbreviations valid (3-letter format)")
            results.add_test("Data Integrity: Team Abbreviations", True, "All valid")
        else:
            print(f"  [FAIL] Invalid abbreviations: {invalid_abbrs}")
            results.add_test("Data Integrity: Team Abbreviations", False, f"Invalid: {invalid_abbrs}")

        # Check season_stage_id values
        print(f"\nValidating season stages...")
        valid_stages = [1, 2, 4]
        actual_stages = df['season_stage_id'].unique().tolist()
        invalid_stages = [s for s in actual_stages if s not in valid_stages]

        if len(invalid_stages) == 0:
            print(f"  [PASS] All stage IDs valid: {actual_stages}")
            results.add_test("Data Integrity: Season Stages", True, f"Stages: {actual_stages}")
        else:
            print(f"  [FAIL] Invalid stage IDs: {invalid_stages}")
            results.add_test("Data Integrity: Season Stages", False, f"Invalid: {invalid_stages}")

    except Exception as e:
        print(f"  [FAIL] Error during integrity checks: {e}")
        import traceback
        traceback.print_exc()
        results.add_test("Data Integrity", False, str(e))


async def test_8_output_formats():
    """Test 8: Verify different output formats"""
    print("\n" + "=" * 80)
    print("TEST 8: Output Format Testing")
    print("=" * 80)

    # Test markdown format
    print("\nTest 8a: Markdown format")
    try:
        df = await get_nba_schedule(team="LAL", season_stage="regular")
        markdown = format_schedule_markdown(df, max_games=5)

        if markdown and len(markdown) > 0:
            print(f"  [PASS] Generated markdown output ({len(markdown)} chars)")
            print(f"\n  Preview:")
            print("  " + "\n  ".join(markdown.split("\n")[:10]))
            results.add_test("Output Format: Markdown", True, f"{len(markdown)} chars")
        else:
            print(f"  [INFO] Empty markdown (no games)")
            results.add_test("Output Format: Markdown", True, "Empty (no games)")

    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        results.add_test("Output Format: Markdown", False, str(e))

    # Test JSON format (via DataFrame)
    print("\nTest 8b: JSON format (DataFrame to dict)")
    try:
        df = await get_nba_schedule(team="BOS", season_stage="regular")

        if len(df) > 0:
            json_data = df.head(3).to_dict(orient='records')
            json_str = json.dumps(json_data, indent=2, default=str)

            print(f"  [PASS] Converted to JSON ({len(json_data)} games)")
            print(f"  Sample game keys: {list(json_data[0].keys())}")
            results.add_test("Output Format: JSON", True, f"{len(json_data)} games")
        else:
            print(f"  [INFO] No games to convert")
            results.add_test("Output Format: JSON", True, "No games")

    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        results.add_test("Output Format: JSON", False, str(e))


async def test_9_real_world_scenarios():
    """Test 9: Real-world usage scenarios"""
    print("\n" + "=" * 80)
    print("TEST 9: Real-World Usage Scenarios")
    print("=" * 80)

    scenarios = [
        {
            "name": "Find next 5 Lakers games",
            "description": "Get upcoming games for a team",
            "code": """
# Scenario: Find next 5 Lakers games from today
from datetime import datetime
today = datetime.now().strftime("%Y-%m-%d")
df = await get_nba_schedule(
    team="LAL",
    date_from=today,
    season_stage="regular"
)
upcoming = df.head(5)
            """
        },
        {
            "name": "Count Christmas Day games",
            "description": "How many games on Christmas?",
            "code": """
# Scenario: Christmas Day games 2024
df = await get_nba_schedule(
    season="2024-25",
    date_from="2024-12-25",
    date_to="2024-12-25"
)
christmas_games = len(df)
            """
        },
        {
            "name": "Team back-to-back games",
            "description": "Find Lakers back-to-back games",
            "code": """
# Scenario: Lakers back-to-back games
df = await get_nba_schedule(team="LAL", season="2024-25")
# Sort by date and check consecutive dates
            """
        }
    ]

    for scenario in scenarios:
        print(f"\nScenario: {scenario['name']}")
        print(f"  Description: {scenario['description']}")

        try:
            # Execute scenario-specific logic
            if "next 5 Lakers" in scenario['name']:
                today = datetime.now().strftime("%Y-%m-%d")
                df = await get_nba_schedule(
                    team="LAL",
                    date_from=today,
                    season_stage="regular"
                )
                upcoming = df.head(5)

                if len(upcoming) > 0:
                    print(f"  [PASS] Found {len(upcoming)} upcoming games")
                    for _, row in upcoming.iterrows():
                        matchup = f"{row['away_abbr']} @ {row['home_abbr']}"
                        print(f"    {row['game_date_local']}: {matchup}")
                else:
                    print(f"  [INFO] No upcoming games found")

                results.add_test(f"Scenario: {scenario['name']}", True, f"{len(upcoming)} games")

            elif "Christmas" in scenario['name']:
                df = await get_nba_schedule(
                    season="2024-25",
                    date_from="2024-12-25",
                    date_to="2024-12-25"
                )

                print(f"  [PASS] Found {len(df)} Christmas Day games")
                if len(df) > 0:
                    for _, row in df.iterrows():
                        matchup = f"{row['away_abbr']} @ {row['home_abbr']}"
                        print(f"    {matchup}")

                results.add_test(f"Scenario: {scenario['name']}", True, f"{len(df)} games")

            elif "back-to-back" in scenario['name']:
                df = await get_nba_schedule(team="LAL", season="2024-25")

                if len(df) > 0:
                    # Convert dates and sort
                    df['date_obj'] = pd.to_datetime(df['game_date_local'])
                    df = df.sort_values('date_obj')

                    # Find back-to-backs (consecutive days)
                    df['prev_date'] = df['date_obj'].shift(1)
                    df['days_diff'] = (df['date_obj'] - df['prev_date']).dt.days

                    back_to_backs = df[df['days_diff'] == 1]

                    print(f"  [PASS] Found {len(back_to_backs)} back-to-back games")
                    if len(back_to_backs) > 0:
                        print(f"  Sample back-to-backs:")
                        for _, row in back_to_backs.head(3).iterrows():
                            matchup = f"{row['away_abbr']} @ {row['home_abbr']}"
                            print(f"    {row['game_date_local']}: {matchup}")
                else:
                    print(f"  [INFO] No games to analyze")

                results.add_test(
                    f"Scenario: {scenario['name']}",
                    True,
                    f"{len(back_to_backs) if len(df) > 0 else 0} B2B games"
                )

        except Exception as e:
            print(f"  [FAIL] Error: {e}")
            import traceback
            traceback.print_exc()
            results.add_test(f"Scenario: {scenario['name']}", False, str(e))


async def test_10_error_handling():
    """Test 10: Error handling and edge cases"""
    print("\n" + "=" * 80)
    print("TEST 10: Error Handling & Edge Cases")
    print("=" * 80)

    # Test invalid season format
    print("\nTest 10a: Invalid season format")
    try:
        df = await get_nba_schedule(season="2024")  # Missing -YY
        print(f"  [FAIL] Should have raised ValueError for invalid season")
        results.add_test("Error: Invalid Season Format", False, "No error raised")
    except ValueError as e:
        print(f"  [PASS] Correctly rejected invalid season: {e}")
        results.add_test("Error: Invalid Season Format", True, "ValueError raised")
    except Exception as e:
        print(f"  [FAIL] Wrong exception type: {e}")
        results.add_test("Error: Invalid Season Format", False, f"Wrong exception: {type(e)}")

    # Test invalid season stage
    print("\nTest 10b: Invalid season stage")
    try:
        df = await get_nba_schedule(season_stage="invalid_stage")
        print(f"  [FAIL] Should have raised ValueError for invalid stage")
        results.add_test("Error: Invalid Season Stage", False, "No error raised")
    except ValueError as e:
        print(f"  [PASS] Correctly rejected invalid stage: {e}")
        results.add_test("Error: Invalid Season Stage", True, "ValueError raised")
    except Exception as e:
        print(f"  [FAIL] Wrong exception type: {e}")
        results.add_test("Error: Invalid Season Stage", False, f"Wrong exception: {type(e)}")

    # Test future season (should work but return empty)
    print("\nTest 10c: Future season (2030-31)")
    try:
        df = await get_nba_schedule(season="2030-31")
        print(f"  [PASS] Handled future season gracefully ({len(df)} games)")
        results.add_test("Edge Case: Future Season", True, f"{len(df)} games")
    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        results.add_test("Edge Case: Future Season", False, str(e))

    # Test very old season (should work but return empty)
    print("\nTest 10d: Old season (2000-01)")
    try:
        df = await get_nba_schedule(season="2000-01")
        print(f"  [PASS] Handled old season gracefully ({len(df)} games)")
        results.add_test("Edge Case: Old Season", True, f"{len(df)} games")
    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        results.add_test("Edge Case: Old Season", False, str(e))


async def run_comprehensive_tests():
    """Run all comprehensive tests"""
    print("\n" + "=" * 80)
    print("NBA SCHEDULE COMPREHENSIVE TEST SUITE")
    print("Testing across multiple seasons, all filters, and real-world scenarios")
    print("=" * 80)

    # Import pandas for scenario tests
    global pd
    import pandas as pd

    # Run all tests
    await test_1_season_auto_detection()
    await test_2_fetch_multiple_seasons()
    await test_3_all_season_stages()
    await test_4_team_filtering()
    await test_5_date_range_filtering()
    await test_6_combined_filters()
    await test_7_data_integrity()
    await test_8_output_formats()
    await test_9_real_world_scenarios()
    await test_10_error_handling()

    # Print summary
    success = results.print_summary()

    return success


if __name__ == "__main__":
    success = asyncio.run(run_comprehensive_tests())
    sys.exit(0 if success else 1)
