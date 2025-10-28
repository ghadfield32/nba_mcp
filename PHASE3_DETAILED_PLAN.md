# Phase 3 Detailed Implementation Plan
## Shot Charts + Game Context Composition

**Date**: 2025-10-28
**Approach**: Incremental implementation with testing at each step

---

## Implementation Order (Minimize Risk)

### Phase A: Shot Charts (Days 1-2)
1. Create core shot_charts.py module
2. Add MCP tool to nba_server.py
3. Add parameter model to tool_params.py
4. Register in publisher.py
5. Write tests
6. Format and validate

### Phase B: Game Context (Days 2-3)
1. Create core game_context.py module
2. Add MCP tool to nba_server.py
3. Add parameter model to tool_params.py
4. Register in publisher.py
5. Write tests
6. Format and validate

### Phase C: Documentation & Finalization (Day 3)
1. Update CHANGELOG.md
2. Create comprehensive test suite
3. Run golden tests
4. Format all code
5. Commit and push

---

## Detailed File-by-File Changes

### File 1: `nba_mcp/api/shot_charts.py` (NEW)

**Purpose**: Core shot chart data fetching and aggregation logic

**Functions to Implement**:

```python
# 1. Data Fetching
async def fetch_shot_chart_data(
    entity_id: int,
    entity_type: Literal["player", "team"],
    season: str,
    season_type: str = "Regular Season",
) -> pd.DataFrame:
    """
    Fetch raw shot chart data from NBA API.

    Uses nba_api.stats.endpoints.shotchartdetail.

    Args:
        entity_id: Player ID or Team ID
        entity_type: "player" or "team"
        season: Season in YYYY-YY format
        season_type: "Regular Season", "Playoffs", etc.

    Returns:
        DataFrame with columns: LOC_X, LOC_Y, SHOT_MADE_FLAG, SHOT_DISTANCE,
        SHOT_TYPE, PERIOD, MINUTES_REMAINING, SECONDS_REMAINING, etc.

    Raises:
        NBAApiError: If API call fails after retries
        InvalidParameterError: If parameters invalid
    """
    # Implementation here
    pass


# 2. Coordinate Validation
def validate_shot_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Validate and filter shot coordinates.

    NBA court coordinates:
    - X-axis: -250 to +250 (left to right, tenths of feet)
    - Y-axis: -52.5 to +417.5 (baseline to opposite baseline)

    Args:
        df: DataFrame with LOC_X and LOC_Y columns

    Returns:
        Filtered DataFrame with only valid coordinates

    Logs:
        Warning for any invalid coordinates found
    """
    # Implementation here
    pass


# 3. Hexbin Aggregation
def aggregate_to_hexbin(
    shots: pd.DataFrame,
    grid_size: int = 10,
    min_shots: int = 5
) -> List[Dict[str, Any]]:
    """
    Aggregate shots into hexagonal bins.

    Algorithm:
    1. Create 2D grid (default: 10 ft × 10 ft bins)
    2. Map each shot to grid cell: bin_x = (LOC_X + 250) // grid_size
    3. Group shots by cell, calculate FG% per cell
    4. Filter cells with < min_shots (statistical significance)

    Args:
        shots: DataFrame with LOC_X, LOC_Y, SHOT_MADE_FLAG
        grid_size: Size of each bin in tenths of feet (default: 10 = 1 foot)
        min_shots: Minimum shots per bin to include (default: 5)

    Returns:
        List of bins with structure:
        {
            "bin_x": int,  # X coordinate of bin center
            "bin_y": int,  # Y coordinate of bin center
            "shot_count": int,  # Number of shots in bin
            "made_count": int,  # Number of makes in bin
            "fg_pct": float,  # Field goal percentage (0.0-1.0)
            "distance_avg": float,  # Average shot distance in feet
        }

    Example:
        >>> shots = pd.DataFrame({
        ...     'LOC_X': [0, 5, 10, 15, 20],
        ...     'LOC_Y': [0, 5, 10, 15, 20],
        ...     'SHOT_MADE_FLAG': [1, 0, 1, 1, 0],
        ...     'SHOT_DISTANCE': [10, 12, 15, 18, 20]
        ... })
        >>> bins = aggregate_to_hexbin(shots, grid_size=10, min_shots=2)
    """
    # Implementation here
    pass


# 4. Shot Zone Summary
def calculate_zone_summary(shots: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculate summary statistics by shot zone.

    Zones:
    - Paint: Distance < 8 feet
    - Short Mid-Range: 8-16 feet
    - Long Mid-Range: 16-23.75 feet (non-3PT)
    - Three-Point: Distance >= 23.75 feet (corner = 22 feet)

    Args:
        shots: DataFrame with SHOT_DISTANCE, SHOT_MADE_FLAG

    Returns:
        Dict with zone-level statistics:
        {
            "paint": {"attempts": int, "made": int, "pct": float},
            "short_mid": {...},
            "long_mid": {...},
            "three": {...},
            "overall": {...}
        }
    """
    # Implementation here
    pass


# 5. Main Entry Point
async def get_shot_chart(
    entity_name: str,
    entity_type: Literal["player", "team"],
    season: str,
    season_type: str = "Regular Season",
    granularity: Literal["raw", "hexbin", "both", "summary"] = "both",
) -> Dict[str, Any]:
    """
    Get shot chart data with optional hexbin aggregation.

    This is the main entry point called by the MCP tool.

    Args:
        entity_name: Player or team name (fuzzy matching supported)
        entity_type: "player" or "team"
        season: Season in YYYY-YY format (e.g., "2023-24")
        season_type: "Regular Season", "Playoffs", etc.
        granularity: Output format
            - "raw": Individual shot coordinates only
            - "hexbin": Aggregated hexbin data only
            - "both": Both raw and hexbin (default)
            - "summary": Zone summary statistics only

    Returns:
        Dict with structure based on granularity:
        {
            "entity": {"id": int, "name": str, "type": str},
            "season": str,
            "season_type": str,
            "raw_shots": List[Dict] (if granularity includes raw),
            "hexbin": List[Dict] (if granularity includes hexbin),
            "zone_summary": Dict (if granularity includes summary),
            "metadata": {
                "total_shots": int,
                "made_shots": int,
                "fg_pct": float,
                "coordinate_system": str,
            }
        }

    Raises:
        EntityNotFoundError: If entity not found
        InvalidParameterError: If parameters invalid
        NBAApiError: If API call fails
    """
    # Implementation here
    pass
```

