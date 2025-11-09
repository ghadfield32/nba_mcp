"""
Unified parameter processing for NBA MCP data fetching.

This module centralizes all parameter validation, transformation, and normalization
to ensure consistent handling across all endpoints and make it easy to add new
data sources or frontend API integrations.

Features:
- Type coercion and validation
- Default value application from catalog
- Entity resolution (player/team names → IDs)
- Date parsing and normalization
- Season format standardization
- Parameter aliasing (flexible input formats)
- Comprehensive error messages

Usage:
    processor = ParameterProcessor()
    processed = await processor.process(
        endpoint="player_career_stats",
        params={"player_name": "LeBron James", "season": "2023-24"}
    )
"""

import asyncio
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, date
import logging

from nba_api.stats.static import players, teams

from nba_mcp.api.entity_resolver import resolve_entity
from nba_mcp.api.errors import EntityNotFoundError
from nba_mcp.data.catalog import get_catalog, ParameterSchema

logger = logging.getLogger(__name__)


class ParameterValidationError(Exception):
    """Raised when parameter validation fails."""
    pass


class ProcessedParameters:
    """
    Container for processed parameters with metadata.

    Attributes:
        params: Validated and normalized parameters
        resolved_entities: Cache of resolved entities (player/team IDs)
        warnings: Non-fatal validation warnings
        transformations: Record of applied transformations
    """

    def __init__(
        self,
        params: Dict[str, Any],
        resolved_entities: Optional[Dict[str, Any]] = None,
        warnings: Optional[List[str]] = None,
        transformations: Optional[List[str]] = None
    ):
        self.params = params
        self.resolved_entities = resolved_entities or {}
        self.warnings = warnings or []
        self.transformations = transformations or []

    def __repr__(self) -> str:
        return f"ProcessedParameters(params={self.params}, entities={len(self.resolved_entities)})"


