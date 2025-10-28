# NBA MCP Standardization & Enhancement Plan

## Date: 2025-10-28
## Goal: Make NBA MCP the most robust, standardized, and comprehensive NBA API tool

---

## Overview

This plan addresses the remaining improvements from the original roadmap to make NBA MCP:
1. **Standardized**: Easy to use with any LLM (GPT, Claude, Gemini)
2. **Comprehensive**: Answer any NBA question
3. **Reliable**: Handle schema changes and API issues gracefully
4. **Professional**: Follow best practices for production APIs

---

## Phase 1: Standardization (High Priority)

### 1.1 Publish JSON Schemas ✅ NEXT

**Goal**: Make all tool schemas available for LLM function calling

**Implementation**:
```python
# nba_mcp/schemas/publish.py
def export_schemas():
    """Export all tool schemas as JSON Schema files."""
    schemas = {
        "resolve_entity": ResolveEntityParams.model_json_schema(),
        "get_team_standings": GetTeamStandingsParams.model_json_schema(),
        "get_player_stats": GetPlayerStatsParams.model_json_schema(),
        # ... all tools
    }

    # Write to schemas/ directory
    for name, schema in schemas.items():
        with open(f"schemas/{name}.json", "w") as f:
            json.dump(schema, f, indent=2)
```

**Benefits**:
- LLMs can discover and use tools automatically
- Stable API contracts
- OpenAPI/Swagger compatibility
- Better documentation

**Files to Create**:
- `nba_mcp/schemas/__init__.py`
- `nba_mcp/schemas/publish.py`
- `schemas/*.json` (exported schemas)
- `schemas/openapi.yaml` (OpenAPI spec)

### 1.2 Versioning Support

**Goal**: Allow v1 and v2 to coexist during breaking changes

**Implementation**:
```python
# All responses include version in metadata
class ResponseMetadata(BaseModel):
    version: str = "v1"  # ✓ Already implemented
    schema_version: str = "2024-01"  # Add schema version

# Tool naming convention
@mcp_server.tool()
async def get_player_stats_v1(...):  # Explicit version
    pass

@mcp_server.tool()
async def get_player_stats(...):  # Always points to latest
    return await get_player_stats_v1(...)
```

**Benefits**:
- Backward compatibility
- Gradual migration for users
- Clear deprecation path

### 1.3 User-Agent and Referer Headers

**Goal**: Be a good API citizen, avoid rate limiting

**Implementation**:
```python
# nba_mcp/api/client.py
HEADERS = {
    "User-Agent": "NBA-MCP/1.0.0 (https://github.com/your-org/nba_mcp)",
    "Referer": "https://stats.nba.com",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9"
}

class NBAApiClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
```

**Benefits**:
- Reduced risk of IP bans
- Better rate limit treatment
- Professional API usage

---

## Phase 2: Reliability Enhancements

### 2.1 Schema Drift Detection

**Goal**: Detect when NBA API changes schema, handle gracefully

**Implementation**:
```python
# nba_mcp/api/schema_validator.py
class SchemaValidator:
    """Validates NBA API responses against expected schemas."""

    def __init__(self):
        self.expected_schemas = load_expected_schemas()

    def validate(self, endpoint: str, response: dict) -> ValidationResult:
        """Validate response against expected schema."""
        expected = self.expected_schemas[endpoint]

        # Check required fields
        missing = set(expected["required"]) - set(response.keys())
        if missing:
            raise UpstreamSchemaError(
                endpoint=endpoint,
                missing_fields=list(missing),
                message=f"NBA API schema changed: missing {missing}"
            )

        # Check field types
        for field, expected_type in expected["types"].items():
            if field in response:
                actual_type = type(response[field]).__name__
                if actual_type != expected_type:
                    warnings.warn(f"Type mismatch: {field} expected {expected_type}, got {actual_type}")

        return ValidationResult(valid=True, warnings=[...])

# Usage in client
@retry_with_backoff(max_retries=3)
async def fetch_player_stats(player_id: int):
    response = await nba_api.playercareerstats(player_id)
    validator.validate("playercareerstats", response)
    return response
```

