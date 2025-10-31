"""
Merge Manager for NBA Data Groupings

Provides safe, validated merge operations for combining different data sources
(game logs, advanced metrics, shot charts, etc.) at the appropriate granularity level.

Key Features:
- Granularity-aware merging with correct identifier columns
- Pre/post-merge validation to prevent data loss
- Support for all grouping levels (player/game, team/season, play-by-play, shot charts)
- Comprehensive merge statistics and diagnostics
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Set, Tuple, Union

import pandas as pd
import pyarrow as pa
import duckdb

from nba_mcp.api.data_groupings import GroupingLevel, GranularityLevel
from nba_mcp.data.joins import join_tables, validate_join_columns, JoinError

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION & METADATA
# ============================================================================

class MergeValidationLevel(str, Enum):
    """Validation strictness levels"""
    STRICT = "strict"      # Fail on any validation issue
    WARN = "warn"          # Log warnings but continue
    MINIMAL = "minimal"    # Only critical validations


@dataclass
class MergeConfig:
    """Configuration for a specific merge operation"""
    grouping_level: GroupingLevel
    identifier_columns: List[str]
    optional_identifier_columns: List[str] = field(default_factory=list)
    special_columns: List[str] = field(default_factory=list)
    granularity: GranularityLevel = GranularityLevel.DAY

    def get_all_identifier_columns(self) -> List[str]:
        """Get all identifier columns (required + optional)"""
        return self.identifier_columns + self.optional_identifier_columns


# Merge configuration catalog - defines identifier columns for each grouping
MERGE_CONFIG_CATALOG: Dict[GroupingLevel, MergeConfig] = {
    GroupingLevel.PLAYER_GAME: MergeConfig(
        grouping_level=GroupingLevel.PLAYER_GAME,
        identifier_columns=["PLAYER_ID", "GAME_ID"],
        optional_identifier_columns=["GAME_DATE", "SEASON_YEAR"],
        granularity=GranularityLevel.DAY,
    ),
    GroupingLevel.PLAYER_TEAM_GAME: MergeConfig(
        grouping_level=GroupingLevel.PLAYER_TEAM_GAME,
        identifier_columns=["PLAYER_ID", "TEAM_ID", "GAME_ID"],
        optional_identifier_columns=["GAME_DATE", "SEASON_YEAR"],
        granularity=GranularityLevel.DAY,
    ),
    GroupingLevel.PLAYER_SEASON: MergeConfig(
        grouping_level=GroupingLevel.PLAYER_SEASON,
        identifier_columns=["PLAYER_ID", "SEASON_YEAR"],
        granularity=GranularityLevel.SEASON,
    ),
    GroupingLevel.PLAYER_TEAM_SEASON: MergeConfig(
        grouping_level=GroupingLevel.PLAYER_TEAM_SEASON,
        identifier_columns=["PLAYER_ID", "TEAM_ID", "SEASON_YEAR"],
        granularity=GranularityLevel.SEASON,
    ),
    GroupingLevel.TEAM_GAME: MergeConfig(
        grouping_level=GroupingLevel.TEAM_GAME,
        identifier_columns=["TEAM_ID", "GAME_ID"],
        optional_identifier_columns=["GAME_DATE", "SEASON_YEAR"],
        granularity=GranularityLevel.DAY,
    ),
    GroupingLevel.TEAM_SEASON: MergeConfig(
        grouping_level=GroupingLevel.TEAM_SEASON,
        identifier_columns=["TEAM_ID", "SEASON_YEAR"],
        granularity=GranularityLevel.SEASON,
    ),
    GroupingLevel.PLAY_BY_PLAY_PLAYER: MergeConfig(
        grouping_level=GroupingLevel.PLAY_BY_PLAY_PLAYER,
        identifier_columns=["GAME_ID", "EVENTNUM"],
        optional_identifier_columns=["PLAYER_ID"],
        special_columns=["CURRENT_LINEUP_HOME", "CURRENT_LINEUP_AWAY",
                        "LINEUP_ID_HOME", "LINEUP_ID_AWAY"],
        granularity=GranularityLevel.SECOND,
    ),
    GroupingLevel.PLAY_BY_PLAY_TEAM: MergeConfig(
        grouping_level=GroupingLevel.PLAY_BY_PLAY_TEAM,
        identifier_columns=["GAME_ID", "EVENTNUM"],
        optional_identifier_columns=["TEAM_ID"],
        special_columns=["CURRENT_LINEUP_HOME", "CURRENT_LINEUP_AWAY",
                        "LINEUP_ID_HOME", "LINEUP_ID_AWAY"],
        granularity=GranularityLevel.SECOND,
    ),
    GroupingLevel.SHOT_CHART_PLAYER: MergeConfig(
        grouping_level=GroupingLevel.SHOT_CHART_PLAYER,
        identifier_columns=["PLAYER_ID", "GAME_ID", "GAME_EVENT_ID"],
        optional_identifier_columns=["GAME_DATE", "SEASON"],
        special_columns=["LOC_X", "LOC_Y", "SHOT_ZONE_BASIC",
                        "SHOT_ZONE_AREA", "SHOT_ZONE_RANGE"],
        granularity=GranularityLevel.SPATIAL,
    ),
    GroupingLevel.SHOT_CHART_TEAM: MergeConfig(
        grouping_level=GroupingLevel.SHOT_CHART_TEAM,
        identifier_columns=["TEAM_ID", "GAME_ID", "GAME_EVENT_ID"],
        optional_identifier_columns=["GAME_DATE", "SEASON"],
        special_columns=["LOC_X", "LOC_Y", "SHOT_ZONE_BASIC",
                        "SHOT_ZONE_AREA", "SHOT_ZONE_RANGE"],
        granularity=GranularityLevel.SPATIAL,
    ),
    GroupingLevel.LINEUP: MergeConfig(
        grouping_level=GroupingLevel.LINEUP,
        identifier_columns=["GAME_ID", "LINEUP_ID"],
        optional_identifier_columns=["PERIOD"],
        special_columns=["LINEUP_PLAYERS", "LINEUP_MIN", "LINEUP_PLUS_MINUS"],
        granularity=GranularityLevel.COMBINATION,
    ),
}


# ============================================================================
# VALIDATION RESULT CLASSES
# ============================================================================

@dataclass
class ValidationIssue:
    """A single validation issue found during merge"""
    severity: Literal["error", "warning", "info"]
    category: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MergeValidationResult:
    """Results from merge validation"""
    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)

    def add_error(self, category: str, message: str, **details):
        """Add an error-level issue"""
        self.issues.append(ValidationIssue("error", category, message, details))
        self.is_valid = False

    def add_warning(self, category: str, message: str, **details):
        """Add a warning-level issue"""
        self.issues.append(ValidationIssue("warning", category, message, details))

    def add_info(self, category: str, message: str, **details):
        """Add an info-level issue"""
        self.issues.append(ValidationIssue("info", category, message, details))

    def get_errors(self) -> List[ValidationIssue]:
        """Get all error-level issues"""
        return [i for i in self.issues if i.severity == "error"]

    def get_warnings(self) -> List[ValidationIssue]:
        """Get all warning-level issues"""
        return [i for i in self.issues if i.severity == "warning"]


@dataclass
class MergeStatistics:
    """Statistics about a merge operation"""
    left_rows: int
    right_rows: int
    result_rows: int
    left_columns: int
    right_columns: int
    result_columns: int
    join_type: str
    identifier_columns: List[str]
    rows_matched: int
    rows_unmatched_left: int
    rows_unmatched_right: int
    execution_time_ms: float

    @property
    def match_rate(self) -> float:
        """Percentage of left rows that matched"""
        if self.left_rows == 0:
            return 0.0
        return (self.rows_matched / self.left_rows) * 100

    @property
    def data_loss(self) -> int:
        """Number of rows lost (for inner joins)"""
        if self.join_type == "inner":
            return self.left_rows - self.result_rows
        return 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "left_rows": self.left_rows,
            "right_rows": self.right_rows,
            "result_rows": self.result_rows,
            "left_columns": self.left_columns,
            "right_columns": self.right_columns,
            "result_columns": self.result_columns,
            "join_type": self.join_type,
            "identifier_columns": self.identifier_columns,
            "rows_matched": self.rows_matched,
            "rows_unmatched_left": self.rows_unmatched_left,
            "rows_unmatched_right": self.rows_unmatched_right,
            "match_rate_pct": round(self.match_rate, 2),
            "data_loss": self.data_loss,
            "execution_time_ms": round(self.execution_time_ms, 2),
        }


# ============================================================================
# MERGE MANAGER
# ============================================================================

class MergeManager:
    """
    Manages safe, validated merges for NBA data groupings.

    Features:
    - Granularity-aware identifier column selection
    - Pre-merge and post-merge validation
    - Detailed merge statistics
    - Support for different validation levels
    - Automatic join type selection
    """

    def __init__(self, validation_level: MergeValidationLevel = MergeValidationLevel.WARN):
        """
        Initialize merge manager.

        Args:
            validation_level: How strict to be with validation
        """
        self.validation_level = validation_level

    def merge(
        self,
        base_data: Union[pd.DataFrame, pa.Table],
        merge_data: Union[pd.DataFrame, pa.Table],
        grouping_level: Union[GroupingLevel, str],
        how: Literal["inner", "left", "right", "outer"] = "left",
        identifier_columns: Optional[List[str]] = None,
        validate: bool = True,
    ) -> Tuple[Union[pd.DataFrame, pa.Table], MergeStatistics]:
        """
        Merge two datasets at a specific grouping level with validation.

        Args:
            base_data: Base dataset (left side of join)
            merge_data: Dataset to merge (right side of join)
            grouping_level: Grouping level (e.g., "player/game", GroupingLevel.PLAYER_GAME)
            how: Join type (inner, left, right, outer)
            identifier_columns: Override default identifier columns
            validate: Whether to perform validation

        Returns:
            Tuple of (merged_data, merge_statistics)

        Raises:
            ValueError: If validation fails and validation_level is STRICT
        """
        import time
        start_time = time.time()

        # Convert grouping_level to enum if string
        if isinstance(grouping_level, str):
            grouping_level = GroupingLevel(grouping_level)

        # Get merge configuration
        if grouping_level not in MERGE_CONFIG_CATALOG:
            raise ValueError(f"Unsupported grouping level: {grouping_level.value}")

        config = MERGE_CONFIG_CATALOG[grouping_level]

        # Determine identifier columns
        if identifier_columns is None:
            identifier_columns = self._select_identifier_columns(
                base_data, merge_data, config
            )

        logger.info(
            f"Merging at {grouping_level.value} level using identifiers: {identifier_columns}"
        )

        # Convert to PyArrow tables if needed
        base_table = self._to_arrow_table(base_data)
        merge_table = self._to_arrow_table(merge_data)

        # Pre-merge validation
        if validate:
            validation_result = self._validate_pre_merge(
                base_table, merge_table, identifier_columns, config
            )
            self._handle_validation_result(validation_result, "pre-merge")

        # Perform the merge using DuckDB join
        try:
            result_table = join_tables(
                tables=[base_table, merge_table],
                on=identifier_columns,
                how=how,
            )
        except JoinError as e:
            raise ValueError(f"Merge failed: {str(e)}") from e

        # Calculate merge statistics
        stats = self._calculate_merge_statistics(
            base_table, merge_table, result_table,
            how, identifier_columns, time.time() - start_time
        )

        logger.info(
            f"Merge complete: {stats.left_rows} + {stats.right_rows} → "
            f"{stats.result_rows} rows ({stats.match_rate:.1f}% match rate)"
        )

        # Post-merge validation
        if validate:
            validation_result = self._validate_post_merge(
                base_table, merge_table, result_table, stats, how
            )
            self._handle_validation_result(validation_result, "post-merge")

        # Convert back to original format if needed
        if isinstance(base_data, pd.DataFrame):
            return result_table.to_pandas(), stats
        return result_table, stats

    def merge_advanced_metrics(
        self,
        game_data: Union[pd.DataFrame, pa.Table],
        grouping_level: Union[GroupingLevel, str],
        metrics: Optional[List[str]] = None,
        how: Literal["left", "inner"] = "left",
    ) -> Tuple[Union[pd.DataFrame, pa.Table], MergeStatistics]:
        """
        Merge advanced metrics onto game-level or season-level data.

        This is a convenience method that computes advanced metrics from the
        base data and merges them back at the appropriate granularity.

        Args:
            game_data: Base game data (must include PTS, FGA, FTA, etc.)
            grouping_level: Target grouping level
            metrics: Specific metrics to compute (default: all)
            how: Join type (left recommended to preserve all base rows)

        Returns:
            Tuple of (data_with_metrics, merge_statistics)
        """
        from nba_mcp.api.advanced_metrics_calculator import (
            calculate_game_score,
            calculate_true_shooting_pct,
            calculate_effective_fg_pct,
        )

        # Convert to DataFrame for metric calculation
        if isinstance(game_data, pa.Table):
            df = game_data.to_pandas()
        else:
            df = game_data.copy()

        # Calculate advanced metrics
        metrics_df = pd.DataFrame()

        # Determine identifier columns based on grouping level
        if isinstance(grouping_level, str):
            grouping_level = GroupingLevel(grouping_level)

        config = MERGE_CONFIG_CATALOG[grouping_level]

        # Copy identifier columns
        for col in config.identifier_columns:
            if col in df.columns:
                metrics_df[col] = df[col]

        # Calculate metrics (if columns exist)
        if metrics is None or "TRUE_SHOOTING_PCT" in metrics:
            if all(c in df.columns for c in ["PTS", "FGA", "FTA"]):
                metrics_df["TRUE_SHOOTING_PCT"] = df.apply(
                    lambda row: calculate_true_shooting_pct(row["PTS"], row["FGA"], row["FTA"]), axis=1
                )

        if metrics is None or "EFFECTIVE_FG_PCT" in metrics:
            if all(c in df.columns for c in ["FGM", "FG3M", "FGA"]):
                metrics_df["EFFECTIVE_FG_PCT"] = df.apply(
                    lambda row: calculate_effective_fg_pct(row["FGM"], row["FG3M"], row["FGA"]), axis=1
                )

        if metrics is None or "GAME_SCORE" in metrics:
            required_cols = ["PTS", "FGM", "FGA", "FTM", "FTA", "OREB", "DREB",
                           "STL", "AST", "BLK", "PF", "TOV"]
            if all(c in df.columns for c in required_cols):
                metrics_df["GAME_SCORE"] = df.apply(
                    lambda row: calculate_game_score(row.to_dict()), axis=1
                )

        # Merge back onto original data
        return self.merge(
            base_data=game_data,
            merge_data=metrics_df,
            grouping_level=grouping_level,
            how=how,
            validate=True,
        )

    def merge_shot_chart_data(
        self,
        game_data: Union[pd.DataFrame, pa.Table],
        shot_chart_data: Union[pd.DataFrame, pa.Table],
        grouping_level: Union[GroupingLevel, str],
        aggregation: Literal["count", "avg", "zone_summary"] = "zone_summary",
        how: Literal["left", "inner"] = "left",
    ) -> Tuple[Union[pd.DataFrame, pa.Table], MergeStatistics]:
        """
        Merge shot chart data onto game-level data with spatial aggregation.

        Args:
            game_data: Base game data
            shot_chart_data: Raw shot chart data with LOC_X, LOC_Y
            grouping_level: Target grouping level (must be game-level)
            aggregation: How to aggregate shots (count, avg, zone_summary)
            how: Join type

        Returns:
            Tuple of (data_with_shots, merge_statistics)
        """
        # Convert to DataFrames for aggregation
        if isinstance(shot_chart_data, pa.Table):
            shots_df = shot_chart_data.to_pandas()
        else:
            shots_df = shot_chart_data.copy()

        # Get grouping config
        if isinstance(grouping_level, str):
            grouping_level = GroupingLevel(grouping_level)

        config = MERGE_CONFIG_CATALOG[grouping_level]

        # Aggregate shots by the identifier columns
        if aggregation == "count":
            agg_shots = shots_df.groupby(config.identifier_columns).size().reset_index(name="SHOT_COUNT")
        elif aggregation == "avg":
            agg_shots = shots_df.groupby(config.identifier_columns).agg({
                "SHOT_MADE_FLAG": ["sum", "mean"],
                "SHOT_DISTANCE": "mean",
            }).reset_index()
            agg_shots.columns = config.identifier_columns + [
                "SHOTS_MADE", "FG_PCT_SHOTS", "AVG_SHOT_DISTANCE"
            ]
        elif aggregation == "zone_summary":
            # Aggregate by zone
            zone_stats = []
            for zone in ["Paint", "Mid-Range", "Three Point"]:
                zone_df = shots_df[shots_df["SHOT_ZONE_BASIC"] == zone]
                if not zone_df.empty:
                    zone_agg = zone_df.groupby(config.identifier_columns).agg({
                        "SHOT_MADE_FLAG": ["sum", "count", "mean"]
                    }).reset_index()
                    zone_agg.columns = config.identifier_columns + [
                        f"{zone.replace(' ', '_').upper()}_MADE",
                        f"{zone.replace(' ', '_').upper()}_ATTEMPTS",
                        f"{zone.replace(' ', '_').upper()}_PCT",
                    ]
                    zone_stats.append(zone_agg)

            # Merge all zones
            agg_shots = zone_stats[0] if zone_stats else pd.DataFrame()
            for zone_df in zone_stats[1:]:
                agg_shots = pd.merge(agg_shots, zone_df, on=config.identifier_columns, how="outer")

        # Merge onto game data
        return self.merge(
            base_data=game_data,
            merge_data=agg_shots,
            grouping_level=grouping_level,
            how=how,
            validate=True,
        )

    # ========================================================================
    # INTERNAL VALIDATION METHODS
    # ========================================================================

    def _validate_pre_merge(
        self,
        base_table: pa.Table,
        merge_table: pa.Table,
        identifier_columns: List[str],
        config: MergeConfig,
    ) -> MergeValidationResult:
        """Validate datasets before merge"""
        result = MergeValidationResult(is_valid=True)

        # Check identifier columns exist
        base_cols = set(base_table.column_names)
        merge_cols = set(merge_table.column_names)

        for col in identifier_columns:
            if col not in base_cols:
                result.add_error(
                    "missing_column",
                    f"Identifier column '{col}' not found in base dataset",
                    column=col,
                    available_columns=list(base_cols),
                )
            if col not in merge_cols:
                result.add_error(
                    "missing_column",
                    f"Identifier column '{col}' not found in merge dataset",
                    column=col,
                    available_columns=list(merge_cols),
                )

        # Check for nulls in identifier columns
        for col in identifier_columns:
            if col in base_cols:
                null_count = base_table.column(col).null_count
                if null_count > 0:
                    result.add_warning(
                        "null_identifiers",
                        f"Base dataset has {null_count} null values in '{col}'",
                        column=col,
                        null_count=null_count,
                    )

            if col in merge_cols:
                null_count = merge_table.column(col).null_count
                if null_count > 0:
                    result.add_warning(
                        "null_identifiers",
                        f"Merge dataset has {null_count} null values in '{col}'",
                        column=col,
                        null_count=null_count,
                    )

        # Check for duplicates in identifier columns
        base_df = base_table.to_pandas()
        merge_df = merge_table.to_pandas()

        base_duplicates = base_df.duplicated(subset=identifier_columns, keep=False).sum()
        if base_duplicates > 0:
            result.add_warning(
                "duplicate_identifiers",
                f"Base dataset has {base_duplicates} duplicate rows on identifier columns",
                duplicate_count=base_duplicates,
            )

        merge_duplicates = merge_df.duplicated(subset=identifier_columns, keep=False).sum()
        if merge_duplicates > 0:
            result.add_warning(
                "duplicate_identifiers",
                f"Merge dataset has {merge_duplicates} duplicate rows on identifier columns",
                duplicate_count=merge_duplicates,
            )

        return result

    def _validate_post_merge(
        self,
        base_table: pa.Table,
        merge_table: pa.Table,
        result_table: pa.Table,
        stats: MergeStatistics,
        join_type: str,
    ) -> MergeValidationResult:
        """Validate results after merge"""
        result = MergeValidationResult(is_valid=True)

        # Check for unexpected data loss
        if join_type == "left" and stats.result_rows < stats.left_rows:
            result.add_error(
                "data_loss",
                f"Left join lost {stats.left_rows - stats.result_rows} rows",
                expected_rows=stats.left_rows,
                actual_rows=stats.result_rows,
            )

        if join_type == "inner" and stats.data_loss > 0:
            loss_pct = (stats.data_loss / stats.left_rows) * 100
            if loss_pct > 10:  # More than 10% data loss
                result.add_warning(
                    "high_data_loss",
                    f"Inner join lost {loss_pct:.1f}% of base data ({stats.data_loss} rows)",
                    data_loss=stats.data_loss,
                    data_loss_pct=loss_pct,
                )

        # Check for unexpected duplicates
        expected_rows = stats.left_rows if join_type == "left" else None
        if expected_rows and stats.result_rows > expected_rows:
            result.add_warning(
                "unexpected_duplicates",
                f"Result has more rows ({stats.result_rows}) than expected ({expected_rows})",
                expected_rows=expected_rows,
                actual_rows=stats.result_rows,
            )

        # Check match rate
        if stats.match_rate < 50:
            result.add_warning(
                "low_match_rate",
                f"Only {stats.match_rate:.1f}% of base rows matched",
                match_rate=stats.match_rate,
                rows_matched=stats.rows_matched,
                rows_unmatched=stats.rows_unmatched_left,
            )

        return result

    def _handle_validation_result(self, validation_result: MergeValidationResult, stage: str):
        """Handle validation results based on validation level"""
        if not validation_result.is_valid:
            error_msg = f"{stage} validation failed:\n"
            for issue in validation_result.get_errors():
                error_msg += f"  - [{issue.category}] {issue.message}\n"

            if self.validation_level == MergeValidationLevel.STRICT:
                raise ValueError(error_msg)
            else:
                logger.warning(error_msg)

        # Log warnings
        for warning in validation_result.get_warnings():
            logger.warning(f"[{stage}] [{warning.category}] {warning.message}")

    def _select_identifier_columns(
        self,
        base_data: Union[pd.DataFrame, pa.Table],
        merge_data: Union[pd.DataFrame, pa.Table],
        config: MergeConfig,
    ) -> List[str]:
        """
        Intelligently select identifier columns based on available columns.

        Prioritizes required columns, then adds optional columns if available.
        """
        if isinstance(base_data, pa.Table):
            base_cols = set(base_data.column_names)
        else:
            base_cols = set(base_data.columns)

        if isinstance(merge_data, pa.Table):
            merge_cols = set(merge_data.column_names)
        else:
            merge_cols = set(merge_data.columns)

        # Start with required columns
        identifier_columns = []

        for col in config.identifier_columns:
            if col in base_cols and col in merge_cols:
                identifier_columns.append(col)
            else:
                # Required column missing - this is an error
                raise ValueError(
                    f"Required identifier column '{col}' not found in both datasets. "
                    f"Base columns: {list(base_cols)}, Merge columns: {list(merge_cols)}"
                )

        # Add optional columns if available
        for col in config.optional_identifier_columns:
            if col in base_cols and col in merge_cols:
                identifier_columns.append(col)

        return identifier_columns

    def _calculate_merge_statistics(
        self,
        base_table: pa.Table,
        merge_table: pa.Table,
        result_table: pa.Table,
        join_type: str,
        identifier_columns: List[str],
        execution_time: float,
    ) -> MergeStatistics:
        """Calculate comprehensive merge statistics"""
        # Calculate matched vs unmatched rows
        if join_type == "left":
            rows_matched = result_table.num_rows  # All rows have at least base data
            rows_unmatched_left = 0
            rows_unmatched_right = merge_table.num_rows - rows_matched
        elif join_type == "inner":
            rows_matched = result_table.num_rows
            rows_unmatched_left = base_table.num_rows - rows_matched
            rows_unmatched_right = merge_table.num_rows - rows_matched
        else:
            # For right/outer joins, calculate based on comparison
            rows_matched = min(base_table.num_rows, merge_table.num_rows)
            rows_unmatched_left = max(0, base_table.num_rows - rows_matched)
            rows_unmatched_right = max(0, merge_table.num_rows - rows_matched)

        return MergeStatistics(
            left_rows=base_table.num_rows,
            right_rows=merge_table.num_rows,
            result_rows=result_table.num_rows,
            left_columns=base_table.num_columns,
            right_columns=merge_table.num_columns,
            result_columns=result_table.num_columns,
            join_type=join_type,
            identifier_columns=identifier_columns,
            rows_matched=rows_matched,
            rows_unmatched_left=rows_unmatched_left,
            rows_unmatched_right=rows_unmatched_right,
            execution_time_ms=execution_time * 1000,
        )

    @staticmethod
    def _to_arrow_table(data: Union[pd.DataFrame, pa.Table]) -> pa.Table:
        """Convert data to PyArrow table if needed"""
        if isinstance(data, pa.Table):
            return data
        return pa.Table.from_pandas(data)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def merge_datasets(
    base_data: Union[pd.DataFrame, pa.Table],
    merge_data: Union[pd.DataFrame, pa.Table],
    grouping_level: Union[GroupingLevel, str],
    how: Literal["inner", "left", "right", "outer"] = "left",
    validation_level: MergeValidationLevel = MergeValidationLevel.WARN,
) -> Tuple[Union[pd.DataFrame, pa.Table], MergeStatistics]:
    """
    Convenience function to merge two datasets at a specific grouping level.

    Args:
        base_data: Base dataset
        merge_data: Dataset to merge
        grouping_level: Grouping level (e.g., "player/game")
        how: Join type
        validation_level: Validation strictness

    Returns:
        Tuple of (merged_data, merge_statistics)

    Example:
        merged_df, stats = merge_datasets(
            game_logs,
            advanced_metrics,
            grouping_level="player/game",
            how="left"
        )
        print(f"Match rate: {stats.match_rate:.1f}%")
    """
    manager = MergeManager(validation_level=validation_level)
    return manager.merge(base_data, merge_data, grouping_level, how)


def get_merge_config(grouping_level: Union[GroupingLevel, str]) -> MergeConfig:
    """
    Get merge configuration for a specific grouping level.

    Args:
        grouping_level: Grouping level to query

    Returns:
        MergeConfig with identifier columns and metadata

    Example:
        config = get_merge_config("player/game")
        print(f"Identifier columns: {config.identifier_columns}")
    """
    if isinstance(grouping_level, str):
        grouping_level = GroupingLevel(grouping_level)

    if grouping_level not in MERGE_CONFIG_CATALOG:
        raise ValueError(f"Unsupported grouping level: {grouping_level.value}")

    return MERGE_CONFIG_CATALOG[grouping_level]


def list_merge_configs() -> Dict[str, Dict[str, Any]]:
    """
    List all available merge configurations.

    Returns:
        Dictionary mapping grouping levels to their configurations

    Example:
        configs = list_merge_configs()
        for level, config in configs.items():
            print(f"{level}: {config['identifier_columns']}")
    """
    return {
        level.value: {
            "identifier_columns": config.identifier_columns,
            "optional_identifier_columns": config.optional_identifier_columns,
            "special_columns": config.special_columns,
            "granularity": config.granularity.value,
        }
        for level, config in MERGE_CONFIG_CATALOG.items()
    }
