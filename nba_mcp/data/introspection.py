"""
Endpoint introspection for NBA API.

Provides tools to inspect endpoints and discover metadata without fetching full datasets:
- Column names and types
- Available date ranges
- Row count estimation
- Parameter discovery
- Pagination capabilities

This enables intelligent data fetching and dataset size prediction.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import date, datetime, timedelta
from dataclasses import dataclass
import pandas as pd

from nba_mcp.data.fetch import fetch_endpoint, FetchError
from nba_mcp.api.errors import NBAApiError, EntityNotFoundError

logger = logging.getLogger(__name__)


@dataclass
class EndpointCapabilities:
    """Metadata about an endpoint's capabilities."""

    endpoint: str
    columns: List[str]
    column_types: Dict[str, str]
    supports_date_range: bool
    supports_season_filter: bool
    supports_pagination: bool
    estimated_row_count: Optional[int]
    min_date: Optional[date]
    max_date: Optional[date]
    available_seasons: List[str]
    sample_data_shape: Tuple[int, int]  # (rows, cols)
    chunk_strategy: str  # "date", "season", "game", "none"
    notes: str


class EndpointIntrospector:
    """
    Inspect NBA API endpoints to discover metadata and capabilities.

    This class provides methods to:
    1. Discover columns without fetching full datasets
    2. Estimate row counts for parameter combinations
    3. Find available date ranges
    4. Detect pagination needs
    5. Recommend chunking strategies
    """

    def __init__(self):
        """Initialize the introspector."""
        self._cache: Dict[str, EndpointCapabilities] = {}

    async def inspect_endpoint(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
    ) -> EndpointCapabilities:
        """
        Inspect an endpoint to discover its capabilities and metadata.

        Args:
            endpoint: Endpoint name from catalog
            params: Optional parameters to test with
            use_cache: Whether to use cached results

        Returns:
            EndpointCapabilities with full metadata

        Example:
            caps = await inspector.inspect_endpoint("player_career_stats")
            print(f"Columns: {caps.columns}")
            print(f"Estimated rows: {caps.estimated_row_count}")
        """
        cache_key = f"{endpoint}:{str(params)}"

        if use_cache and cache_key in self._cache:
            logger.debug(f"Using cached capabilities for {endpoint}")
            return self._cache[cache_key]

        logger.info(f"Inspecting endpoint: {endpoint}")

        try:
            # Fetch small sample to discover schema
            sample_params = params or self._get_minimal_params(endpoint)
            table, provenance = await fetch_endpoint(endpoint, sample_params)

            # Convert to pandas for analysis
            df = table.to_pandas()

            # Discover columns and types
            columns = df.columns.tolist()
            column_types = {col: str(df[col].dtype) for col in columns}

            # Detect capabilities
            supports_date = self._detect_date_support(endpoint)
            supports_season = self._detect_season_support(endpoint)
            supports_pagination = self._detect_pagination_support(endpoint)

            # Estimate row count
            estimated_rows = await self._estimate_row_count(endpoint, sample_params, df)

            # Find date range if supported
            min_date_val, max_date_val = await self._find_date_range(
                endpoint, supports_date
            )

            # Find available seasons
            seasons = await self._find_available_seasons(endpoint, supports_season)

            # Recommend chunking strategy
            chunk_strategy = self._recommend_chunk_strategy(
                endpoint, estimated_rows, supports_date, supports_season
            )

            # Build capabilities object
            caps = EndpointCapabilities(
                endpoint=endpoint,
                columns=columns,
                column_types=column_types,
                supports_date_range=supports_date,
                supports_season_filter=supports_season,
                supports_pagination=supports_pagination,
                estimated_row_count=estimated_rows,
                min_date=min_date_val,
                max_date=max_date_val,
                available_seasons=seasons,
                sample_data_shape=(df.shape[0], df.shape[1]),
                chunk_strategy=chunk_strategy,
                notes=self._generate_notes(endpoint, estimated_rows, chunk_strategy),
            )

            # Cache and return
            self._cache[cache_key] = caps
            return caps

        except (FetchError, NBAApiError, EntityNotFoundError) as e:
            logger.error(f"Failed to inspect endpoint {endpoint}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error inspecting {endpoint}")
            raise FetchError(f"Inspection failed: {e}")

    def _get_minimal_params(self, endpoint: str) -> Dict[str, Any]:
        """
        Get minimal parameters needed to fetch a small sample from an endpoint.

        Args:
            endpoint: Endpoint name

        Returns:
            Dictionary of minimal parameters
        """
        # Define minimal params for each endpoint type
        minimal_params = {
            "player_career_stats": {"player_name": "LeBron James"},
            "player_advanced_stats": {"player_name": "LeBron James"},
            "team_standings": {"season": "2024-25"},
            "team_advanced_stats": {"team_name": "Lakers"},
            "team_game_log": {"team": "Lakers", "season": "2024-25"},
            "league_leaders": {"stat_category": "PTS", "limit": 5},
            "shot_chart": {"entity_name": "Stephen Curry", "granularity": "summary"},
            "live_scores": {},
        }

        return minimal_params.get(endpoint, {})

    def _detect_date_support(self, endpoint: str) -> bool:
        """Check if endpoint supports date range parameters."""
        date_supported_endpoints = [
            "team_game_log",
            "shot_chart",
            "play_by_play",
            "live_scores",
        ]
        return endpoint in date_supported_endpoints

    def _detect_season_support(self, endpoint: str) -> bool:
        """Check if endpoint supports season filtering."""
        season_supported_endpoints = [
            "player_career_stats",
            "player_advanced_stats",
            "team_standings",
            "team_advanced_stats",
            "team_game_log",
            "league_leaders",
            "shot_chart",
        ]
        return endpoint in season_supported_endpoints

    def _detect_pagination_support(self, endpoint: str) -> bool:
        """
        Check if endpoint needs pagination/chunking.

        Note: NBA API doesn't have built-in pagination, but we support
        chunking via date ranges or season filtering.
        """
        # Endpoints that may return large datasets
        large_dataset_endpoints = ["team_game_log", "shot_chart", "play_by_play"]
        return endpoint in large_dataset_endpoints

    async def _estimate_row_count(
        self, endpoint: str, params: Dict[str, Any], sample_df: pd.DataFrame
    ) -> Optional[int]:
        """
        Estimate total row count for given parameters.

        Args:
            endpoint: Endpoint name
            params: Parameters used
            sample_df: Sample DataFrame

        Returns:
            Estimated row count or None if unknown
        """
        # Define typical row counts based on endpoint type
        typical_counts = {
            "player_career_stats": 20,  # ~20 seasons per player
            "player_advanced_stats": 1,  # 1 row per season
            "team_standings": 30,  # 30 teams
            "team_advanced_stats": 1,  # 1 row per season
            "team_game_log": 82,  # 82 games per season
            "league_leaders": 50,  # Top 50 players default
            "shot_chart": 1500,  # ~1500 shots per season
            "live_scores": 15,  # ~15 games per day max
        }

        base_count = typical_counts.get(endpoint)

        if base_count is None:
            return None

        # Adjust based on parameters
        if endpoint == "player_career_stats" and not params.get("season"):
            # All seasons: multiply by typical career length
            return base_count

        if endpoint == "shot_chart":
            # Shots vary by player and season
            if params.get("season"):
                return base_count  # One season
            else:
                return base_count * 10  # Multiple seasons

        if endpoint == "team_game_log":
            season_type = params.get("season_type", "Regular Season")
            if season_type == "Regular Season":
                return 82
            elif season_type == "Playoffs":
                return 28  # Max playoff games
            else:
                return 82

        return base_count

    async def _find_date_range(
        self, endpoint: str, supports_date: bool
    ) -> Tuple[Optional[date], Optional[date]]:
        """
        Find available date range for an endpoint.

        Args:
            endpoint: Endpoint name
            supports_date: Whether endpoint supports date filtering

        Returns:
            Tuple of (min_date, max_date) or (None, None)
        """
        if not supports_date:
            return None, None

        # NBA data generally available from 1996-97 season onwards
        # For live data, current season only
        if endpoint == "live_scores":
            # Current season: October to June
            today = datetime.now().date()
            if today.month >= 10:  # October-December
                min_date_val = date(today.year, 10, 1)
                max_date_val = date(today.year + 1, 6, 30)
            else:  # January-September
                min_date_val = date(today.year - 1, 10, 1)
                max_date_val = date(today.year, 6, 30)
            return min_date_val, max_date_val

        # Historical data endpoints
        min_date_val = date(1996, 10, 1)  # Start of 1996-97 season
        max_date_val = datetime.now().date()

        return min_date_val, max_date_val

    async def _find_available_seasons(
        self, endpoint: str, supports_season: bool
    ) -> List[str]:
        """
        Find available seasons for an endpoint.

        Args:
            endpoint: Endpoint name
            supports_season: Whether endpoint supports season filtering

        Returns:
            List of season strings (e.g., ["2023-24", "2024-25"])
        """
        if not supports_season:
            return []

        # Generate season list from 1996-97 to current
        seasons = []
        current_year = datetime.now().year
        current_month = datetime.now().month

        # If before October, current season is previous year
        if current_month < 10:
            current_year -= 1

        start_year = 1996
        for year in range(start_year, current_year + 1):
            season = f"{year}-{str(year + 1)[2:]}"
            seasons.append(season)

        return seasons

    def _recommend_chunk_strategy(
        self,
        endpoint: str,
        estimated_rows: Optional[int],
        supports_date: bool,
        supports_season: bool,
    ) -> str:
        """
        Recommend chunking strategy for large datasets.

        Args:
            endpoint: Endpoint name
            estimated_rows: Estimated row count
            supports_date: Whether endpoint supports date filtering
            supports_season: Whether endpoint supports season filtering

        Returns:
            Recommended strategy: "date", "season", "game", or "none"
        """
        if estimated_rows is None:
            return "none"

        # No chunking needed for small datasets
        if estimated_rows < 1000:
            return "none"

        # Prefer date-based chunking for time-series data
        if supports_date and estimated_rows > 5000:
            return "date"

        # Use season-based chunking for moderate datasets
        if supports_season and estimated_rows > 1000:
            return "season"

        # Default to no chunking
        return "none"

    def _generate_notes(
        self, endpoint: str, estimated_rows: Optional[int], chunk_strategy: str
    ) -> str:
        """Generate helpful notes about the endpoint."""
        notes = []

        if estimated_rows:
            if estimated_rows < 100:
                notes.append("Small dataset - fast fetch expected")
            elif estimated_rows < 1000:
                notes.append("Medium dataset - should fetch quickly")
            elif estimated_rows < 10000:
                notes.append("Large dataset - consider chunking")
            else:
                notes.append("Very large dataset - chunking recommended")

        if chunk_strategy != "none":
            notes.append(f"Recommended chunking: {chunk_strategy}-based")

        if not notes:
            notes.append("Standard endpoint - no special considerations")

        return "; ".join(notes)

    async def check_size_limit(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ):
        """
        Check if estimated dataset size exceeds fetch limits.

        Inspects the endpoint, estimates dataset size, and checks against
        configured fetch size limits. Returns detailed result with warnings
        if size exceeds limit.

        Args:
            endpoint: Endpoint name to check
            params: Optional parameters for size estimation

        Returns:
            SizeCheckResult with:
            - allowed: bool (True if within limits)
            - estimated_mb: float (estimated dataset size in MB)
            - limit_mb: float (current limit in MB)
            - message: str (summary message)
            - warning_message: Optional[str] (detailed warning if exceeded)

        Example:
            result = await introspector.check_size_limit("shot_chart", {...})
            if not result.allowed:
                print(result.warning_message)
        """
        from nba_mcp.data.limits import get_limits

        # Inspect endpoint to get capabilities
        caps = await self.inspect_endpoint(endpoint, params or {})

        # Estimate memory usage (1KB per row)
        estimated_rows = caps.estimated_row_count or 1000
        estimated_mb = (estimated_rows * 1024) / (1024 * 1024)

        # Check against limits
        limits = get_limits()
        result = limits.check_size(estimated_mb, operation="fetch")

        logger.info(
            f"Size check for {endpoint}: {estimated_mb:.2f} MB "
            f"(limit: {result.limit_mb:.0f} MB) - {'✓ allowed' if result.allowed else '⚠ exceeded'}"
        )

        return result

    def clear_cache(self):
        """Clear the inspection cache."""
        self._cache.clear()
        logger.info("Inspection cache cleared")


# Global introspector instance
_introspector = None


def get_introspector() -> EndpointIntrospector:
    """
    Get the global endpoint introspector instance (singleton pattern).

    Returns:
        EndpointIntrospector instance
    """
    global _introspector
    if _introspector is None:
        _introspector = EndpointIntrospector()
    return _introspector
