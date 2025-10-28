# Phase 3 Implementation Analysis
## Shot Charts + Game Context Composition

**Date**: 2025-10-28
**Goal**: Implement remaining Phase 3 features with maximum efficiency

---

## Feature 1: Unified Shot Chart Tool

### Current State Analysis
- **Available Endpoint**: `nba_api.stats.endpoints.shotchartdetail`
- **Required Parameters**: `team_id`, `player_id`, `season_nullable`, `season_type_all_star`
- **Returns**: DataFrame with columns: LOC_X, LOC_Y, SHOT_MADE_FLAG, SHOT_DISTANCE, SHOT_TYPE, etc.
- **Already Documented**: Yes, in `/api_documentation/endpoints.json`

### Efficiency Considerations

#### 1. Data Format Strategy
**Option A**: Return only raw coordinates
- Pros: Simple, complete data
- Cons: Client must do hexbin aggregation

**Option B**: Return only hexbin aggregated
- Pros: Smaller payload, visualization-ready
- Cons: Loses individual shot detail

**Option C** (RECOMMENDED): Return both raw + aggregated
- Pros: Maximum flexibility, one API call
- Cons: Slightly larger payload (but cacheable!)

**Decision**: Option C - Return both formats in ResponseEnvelope

#### 2. Entity Resolution Reuse
**Existing**: `entity_resolver.resolve_entity()` already handles fuzzy matching
**Efficiency**: Reuse this instead of duplicating logic
**Benefit**: Consistent entity resolution across all tools

#### 3. Caching Strategy
**TTL**: Historical shot charts = HISTORICAL tier (24 hours)
**TTL**: Current season = DAILY tier (1 hour)
**Key**: `{tool_name}:{player_id}:{season}:{season_type}:{granularity}`
**Benefit**: Shot data rarely changes, heavy caching appropriate

#### 4. Hexbin Aggregation Algorithm
**Approach**: Use numpy for performance
- Create 2D grid (50x50 bins covering court dimensions)
- Map each shot to grid cell: `bin_x = (LOC_X + 250) // 10`
- Aggregate: count shots per bin, calculate FG% per bin
- Filter: Only return bins with min 5 shots (statistical significance)

**Performance**: O(n) where n = number of shots (~100-500 per season)
**Memory**: Minimal (50x50 = 2,500 cells max)

#### 5. Court Coordinate System
**NBA API Coordinates**:
- Origin (0, 0) = center of basket
- X-axis: -250 to +250 (left to right, in tenths of feet)
- Y-axis: -52.5 to +417.5 (baseline to opposite baseline)
- Units: Tenths of feet (divide by 10 for feet)

**Validation**: Check LOC_X in [-250, 250], LOC_Y in [-52.5, 417.5]

---

## Feature 2: Game Context Composition

### Current State Analysis
**Existing Tools Available**:
1. `get_team_standings` - Current standings with W-L, GB, streak
2. `get_team_advanced_stats` - OffRtg, DefRtg, Pace, NetRtg
3. `get_date_range_game_log_or_team_game_log` - Game-by-game results (for recent form)
4. `get_live_scores` - Today's games with scores
5. `resolve_nba_entity` - Fuzzy team name matching

