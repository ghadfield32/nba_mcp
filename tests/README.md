# NBA MCP Comprehensive Test Suite

## Overview

This test suite provides extensive coverage of all 24+ NBA MCP tools with real-world scenarios designed for NBA teams and betting companies. Tests are fully automated, parameterized, and cover deep functionality of each tool.

## Test Coverage

### Total Coverage
- **24+ MCP Tools** tested
- **70+ Individual Tests**
- **5 Integration Scenarios**
- **10 Test Categories**
- **2 Primary Use Cases** (NBA Teams, Betting Companies)

### Test Categories

1. **Entity Resolution** (5 tests)
   - Player name resolution (full, partial)
   - Team name resolution (full, abbreviation, city)

2. **Player Analytics** (5 tests)
   - Career information
   - Advanced stats (current, historical)
   - Multi-season trend analysis

3. **Team Analytics** (6 tests)
   - Standings (all teams, conference-specific, historical)
   - Advanced stats
   - Multi-team comparisons

4. **Comparative Analysis** (4 tests)
   - Same-era player comparisons
   - Cross-position comparisons
   - Era-adjusted comparisons (cross-generation, 80s vs 90s)

5. **League-Wide Data** (6 tests)
   - League leaders (multiple categories)
   - Different aggregation modes
   - Live scores (today, historical)

6. **Game Intelligence** (8 tests)
   - Game logs (season, date range, team-specific)
   - Play-by-play (live, historical)
   - Game context (rivalry, cross-conference, historical)

7. **Shot Analytics** (6 tests)
   - Player/team shot charts
   - Date range filtering
   - Different granularities (raw, summary)
   - Playoffs vs Regular Season

8. **Natural Language Queries** (4 tests)
   - League leaders
   - Player comparisons
   - Team stats
   - Standings

9. **Data Persistence** (3 tests)
   - Auto-generated filenames
   - Custom filenames
   - Descriptive naming validation

10. **System & Configuration** (1 test)
    - Metrics retrieval

### Integration Scenarios

#### NBA Team Scenarios (3)
1. **Pre-Game Scouting Report**
   - Opponent standings & record
   - Advanced stats (offensive/defensive ratings)
   - Game context (head-to-head history)
   - Shot chart analysis
   - Key player stats
   - Data persistence for coaching staff

2. **Player Trade Analysis**
   - Direct player comparison
   - Advanced stats for both players
   - Career trajectory analysis
   - Era-adjusted comparison if needed
   - Comprehensive report generation

3. **Season Performance Tracking**
   - Standings progression
   - Advanced stats trends
   - Game logs throughout season
   - Pattern identification
   - Season report generation

#### Betting Company Scenarios (2)
1. **Betting Odds Calculation**
   - Both teams' standings & records
   - Advanced stats for matchup
   - Head-to-head history
   - Recent form (last 10 games)
   - Key players' current performance
   - Data compilation for odds algorithm

2. **Live Game Tracking**
   - Real-time score updates
   - Play-by-play monitoring
   - Player performance tracking
   - Statistical trend monitoring

## Usage

### Run All Tests
```bash
python tests/comprehensive_nba_mcp_tests.py
```

### Run Specific Category
```bash
python tests/comprehensive_nba_mcp_tests.py --category player_analytics
python tests/comprehensive_nba_mcp_tests.py --category shot_analytics
python tests/comprehensive_nba_mcp_tests.py --category game_intelligence
```

### Run Specific Scenario
```bash
python tests/comprehensive_nba_mcp_tests.py --scenario nba_team
python tests/comprehensive_nba_mcp_tests.py --scenario betting_company
```

### Available Categories
- `entity_resolution`
- `player_analytics`
- `team_analytics`
- `comparative`
- `league_data`
- `game_intelligence`
- `shot_analytics`
- `nlq`
- `data_persistence`
- `system`

### Available Scenarios
- `nba_team` - NBA team use cases
- `betting_company` - Betting company use cases

## Test Configuration

Tests are configured via the `TestConfig` class in the test file. You can easily adjust:

### Players
```python
PLAYERS = {
    "superstar_current": "LeBron James",
    "superstar_young": "Luka Doncic",
    "star_guard": "Stephen Curry",
    "star_forward": "Kevin Durant",
    "star_center": "Joel Embiid",
    "legend_90s": "Michael Jordan",
    "legend_80s": "Magic Johnson",
    "role_player": "Draymond Green",
}
```

