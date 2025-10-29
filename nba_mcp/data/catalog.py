"""
Data catalog for NBA MCP endpoints.

Provides comprehensive metadata about all available endpoints including:
- Parameter schemas
- Primary and foreign keys
- Join relationships
- Example queries
- Data dictionary

This module serves as the single source of truth for endpoint metadata.
"""

from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field
from enum import Enum


class EndpointCategory(str, Enum):
    """Categories for organizing endpoints."""

    PLAYER_STATS = "player_stats"
    TEAM_STATS = "team_stats"
    GAME_DATA = "game_data"
    LEAGUE_DATA = "league_data"
    ADVANCED_ANALYTICS = "advanced_analytics"


class ParameterSchema(BaseModel):
    """Schema definition for an endpoint parameter."""

    name: str
    type: str  # "string", "integer", "boolean", "array", "date"
    required: bool = False
    description: str = ""
    default: Optional[Any] = None
    enum: Optional[List[str]] = None
    example: Optional[Any] = None


class EndpointMetadata(BaseModel):
    """Comprehensive metadata for an NBA API endpoint."""

    name: str = Field(description="Unique endpoint identifier")
    display_name: str = Field(description="Human-readable name")
    category: EndpointCategory
    description: str
    parameters: List[ParameterSchema] = Field(default_factory=list)
    primary_keys: List[str] = Field(default_factory=list)
    output_columns: List[str] = Field(default_factory=list)
    sample_params: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None

    # New pagination/chunking metadata
    supports_date_range: bool = False
    supports_season_filter: bool = False
    supports_pagination: bool = False
    typical_row_count: Optional[int] = None
    max_row_count: Optional[int] = None
    available_seasons: Optional[List[str]] = None
    chunk_strategy: Optional[str] = None  # "date", "season", "game", "none"
    min_date: Optional[str] = None  # Format: "YYYY-MM-DD"
    max_date: Optional[str] = None  # Format: "YYYY-MM-DD"


class JoinRelationship(BaseModel):
    """Defines a join relationship between two endpoints."""

    from_endpoint: str
    to_endpoint: str
    join_keys: Dict[str, str] = Field(
        description="Mapping of {from_column: to_column}"
    )
    join_type: Literal["inner", "left", "right", "outer"] = "left"
    description: str
    example_use_case: str


class JoinExample(BaseModel):
    """Complete example of a multi-step dataset build."""

    name: str
    description: str
    steps: List[Dict[str, Any]]
    expected_output: str


