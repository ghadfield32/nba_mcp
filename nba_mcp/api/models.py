# nba_mcp/api/models.py
"""
Standard response envelope and data models for NBA MCP.

All MCP tool responses use the ResponseEnvelope structure to ensure:
1. Consistent error handling
2. Metadata tracking (version, cache status, source)
3. JSON Schema validation for LLM function calling
4. Type safety with Pydantic
"""

from typing import Any, Dict, List, Optional, Literal, Union
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
import json


# ============================================================================
# RESPONSE ENVELOPE
# ============================================================================


class ErrorDetail(BaseModel):
    """Structured error information."""

    code: str = Field(
        ..., description="Error code (e.g., 'RATE_LIMIT_EXCEEDED', 'ENTITY_NOT_FOUND')"
    )
    message: str = Field(..., description="Human-readable error message")
    retry_after: Optional[int] = Field(
        None, description="Seconds to wait before retry (for rate limits)"
    )
    details: Optional[Dict[str, Any]] = Field(
        None, description="Additional error context"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "NBA API rate limit exceeded. Please retry after 60 seconds.",
                "retry_after": 60,
                "details": {"quota_used": 100, "quota_limit": 100},
            }
        }
    )


class ResponseMetadata(BaseModel):
    """Metadata for every response."""

    version: str = Field(default="v1", description="API version")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z",
        description="ISO-8601 UTC timestamp",
    )
    source: Literal["live", "historical", "static"] = Field(
        default="historical", description="Data source type"
    )
    cache_status: Literal["miss", "hit", "stale", "error"] = Field(
        default="miss", description="Cache hit/miss status"
    )
    execution_time_ms: Optional[float] = Field(
        None, description="Tool execution time in milliseconds"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "version": "v1",
                "timestamp": "2025-01-28T12:34:56.789Z",
                "source": "live",
                "cache_status": "hit",
                "execution_time_ms": 125.5,
            }
        }
    )


class ResponseEnvelope(BaseModel):
    """
    Universal response envelope for all NBA MCP tools.

    Provides consistent structure for success and error responses,
    enabling LLMs to reliably parse results and handle errors.
    """

    status: Literal["success", "error", "partial"] = Field(
        ...,
        description="Response status: 'success' for complete data, 'error' for failure, 'partial' for degraded",
    )
    data: Optional[Any] = Field(
        None, description="Response payload (tool-specific structure)"
    )
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata)
    errors: Optional[List[ErrorDetail]] = Field(
        None, description="Error details (present if status != success)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "success",
                "data": {"player_name": "LeBron James", "ppg": 25.4},
                "metadata": {
                    "version": "v1",
                    "timestamp": "2025-01-28T12:34:56.789Z",
                    "source": "historical",
                    "cache_status": "hit",
                },
                "errors": None,
            }
        }
    )

    def to_json_string(self, **kwargs) -> str:
        """
        Serialize to JSON with deterministic key ordering.
        Ensures response stability for caching and testing.
        """
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,  # Deterministic key ordering
            **kwargs,
        )


# ============================================================================
# ENTITY MODELS
# ============================================================================


class EntityReference(BaseModel):
    """
    Resolved entity reference (player, team, referee, arena).
    Returned by resolve_entity tool.
    """

    entity_type: Literal["player", "team", "referee", "arena"] = Field(
        ..., description="Type of entity resolved"
    )
    entity_id: Union[int, str] = Field(
        ..., description="Unique identifier (NBA API ID)"
    )
    name: str = Field(..., description="Full canonical name")
    abbreviation: Optional[str] = Field(
        None, description="Common abbreviation (teams only)"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Matching confidence score (0.0-1.0)"
    )
    alternate_names: Optional[List[str]] = Field(
        None, description="Alternative names/nicknames"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Additional entity metadata"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "entity_type": "player",
                    "entity_id": 2544,
                    "name": "LeBron James",
                    "abbreviation": None,
                    "confidence": 1.0,
                    "alternate_names": ["LBJ", "King James", "The King"],
                    "metadata": {"active": True, "rookie_year": 2003},
                },
                {
                    "entity_type": "team",
                    "entity_id": 1610612747,
                    "name": "Los Angeles Lakers",
                    "abbreviation": "LAL",
                    "confidence": 1.0,
                    "alternate_names": ["Lakers", "LA Lakers", "LAL"],
                    "metadata": {"conference": "West", "division": "Pacific"},
                },
            ]
        }
    )


# ============================================================================
# STATS MODELS
# ============================================================================


