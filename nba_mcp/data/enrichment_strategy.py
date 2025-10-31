"""
Data Enrichment Strategy for NBA Grouping Datasets

Defines what additional data can be added to each grouping level to create
comprehensive "data lake" tables with all available information.

This module provides:
1. Enrichment catalog - maps available enrichments per grouping
2. Enrichment functions - applies enrichments with validation
3. Automatic enrichment - opt-in/opt-out for MCP tools
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Literal
import asyncio

import pandas as pd
import pyarrow as pa

from nba_mcp.api.data_groupings import GroupingLevel, GranularityLevel
from nba_mcp.data.merge_manager import MergeManager, MergeValidationLevel

logger = logging.getLogger(__name__)


# ============================================================================
# ENRICHMENT TYPES
# ============================================================================

class EnrichmentType(str, Enum):
    """Types of enrichment available"""
    ADVANCED_METRICS = "advanced_metrics"          # TS%, eFG%, Game Score, Usage%
    SHOT_CHART = "shot_chart"                      # Shot zone summaries
    OPPONENT_INFO = "opponent_info"                # Opponent team details
    TEAM_CONTEXT = "team_context"                  # Team standings, ratings
    GAME_CONTEXT = "game_context"                  # Home/away, back-to-back
    SEASON_AGGREGATES = "season_aggregates"        # Season totals/averages
    AWARDS_HONORS = "awards_honors"                # Player awards for season
    LINEUP_CONTEXT = "lineup_context"              # Lineup plus/minus, on-court stats
    DEFENSIVE_MATCHUP = "defensive_matchup"        # Primary defender info (if available)
    CLUTCH_STATS = "clutch_stats"                  # Final 5 min, close game stats


@dataclass
class EnrichmentConfig:
    """Configuration for enriching a specific grouping level"""
    grouping_level: GroupingLevel
    available_enrichments: List[EnrichmentType] = field(default_factory=list)
    default_enrichments: List[EnrichmentType] = field(default_factory=list)

    # Estimated impact
    typical_columns_added: int = 0
    estimated_fetch_time_ms: int = 0

    # Requirements
    requires_additional_api_calls: bool = False
    requires_columns: List[str] = field(default_factory=list)


# ============================================================================
# ENRICHMENT CATALOG
# ============================================================================

ENRICHMENT_CATALOG: Dict[GroupingLevel, EnrichmentConfig] = {
    GroupingLevel.PLAYER_GAME: EnrichmentConfig(
        grouping_level=GroupingLevel.PLAYER_GAME,
        available_enrichments=[
            EnrichmentType.ADVANCED_METRICS,      # TS%, eFG%, Game Score
            EnrichmentType.SHOT_CHART,            # Zone summaries
            EnrichmentType.OPPONENT_INFO,         # Opponent team details
            EnrichmentType.GAME_CONTEXT,          # Home/away, B2B
        ],
        default_enrichments=[
            EnrichmentType.ADVANCED_METRICS,      # Default: always add advanced metrics
            EnrichmentType.GAME_CONTEXT,          # Default: always add context
        ],
        typical_columns_added=10,  # TS%, eFG%, Game Score, home/away, etc.
        estimated_fetch_time_ms=50,
        requires_additional_api_calls=False,  # Can compute from base data
        requires_columns=["PTS", "FGA", "FTA", "FGM", "FG3M", "FTM"],
    ),

    GroupingLevel.PLAYER_TEAM_GAME: EnrichmentConfig(
        grouping_level=GroupingLevel.PLAYER_TEAM_GAME,
        available_enrichments=[
            EnrichmentType.ADVANCED_METRICS,
            EnrichmentType.SHOT_CHART,
            EnrichmentType.OPPONENT_INFO,
            EnrichmentType.GAME_CONTEXT,
            EnrichmentType.TEAM_CONTEXT,          # Add team stats context
        ],
        default_enrichments=[
            EnrichmentType.ADVANCED_METRICS,
            EnrichmentType.GAME_CONTEXT,
        ],
        typical_columns_added=12,
        estimated_fetch_time_ms=75,
        requires_additional_api_calls=True,  # Needs team context
        requires_columns=["PTS", "FGA", "FTA", "FGM", "FG3M", "FTM", "TEAM_ID"],
    ),

    GroupingLevel.PLAYER_SEASON: EnrichmentConfig(
        grouping_level=GroupingLevel.PLAYER_SEASON,
        available_enrichments=[
            EnrichmentType.ADVANCED_METRICS,      # Season-level advanced metrics
            EnrichmentType.SHOT_CHART,            # Season shot summaries
            EnrichmentType.AWARDS_HONORS,         # Awards won that season
            EnrichmentType.TEAM_CONTEXT,          # Team performance context
        ],
        default_enrichments=[
            EnrichmentType.ADVANCED_METRICS,
        ],
        typical_columns_added=15,
        estimated_fetch_time_ms=100,
        requires_additional_api_calls=True,
        requires_columns=["PLAYER_ID", "SEASON_YEAR"],
    ),

    GroupingLevel.PLAYER_TEAM_SEASON: EnrichmentConfig(
        grouping_level=GroupingLevel.PLAYER_TEAM_SEASON,
        available_enrichments=[
            EnrichmentType.ADVANCED_METRICS,
            EnrichmentType.SHOT_CHART,
            EnrichmentType.AWARDS_HONORS,
            EnrichmentType.TEAM_CONTEXT,
        ],
        default_enrichments=[
            EnrichmentType.ADVANCED_METRICS,
            EnrichmentType.TEAM_CONTEXT,
        ],
        typical_columns_added=18,
        estimated_fetch_time_ms=150,
        requires_additional_api_calls=True,
        requires_columns=["PLAYER_ID", "TEAM_ID", "SEASON_YEAR"],
    ),

    GroupingLevel.TEAM_GAME: EnrichmentConfig(
        grouping_level=GroupingLevel.TEAM_GAME,
        available_enrichments=[
            EnrichmentType.ADVANCED_METRICS,      # Team OffRtg, DefRtg, Pace, NetRtg
            EnrichmentType.SHOT_CHART,            # Team shot patterns
            EnrichmentType.OPPONENT_INFO,         # Opponent stats
            EnrichmentType.GAME_CONTEXT,          # Context (home, streak, etc.)
        ],
        default_enrichments=[
            EnrichmentType.ADVANCED_METRICS,
            EnrichmentType.GAME_CONTEXT,
        ],
        typical_columns_added=12,
        estimated_fetch_time_ms=100,
        requires_additional_api_calls=True,
        requires_columns=["TEAM_ID", "GAME_ID"],
    ),

    GroupingLevel.TEAM_SEASON: EnrichmentConfig(
        grouping_level=GroupingLevel.TEAM_SEASON,
        available_enrichments=[
            EnrichmentType.ADVANCED_METRICS,      # Season-level team metrics
            EnrichmentType.SHOT_CHART,            # Season shot patterns
            EnrichmentType.TEAM_CONTEXT,          # Final standings, playoff results
        ],
        default_enrichments=[
            EnrichmentType.ADVANCED_METRICS,
            EnrichmentType.TEAM_CONTEXT,
        ],
        typical_columns_added=15,
        estimated_fetch_time_ms=150,
        requires_additional_api_calls=True,
        requires_columns=["TEAM_ID", "SEASON_YEAR"],
    ),

    GroupingLevel.PLAY_BY_PLAY_PLAYER: EnrichmentConfig(
        grouping_level=GroupingLevel.PLAY_BY_PLAY_PLAYER,
        available_enrichments=[
            EnrichmentType.LINEUP_CONTEXT,        # Lineup plus/minus
        ],
        default_enrichments=[
            # No defaults - play-by-play already has lineups
        ],
        typical_columns_added=5,
        estimated_fetch_time_ms=200,
        requires_additional_api_calls=False,
        requires_columns=["GAME_ID", "EVENTNUM", "CURRENT_LINEUP_HOME", "CURRENT_LINEUP_AWAY"],
    ),

    GroupingLevel.PLAY_BY_PLAY_TEAM: EnrichmentConfig(
        grouping_level=GroupingLevel.PLAY_BY_PLAY_TEAM,
        available_enrichments=[
            EnrichmentType.LINEUP_CONTEXT,
        ],
        default_enrichments=[],
        typical_columns_added=5,
        estimated_fetch_time_ms=200,
        requires_additional_api_calls=False,
        requires_columns=["GAME_ID", "EVENTNUM"],
    ),

    GroupingLevel.SHOT_CHART_PLAYER: EnrichmentConfig(
        grouping_level=GroupingLevel.SHOT_CHART_PLAYER,
        available_enrichments=[
            # Shot charts are already enriched with zones
        ],
        default_enrichments=[],
        typical_columns_added=0,
        estimated_fetch_time_ms=0,
        requires_additional_api_calls=False,
        requires_columns=["LOC_X", "LOC_Y"],
    ),

    GroupingLevel.SHOT_CHART_TEAM: EnrichmentConfig(
        grouping_level=GroupingLevel.SHOT_CHART_TEAM,
        available_enrichments=[],
        default_enrichments=[],
        typical_columns_added=0,
        estimated_fetch_time_ms=0,
        requires_additional_api_calls=False,
        requires_columns=["LOC_X", "LOC_Y"],
    ),

    GroupingLevel.LINEUP: EnrichmentConfig(
        grouping_level=GroupingLevel.LINEUP,
        available_enrichments=[
            EnrichmentType.ADVANCED_METRICS,      # Lineup net rating, etc.
        ],
        default_enrichments=[],
        typical_columns_added=5,
        estimated_fetch_time_ms=100,
        requires_additional_api_calls=False,
        requires_columns=["GAME_ID", "LINEUP_ID"],
    ),
}


# ============================================================================
# ENRICHMENT ENGINE
# ============================================================================

class EnrichmentEngine:
    """
    Applies enrichments to datasets at the appropriate granularity.

    Features:
    - Automatic enrichment based on grouping level
    - Opt-in/opt-out control
    - Validation to prevent duplicates
    - Parallel enrichment for performance
    """

    def __init__(
        self,
        validation_level: MergeValidationLevel = MergeValidationLevel.WARN
    ):
        """
        Initialize enrichment engine.

        Args:
            validation_level: Validation strictness for merges
        """
        self.merge_manager = MergeManager(validation_level=validation_level)
        self.validation_level = validation_level

    async def enrich(
        self,
        data: pd.DataFrame,
        grouping_level: GroupingLevel,
        enrichments: Optional[List[EnrichmentType]] = None,
        use_defaults: bool = True,
        exclude: Optional[List[EnrichmentType]] = None,
    ) -> pd.DataFrame:
        """
        Enrich a dataset with additional data.

        Args:
            data: Base dataset to enrich
            grouping_level: Grouping level of the data
            enrichments: Specific enrichments to apply (None = use defaults)
            use_defaults: Whether to use default enrichments
            exclude: Enrichments to exclude

        Returns:
            Enriched dataset

        Example:
            # Use default enrichments
            enriched = await engine.enrich(game_logs, GroupingLevel.PLAYER_GAME)

            # Custom enrichments
            enriched = await engine.enrich(
                game_logs,
                GroupingLevel.PLAYER_GAME,
                enrichments=[EnrichmentType.ADVANCED_METRICS, EnrichmentType.SHOT_CHART]
            )

            # Defaults except shot charts
            enriched = await engine.enrich(
                game_logs,
                GroupingLevel.PLAYER_GAME,
                exclude=[EnrichmentType.SHOT_CHART]
            )
        """
        if grouping_level not in ENRICHMENT_CATALOG:
            logger.warning(f"No enrichment config for {grouping_level.value}")
            return data

        config = ENRICHMENT_CATALOG[grouping_level]

        # Determine which enrichments to apply
        if enrichments is None:
            if use_defaults:
                enrichments = config.default_enrichments
            else:
                enrichments = []

        # Apply exclusions
        if exclude:
            enrichments = [e for e in enrichments if e not in exclude]

        if not enrichments:
            logger.debug(f"No enrichments to apply for {grouping_level.value}")
            return data

        logger.info(
            f"Applying {len(enrichments)} enrichments to {grouping_level.value}: "
            f"{[e.value for e in enrichments]}"
        )

        # Apply enrichments in parallel where possible
        enriched_data = data.copy()

        # Group enrichments by whether they require API calls
        sync_enrichments = [e for e in enrichments if not self._requires_api_call(e)]
        async_enrichments = [e for e in enrichments if self._requires_api_call(e)]

        # Apply sync enrichments first (fast)
        for enrichment in sync_enrichments:
            try:
                enriched_data = await self._apply_enrichment(
                    enriched_data, grouping_level, enrichment
                )
            except Exception as e:
                logger.error(f"Failed to apply {enrichment.value}: {e}")
                if self.validation_level == MergeValidationLevel.STRICT:
                    raise

        # Apply async enrichments in parallel
        if async_enrichments:
            tasks = [
                self._apply_enrichment(enriched_data, grouping_level, e)
                for e in async_enrichments
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Use the last successful result (all should be merging onto same base)
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Async enrichment failed: {result}")
                    if self.validation_level == MergeValidationLevel.STRICT:
                        raise result
                elif isinstance(result, pd.DataFrame):
                    enriched_data = result

        # Log enrichment summary
        original_cols = len(data.columns)
        enriched_cols = len(enriched_data.columns)
        logger.info(
            f"Enrichment complete: {original_cols} → {enriched_cols} columns "
            f"(+{enriched_cols - original_cols})"
        )

        return enriched_data

    async def _apply_enrichment(
        self,
        data: pd.DataFrame,
        grouping_level: GroupingLevel,
        enrichment_type: EnrichmentType,
    ) -> pd.DataFrame:
        """Apply a specific enrichment"""
        if enrichment_type == EnrichmentType.ADVANCED_METRICS:
            return await self._enrich_advanced_metrics(data, grouping_level)
        elif enrichment_type == EnrichmentType.SHOT_CHART:
            return await self._enrich_shot_chart(data, grouping_level)
        elif enrichment_type == EnrichmentType.OPPONENT_INFO:
            return await self._enrich_opponent_info(data, grouping_level)
        elif enrichment_type == EnrichmentType.GAME_CONTEXT:
            return await self._enrich_game_context(data, grouping_level)
        elif enrichment_type == EnrichmentType.TEAM_CONTEXT:
            return await self._enrich_team_context(data, grouping_level)
        elif enrichment_type == EnrichmentType.SEASON_AGGREGATES:
            return await self._enrich_season_aggregates(data, grouping_level)
        elif enrichment_type == EnrichmentType.AWARDS_HONORS:
            return await self._enrich_awards(data, grouping_level)
        elif enrichment_type == EnrichmentType.LINEUP_CONTEXT:
            return await self._enrich_lineup_context(data, grouping_level)
        else:
            logger.warning(f"Unknown enrichment type: {enrichment_type}")
            return data

    async def _enrich_advanced_metrics(
        self,
        data: pd.DataFrame,
        grouping_level: GroupingLevel,
    ) -> pd.DataFrame:
        """Add advanced metrics (TS%, eFG%, Game Score, etc.)"""
        from nba_mcp.api.data_groupings import merge_with_advanced_metrics

        try:
            enriched, stats = merge_with_advanced_metrics(
                data,
                grouping_level=grouping_level,
                how="left",
                validation_level="warn",
            )
            logger.debug(
                f"Advanced metrics: {stats['match_rate_pct']:.1f}% match rate, "
                f"+{stats['result_columns'] - stats['left_columns']} columns"
            )
            return enriched
        except Exception as e:
            logger.error(f"Failed to add advanced metrics: {e}")
            return data

    async def _enrich_shot_chart(
        self,
        data: pd.DataFrame,
        grouping_level: GroupingLevel,
    ) -> pd.DataFrame:
        """Add shot chart zone summaries"""
        # This would require fetching shot chart data first
        # For now, return as-is
        logger.debug("Shot chart enrichment not yet implemented")
        return data

    async def _enrich_opponent_info(
        self,
        data: pd.DataFrame,
        grouping_level: GroupingLevel,
    ) -> pd.DataFrame:
        """Add opponent team information"""
        # Extract opponent from MATCHUP column if available
        if "MATCHUP" in data.columns:
            # Parse MATCHUP like "LAL @ BOS" or "LAL vs. BOS"
            data["IS_HOME"] = data["MATCHUP"].str.contains("vs.", na=False)
            data["OPPONENT_ABBR"] = data["MATCHUP"].apply(self._extract_opponent)

        return data

    async def _enrich_game_context(
        self,
        data: pd.DataFrame,
        grouping_level: GroupingLevel,
    ) -> pd.DataFrame:
        """Add game context (home/away, back-to-back, etc.)"""
        # Add home/away if not already present
        if "MATCHUP" in data.columns and "IS_HOME" not in data.columns:
            data["IS_HOME"] = data["MATCHUP"].str.contains("vs.", na=False)

        # Detect back-to-back games if GAME_DATE is available
        if "GAME_DATE" in data.columns and "PLAYER_ID" in data.columns:
            data = data.sort_values(["PLAYER_ID", "GAME_DATE"])
            data["DAYS_REST"] = data.groupby("PLAYER_ID")["GAME_DATE"].transform(
                lambda x: pd.to_datetime(x).diff().dt.days
            )
            data["IS_BACK_TO_BACK"] = data["DAYS_REST"] == 1
        elif "GAME_DATE" in data.columns and "TEAM_ID" in data.columns:
            data = data.sort_values(["TEAM_ID", "GAME_DATE"])
            data["DAYS_REST"] = data.groupby("TEAM_ID")["GAME_DATE"].transform(
                lambda x: pd.to_datetime(x).diff().dt.days
            )
            data["IS_BACK_TO_BACK"] = data["DAYS_REST"] == 1

        return data

    async def _enrich_team_context(
        self,
        data: pd.DataFrame,
        grouping_level: GroupingLevel,
    ) -> pd.DataFrame:
        """Add team context (standings, ratings, etc.)"""
        # This would require fetching team standings/advanced stats
        # Placeholder for now
        logger.debug("Team context enrichment not yet fully implemented")
        return data

    async def _enrich_season_aggregates(
        self,
        data: pd.DataFrame,
        grouping_level: GroupingLevel,
    ) -> pd.DataFrame:
        """Add season aggregate statistics"""
        logger.debug("Season aggregates enrichment not yet implemented")
        return data

    async def _enrich_awards(
        self,
        data: pd.DataFrame,
        grouping_level: GroupingLevel,
    ) -> pd.DataFrame:
        """Add awards and honors information"""
        logger.debug("Awards enrichment not yet implemented")
        return data

    async def _enrich_lineup_context(
        self,
        data: pd.DataFrame,
        grouping_level: GroupingLevel,
    ) -> pd.DataFrame:
        """Add lineup plus/minus and on-court statistics"""
        logger.debug("Lineup context enrichment not yet implemented")
        return data

    @staticmethod
    def _requires_api_call(enrichment_type: EnrichmentType) -> bool:
        """Check if enrichment requires additional API calls"""
        api_required = {
            EnrichmentType.TEAM_CONTEXT,
            EnrichmentType.AWARDS_HONORS,
            EnrichmentType.SHOT_CHART,
        }
        return enrichment_type in api_required

    @staticmethod
    def _extract_opponent(matchup: str) -> str:
        """Extract opponent abbreviation from MATCHUP string"""
        if pd.isna(matchup):
            return ""
        # "LAL @ BOS" -> "BOS", "LAL vs. BOS" -> "BOS"
        parts = matchup.replace("@", "vs.").split("vs.")
        return parts[-1].strip() if len(parts) > 1 else ""


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

_enrichment_engine: Optional[EnrichmentEngine] = None


def get_enrichment_engine() -> EnrichmentEngine:
    """Get singleton enrichment engine"""
    global _enrichment_engine
    if _enrichment_engine is None:
        _enrichment_engine = EnrichmentEngine()
    return _enrichment_engine


async def enrich_dataset(
    data: pd.DataFrame,
    grouping_level: GroupingLevel,
    enrichments: Optional[List[EnrichmentType]] = None,
    use_defaults: bool = True,
    exclude: Optional[List[EnrichmentType]] = None,
) -> pd.DataFrame:
    """
    Convenience function to enrich a dataset.

    Args:
        data: Dataset to enrich
        grouping_level: Grouping level
        enrichments: Specific enrichments (None = defaults)
        use_defaults: Use default enrichments
        exclude: Enrichments to exclude

    Returns:
        Enriched dataset

    Example:
        enriched = await enrich_dataset(game_logs, GroupingLevel.PLAYER_GAME)
    """
    engine = get_enrichment_engine()
    return await engine.enrich(
        data, grouping_level, enrichments, use_defaults, exclude
    )


def get_available_enrichments(grouping_level: GroupingLevel) -> List[str]:
    """
    Get available enrichments for a grouping level.

    Args:
        grouping_level: Grouping level to query

    Returns:
        List of enrichment type names

    Example:
        enrichments = get_available_enrichments(GroupingLevel.PLAYER_GAME)
        print(f"Available: {enrichments}")
    """
    if grouping_level not in ENRICHMENT_CATALOG:
        return []

    config = ENRICHMENT_CATALOG[grouping_level]
    return [e.value for e in config.available_enrichments]


def get_default_enrichments(grouping_level: GroupingLevel) -> List[str]:
    """
    Get default enrichments for a grouping level.

    Args:
        grouping_level: Grouping level to query

    Returns:
        List of default enrichment type names
    """
    if grouping_level not in ENRICHMENT_CATALOG:
        return []

    config = ENRICHMENT_CATALOG[grouping_level]
    return [e.value for e in config.default_enrichments]


def get_enrichment_info(grouping_level: GroupingLevel) -> Dict[str, Any]:
    """
    Get comprehensive enrichment information for a grouping level.

    Args:
        grouping_level: Grouping level to query

    Returns:
        Dictionary with enrichment details
    """
    if grouping_level not in ENRICHMENT_CATALOG:
        return {}

    config = ENRICHMENT_CATALOG[grouping_level]
    return {
        "grouping_level": config.grouping_level.value,
        "available_enrichments": [e.value for e in config.available_enrichments],
        "default_enrichments": [e.value for e in config.default_enrichments],
        "typical_columns_added": config.typical_columns_added,
        "estimated_fetch_time_ms": config.estimated_fetch_time_ms,
        "requires_additional_api_calls": config.requires_additional_api_calls,
        "requires_columns": config.requires_columns,
    }
