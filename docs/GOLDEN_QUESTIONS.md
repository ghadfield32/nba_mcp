# NBA MCP Golden Questions Test Suite

This document contains a comprehensive set of "golden questions" that test all major features of the NBA MCP server. Use these questions to validate that the server is working correctly with real NBA API data.

## Purpose

Golden questions serve as:
1. **Integration tests** - Verify real NBA API connectivity
2. **Feature validation** - Ensure all tools return correct data
3. **User acceptance** - Demonstrate capabilities to users
4. **Regression testing** - Detect breaking changes

## Test Categories

### 1. Entity Resolution (Fuzzy Matching)

**Q1.1:** "Show me LeBron James' career stats"
- **Expected**: Should resolve "LeBron James" to player ID 2544
- **Validates**: Entity resolution, career information retrieval

**Q1.2:** "Get stats for the Lakers"
- **Expected**: Should resolve "Lakers" to Los Angeles Lakers (team ID 1610612747)
- **Validates**: Team entity resolution

**Q1.3:** "Compare Steph Curry and KD"
- **Expected**: Should resolve "Steph" to Stephen Curry, "KD" to Kevin Durant
- **Validates**: Partial name matching, nickname resolution

---

### 2. Live Data

**Q2.1:** "What are today's NBA scores?"
- **Expected**: Returns live scores for today's games (or empty if no games)
- **Validates**: Live data API, date handling

**Q2.2:** "Show me games on December 25, 2024"
- **Expected**: Returns Christmas Day games if available
- **Validates**: Date-specific queries, historical data

---

### 3. Player Statistics

**Q3.1:** "Get Stephen Curry's stats for the 2023-24 season"
- **Expected**: Returns season averages (PTS, AST, REB, 3P%, etc.)
- **Validates**: Player stats retrieval, season parameter handling

**Q3.2:** "Show LeBron's career information"
- **Expected**: Returns career overview, draft info, teams played for
- **Validates**: Career endpoint, multi-year data

**Q3.3:** "Get Giannis' advanced stats this season"
- **Expected**: Returns PER, TS%, OffRtg, DefRtg, etc.
- **Validates**: Advanced stats endpoint

---

### 4. Team Statistics

**Q4.1:** "Get the Lakers' team standings"
- **Expected**: Returns W-L record, conference rank, games behind
- **Validates**: Team standings endpoint

**Q4.2:** "Show me the Celtics' advanced stats"
- **Expected**: Returns team OffRtg, DefRtg, NetRtg, Pace
- **Validates**: Team advanced stats

---

### 5. League Leaders

**Q5.1:** "Who are the top 10 scorers this season?"
- **Expected**: Returns top 10 players by PPG
- **Validates**: League leaders endpoint, stat category resolution

**Q5.2:** "Show me the top 3PT shooters"
- **Expected**: Returns top players by 3P%
- **Validates**: Percentage stat handling

---

### 6. Player Comparison

**Q6.1:** "Compare LeBron James and Michael Jordan"
- **Expected**: Returns side-by-side career stats comparison
- **Validates**: Player comparison, career data

**Q6.2:** "Compare LeBron and MJ with era adjustments"
- **Expected**: Returns pace-adjusted and scoring-environment-adjusted stats
- **Validates**: Era-adjusted comparison, historical context

---

### 7. Game Logs

**Q7.1:** "Show LeBron's game log for November 2024"
- **Expected**: Returns all games played in November with stats
- **Validates**: Date range queries, game log endpoint

**Q7.2:** "Get the Lakers' last 10 games"
- **Expected**: Returns team game log for last 10 games
- **Validates**: Team game logs, recent games

---

### 8. Play-by-Play Data

**Q8.1:** "Get play-by-play for game ID 0022300001"
- **Expected**: Returns detailed play-by-play data
- **Validates**: Play-by-play endpoint, game ID handling

---

### 9. Shot Charts (Phase 3)

**Q9.1:** "Get Stephen Curry's shot chart for 2023-24"
- **Expected**: Returns shot coordinates with hexbin aggregation
- **Validates**: Shot chart endpoint, coordinate validation

**Q9.2:** "Show me the Warriors' shot chart with hexbin only"
- **Expected**: Returns aggregated heat map data
- **Validates**: Team shot charts, granularity parameter

**Q9.3:** "Get Damian Lillard's shot chart summary"
- **Expected**: Returns zone summary (paint, mid-range, three-point stats)
- **Validates**: Zone summary calculation