### Teams
```python
TEAMS = {
    "western_top": "Golden State Warriors",
    "western_mid": "Los Angeles Lakers",
    "eastern_top": "Boston Celtics",
    "eastern_mid": "Miami Heat",
    "small_market": "Memphis Grizzlies",
}
```

### Seasons
```python
SEASONS = {
    "current": "2025-26",
    "recent": "2024-25",
    "historic_jordan": "1995-96",
    "historic_magic": "1986-87",
}
```

### Stat Categories
```python
STAT_CATEGORIES = ["PTS", "AST", "REB", "STL", "BLK", "FG_PCT", "FG3_PCT"]
```

## Parameterized Testing

All tests are designed to be easily parameterized. Simply modify the `TestConfig` class to test different:
- Players (current stars, legends, role players)
- Teams (contenders, mid-tier, rebuilding)
- Seasons (current, recent, historical)
- Date ranges (today, week, month, season)
- Stat categories (scoring, assists, rebounds, etc.)

## Expected Output

```
================================================================================
NBA MCP COMPREHENSIVE TEST SUITE
================================================================================
Started: 2025-10-29 14:30:00
Filter - Category: ALL, Scenario: ALL
================================================================================

[CATEGORY 1] Entity Resolution Tests
--------------------------------------------------------------------------------
[PASS] Entity: Player Full Name (156ms)
[PASS] Entity: Player Partial Name (142ms)
[PASS] Entity: Team Full Name (98ms)
[PASS] Entity: Team Abbreviation (105ms)
[PASS] Entity: Team City (112ms)

...

[INTEGRATION] NBA Team Scenarios
--------------------------------------------------------------------------------
[INTEGRATION] Pre-Game Scouting Report
  ✓ Retrieved league standings
  ✓ Retrieved opponent advanced stats
  ✓ Retrieved game context and matchup history
  ✓ Retrieved opponent shot chart
  ✓ Saved scouting report
[INTEGRATION] Pre-Game Scouting Report: COMPLETED
[PASS] Scenario: Pre-Game Scouting (1245ms)

...

================================================================================
NBA MCP TEST SUITE - RESULTS
================================================================================
Total Tests: 75
Passed: 75 (100.0%)
Failed: 0
Skipped: 0
Duration: 45.23s
================================================================================
```

## Test Validation

Each test validates:
- ✅ Successful API response
- ✅ Correct data structure
- ✅ Expected content in results
- ✅ Error handling (where applicable)
- ✅ Data persistence (for save operations)

## Continuous Integration

These tests are designed to be run as part of CI/CD pipelines:
- All tests are independent
- No test data pollution
- Automated cleanup
- Exit codes for CI systems (0 = pass, 1 = fail)

## Real-World Validation

Tests use realistic scenarios:
- Actual player names (LeBron James, Stephen Curry, etc.)
- Real team names (Warriors, Lakers, Celtics, etc.)
- Historical seasons (1995-96 Bulls, 1986-87 Lakers, etc.)
- Current season data
- Live game scenarios

## Extending Tests

To add new tests:

1. Create test function following naming convention:
```python
async def test_new_feature():
    """Test description"""
    result = await some_mcp_tool()
    assert condition
```

2. Add to appropriate category in `run_all_tests()`

3. Update this README with new test details

## Performance

Typical test suite completion times:
- **Full Suite**: ~30-60 seconds (depends on API response times)
- **Single Category**: ~5-10 seconds
- **Integration Scenario**: ~3-5 seconds

## Requirements

- Python 3.8+
- All NBA MCP dependencies
- Active MCP server
- Internet connection (for NBA API calls)

## Troubleshooting

### Tests Failing
1. Ensure MCP server is running
2. Check API rate limits
3. Verify test dates are recent (for live data tests)
4. Check player/team names are current

### Slow Tests
- Normal for first run (API caching)
- Subsequent runs should be faster
- Can run single categories for faster feedback

### Skipped Tests
- Some tests may skip if no game data available
- Check test dates and adjust if needed

## Support

For issues or questions:
1. Check test output for specific error messages
2. Verify MCP server is running
3. Review DEVELOPMENT_LOG.md for recent changes
4. Check NBA API status

## License

Part of NBA MCP project. See main project README for license information.