**Missing**:
- Head-to-head record (can derive from game logs)
- Injury report (NBA API doesn't have official endpoint, would need external source)

### Efficiency Considerations

#### 1. Parallel Execution Pattern
**Approach**: Use `asyncio.gather()` to fetch all data concurrently
```python
standings, advanced, recent_form, h2h = await asyncio.gather(
    get_standings_for_teams(team1, team2),
    get_advanced_stats_for_teams(team1, team2),
    get_recent_form(team1, team2, last_n=10),
    get_head_to_head(team1, team2, season),
    return_exceptions=True  # Graceful degradation
)
```

**Performance**: 4x speedup vs sequential calls
**Latency**: p95 < 500ms with cache hits, <2s with cache misses

#### 2. Graceful Degradation
**Strategy**: If any data source fails, return partial context
**Implementation**:
- Check each result for exceptions
- Build context with available data
- Note missing data in response metadata

**Example**:
```json
{
  "status": "partial",
  "data": {
    "standings": {...},
    "recent_form": {...}
  },
  "metadata": {
    "missing_data": ["injuries", "h2h"],
    "partial_reason": "H2H: No games played this season"
  }
}
```

#### 3. Caching Strategy
**Component TTLs**:
- Standings: DAILY (1 hour) - changes daily
- Advanced stats: DAILY (1 hour) - changes daily
- Recent form: DAILY (1 hour) - changes after each game
- H2H record: DAILY (1 hour) - changes after each game

**Cache Keys**:
- `game_context:{team1_id}:{team2_id}:{date}:standings`
- `game_context:{team1_id}:{team2_id}:{date}:form`
- `game_context:{team1_id}:{team2_id}:{season}:h2h`

**Benefit**: Repeated queries for same matchup (e.g., pre-game analysis) served from cache

#### 4. Data Synthesis Strategy
**Output Format**: Markdown narrative + structured data
**Sections**:
1. **Matchup Header**: "Team A (W-L, Rank) vs Team B (W-L, Rank)"
2. **Season Series**: "Team A leads series 2-1 this season"
3. **Recent Form**: "Team A: 7-3 last 10 | Team B: 4-6 last 10"
4. **Statistical Edge**: "Team A: +5.2 NetRtg advantage"
5. **Key Storylines**: Auto-generated based on data (e.g., "Team A on 5-game win streak")

**Narrative Generation**:
- Template-based (no LLM needed)
- Rules-based storylines (e.g., streak >= 5 games = "on fire")
- Comparison logic (e.g., if NetRtg diff > 5 = "significant advantage")

#### 5. Head-to-Head Calculation
**Approach**: Filter game logs for games between both teams
```python
def get_head_to_head(team1_id, team2_id, season):
    # Get team1's games
    team1_log = await get_game_log(team1_id, season)
    # Filter for games vs team2
    h2h_games = team1_log[team1_log['MATCHUP'].str.contains(team2_abbrev)]
    # Calculate record
    wins = (h2h_games['WL'] == 'W').sum()
    losses = (h2h_games['WL'] == 'L').sum()
    return {"wins": wins, "losses": losses, "games": h2h_games}
```

**Performance**: O(n) where n = ~82 games per season
**Optimization**: Cache game logs separately (reused across tools)

---

## Code Reuse Opportunities

### 1. Entity Resolution (100% Reuse)
- Already implemented in `entity_resolver.py`
- No need to duplicate player/team matching logic
- Consistent confidence scoring across all tools

### 2. Response Envelope (100% Reuse)
- Already implemented in `models.py`
- Use `success_response()`, `error_response()`, `partial_response()`
- No need to create new response formats

### 3. Error Handling (100% Reuse)
- Already implemented in `errors.py`
- Use `@retry_with_backoff` decorator
- Use enhanced error classes (EntityNotFoundError, etc.)

### 4. Caching Infrastructure (100% Reuse)
- Already implemented in `cache/redis_cache.py`
- Use `@cached` decorator with appropriate TTL tiers
- No need to add new caching logic

### 5. Rate Limiting (100% Reuse)
- Already implemented in `rate_limit/token_bucket.py`
- Use `@rate_limited` decorator
- No need to add new rate limit logic

### 6. Parameter Validation (100% Reuse)
- Already implemented in `schemas/tool_params.py` pattern
- Create new Pydantic models following existing pattern
- Automatic JSON Schema generation

### 7. Season Normalization (100% Reuse)
- Already implemented in `tools/nba_api_utils.py`
- Use `normalize_season()` for consistent season format
- No need to duplicate validation

---

## Integration Points

### New Modules to Create
1. `nba_mcp/api/shot_charts.py` - Shot chart data fetching and aggregation
2. `nba_mcp/api/game_context.py` - Game context composition logic

### Existing Modules to Update
1. `nba_mcp/nba_server.py` - Add 2 new MCP tools:
   - `get_shot_chart(entity, entity_type, season, granularity)`
   - `get_game_context(team1, team2, date)`

2. `nba_mcp/schemas/tool_params.py` - Add 2 new Pydantic models:
   - `GetShotChartParams`
   - `GetGameContextParams`

3. `nba_mcp/schemas/publisher.py` - Register new tools in TOOL_REGISTRY

### No Changes Required (Reuse)
- `nba_mcp/api/models.py` - Response envelope (already sufficient)
- `nba_mcp/api/errors.py` - Error handling (already comprehensive)
- `nba_mcp/api/entity_resolver.py` - Entity matching (already working)
- `nba_mcp/cache/` - Caching (already working)
- `nba_mcp/rate_limit/` - Rate limiting (already working)

---

## Testing Strategy

### Unit Tests
1. **Shot Chart Aggregation**:
   - Test hexbin algorithm with known coordinates
   - Test edge cases (no shots, single shot)
   - Test coordinate validation

2. **Game Context Composition**:
   - Test parallel execution with mock tools
   - Test graceful degradation (one tool fails)
   - Test h2h calculation logic

### Integration Tests
1. **Shot Charts**:
   - Fetch real data for known player (Stephen Curry)
   - Validate coordinate ranges
   - Validate hexbin aggregation correctness

2. **Game Context**:
   - Fetch real data for known matchup (Lakers vs Celtics)
   - Validate all components present
   - Validate narrative generation

### Golden Tests
Add to existing golden test suite:
- Query: "Show me Curry's shot chart from 2023-24"
- Query: "Lakers vs Warriors game context"
- Validate response structure and performance budgets

---

## Performance Targets

### Shot Charts
- **Cold Cache**: < 2s p95 latency
- **Warm Cache**: < 100ms p95 latency
- **Payload Size**: < 50KB (raw) + < 10KB (hexbin)
- **Rate Limit**: 30 requests/min (complex tool tier)

### Game Context
- **Cold Cache**: < 3s p95 latency (parallel execution)
- **Warm Cache**: < 150ms p95 latency
- **Payload Size**: < 20KB (markdown + structured)
- **Rate Limit**: 30 requests/min (complex tool tier)

---

## Dependencies

### Required (Already Installed)
- `nba-api>=1.4.0` - ShotChartDetail endpoint
- `pandas>=2.0.0` - DataFrame operations
- `numpy>=1.24.0` - Hexbin aggregation
- `asyncio` (stdlib) - Parallel execution

### Optional (For Visualization)
- `matplotlib>=3.7.0` - Court visualization
- `plotly>=5.18.0` - Interactive shot charts

**Decision**: Make visualization optional (not in core tool)
**Reason**: Keep tool fast and dependency-light. Visualization can be client-side.

---

## Implementation Priorities

### Priority 1: Shot Charts (Day 1-2)
**Reason**: Standalone feature, no dependencies on other tools
**Complexity**: Medium (hexbin aggregation)
**Value**: High (unique feature, not available in other tools)

### Priority 2: Game Context (Day 2-3)
**Reason**: Builds on existing tools, composition logic
**Complexity**: Medium (parallel execution, graceful degradation)
**Value**: High (comprehensive analysis, unique value proposition)

### Priority 3: Tests & Documentation (Day 3)
**Reason**: Ensure quality and usability
**Complexity**: Low (follow existing patterns)
**Value**: Critical (no feature without tests)

---

## Success Criteria

### Shot Charts
- ✅ Returns both raw coordinates and hexbin aggregated data
- ✅ Supports player AND team queries
- ✅ Entity resolution via fuzzy matching
- ✅ Proper caching (HISTORICAL/DAILY tiers)
- ✅ Rate limiting (30/min tier)
- ✅ Response envelope format
- ✅ < 2s p95 latency (cold cache)
- ✅ < 100ms p95 latency (warm cache)
- ✅ 100% test coverage on aggregation logic

### Game Context
- ✅ Parallel execution (4+ concurrent API calls)
- ✅ Graceful degradation (partial responses on errors)
- ✅ Includes: standings, advanced stats, recent form, h2h record
- ✅ Markdown narrative synthesis
- ✅ Proper caching (DAILY tier)
- ✅ Rate limiting (30/min tier)
- ✅ Response envelope format
- ✅ < 3s p95 latency (cold cache)
- ✅ < 150ms p95 latency (warm cache)
- ✅ 100% test coverage on composition logic

---

## Risks & Mitigation

### Risk 1: Shot Chart Data Volume
**Risk**: Large payloads for players with many shots (Curry ~1000+ per season)
**Mitigation**:
- Offer granularity parameter: "summary" returns only hexbin, "full" returns both
- Compress hexbin data (filter bins with < 5 shots)
- Use gzip compression in HTTP response

### Risk 2: NBA API Rate Limits
**Risk**: Multiple API calls for game context could trigger rate limits
**Mitigation**:
- Heavy caching (1 hour TTL for all components)
- Rate limit at 30/min (conservative)
- Circuit breaker pattern (already implemented)
- Graceful degradation (return partial data)

### Risk 3: Coordinate System Complexity
**Risk**: NBA court coordinates are non-standard (tenths of feet)
**Mitigation**:
- Document coordinate system clearly
- Validate all coordinates in range
- Provide helper functions for conversion (to_feet, to_meters)
- Example visualizations in documentation

### Risk 4: H2H Data Sparsity
**Risk**: Early season, teams haven't played yet (0-0 record)
**Mitigation**:
- Check if h2h_games empty
- Return "No games played this season" message
- Offer previous season h2h as fallback
- Graceful degradation in narrative

---

## Next Steps

1. ✅ Create detailed implementation plan (this document)
2. ⏳ Implement shot_charts.py module
3. ⏳ Implement game_context.py module
4. ⏳ Add MCP tools to nba_server.py
5. ⏳ Add parameter models to tool_params.py
6. ⏳ Register tools in publisher.py
7. ⏳ Write unit tests
8. ⏳ Write integration tests
9. ⏳ Add to golden test suite
10. ⏳ Update CHANGELOG.md
11. ⏳ Commit and push

---

**Estimated Effort**: 2-3 days (16-24 hours)
**Risk Level**: Low (building on solid foundation, reusing 90% of infrastructure)
**Dependencies**: None (all prerequisites already in place)
**Blockers**: None