**Decorators to Apply**:
- `@retry_with_backoff` on `fetch_shot_chart_data`
- `@cached(tier=CacheTier.HISTORICAL)` on `get_shot_chart` for past seasons
- `@rate_limited(tool_name="get_shot_chart")` on `get_shot_chart`

**Dependencies**:
- `from nba_api.stats.endpoints import shotchartdetail`
- `import pandas as pd`
- `import numpy as np`
- `from typing import Any, Dict, List, Literal`
- `from ..entity_resolver import resolve_entity`
- `from ..errors import EntityNotFoundError, InvalidParameterError, NBAApiError, retry_with_backoff`
- `from ..tools.nba_api_utils import normalize_season`

**Estimated Lines**: 400-500

---

### File 2: `nba_mcp/api/game_context.py` (NEW)

**Purpose**: Game context composition with parallel execution

**Functions to Implement**:

```python
# 1. Standings Component
async def fetch_standings_context(
    team1_id: int,
    team2_id: int,
    season: str
) -> Dict[str, Any]:
    """
    Fetch standings for both teams.

    Calls existing get_team_standings tool internally.

    Returns:
        {
            "team1": {
                "wins": int, "losses": int,
                "conference_rank": int, "division_rank": int,
                "games_behind": float
            },
            "team2": {...}
        }
    """
    # Implementation here
    pass


# 2. Advanced Stats Component
async def fetch_advanced_stats_context(
    team1_id: int,
    team2_id: int,
    season: str
) -> Dict[str, Any]:
    """
    Fetch advanced stats for both teams.

    Calls existing get_team_advanced_stats tool internally.

    Returns:
        {
            "team1": {
                "off_rtg": float, "def_rtg": float,
                "net_rtg": float, "pace": float
            },
            "team2": {...}
        }
    """
    # Implementation here
    pass


# 3. Recent Form Component
async def fetch_recent_form(
    team_id: int,
    season: str,
    last_n: int = 10
) -> Dict[str, Any]:
    """
    Fetch recent game results for a team.

    Calls existing get_date_range_game_log_or_team_game_log tool internally.

    Returns:
        {
            "wins": int,
            "losses": int,
            "streak": {"type": "W" or "L", "length": int},
            "games": List[Dict] (last N games)
        }
    """
    # Implementation here
    pass


# 4. Head-to-Head Component
async def fetch_head_to_head(
    team1_id: int,
    team2_id: int,
    season: str
) -> Dict[str, Any]:
    """
    Calculate head-to-head record this season.

    Algorithm:
    1. Fetch team1's game log for season
    2. Filter for games vs team2
    3. Calculate W-L record

    Returns:
        {
            "team1_wins": int,
            "team2_wins": int,
            "games_played": int,
            "games": List[Dict] (all h2h games this season)
        }

    Note: Returns empty dict if no games played yet
    """
    # Implementation here
    pass


# 5. Narrative Synthesis
def synthesize_narrative(
    team1_name: str,
    team2_name: str,
    standings: Dict,
    advanced: Dict,
    form1: Dict,
    form2: Dict,
    h2h: Dict
) -> str:
    """
    Synthesize game context into readable markdown narrative.

    Template sections:
    1. Matchup header (ranks, records)
    2. Season series (h2h record)
    3. Recent form (last 10 games, streaks)
    4. Statistical edge (net rating comparison)
    5. Key storylines (auto-generated based on data)

    Args:
        team1_name: First team name
        team2_name: Second team name
        standings: Standings context dict
        advanced: Advanced stats context dict
        form1: Team 1 recent form dict
        form2: Team 2 recent form dict
        h2h: Head-to-head record dict

    Returns:
        Markdown formatted narrative

    Example Output:
        # Lakers (34-28, 9th West) vs Warriors (32-30, 10th West)

        ## Season Series
        Series tied 2-2

        ## Recent Form
        - Lakers: 7-3 in last 10 (Won 3)
        - Warriors: 4-6 in last 10 (Lost 2)

        ## Statistical Edge
        Lakers hold +3.5 Net Rating advantage
        - Lakers: +2.1 Net Rating (112.5 OffRtg, 110.4 DefRtg)
        - Warriors: -1.4 Net Rating (111.2 OffRtg, 112.6 DefRtg)

        ## Key Storylines
        - Lakers on 3-game win streak
        - Warriors struggling defensively (112.6 DefRtg)
    """
    # Implementation here
    pass


# 6. Main Entry Point
async def get_game_context(
    team1_name: str,
    team2_name: str,
    season: Optional[str] = None,
    date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get comprehensive game context for a matchup.

    Fetches data from multiple sources in parallel:
    1. Team standings (both teams)
    2. Team advanced stats (both teams)
    3. Recent form (last 10 games, both teams)
    4. Head-to-head record (this season)

    Args:
        team1_name: First team name (fuzzy matching supported)
        team2_name: Second team name (fuzzy matching supported)
        season: Season in YYYY-YY format (defaults to current)
        date: Date in YYYY-MM-DD format (for future use, not yet implemented)

    Returns:
        {
            "matchup": {
                "team1": {"name": str, "id": int},
                "team2": {"name": str, "id": int}
            },
            "standings": Dict,
            "advanced_stats": Dict,
            "recent_form": {
                "team1": Dict,
                "team2": Dict
            },
            "head_to_head": Dict,
            "narrative": str (markdown formatted),
            "metadata": {
                "components_loaded": List[str],
                "components_failed": List[str]
            }
        }

    Raises:
        EntityNotFoundError: If team not found
        PartialDataError: If some components fail (returns partial context)

    Note: Uses asyncio.gather with return_exceptions=True for graceful degradation
    """
    # Implementation here
    pass
```