class DataCatalog:
    """
    Central catalog of all NBA MCP endpoints and their relationships.

    This class provides:
    1. Endpoint discovery and enumeration
    2. Parameter schema information
    3. Primary/foreign key relationships
    4. Join recommendations
    5. Example queries
    """

    def __init__(self):
        """Initialize the data catalog with all endpoint metadata."""
        self._endpoints: Dict[str, EndpointMetadata] = {}
        self._relationships: List[JoinRelationship] = []
        self._join_examples: List[JoinExample] = []
        self._initialize_catalog()

    def _initialize_catalog(self):
        """Populate the catalog with all endpoint definitions."""
        # Player Stats Endpoints
        self._add_endpoint(
            EndpointMetadata(
                name="player_career_stats",
                display_name="Player Career Statistics",
                category=EndpointCategory.PLAYER_STATS,
                description="Comprehensive career statistics for a player across all seasons",
                parameters=[
                    ParameterSchema(
                        name="player_name",
                        type="string",
                        required=True,
                        description="Player name (fuzzy matching supported)",
                        example="LeBron James",
                    ),
                    ParameterSchema(
                        name="season",
                        type="string",
                        required=False,
                        description="Specific season in YYYY-YY format",
                        example="2023-24",
                    ),
                ],
                primary_keys=["PLAYER_ID", "SEASON_ID"],
                output_columns=[
                    "PLAYER_ID",
                    "PLAYER_NAME",
                    "SEASON_ID",
                    "TEAM_ID",
                    "TEAM_ABBREVIATION",
                    "GP",
                    "GS",
                    "MIN",
                    "FGM",
                    "FGA",
                    "FG_PCT",
                    "FG3M",
                    "FG3A",
                    "FG3_PCT",
                    "FTM",
                    "FTA",
                    "FT_PCT",
                    "OREB",
                    "DREB",
                    "REB",
                    "AST",
                    "STL",
                    "BLK",
                    "TOV",
                    "PF",
                    "PTS",
                ],
                sample_params={"player_name": "LeBron James"},
                notes="Returns all seasons if season not specified",
            )
        )

        self._add_endpoint(
            EndpointMetadata(
                name="player_advanced_stats",
                display_name="Player Advanced Statistics",
                category=EndpointCategory.ADVANCED_ANALYTICS,
                description="Advanced efficiency metrics for a player (TS%, Usage%, PER, etc.)",
                parameters=[
                    ParameterSchema(
                        name="player_name",
                        type="string",
                        required=True,
                        description="Player name",
                        example="Stephen Curry",
                    ),
                    ParameterSchema(
                        name="season",
                        type="string",
                        required=False,
                        description="Season in YYYY-YY format",
                        example="2023-24",
                    ),
                ],
                primary_keys=["PLAYER_ID", "SEASON"],
                output_columns=[
                    "PLAYER_ID",
                    "PLAYER_NAME",
                    "SEASON",
                    "TEAM_ID",
                    "GP",
                    "MIN",
                    "TS_PCT",
                    "EFG_PCT",
                    "USAGE_PCT",
                    "PIE",
                    "OFF_RATING",
                    "DEF_RATING",
                    "NET_RATING",
                    "AST_PCT",
                    "REB_PCT",
                    "TOV_PCT",
                ],
                sample_params={"player_name": "Stephen Curry", "season": "2023-24"},
            )
        )

        # Team Stats Endpoints
        self._add_endpoint(
            EndpointMetadata(
                name="team_standings",
                display_name="Team Standings",
                category=EndpointCategory.TEAM_STATS,
                description="Conference and division standings with win/loss records",
                parameters=[
                    ParameterSchema(
                        name="season",
                        type="string",
                        required=False,
                        description="Season in YYYY-YY format (defaults to current)",
                        example="2023-24",
                    ),
                    ParameterSchema(
                        name="conference",
                        type="string",
                        required=False,
                        description="Filter by conference",
                        enum=["East", "West"],
                        example="East",
                    ),
                ],
                primary_keys=["TEAM_ID", "SEASON"],
                output_columns=[
                    "TEAM_ID",
                    "TEAM_NAME",
                    "SEASON",
                    "CONFERENCE",
                    "CONFERENCE_RANK",
                    "DIVISION",
                    "DIVISION_RANK",
                    "W",
                    "L",
                    "W_PCT",
                    "GB",
                    "HOME_RECORD",
                    "ROAD_RECORD",
                    "LAST_10",
                    "STREAK",
                ],
                sample_params={"season": "2023-24", "conference": "East"},
            )
        )

        self._add_endpoint(
            EndpointMetadata(
                name="team_advanced_stats",
                display_name="Team Advanced Statistics",
                category=EndpointCategory.ADVANCED_ANALYTICS,
                description="Team efficiency metrics (OffRtg, DefRtg, Pace, Four Factors)",
                parameters=[
                    ParameterSchema(
                        name="team_name",
                        type="string",
                        required=True,
                        description="Team name or abbreviation",
                        example="Lakers",
                    ),
                    ParameterSchema(
                        name="season",
                        type="string",
                        required=False,
                        description="Season in YYYY-YY format",
                        example="2023-24",
                    ),
                ],
                primary_keys=["TEAM_ID", "SEASON"],
                output_columns=[
                    "TEAM_ID",
                    "TEAM_NAME",
                    "SEASON",
                    "GP",
                    "W",
                    "L",
                    "W_PCT",
                    "OFF_RATING",
                    "DEF_RATING",
                    "NET_RATING",
                    "PACE",
                    "TS_PCT",
                    "EFG_PCT",
                    "TOV_PCT",
                    "OREB_PCT",
                    "FTA_RATE",
                    "OPP_EFG_PCT",
                    "OPP_TOV_PCT",
                    "OPP_OREB_PCT",
                    "OPP_FTA_RATE",
                ],
                sample_params={"team_name": "Lakers", "season": "2023-24"},
            )
        )

        self._add_endpoint(
            EndpointMetadata(
                name="team_game_log",
                display_name="Team Game Log",
                category=EndpointCategory.TEAM_STATS,
                description="Historical game-by-game results for a team",
                parameters=[
                    ParameterSchema(
                        name="team",
                        type="string",
                        required=True,
                        description="Team name or abbreviation",
                        example="Lakers",
                    ),
                    ParameterSchema(
                        name="season",
                        type="string",
                        required=True,
                        description="Season in YYYY-YY format",
                        example="2023-24",
                    ),
                    ParameterSchema(
                        name="date_from",
                        type="date",
                        required=False,
                        description="Start date (YYYY-MM-DD)",
                        example="2024-01-01",
                    ),
                    ParameterSchema(
                        name="date_to",
                        type="date",
                        required=False,
                        description="End date (YYYY-MM-DD)",
                        example="2024-01-31",
                    ),
                ],
                primary_keys=["GAME_ID"],
                output_columns=[
                    "GAME_ID",
                    "GAME_DATE",
                    "TEAM_ID",
                    "TEAM_NAME",
                    "MATCHUP",
                    "WL",
                    "PTS",
                    "FGM",
                    "FGA",
                    "FG_PCT",
                    "FG3M",
                    "FG3A",
                    "FG3_PCT",
                    "FTM",
                    "FTA",
                    "FT_PCT",
                    "OREB",
                    "DREB",
                    "REB",
                    "AST",
                    "STL",
                    "BLK",
                    "TOV",
                    "PF",
                    "PLUS_MINUS",
                ],
                sample_params={
                    "team": "Lakers",
                    "season": "2023-24",
                    "date_from": "2024-01-01",
                },
            )
        )

        # Game Data Endpoints
        self._add_endpoint(
            EndpointMetadata(
                name="live_scores",
                display_name="Live Game Scores",
                category=EndpointCategory.GAME_DATA,
                description="Current or historical game scores and status",
                parameters=[
                    ParameterSchema(
                        name="target_date",
                        type="date",
                        required=False,
                        description="Date for scores (YYYY-MM-DD), defaults to today",
                        example="2024-03-15",
                    )
                ],
                primary_keys=["GAME_ID"],
                output_columns=[
                    "GAME_ID",
                    "GAME_DATE",
                    "HOME_TEAM_ID",
                    "HOME_TEAM_NAME",
                    "HOME_TEAM_SCORE",
                    "AWAY_TEAM_ID",
                    "AWAY_TEAM_NAME",
                    "AWAY_TEAM_SCORE",
                    "GAME_STATUS",
                    "PERIOD",
                    "TIME_REMAINING",
                ],
                sample_params={"target_date": "2024-03-15"},
            )
        )

        self._add_endpoint(
            EndpointMetadata(
                name="play_by_play",
                display_name="Play-by-Play Data",
                category=EndpointCategory.GAME_DATA,
                description="Detailed play-by-play action for a game",
                parameters=[
                    ParameterSchema(
                        name="game_date",
                        type="date",
                        required=False,
                        description="Game date (YYYY-MM-DD)",
                        example="2024-03-15",
                    ),
                    ParameterSchema(
                        name="team",
                        type="string",
                        required=False,
                        description="Filter by team",
                        example="Lakers",
                    ),
                    ParameterSchema(
                        name="start_period",
                        type="integer",
                        required=False,
                        description="Starting period",
                        default=1,
                    ),
                    ParameterSchema(
                        name="end_period",
                        type="integer",
                        required=False,
                        description="Ending period",
                        default=4,
                    ),
                ],
                primary_keys=["GAME_ID", "EVENT_NUM"],
                output_columns=[
                    "GAME_ID",
                    "EVENT_NUM",
                    "PERIOD",
                    "CLOCK",
                    "TEAM_ID",
                    "PLAYER_ID",
                    "EVENT_TYPE",
                    "ACTION_TYPE",
                    "DESCRIPTION",
                    "SCORE",
                ],
                sample_params={"game_date": "2024-03-15", "team": "Lakers"},
            )
        )

        # League Data Endpoints
        self._add_endpoint(
            EndpointMetadata(
                name="league_leaders",
                display_name="League Leaders",
                category=EndpointCategory.LEAGUE_DATA,
                description="Top performers in any statistical category",
                parameters=[
                    ParameterSchema(
                        name="stat_category",
                        type="string",
                        required=True,
                        description="Statistical category",
                        enum=["PTS", "REB", "AST", "STL", "BLK", "FG_PCT", "FG3_PCT", "FT_PCT"],
                        example="PTS",
                    ),
                    ParameterSchema(
                        name="season",
                        type="string",
                        required=False,
                        description="Season in YYYY-YY format",
                        example="2023-24",
                    ),
                    ParameterSchema(
                        name="per_mode",
                        type="string",
                        required=False,
                        description="Per-game, totals, or per-48 minutes",
                        enum=["PerGame", "Totals", "Per48"],
                        default="PerGame",
                    ),
                    ParameterSchema(
                        name="limit",
                        type="integer",
                        required=False,
                        description="Number of leaders to return",
                        default=10,
                    ),
                ],
                primary_keys=["PLAYER_ID", "SEASON", "STAT_CATEGORY"],
                output_columns=[
                    "RANK",
                    "PLAYER_ID",
                    "PLAYER_NAME",
                    "TEAM_ID",
                    "TEAM_ABBREVIATION",
                    "GP",
                    "MIN",
                    "STAT_VALUE",
                    "PTS",
                    "REB",
                    "AST",
                ],
                sample_params={
                    "stat_category": "PTS",
                    "season": "2023-24",
                    "per_mode": "PerGame",
                    "limit": 10,
                },
            )
        )

        self._add_endpoint(
            EndpointMetadata(
                name="shot_chart",
                display_name="Shot Chart Data",
                category=EndpointCategory.ADVANCED_ANALYTICS,
                description="Shot location data with optional hexagonal binning",
                parameters=[
                    ParameterSchema(
                        name="entity_name",
                        type="string",
                        required=True,
                        description="Player or team name",
                        example="Stephen Curry",
                    ),
                    ParameterSchema(
                        name="entity_type",
                        type="string",
                        required=False,
                        description="Entity type",
                        enum=["player", "team"],
                        default="player",
                    ),
                    ParameterSchema(
                        name="season",
                        type="string",
                        required=False,
                        description="Season in YYYY-YY format",
                        example="2023-24",
                    ),
                    ParameterSchema(
                        name="granularity",
                        type="string",
                        required=False,
                        description="Output granularity",
                        enum=["raw", "hexbin", "both", "summary"],
                        default="both",
                    ),
                ],
                primary_keys=["SHOT_ID"],
                output_columns=[
                    "SHOT_ID",
                    "PLAYER_ID",
                    "TEAM_ID",
                    "LOC_X",
                    "LOC_Y",
                    "SHOT_MADE_FLAG",
                    "SHOT_DISTANCE",
                    "SHOT_TYPE",
                    "SHOT_ZONE_BASIC",
                    "SHOT_ZONE_AREA",
                ],
                sample_params={
                    "entity_name": "Stephen Curry",
                    "season": "2023-24",
                    "granularity": "hexbin",
                },
            )
        )

        # Add join relationships
        self._add_relationships()

        # Add join examples
        self._add_join_examples()

    def _add_endpoint(self, endpoint: EndpointMetadata):
        """Add an endpoint to the catalog."""
        self._endpoints[endpoint.name] = endpoint

    def _add_relationships(self):
        """Define all join relationships between endpoints."""
        # Player stats to team stats
        self._relationships.append(
            JoinRelationship(
                from_endpoint="player_career_stats",
                to_endpoint="team_standings",
                join_keys={"TEAM_ID": "TEAM_ID", "SEASON_ID": "SEASON"},
                join_type="left",
                description="Enrich player stats with team standings",
                example_use_case="Get player performance in context of team success",
            )
        )

        self._relationships.append(
            JoinRelationship(
                from_endpoint="player_career_stats",
                to_endpoint="team_advanced_stats",
                join_keys={"TEAM_ID": "TEAM_ID", "SEASON_ID": "SEASON"},
                join_type="left",
                description="Enrich player stats with team efficiency metrics",
                example_use_case="Analyze player performance vs team pace and ratings",
            )
        )

        # Player basic to advanced stats
        self._relationships.append(
            JoinRelationship(
                from_endpoint="player_career_stats",
                to_endpoint="player_advanced_stats",
                join_keys={"PLAYER_ID": "PLAYER_ID", "SEASON_ID": "SEASON"},
                join_type="inner",
                description="Combine basic and advanced player metrics",
                example_use_case="Complete player profile with efficiency and volume stats",
            )
        )

        # League leaders to advanced stats
        self._relationships.append(
            JoinRelationship(
                from_endpoint="league_leaders",
                to_endpoint="player_advanced_stats",
                join_keys={"PLAYER_ID": "PLAYER_ID"},
                join_type="inner",
                description="Enrich league leaders with advanced metrics",
                example_use_case="Find most efficient high-volume scorers",
            )
        )

        # Game data to team info
        self._relationships.append(
            JoinRelationship(
                from_endpoint="live_scores",
                to_endpoint="team_standings",
                join_keys={"HOME_TEAM_ID": "TEAM_ID"},
                join_type="left",
                description="Add home team standings to game scores",
                example_use_case="Game context with team records",
            )
        )

        self._relationships.append(
            JoinRelationship(
                from_endpoint="team_game_log",
                to_endpoint="team_advanced_stats",
                join_keys={"TEAM_ID": "TEAM_ID", "SEASON": "SEASON"},
                join_type="left",
                description="Enrich game logs with team season averages",
                example_use_case="Compare game performance to season averages",
            )
        )

    def _add_join_examples(self):
        """Add complete join examples."""
        self._join_examples.append(
            JoinExample(
                name="Player Performance with Team Context",
                description="Get player stats enriched with team standings and efficiency metrics",
                steps=[
                    {
                        "action": "fetch",
                        "endpoint": "player_career_stats",
                        "params": {"player_name": "LeBron James", "season": "2023-24"},
                    },
                    {
                        "action": "fetch",
                        "endpoint": "team_standings",
                        "params": {"season": "2023-24"},
                    },
                    {
                        "action": "fetch",
                        "endpoint": "team_advanced_stats",
                        "params": {"team_name": "Lakers", "season": "2023-24"},
                    },
                    {
                        "action": "join",
                        "tables": [0, 1],
                        "on": {"TEAM_ID": "TEAM_ID"},
                        "how": "left",
                    },
                    {
                        "action": "join",
                        "tables": ["previous", 2],
                        "on": {"TEAM_ID": "TEAM_ID"},
                        "how": "left",
                    },
                ],
                expected_output="Player stats with team record, rank, and efficiency metrics",
            )
        )

        self._join_examples.append(
            JoinExample(
                name="League Leaders with Efficiency Metrics",
                description="Top scorers enriched with advanced efficiency stats",
                steps=[
                    {
                        "action": "fetch",
                        "endpoint": "league_leaders",
                        "params": {
                            "stat_category": "PTS",
                            "season": "2023-24",
                            "limit": 20,
                        },
                    },
                    {
                        "action": "fetch",
                        "endpoint": "player_advanced_stats",
                        "params": {"season": "2023-24"},
                    },
                    {
                        "action": "join",
                        "tables": [0, 1],
                        "on": {"PLAYER_ID": "PLAYER_ID"},
                        "how": "inner",
                    },
                ],
                expected_output="Top scorers with TS%, Usage%, PIE, and ratings",
            )
        )

        self._join_examples.append(
            JoinExample(
                name="Game Results with Team Season Context",
                description="Team game log enriched with season standings and advanced stats",
                steps=[
                    {
                        "action": "fetch",
                        "endpoint": "team_game_log",
                        "params": {
                            "team": "Lakers",
                            "season": "2023-24",
                            "date_from": "2024-01-01",
                            "date_to": "2024-01-31",
                        },
                    },
                    {
                        "action": "fetch",
                        "endpoint": "team_standings",
                        "params": {"season": "2023-24"},
                    },
                    {
                        "action": "fetch",
                        "endpoint": "team_advanced_stats",
                        "params": {"team_name": "Lakers", "season": "2023-24"},
                    },
                    {
                        "action": "join",
                        "tables": [0, 1],
                        "on": {"TEAM_ID": "TEAM_ID"},
                        "how": "left",
                    },
                    {
                        "action": "join",
                        "tables": ["previous", 2],
                        "on": {"TEAM_ID": "TEAM_ID"},
                        "how": "left",
                    },
                ],
                expected_output="Game-by-game results with team record and season efficiency metrics",
            )
        )

    def get_endpoint(self, name: str) -> Optional[EndpointMetadata]:
        """Get metadata for a specific endpoint."""
        return self._endpoints.get(name)

    def list_endpoints(
        self, category: Optional[EndpointCategory] = None
    ) -> List[EndpointMetadata]:
        """
        List all available endpoints, optionally filtered by category.

        Args:
            category: Optional category filter

        Returns:
            List of endpoint metadata objects
        """
        endpoints = list(self._endpoints.values())
        if category:
            endpoints = [e for e in endpoints if e.category == category]
        return endpoints

    def get_relationships(
        self, endpoint: Optional[str] = None
    ) -> List[JoinRelationship]:
        """
        Get join relationships, optionally filtered by endpoint.

        Args:
            endpoint: Optional endpoint name to filter by

        Returns:
            List of join relationships
        """
        if endpoint:
            return [
                r
                for r in self._relationships
                if r.from_endpoint == endpoint or r.to_endpoint == endpoint
            ]
        return self._relationships

    def get_join_examples(self) -> List[JoinExample]:
        """Get all join examples."""
        return self._join_examples

    def to_dict(self) -> Dict[str, Any]:
        """Convert entire catalog to dictionary format."""
        return {
            "endpoints": {
                name: endpoint.model_dump() for name, endpoint in self._endpoints.items()
            },
            "relationships": [r.model_dump() for r in self._relationships],
            "join_examples": [e.model_dump() for e in self._join_examples],
            "summary": {
                "total_endpoints": len(self._endpoints),
                "categories": list(set(e.category for e in self._endpoints.values())),
                "total_relationships": len(self._relationships),
                "total_examples": len(self._join_examples),
            },
        }


# Global catalog instance
_catalog = None


def get_catalog() -> DataCatalog:
    """
    Get the global data catalog instance (singleton pattern).

    Returns:
        DataCatalog instance
    """
    global _catalog
    if _catalog is None:
        _catalog = DataCatalog()
    return _catalog