**Benefits**:
- Early detection of API changes
- Graceful degradation (warnings vs errors)
- Automatic alerts when schema drifts

### 2.2 Graceful Degradation

**Goal**: Return partial data if non-critical fields missing

**Implementation**:
```python
def extract_player_stats(response: dict) -> PlayerStats:
    """Extract stats with fallbacks for missing fields."""
    try:
        # Core fields (required)
        stats = {
            "ppg": response["PTS"],
            "rpg": response["REB"],
            "apg": response["AST"],
        }

        # Optional fields (best-effort)
        optional = {
            "ts_pct": response.get("TS_PCT", None),
            "usg_pct": response.get("USG_PCT", None),
            "pie": response.get("PIE", None),
        }
        stats.update({k: v for k, v in optional.items() if v is not None})

        return PlayerStats(**stats)
    except KeyError as e:
        # Raise with partial data
        raise PartialDataError(
            available_data=stats,
            missing_fields=[str(e)],
            message=f"Some stats unavailable: {e}"
        )
```

**Benefits**:
- Better user experience (some data > no data)
- Resilience to minor API changes
- Clear communication about missing data

---

## Phase 3: Feature Enhancements

### 3.1 Unified Shot Chart Tool

**Goal**: Single tool for all shot chart needs

**Design**:
```python
@mcp_server.tool()
async def get_shot_chart(
    entity: str,  # Player or team name
    entity_type: Literal["player", "team"] = "player",
    season: str = "2023-24",
    season_type: Literal["Regular Season", "Playoffs"] = "Regular Season",
    granularity: Literal["raw", "hex", "both"] = "both"
) -> str:
    """
    Get shot chart data for a player or team.

    Returns:
    - raw: Individual shot coordinates with make/miss
    - hex: Hexbin aggregated shooting percentages
    - both: Both raw and hex data

    Example:
        get_shot_chart("Stephen Curry", granularity="hex")
        → Returns hexbin data showing shooting efficiency by zone
    """
    # Implementation...
```

**Features**:
- Dual format (raw coordinates + hexbin aggregation)
- Player and team support
- Season and playoff filtering
- Optional visualization (if matplotlib available)

### 3.2 Era-Adjusted Statistics

**Goal**: Compare players across eras fairly

**Implementation**:
```python
def adjust_for_era(stats: dict, season: str) -> dict:
    """Adjust stats for league-wide pace and scoring."""
    league_avg = get_league_averages(season)

    # Pace adjustment
    adjusted_ppg = stats["ppg"] * (100 / league_avg["pace"])

    # Scoring environment adjustment
    era_factor = league_avg["ppg"] / 100  # League scoring vs baseline
    normalized_ppg = adjusted_ppg / era_factor

    return {
        "ppg_raw": stats["ppg"],
        "ppg_adjusted": normalized_ppg,
        "era_factor": era_factor,
        "pace_adjustment": 100 / league_avg["pace"]
    }

@mcp_server.tool()
async def compare_players_era_adjusted(
    player1: str,
    player2: str,
    season1: str = "2023-24",
    season2: str = "2023-24"
) -> str:
    """Compare players with era adjustments."""
    stats1 = await get_player_stats(player1, season1)
    stats2 = await get_player_stats(player2, season2)

    adj1 = adjust_for_era(stats1, season1)
    adj2 = adjust_for_era(stats2, season2)

    # Return comparison...
```

**Benefits**:
- Fair MJ vs LeBron comparisons
- Account for pace changes (90s vs 2020s)
- Account for scoring environment changes

### 3.3 Game Context Composition

**Goal**: Rich context for game analysis

**Implementation**:
```python
@mcp_server.tool()
async def get_game_context(
    team1: str,
    team2: str,
    date: str = "today"
) -> str:
    """
    Get comprehensive game context combining multiple data sources.

    Returns:
    - Current standings (both teams)
    - Recent form (last 10 games)
    - Head-to-head record this season
    - Injury report (if available)
    - Key storylines

    Example:
        get_game_context("Lakers", "Warriors")
        → Returns formatted analysis with all context
    """
    # Parallel fetch all data
    standings, recent_form, h2h, injuries = await asyncio.gather(
        get_standings_for_teams(team1, team2),
        get_recent_form(team1, team2, games=10),
        get_head_to_head(team1, team2),
        get_injury_report(team1, team2),
        return_exceptions=True
    )

    # Synthesize into narrative
    context = synthesize_game_context(
        standings=standings,
        form=recent_form,
        h2h=h2h,
        injuries=injuries
    )

    return context
```