**Decorators to Apply**:
- `@retry_with_backoff` on component fetchers
- `@cached(tier=CacheTier.DAILY)` on `get_game_context`
- `@rate_limited(tool_name="get_game_context")` on `get_game_context`

**Dependencies**:
- `import asyncio`
- `from typing import Any, Dict, List, Optional`
- `from ..entity_resolver import resolve_entity`
- `from ..errors import EntityNotFoundError, PartialDataError, retry_with_backoff`
- `from ..advanced_stats import get_team_standings, get_team_advanced_stats`
- `from ..client import NBAApiClient`
- `from ..tools.nba_api_utils import normalize_season`

**Estimated Lines**: 500-600

---

### File 3: `nba_mcp/nba_server.py` (MODIFY)

**Changes to Make**:

#### Addition 1: Import new modules (at top)
```python
# Line ~60 (after existing imports)
from nba_mcp.api.game_context import get_game_context as fetch_game_context
from nba_mcp.api.shot_charts import get_shot_chart as fetch_shot_chart
```

#### Addition 2: Shot Chart MCP Tool (after compare_players_era_adjusted, ~line 1150)
```python
@mcp_server.tool()
async def get_shot_chart(
    entity_name: str,
    entity_type: Literal["player", "team"] = "player",
    season: Optional[str] = None,
    season_type: Literal["Regular Season", "Playoffs"] = "Regular Season",
    granularity: Literal["raw", "hexbin", "both", "summary"] = "both",
) -> str:
    """
    Get shot chart data for a player or team.

    Returns shooting data with coordinates and optional hexbin aggregation.
    Perfect for visualizing shooting patterns and hot zones.

    Args:
        entity_name: Player or team name (e.g., "Stephen Curry", "Warriors")
        entity_type: "player" or "team" (default: "player")
        season: Season in 'YYYY-YY' format (e.g., "2023-24"). If None, uses current season.
        season_type: "Regular Season" or "Playoffs" (default: "Regular Season")
        granularity: Output format:
            - "raw": Individual shot coordinates (X, Y, make/miss)
            - "hexbin": Aggregated data (50x50 grid with FG% per zone)
            - "both": Both raw and hexbin data (default)
            - "summary": Zone summary (paint, mid-range, three-point stats)

    Returns:
        JSON string with ResponseEnvelope containing:
        - raw_shots: List of shot coordinates (if granularity includes raw)
        - hexbin: List of bins with FG% (if granularity includes hexbin)
        - zone_summary: Stats by zone (if granularity includes summary)
        - metadata: Total shots, FG%, coordinate system info

    Examples:
        get_shot_chart("Stephen Curry", season="2023-24", granularity="hexbin")
        → Returns hexbin data showing Curry's hot zones

        get_shot_chart("Lakers", entity_type="team", granularity="summary")
        → Returns Lakers team shooting stats by zone

    Coordinate System:
        - Origin (0, 0) = center of basket
        - X-axis: -250 to +250 (left to right, in tenths of feet)
        - Y-axis: -52.5 to +417.5 (baseline to opposite baseline)
        - Units: Tenths of feet (divide by 10 for feet)

    Shot Zones:
        - Paint: < 8 feet from basket
        - Short Mid-Range: 8-16 feet
        - Long Mid-Range: 16-23.75 feet (non-3PT)
        - Three-Point: >= 23.75 feet (corner 3 = 22 feet)
    """
    start_time = time.time()

    try:
        # Fetch shot chart data
        data = await fetch_shot_chart(
            entity_name=entity_name,
            entity_type=entity_type,
            season=season or client.get_season_string(),
            season_type=season_type,
            granularity=granularity,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        response = success_response(
            data=data,
            source="historical",
            cache_status="miss",  # Will be "hit" if cached
            execution_time_ms=execution_time_ms,
        )

        return response.to_json_string()

    except EntityNotFoundError as e:
        response = error_response(
            error_code=e.code, error_message=e.message, details=e.details
        )
        return response.to_json_string()

    except InvalidParameterError as e:
        response = error_response(
            error_code=e.code, error_message=e.message, details=e.details
        )
        return response.to_json_string()

    except Exception as e:
        logger.exception("Error in get_shot_chart")
        response = error_response(
            error_code="NBA_API_ERROR",
            error_message=f"Failed to fetch shot chart: {str(e)}",
        )
        return response.to_json_string()
```