---

### 10. Game Context (Phase 3)

**Q10.1:** "Get game context for Lakers vs Warriors"
- **Expected**: Returns standings, advanced stats, recent form, h2h, narrative
- **Validates**: Multi-source composition, parallel API execution

**Q10.2:** "Show me Celtics vs Heat matchup context"
- **Expected**: Returns comprehensive game preview with narrative
- **Validates**: Narrative synthesis, storyline generation

---

### 11. Natural Language Queries (NLQ)

**Q11.1:** "Who is the best three-point shooter in the league?"
- **Expected**: Interprets query, fetches league leaders by 3P%, returns formatted answer
- **Validates**: NLQ pipeline, intent classification

**Q11.2:** "How many points did LeBron score last game?"
- **Expected**: Fetches recent game log, extracts PTS from latest game
- **Validates**: Recency understanding, data extraction

---

## Running Golden Questions

### Method 1: Via MCP Client (Claude Desktop / VS Code)

1. Connect to NBA MCP server
2. Ask questions naturally in conversation
3. Verify responses match expected results

### Method 2: Via Direct API Call

```bash
# Using MCP inspector tool
npx @modelcontextprotocol/inspector python -m nba_mcp.nba_server

# Then test individual tools
```

### Method 3: Via Python Script

```python
import asyncio
from nba_mcp.nba_server import get_player_stats, get_shot_chart, get_game_context

async def test_golden_questions():
    # Q3.1: Get player stats
    result = await get_player_stats(
        player_name="Stephen Curry",
        season="2023-24"
    )
    print(f"✅ Q3.1: {result}")

    # Q9.1: Get shot chart
    result = await get_shot_chart(
        entity_name="Stephen Curry",
        season="2023-24",
        granularity="hexbin"
    )
    print(f"✅ Q9.1: {result}")

    # Q10.1: Get game context
    result = await get_game_context(
        team1_name="Lakers",
        team2_name="Warriors"
    )
    print(f"✅ Q10.1: {result}")

asyncio.run(test_golden_questions())
```

---

## Expected Behaviors

### Success Criteria

Each question should:
1. **Return valid JSON** - Proper ResponseEnvelope structure
2. **Contain real data** - No fallback values or mock data
3. **Complete in < 3s** - Cold cache performance target
4. **Handle errors gracefully** - Clear error messages if NBA API fails

### Common Issues

**Issue**: "Entity not found" error
- **Cause**: Typo in player/team name
- **Fix**: Check spelling, try partial name

**Issue**: "Rate limit exceeded" error
- **Cause**: Too many requests in short time
- **Fix**: Wait 60 seconds, then retry

**Issue**: Empty data returned
- **Cause**: NBA API flakiness or no data for that query
- **Fix**: Try different season or player

**Issue**: "Season not found" error
- **Cause**: Invalid season format
- **Fix**: Use YYYY-YY format (e.g., "2023-24")

---

## Performance Benchmarks

| Question Category | Expected Latency | Cache Hit Latency |
|-------------------|------------------|-------------------|
| Entity Resolution | < 100ms | < 10ms |
| Live Scores | < 500ms | < 100ms |
| Player Stats | < 1s | < 100ms |
| Shot Charts | < 2s | < 100ms |
| Game Context | < 2s | < 100ms |
| NLQ Pipeline | < 3s | < 1s |

---

## Automation

To automate golden question testing:

```bash
# Run golden questions test suite
python tests/test_golden_questions.py

# Expected output:
# ✅ Q1.1: Entity Resolution - LeBron James
# ✅ Q2.1: Live Scores - Today's games
# ✅ Q3.1: Player Stats - Stephen Curry 2023-24
# ...
# 11/11 golden questions passed ✅
```

---

## Updating Golden Questions

When adding new features:
1. Add corresponding golden question to this document
2. Add test case to `tests/test_golden_questions.py`
3. Update expected results if NBA API changes
4. Verify all questions pass before releasing

---

## Notes

- **Date Sensitivity**: Questions with "today" or "this season" may return different results over time
- **NBA API Flakiness**: shotchartdetail endpoint can be temperamental; retry if needed
- **Season Availability**: Some stats may not be available until season starts
- **Player Movement**: Player team affiliations change; update questions accordingly

---

Last Updated: 2025-10-28