**Features**:
- Parallel data fetching (fast)
- Graceful degradation if some data unavailable
- Rich narrative output
- Useful for betting analysis, fantasy, or just understanding the game

---

## Phase 4: Comprehensive Coverage

### 4.1 Missing Tools

**Tools to Add**:
1. `get_player_game_log` - Game-by-game performance
2. `get_team_game_log` - Team game-by-game performance
3. `get_player_splits` - Performance by various splits (home/away, month, opponent)
4. `get_lineup_stats` - 5-man lineup statistics
5. `get_play_by_play` - Detailed play-by-play data
6. `get_box_score` - Traditional and advanced box scores
7. `search_players` - Full-text search across all players
8. `search_games` - Find games by criteria

### 4.2 Advanced Queries

**Support for Complex Questions**:
- "Who has the most clutch points this season?" (4th quarter, <5 min, <5 pt diff)
- "Best +/- in wins against winning teams"
- "Shooting % on back-to-backs"
- "Performance in nationally televised games"

**Implementation**: Add query modifiers to NLQ parser

---

## Implementation Priority

### Phase 1: Week 5 (Standardization)
1. ✅ Export JSON Schemas (Day 1-2)
2. ✅ Add UA/Referer headers (Day 1)
3. ✅ Schema drift detection (Day 2-3)
4. ✅ Versioning support (Day 3)

### Phase 2: Week 6 (Reliability)
5. ✅ Graceful degradation (Day 1-2)
6. ✅ Enhanced error messages (Day 2)
7. ✅ Monitoring for schema drift (Day 3)

### Phase 3: Week 7 (Features)
8. ✅ Shot chart tool (Day 1-3)
9. ✅ Era-adjusted stats (Day 3-4)
10. ✅ Game context composition (Day 4-5)

### Phase 4: Week 8+ (Expansion)
11. ✅ Additional tools (ongoing)
12. ✅ Advanced queries (ongoing)
13. ✅ LangGraph integration (when ready)

---

## Testing Strategy

### For Each Phase
1. **Unit tests**: Test individual functions
2. **Integration tests**: Test with real NBA API (limited)
3. **Golden tests**: Add to golden test suite
4. **Documentation**: Update README and examples
5. **Validation**: Run validation script

### Success Metrics
- **Standardization**: All tools have published JSON Schemas
- **Reliability**: Handle 95%+ API responses gracefully
- **Coverage**: Answer 90%+ of common NBA questions
- **Performance**: Maintain <1s p95 latency with cache

---

## Next Steps

1. Start with JSON Schema export (highest value)
2. Add UA headers (quick win)
3. Implement schema validation (critical for reliability)
4. Add versioning (foundation for future changes)
5. Expand tool coverage based on user feedback

---

## Success Criteria

✅ **Standardization**
- [ ] All 20+ tools have published JSON Schemas
- [ ] OpenAPI spec generated
- [ ] Versioning system in place
- [ ] Compatible with GPT, Claude, Gemini

✅ **Reliability**
- [ ] Schema drift detection with alerts
- [ ] Graceful degradation for partial data
- [ ] 95%+ success rate on API calls
- [ ] Clear error messages with suggestions

✅ **Coverage**
- [ ] 30+ tools covering all major NBA data
- [ ] Shot charts with visualization
- [ ] Era-adjusted comparisons
- [ ] Game context composition
- [ ] Answer 90%+ of common questions

✅ **Quality**
- [ ] All tests passing
- [ ] Documentation complete
- [ ] CI/CD pipeline green
- [ ] Production deployment successful

---

**Status**: Ready to begin Phase 1
**Estimated Completion**: 4 weeks for all phases
**Risk Level**: Low (building on solid foundation)