#### Addition 3: Game Context MCP Tool (after get_shot_chart)
```python
@mcp_server.tool()
async def get_game_context(
    team1_name: str,
    team2_name: str,
    season: Optional[str] = None,
) -> str:
    """
    Get comprehensive game context for a matchup.

    Combines multiple data sources to provide rich pre-game analysis:
    - Current standings (both teams)
    - Advanced statistics (OffRtg, DefRtg, Pace, NetRtg)
    - Recent form (last 10 games, win streaks)
    - Head-to-head record (this season)
    - Auto-generated narrative and key storylines

    Args:
        team1_name: First team name (e.g., "Lakers", "Los Angeles Lakers", "LAL")
        team2_name: Second team name (e.g., "Warriors", "Golden State Warriors", "GSW")
        season: Season in 'YYYY-YY' format (e.g., "2023-24"). If None, uses current season.

    Returns:
        JSON string with ResponseEnvelope containing:
        - matchup: Team names and IDs
        - standings: W-L records, ranks, games behind
        - advanced_stats: OffRtg, DefRtg, Pace, NetRtg for both teams
        - recent_form: Last 10 games results, win/loss streaks
        - head_to_head: Season series record
        - narrative: Markdown formatted analysis with key storylines
        - metadata: Components loaded/failed

    Examples:
        get_game_context("Lakers", "Warriors")
        → Returns comprehensive matchup analysis with auto-generated narrative

        get_game_context("Celtics", "Heat", season="2023-24")
        → Returns 2023-24 season matchup context

    Note: Uses parallel execution (4+ API calls concurrently) for fast response.
          Returns partial context if some components fail (graceful degradation).
    """
    start_time = time.time()

    try:
        # Fetch game context with parallel execution
        data = await fetch_game_context(
            team1_name=team1_name,
            team2_name=team2_name,
            season=season,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        # Check if partial data returned
        if data.get("metadata", {}).get("components_failed"):
            response = partial_response(
                data=data,
                source="historical",
                cache_status="miss",
                execution_time_ms=execution_time_ms,
                warnings=[
                    f"Some components failed: {', '.join(data['metadata']['components_failed'])}"
                ],
            )
        else:
            response = success_response(
                data=data,
                source="historical",
                cache_status="miss",
                execution_time_ms=execution_time_ms,
            )

        return response.to_json_string()

    except EntityNotFoundError as e:
        response = error_response(
            error_code=e.code, error_message=e.message, details=e.details
        )
        return response.to_json_string()

    except Exception as e:
        logger.exception("Error in get_game_context")
        response = error_response(
            error_code="NBA_API_ERROR",
            error_message=f"Failed to fetch game context: {str(e)}",
        )
        return response.to_json_string()
```