class PlayerSeasonStats(BaseModel):
    """Player statistics for a single season."""

    player_id: int
    player_name: str
    season: str
    team_abbreviation: Optional[str] = None
    games_played: int
    minutes_per_game: float
    points_per_game: float
    rebounds_per_game: float
    assists_per_game: float
    steals_per_game: float
    blocks_per_game: float
    field_goal_pct: float
    three_point_pct: float
    free_throw_pct: float

    model_config = ConfigDict(
        # Force float64 for all floats, int64 for all ints (determinism)
        json_schema_extra={
            "example": {
                "player_id": 2544,
                "player_name": "LeBron James",
                "season": "2023-24",
                "team_abbreviation": "LAL",
                "games_played": 71,
                "minutes_per_game": 35.3,
                "points_per_game": 25.7,
                "rebounds_per_game": 7.3,
                "assists_per_game": 8.3,
                "steals_per_game": 1.3,
                "blocks_per_game": 0.5,
                "field_goal_pct": 0.540,
                "three_point_pct": 0.410,
                "free_throw_pct": 0.750,
            }
        }
    )


class TeamStanding(BaseModel):
    """Team standing in conference/division."""

    team_id: int
    team_name: str
    team_abbreviation: str
    conference: Literal["East", "West"]
    division: str
    wins: int
    losses: int
    win_pct: float
    games_behind: float
    conference_rank: int
    division_rank: int
    home_record: str
    away_record: str
    last_10: str
    streak: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "team_id": 1610612738,
                "team_name": "Boston Celtics",
                "team_abbreviation": "BOS",
                "conference": "East",
                "division": "Atlantic",
                "wins": 37,
                "losses": 11,
                "win_pct": 0.771,
                "games_behind": 0.0,
                "conference_rank": 1,
                "division_rank": 1,
                "home_record": "20-4",
                "away_record": "17-7",
                "last_10": "8-2",
                "streak": "W3",
            }
        }
    )


class PlayerComparison(BaseModel):
    """Side-by-side player comparison."""

    player1: PlayerSeasonStats
    player2: PlayerSeasonStats
    metric_registry: Dict[str, str] = Field(
        ..., description="Shared metric definitions ensuring identical schema"
    )
    normalization_mode: Literal["raw", "per_game", "per_75_poss", "era_adjusted"] = (
        Field(default="per_game", description="Statistical normalization applied")
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "player1": {"player_name": "LeBron James", "ppg": 25.7},
                "player2": {"player_name": "Kevin Durant", "ppg": 29.1},
                "metric_registry": {
                    "ppg": "Points Per Game",
                    "rpg": "Rebounds Per Game",
                },
                "normalization_mode": "per_game",
            }
        }
    )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def success_response(
    data: Any,
    source: Literal["live", "historical", "static"] = "historical",
    cache_status: Literal["miss", "hit", "stale", "error"] = "miss",
    execution_time_ms: Optional[float] = None,
) -> ResponseEnvelope:
    """
    Create a success response envelope.

    Args:
        data: Tool-specific response data
        source: Data source type
        cache_status: Cache hit/miss status
        execution_time_ms: Execution time in milliseconds

    Returns:
        ResponseEnvelope with status="success"
    """
    return ResponseEnvelope(
        status="success",
        data=data,
        metadata=ResponseMetadata(
            source=source,
            cache_status=cache_status,
            execution_time_ms=execution_time_ms,
        ),
        errors=None,
    )


def error_response(
    error_code: str,
    error_message: str,
    retry_after: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
) -> ResponseEnvelope:
    """
    Create an error response envelope.

    Args:
        error_code: Error code (e.g., 'RATE_LIMIT_EXCEEDED')
        error_message: Human-readable error message
        retry_after: Seconds to wait before retry
        details: Additional error context

    Returns:
        ResponseEnvelope with status="error"
    """
    return ResponseEnvelope(
        status="error",
        data=None,
        metadata=ResponseMetadata(),
        errors=[
            ErrorDetail(
                code=error_code,
                message=error_message,
                retry_after=retry_after,
                details=details,
            )
        ],
    )


def partial_response(
    data: Any,
    errors: List[ErrorDetail],
    source: Literal["live", "historical", "static"] = "historical",
) -> ResponseEnvelope:
    """
    Create a partial response (some data available, but with errors).

    Args:
        data: Partial response data
        errors: List of non-fatal errors encountered
        source: Data source type

    Returns:
        ResponseEnvelope with status="partial"
    """
    return ResponseEnvelope(
        status="partial",
        data=data,
        metadata=ResponseMetadata(source=source),
        errors=errors,
    )