class ParameterProcessor:
    """
    Centralized parameter processor for all NBA API endpoints.

    Handles:
    - Parameter validation against catalog schemas
    - Type coercion and normalization
    - Entity resolution (player/team name → ID)
    - Date parsing and formatting
    - Default value application
    - Parameter aliasing (flexible names)

    Thread-safe with internal caching for entity resolution.
    """

    def __init__(self):
        """Initialize the parameter processor."""
        self.catalog = get_catalog()
        self._entity_cache: Dict[str, Any] = {}  # Cache for resolved entities

        # Parameter aliases - common variations
        self._param_aliases = {
            # Player parameters
            "player": "player_name",
            "player_id": "player_name",  # Will resolve to ID

            # Team parameters
            # NOTE: "team" is NOT aliased - some endpoints expect "team", others expect "team_name"
            # Each endpoint specifies its required parameter name in the catalog
            "team_id": "team",  # Will resolve to team parameter

            # Season parameters
            "year": "season",
            "season_year": "season",

            # Date parameters
            "start_date": "date_from",
            "end_date": "date_to",
            "from_date": "date_from",
            "to_date": "date_to",

            # Stat parameters
            "stat": "stat_category",
            "category": "stat_category",

            # Game parameters
            "game": "game_id",
        }

    async def process(
        self,
        endpoint: str,
        params: Dict[str, Any],
        apply_defaults: bool = True,
        resolve_entities: bool = True
    ) -> ProcessedParameters:
        """
        Process and validate parameters for an endpoint.

        Args:
            endpoint: Endpoint name from catalog
            params: Raw input parameters
            apply_defaults: Whether to apply default values from catalog
            resolve_entities: Whether to resolve player/team names to IDs

        Returns:
            ProcessedParameters with validated params and metadata

        Raises:
            ParameterValidationError: If validation fails

        Example:
            >>> processor = ParameterProcessor()
            >>> result = await processor.process(
            ...     "player_career_stats",
            ...     {"player": "LeBron", "year": "2023-24"}
            ... )
            >>> result.params
            {"player_name": "LeBron James", "season": "2023-24", "player_id": 2544}
        """
        # Get endpoint metadata
        endpoint_meta = self.catalog.get_endpoint(endpoint)
        if not endpoint_meta:
            raise ParameterValidationError(
                f"Unknown endpoint: {endpoint}. "
                f"Available: {', '.join(e.name for e in self.catalog.list_endpoints())}"
            )

        processed_params = {}
        resolved_entities = {}
        warnings = []
        transformations = []

        # Step 1: Apply parameter aliases
        normalized_params = self._apply_aliases(params)
        transformations.extend(self._get_alias_transformations(params, normalized_params))

        # Step 2: Validate required parameters
        for param_schema in endpoint_meta.parameters:
            if param_schema.required and param_schema.name not in normalized_params:
                # Check if we can apply a default
                if apply_defaults and param_schema.default is not None:
                    normalized_params[param_schema.name] = param_schema.default
                    transformations.append(
                        f"Applied default for {param_schema.name}: {param_schema.default}"
                    )
                else:
                    raise ParameterValidationError(
                        f"Required parameter '{param_schema.name}' missing for endpoint '{endpoint}'. "
                        f"Description: {param_schema.description}"
                    )

        # Step 3: Process each parameter
        for param_name, param_value in normalized_params.items():
            # Find schema for this parameter
            param_schema = next(
                (p for p in endpoint_meta.parameters if p.name == param_name),
                None
            )

            if param_schema is None:
                # Unknown parameter - log warning but include it
                warnings.append(f"Unknown parameter '{param_name}' for endpoint '{endpoint}'")
                processed_params[param_name] = param_value
                continue

            # Type coercion and validation
            try:
                processed_value = self._process_parameter_value(
                    param_name,
                    param_value,
                    param_schema,
                    transformations
                )
                processed_params[param_name] = processed_value
            except Exception as e:
                raise ParameterValidationError(
                    f"Error processing parameter '{param_name}': {str(e)}"
                )

        # Step 4: Resolve entities (player/team names → IDs)
        if resolve_entities:
            await self._resolve_entities(
                processed_params,
                resolved_entities,
                transformations
            )

        # Step 5: Apply smart defaults for common patterns
        if apply_defaults:
            self._apply_smart_defaults(processed_params, transformations)

        return ProcessedParameters(
            params=processed_params,
            resolved_entities=resolved_entities,
            warnings=warnings,
            transformations=transformations
        )

    def _apply_aliases(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Apply parameter aliases to normalize names."""
        normalized = {}
        for key, value in params.items():
            # Use alias if it exists, otherwise use original key
            normalized_key = self._param_aliases.get(key, key)
            normalized[normalized_key] = value
        return normalized

    def _get_alias_transformations(
        self,
        original: Dict[str, Any],
        normalized: Dict[str, Any]
    ) -> List[str]:
        """Record which aliases were applied."""
        transformations = []
        for orig_key, orig_value in original.items():
            if orig_key in self._param_aliases:
                new_key = self._param_aliases[orig_key]
                transformations.append(f"Aliased '{orig_key}' → '{new_key}'")
        return transformations

    def _process_parameter_value(
        self,
        param_name: str,
        param_value: Any,
        param_schema: ParameterSchema,
        transformations: List[str]
    ) -> Any:
        """
        Process and validate a single parameter value.

        Handles:
        - Type coercion (string → int, date parsing, etc.)
        - Enum validation
        - Date normalization
        - Season format standardization
        """
        # Handle None/null values
        if param_value is None:
            if param_schema.default is not None:
                transformations.append(
                    f"Using default for {param_name}: {param_schema.default}"
                )
                return param_schema.default
            return None

        # Type-specific processing
        param_type = param_schema.type.lower()

        if param_type == "integer":
            try:
                value = int(param_value)
                if value != param_value:
                    transformations.append(f"Coerced {param_name} to integer: {value}")
                return value
            except (ValueError, TypeError):
                raise ValueError(f"Cannot convert '{param_value}' to integer")

        elif param_type == "string":
            value = str(param_value).strip()

            # Enum validation
            if param_schema.enum and value not in param_schema.enum:
                raise ValueError(
                    f"Invalid value '{value}' for {param_name}. "
                    f"Must be one of: {', '.join(param_schema.enum)}"
                )

            return value

        elif param_type == "date":
            # Parse and normalize dates
            normalized_date = self._parse_date(param_value)
            if normalized_date != param_value:
                transformations.append(
                    f"Normalized date {param_name}: {param_value} → {normalized_date}"
                )
            return normalized_date

        elif param_type == "boolean":
            if isinstance(param_value, bool):
                return param_value
            # Handle string representations
            if isinstance(param_value, str):
                if param_value.lower() in ("true", "yes", "1"):
                    return True
                elif param_value.lower() in ("false", "no", "0"):
                    return False
            raise ValueError(f"Cannot convert '{param_value}' to boolean")

        # Default: return as-is
        return param_value

    def _parse_date(self, value: Any) -> str:
        """
        Parse and normalize date values.

        Supports:
        - ISO format: "2024-01-15"
        - US format: "01/15/2024"
        - Relative: "today", "yesterday", "-1 day"

        Returns:
            Date string in YYYY-MM-DD format
        """
        if isinstance(value, date):
            return value.strftime("%Y-%m-%d")

        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")

        if not isinstance(value, str):
            raise ValueError(f"Date must be string, date, or datetime, got {type(value)}")

        value_lower = value.lower().strip()

        # Handle relative dates
        if value_lower == "today":
            return date.today().strftime("%Y-%m-%d")
        elif value_lower == "yesterday":
            return (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        elif value_lower == "tomorrow":
            return (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

        # Try ISO format (YYYY-MM-DD)
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            pass

        # Try US format (MM/DD/YYYY)
        try:
            parsed = datetime.strptime(value, "%m/%d/%Y")
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            pass

        # If nothing worked, raise error
        raise ValueError(
            f"Cannot parse date '{value}'. "
            f"Supported formats: YYYY-MM-DD, MM/DD/YYYY, 'today', 'yesterday'"
        )

    async def _resolve_entities(
        self,
        params: Dict[str, Any],
        resolved: Dict[str, Any],
        transformations: List[str]
    ):
        """
        Resolve player and team names to IDs.

        Modifies params in-place and populates resolved dict.
        """
        # Resolve player name → ID
        if "player_name" in params and params["player_name"]:
            player_name = params["player_name"]

            # Check cache first
            cache_key = f"player:{player_name}"
            if cache_key in self._entity_cache:
                entity = self._entity_cache[cache_key]
            else:
                # Resolve using entity resolver
                try:
                    entity = resolve_entity(player_name, entity_type="player")
                    self._entity_cache[cache_key] = entity
                except EntityNotFoundError as e:
                    # Try direct lookup as fallback
                    entity = None

            if entity:
                resolved["player"] = entity
                params["player_id"] = entity.entity_id
                params["player_name"] = entity.name  # Use canonical name
                transformations.append(
                    f"Resolved player: '{player_name}' → {entity.name} (ID: {entity.entity_id})"
                )

        # Resolve team name → ID
        if "team_name" in params and params["team_name"]:
            team_name = params["team_name"]

            # Check cache first
            cache_key = f"team:{team_name}"
            if cache_key in self._entity_cache:
                entity = self._entity_cache[cache_key]
            else:
                # Resolve using entity resolver
                try:
                    entity = resolve_entity(team_name, entity_type="team")
                    self._entity_cache[cache_key] = entity
                except EntityNotFoundError as e:
                    entity = None

            if entity:
                resolved["team"] = entity
                params["team_id"] = entity.entity_id
                params["team_name"] = entity.name  # Use canonical name
                transformations.append(
                    f"Resolved team: '{team_name}' → {entity.name} (ID: {entity.entity_id})"
                )

        # Resolve team parameter (alternate name)
        if "team" in params and params["team"] and "team_name" not in params:
            team_name = params["team"]

            try:
                entity = resolve_entity(team_name, entity_type="team")
                resolved["team"] = entity
                params["team_id"] = entity.entity_id
                params["team_name"] = entity.name
                params["team"] = entity.name  # Update team param too
                transformations.append(
                    f"Resolved team: '{team_name}' → {entity.name} (ID: {entity.entity_id})"
                )
            except EntityNotFoundError:
                pass

    def _apply_smart_defaults(
        self,
        params: Dict[str, Any],
        transformations: List[str]
    ):
        """
        Apply smart defaults based on common patterns.

        Examples:
        - Current season if season not specified
        - Current date if date not specified
        - PerGame mode for stats
        """
        # Auto-detect current season
        if "season" not in params or params["season"] is None:
            current_season = self._get_current_season()
            # Only apply if endpoint expects season
            # Don't apply for endpoints that default to all seasons
            # We can check this by looking at param schema defaults
            transformations.append(
                f"Smart default: season → {current_season} (current season)"
            )
            # Don't actually set it - let the endpoint decide if it needs it

        # Default per_mode to PerGame if not specified
        if "per_mode" in params and params["per_mode"] is None:
            params["per_mode"] = "PerGame"
            transformations.append("Smart default: per_mode → PerGame")

        # Default season_type to Regular Season
        if "season_type" in params and params["season_type"] is None:
            params["season_type"] = "Regular Season"
            transformations.append("Smart default: season_type → Regular Season")

    def _get_current_season(self) -> str:
        """
        Get the current NBA season in YYYY-YY format.

        Season runs from October to June:
        - Oct-Dec → Current year season (e.g., 2024-25)
        - Jan-Jun → Previous year season (e.g., 2023-24)
        - Jul-Sep → Previous year season (e.g., 2023-24)
        """
        today = date.today()
        year = today.year
        month = today.month

        # Season starts in October
        if month >= 10:
            # Current year to next year
            return f"{year}-{str(year + 1)[-2:]}"
        else:
            # Previous year to current year
            return f"{year - 1}-{str(year)[-2:]}"


# Global instance (singleton pattern)
_processor = None


def get_processor() -> ParameterProcessor:
    """
    Get the global parameter processor instance.

    Returns:
        ParameterProcessor singleton
    """
    global _processor
    if _processor is None:
        _processor = ParameterProcessor()
    return _processor