**Estimated Changes**: +300 lines

---

### File 4: `nba_mcp/schemas/tool_params.py` (MODIFY)

**Changes to Make**:

#### Addition 1: Import Literal (if not already imported)
```python
# Line ~22
from typing import List, Literal, Optional, Union
```

#### Addition 2: Shot Chart Parameters Model (after ComparePlayersEraAdjustedParams, ~line 388)
```python
# ============================================================================
# Tool 14: get_shot_chart
# ============================================================================


class GetShotChartParams(BaseModel):
    """
    Parameters for retrieving shot chart data.

    Returns shooting data with coordinates and optional hexbin aggregation
    for visualizing shooting patterns and hot zones.
    """

    entity_name: str = Field(
        ...,
        description="Player or team name (full or partial, e.g., 'Stephen Curry', 'Warriors', 'LAL')",
        examples=["Stephen Curry", "LeBron James", "Warriors", "Lakers"],
        min_length=2,
    )
    entity_type: Literal["player", "team"] = Field(
        "player",
        description="Entity type: 'player' for individual, 'team' for entire team",
    )
    season: Optional[str] = Field(
        None,
        description="Season in 'YYYY-YY' format (e.g., '2023-24'). If None, uses current season.",
        examples=["2023-24", "2015-16", "2010-11"],
        pattern=r"^\d{4}-\d{2}$|^$",
    )
    season_type: Literal["Regular Season", "Playoffs"] = Field(
        "Regular Season",
        description="Season type: 'Regular Season' or 'Playoffs'",
    )
    granularity: Literal["raw", "hexbin", "both", "summary"] = Field(
        "both",
        description=(
            "Output format: "
            "'raw'=Individual shot coordinates (X,Y,make/miss), "
            "'hexbin'=Aggregated 50x50 grid with FG% per zone, "
            "'both'=Both raw and hexbin data (default), "
            "'summary'=Zone summary statistics (paint, mid-range, three-point)"
        ),
    )
```

#### Addition 3: Game Context Parameters Model (after GetShotChartParams)
```python
# ============================================================================
# Tool 15: get_game_context
# ============================================================================


class GetGameContextParams(BaseModel):
    """
    Parameters for retrieving comprehensive game context.

    Combines standings, advanced stats, recent form, and head-to-head
    record to provide rich pre-game analysis with auto-generated narrative.
    """

    team1_name: str = Field(
        ...,
        description="First team name or abbreviation (e.g., 'Lakers', 'Los Angeles Lakers', 'LAL')",
        examples=["Lakers", "Warriors", "Celtics", "Heat"],
        min_length=2,
    )
    team2_name: str = Field(
        ...,
        description="Second team name or abbreviation (e.g., 'Warriors', 'Golden State Warriors', 'GSW')",
        examples=["Warriors", "Lakers", "Heat", "Bucks"],
        min_length=2,
    )
    season: Optional[str] = Field(
        None,
        description="Season in 'YYYY-YY' format (e.g., '2023-24'). If None, uses current season.",
        examples=["2023-24", "2022-23"],
        pattern=r"^\d{4}-\d{2}$|^$",
    )
```

#### Addition 4: Update __all__ export (at end of file)
```python
__all__ = [
    "ResolveNBAEntityParams",
    "GetPlayerCareerInformationParams",
    "LeagueLeadersParams",
    "GetLiveScoresParams",
    "GetDateRangeGameLogParams",
    "PlayByPlayParams",
    "GetTeamStandingsParams",
    "GetTeamAdvancedStatsParams",
    "GetPlayerAdvancedStatsParams",
    "ComparePlayersParams",
    "ComparePlayersEraAdjustedParams",
    "GetShotChartParams",        # NEW
    "GetGameContextParams",       # NEW
    "AnswerNBAQuestionParams",
    "GetMetricsInfoParams",
]
```

**Estimated Changes**: +100 lines

---

### File 5: `nba_mcp/schemas/publisher.py` (MODIFY)

**Changes to Make**:

#### Addition 1: Import new parameter models (at top, ~line 40)
```python
from nba_mcp.schemas.tool_params import (
    AnswerNBAQuestionParams,
    ComparePlayersEraAdjustedParams,
    ComparePlayersParams,
    GetDateRangeGameLogParams,
    GetGameContextParams,         # NEW
    GetLiveScoresParams,
    GetMetricsInfoParams,
    GetPlayerAdvancedStatsParams,
    GetPlayerCareerInformationParams,
    GetShotChartParams,           # NEW
    GetTeamAdvancedStatsParams,
    GetTeamStandingsParams,
    LeagueLeadersParams,
    PlayByPlayParams,
    ResolveNBAEntityParams,
)
```

#### Addition 2: Register shot chart tool (in TOOL_REGISTRY dict, ~line 127)
```python
    "get_shot_chart": {
        "model": GetShotChartParams,
        "description": "Get shot chart data with coordinates and hexbin aggregation",
        "category": "Shot Data",
        "returns": "Shooting data with raw coordinates, hexbin aggregation, and zone summaries",
    },
```

#### Addition 3: Register game context tool (after get_shot_chart)
```python
    "get_game_context": {
        "model": GetGameContextParams,
        "description": "Get comprehensive game context (standings, stats, form, h2h) with auto-generated narrative",
        "category": "Game Analysis",
        "returns": "Rich matchup analysis with standings, advanced stats, recent form, h2h record, and storylines",
    },
```

**Estimated Changes**: +20 lines

---

### File 6: `test_shot_charts.py` (NEW)

**Purpose**: Unit and integration tests for shot charts

**Tests to Implement**:
1. `test_validate_coordinates()` - Test coordinate validation
2. `test_aggregate_to_hexbin()` - Test hexbin aggregation with known data
3. `test_aggregate_empty_shots()` - Test edge case: no shots
4. `test_aggregate_single_shot()` - Test edge case: single shot
5. `test_calculate_zone_summary()` - Test zone summary calculation
6. `test_get_shot_chart_player()` - Integration test with real player
7. `test_get_shot_chart_team()` - Integration test with real team
8. `test_get_shot_chart_invalid_entity()` - Test EntityNotFoundError
9. `test_get_shot_chart_granularity_raw()` - Test raw only
10. `test_get_shot_chart_granularity_hexbin()` - Test hexbin only
11. `test_get_shot_chart_granularity_summary()` - Test summary only

**Estimated Lines**: 400-500

---

### File 7: `test_game_context.py` (NEW)

**Purpose**: Unit and integration tests for game context

**Tests to Implement**:
1. `test_fetch_standings_context()` - Test standings component
2. `test_fetch_advanced_stats_context()` - Test advanced stats component
3. `test_fetch_recent_form()` - Test recent form component
4. `test_fetch_head_to_head()` - Test h2h calculation
5. `test_fetch_head_to_head_no_games()` - Test h2h when no games played
6. `test_synthesize_narrative()` - Test narrative generation
7. `test_get_game_context_full()` - Integration test with all components
8. `test_get_game_context_partial()` - Test graceful degradation (1 component fails)
9. `test_get_game_context_parallel_execution()` - Test parallel speedup
10. `test_get_game_context_invalid_team()` - Test EntityNotFoundError

**Estimated Lines**: 500-600

---

## Summary of Changes

### New Files (4)
1. `nba_mcp/api/shot_charts.py` - ~450 lines
2. `nba_mcp/api/game_context.py` - ~550 lines
3. `test_shot_charts.py` - ~450 lines
4. `test_game_context.py` - ~550 lines

### Modified Files (3)
1. `nba_mcp/nba_server.py` - +300 lines (2 new MCP tools)
2. `nba_mcp/schemas/tool_params.py` - +100 lines (2 new param models)
3. `nba_mcp/schemas/publisher.py` - +20 lines (2 new tool registrations)

### Total Impact
- **New Lines**: ~2,420 lines
- **Modified Lines**: ~420 lines
- **Total Effort**: ~2,840 lines of production code + tests

---

## Implementation Checklist

### Phase A: Shot Charts
- [ ] Create `nba_mcp/api/shot_charts.py`
- [ ] Implement `fetch_shot_chart_data()`
- [ ] Implement `validate_shot_coordinates()`
- [ ] Implement `aggregate_to_hexbin()`
- [ ] Implement `calculate_zone_summary()`
- [ ] Implement `get_shot_chart()` (main entry point)
- [ ] Add MCP tool to `nba_server.py`
- [ ] Add `GetShotChartParams` to `tool_params.py`
- [ ] Register in `publisher.py`
- [ ] Create `test_shot_charts.py`
- [ ] Run tests and fix issues
- [ ] Format with isort + Black
- [ ] Validate with mypy

### Phase B: Game Context
- [ ] Create `nba_mcp/api/game_context.py`
- [ ] Implement `fetch_standings_context()`
- [ ] Implement `fetch_advanced_stats_context()`
- [ ] Implement `fetch_recent_form()`
- [ ] Implement `fetch_head_to_head()`
- [ ] Implement `synthesize_narrative()`
- [ ] Implement `get_game_context()` (main entry point)
- [ ] Add MCP tool to `nba_server.py`
- [ ] Add `GetGameContextParams` to `tool_params.py`
- [ ] Register in `publisher.py`
- [ ] Create `test_game_context.py`
- [ ] Run tests and fix issues
- [ ] Format with isort + Black
- [ ] Validate with mypy

### Phase C: Finalization
- [ ] Update CHANGELOG.md with compact details
- [ ] Run full test suite
- [ ] Add to golden tests
- [ ] Format all code (isort + Black)
- [ ] Run mypy type check
- [ ] Verify CI will pass locally
- [ ] Commit changes
- [ ] Push to branch

---

## Risk Mitigation

### Risk 1: Shot Chart API Changes
**Mitigation**: Validate response structure, add schema validation
**Fallback**: Return error with clear message if structure changed

### Risk 2: Parallel Execution Issues
**Mitigation**: Use `return_exceptions=True`, handle each component separately
**Fallback**: Graceful degradation, return partial context

### Risk 3: Performance Regressions
**Mitigation**: Profile hexbin aggregation, optimize if needed
**Fallback**: Offer granularity="summary" for faster response

### Risk 4: Memory Issues with Large Datasets
**Mitigation**: Filter hexbin bins (min_shots=5), limit raw shots if needed
**Fallback**: Truncate to max 1000 shots with warning

---

## Next Step

Ready to proceed to **Step 5: Implement Shot Charts Incrementally**
