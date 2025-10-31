"""
Dataset Inspector for NBA Grouping Datasets

Provides comprehensive information about each grouping dataset including:
- Available columns and their data types
- Identifier columns for merging
- Optional filters and parameters
- Example usage patterns
- Merge compatibility information
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum

from nba_mcp.api.data_groupings import (
    GroupingLevel,
    GranularityLevel,
    GROUPING_CATALOG,
    GroupingMetadata,
)
from nba_mcp.data.merge_manager import (
    MERGE_CONFIG_CATALOG,
    MergeConfig,
)

logger = logging.getLogger(__name__)


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class ColumnInfo:
    """Information about a single column"""
    name: str
    data_type: str
    description: str
    is_identifier: bool = False
    is_optional_identifier: bool = False
    is_special: bool = False
    example_values: List[Any] = field(default_factory=list)


@dataclass
class DatasetInfo:
    """Comprehensive information about a dataset"""
    grouping_level: str
    granularity: str
    description: str

    # Column information
    all_columns: List[ColumnInfo] = field(default_factory=list)
    identifier_columns: List[str] = field(default_factory=list)
    optional_identifier_columns: List[str] = field(default_factory=list)
    special_columns: List[str] = field(default_factory=list)

    # API information
    endpoint: str = ""
    required_params: List[str] = field(default_factory=list)
    optional_params: List[str] = field(default_factory=list)

    # Merge compatibility
    can_merge_with: List[str] = field(default_factory=list)
    typical_row_count: str = ""

    # Usage examples
    example_usage: str = ""
    example_merge: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "grouping_level": self.grouping_level,
            "granularity": self.granularity,
            "description": self.description,
            "columns": {
                "all_columns": [
                    {
                        "name": col.name,
                        "type": col.data_type,
                        "description": col.description,
                        "is_identifier": col.is_identifier,
                        "is_optional_identifier": col.is_optional_identifier,
                        "is_special": col.is_special,
                    }
                    for col in self.all_columns
                ],
                "identifier_columns": self.identifier_columns,
                "optional_identifier_columns": self.optional_identifier_columns,
                "special_columns": self.special_columns,
            },
            "api": {
                "endpoint": self.endpoint,
                "required_params": self.required_params,
                "optional_params": self.optional_params,
            },
            "merge_info": {
                "can_merge_with": self.can_merge_with,
                "typical_row_count": self.typical_row_count,
            },
            "examples": {
                "usage": self.example_usage,
                "merge": self.example_merge,
            },
        }

    def to_markdown(self) -> str:
        """Convert to markdown format for display"""
        md = f"# {self.grouping_level.upper()} Dataset\n\n"
        md += f"**Granularity:** {self.granularity}\n\n"
        md += f"{self.description}\n\n"

        # API Information
        md += "## API Information\n\n"
        md += f"**Endpoint:** `{self.endpoint}`\n\n"
        md += f"**Required Parameters:** {', '.join(f'`{p}`' for p in self.required_params)}\n\n"
        if self.optional_params:
            md += f"**Optional Parameters:** {', '.join(f'`{p}`' for p in self.optional_params)}\n\n"

        # Column Information
        md += "## Columns\n\n"
        md += "### Identifier Columns (for merging)\n"
        for col_name in self.identifier_columns:
            col = next((c for c in self.all_columns if c.name == col_name), None)
            if col:
                md += f"- **{col.name}** ({col.data_type}): {col.description}\n"

        if self.optional_identifier_columns:
            md += "\n### Optional Identifier Columns\n"
            for col_name in self.optional_identifier_columns:
                col = next((c for c in self.all_columns if c.name == col_name), None)
                if col:
                    md += f"- **{col.name}** ({col.data_type}): {col.description}\n"

        if self.special_columns:
            md += "\n### Special Columns\n"
            for col_name in self.special_columns:
                col = next((c for c in self.all_columns if c.name == col_name), None)
                if col:
                    md += f"- **{col.name}** ({col.data_type}): {col.description}\n"

        md += "\n### Data Columns\n"
        for col in self.all_columns:
            if (col.name not in self.identifier_columns and
                col.name not in self.optional_identifier_columns and
                col.name not in self.special_columns):
                md += f"- **{col.name}** ({col.data_type}): {col.description}\n"

        # Merge Information
        md += "\n## Merge Compatibility\n\n"
        md += f"**Typical Row Count:** {self.typical_row_count}\n\n"
        if self.can_merge_with:
            md += "**Can merge with:**\n"
            for mergeable in self.can_merge_with:
                md += f"- {mergeable}\n"

        # Examples
        if self.example_usage:
            md += "\n## Example Usage\n\n"
            md += f"```python\n{self.example_usage}\n```\n\n"

        if self.example_merge:
            md += "## Example Merge\n\n"
            md += f"```python\n{self.example_merge}\n```\n\n"

        return md


# ============================================================================
# COLUMN DEFINITIONS
# ============================================================================

# Common columns across datasets
COMMON_COLUMNS = {
    "PLAYER_ID": ColumnInfo(
        name="PLAYER_ID",
        data_type="int",
        description="Unique NBA player identifier",
        is_identifier=True,
    ),
    "PLAYER_NAME": ColumnInfo(
        name="PLAYER_NAME",
        data_type="str",
        description="Player's full name",
    ),
    "TEAM_ID": ColumnInfo(
        name="TEAM_ID",
        data_type="int",
        description="Unique NBA team identifier",
        is_identifier=True,
    ),
    "TEAM_ABBREVIATION": ColumnInfo(
        name="TEAM_ABBREVIATION",
        data_type="str",
        description="3-letter team abbreviation (e.g., LAL, BOS)",
    ),
    "GAME_ID": ColumnInfo(
        name="GAME_ID",
        data_type="str",
        description="Unique game identifier (10 digits, format: 00SSSTTGGG)",
        is_identifier=True,
    ),
    "GAME_DATE": ColumnInfo(
        name="GAME_DATE",
        data_type="date",
        description="Date of the game (YYYY-MM-DD)",
        is_optional_identifier=True,
    ),
    "SEASON_YEAR": ColumnInfo(
        name="SEASON_YEAR",
        data_type="str",
        description="NBA season (e.g., 2023-24)",
        is_optional_identifier=True,
    ),

    # Box score stats
    "PTS": ColumnInfo(
        name="PTS",
        data_type="int",
        description="Points scored",
    ),
    "REB": ColumnInfo(
        name="REB",
        data_type="int",
        description="Total rebounds",
    ),
    "AST": ColumnInfo(
        name="AST",
        data_type="int",
        description="Assists",
    ),
    "STL": ColumnInfo(
        name="STL",
        data_type="int",
        description="Steals",
    ),
    "BLK": ColumnInfo(
        name="BLK",
        data_type="int",
        description="Blocks",
    ),
    "TOV": ColumnInfo(
        name="TOV",
        data_type="int",
        description="Turnovers",
    ),
    "FGM": ColumnInfo(
        name="FGM",
        data_type="int",
        description="Field goals made",
    ),
    "FGA": ColumnInfo(
        name="FGA",
        data_type="int",
        description="Field goals attempted",
    ),
    "FG_PCT": ColumnInfo(
        name="FG_PCT",
        data_type="float",
        description="Field goal percentage (0.0-1.0)",
    ),
    "FG3M": ColumnInfo(
        name="FG3M",
        data_type="int",
        description="Three-pointers made",
    ),
    "FG3A": ColumnInfo(
        name="FG3A",
        data_type="int",
        description="Three-pointers attempted",
    ),
    "FG3_PCT": ColumnInfo(
        name="FG3_PCT",
        data_type="float",
        description="Three-point percentage (0.0-1.0)",
    ),
    "FTM": ColumnInfo(
        name="FTM",
        data_type="int",
        description="Free throws made",
    ),
    "FTA": ColumnInfo(
        name="FTA",
        data_type="int",
        description="Free throws attempted",
    ),
    "FT_PCT": ColumnInfo(
        name="FT_PCT",
        data_type="float",
        description="Free throw percentage (0.0-1.0)",
    ),
    "OREB": ColumnInfo(
        name="OREB",
        data_type="int",
        description="Offensive rebounds",
    ),
    "DREB": ColumnInfo(
        name="DREB",
        data_type="int",
        description="Defensive rebounds",
    ),
    "PF": ColumnInfo(
        name="PF",
        data_type="int",
        description="Personal fouls",
    ),
    "MIN": ColumnInfo(
        name="MIN",
        data_type="float",
        description="Minutes played",
    ),
    "PLUS_MINUS": ColumnInfo(
        name="PLUS_MINUS",
        data_type="int",
        description="Plus/minus (team point differential while on court)",
    ),

    # Advanced metrics
    "TRUE_SHOOTING_PCT": ColumnInfo(
        name="TRUE_SHOOTING_PCT",
        data_type="float",
        description="True shooting percentage (accounts for 3PT and FT value)",
    ),
    "EFFECTIVE_FG_PCT": ColumnInfo(
        name="EFFECTIVE_FG_PCT",
        data_type="float",
        description="Effective field goal percentage (adjusts for 3PT value)",
    ),
    "GAME_SCORE": ColumnInfo(
        name="GAME_SCORE",
        data_type="float",
        description="Hollinger's Game Score efficiency metric",
    ),

    # Play-by-play specific
    "EVENTNUM": ColumnInfo(
        name="EVENTNUM",
        data_type="int",
        description="Sequential event number in game",
        is_identifier=True,
    ),
    "CURRENT_LINEUP_HOME": ColumnInfo(
        name="CURRENT_LINEUP_HOME",
        data_type="list",
        description="Current 5-player lineup for home team",
        is_special=True,
    ),
    "CURRENT_LINEUP_AWAY": ColumnInfo(
        name="CURRENT_LINEUP_AWAY",
        data_type="list",
        description="Current 5-player lineup for away team",
        is_special=True,
    ),
    "LINEUP_ID_HOME": ColumnInfo(
        name="LINEUP_ID_HOME",
        data_type="str",
        description="NBA API format lineup ID for home team",
        is_special=True,
    ),
    "LINEUP_ID_AWAY": ColumnInfo(
        name="LINEUP_ID_AWAY",
        data_type="str",
        description="NBA API format lineup ID for away team",
        is_special=True,
    ),

    # Shot chart specific
    "LOC_X": ColumnInfo(
        name="LOC_X",
        data_type="int",
        description="X-coordinate on court (-250 to +250, tenths of feet)",
        is_special=True,
    ),
    "LOC_Y": ColumnInfo(
        name="LOC_Y",
        data_type="int",
        description="Y-coordinate on court (-52.5 to +417.5, tenths of feet)",
        is_special=True,
    ),
    "SHOT_ZONE_BASIC": ColumnInfo(
        name="SHOT_ZONE_BASIC",
        data_type="str",
        description="Basic shot zone (Paint, Mid-Range, Three Point)",
        is_special=True,
    ),
    "SHOT_ZONE_AREA": ColumnInfo(
        name="SHOT_ZONE_AREA",
        data_type="str",
        description="Detailed shot zone area",
        is_special=True,
    ),
    "SHOT_ZONE_RANGE": ColumnInfo(
        name="SHOT_ZONE_RANGE",
        data_type="str",
        description="Distance range of shot",
        is_special=True,
    ),
    "GAME_EVENT_ID": ColumnInfo(
        name="GAME_EVENT_ID",
        data_type="int",
        description="Unique event ID for shot in game",
        is_identifier=True,
    ),
}


# ============================================================================
# DATASET INSPECTOR
# ============================================================================

class DatasetInspector:
    """
    Provides comprehensive information about NBA grouping datasets.

    Features:
    - Column descriptions and data types
    - Identifier columns for merging
    - API parameters and usage
    - Merge compatibility information
    - Example code snippets
    """

    def __init__(self):
        """Initialize the dataset inspector"""
        self._build_dataset_info()

    def _build_dataset_info(self):
        """Build comprehensive information for all datasets"""
        self.datasets: Dict[str, DatasetInfo] = {}

        # Build info for each grouping level
        for level in GroupingLevel:
            if level in GROUPING_CATALOG and level in MERGE_CONFIG_CATALOG:
                info = self._build_single_dataset_info(level)
                self.datasets[level.value] = info

    def _build_single_dataset_info(self, level: GroupingLevel) -> DatasetInfo:
        """Build information for a single dataset"""
        grouping_meta = GROUPING_CATALOG[level]
        merge_config = MERGE_CONFIG_CATALOG[level]

        info = DatasetInfo(
            grouping_level=level.value,
            granularity=grouping_meta.granularity.value,
            description=grouping_meta.description,
            endpoint=grouping_meta.endpoint,
            required_params=grouping_meta.required_params,
            optional_params=grouping_meta.optional_filters,
            identifier_columns=merge_config.identifier_columns,
            optional_identifier_columns=merge_config.optional_identifier_columns,
            special_columns=merge_config.special_columns,
        )

        # Add column information
        all_col_names = set()
        all_col_names.update(merge_config.identifier_columns)
        all_col_names.update(merge_config.optional_identifier_columns)
        all_col_names.update(merge_config.special_columns)

        # Add common box score columns for game-level data
        if grouping_meta.granularity == GranularityLevel.DAY:
            all_col_names.update(["PTS", "REB", "AST", "FGM", "FGA", "FG_PCT",
                                 "FG3M", "FG3A", "FG3_PCT", "FTM", "FTA", "FT_PCT",
                                 "OREB", "DREB", "STL", "BLK", "TOV", "PF", "MIN"])

        # Build column info list
        for col_name in sorted(all_col_names):
            if col_name in COMMON_COLUMNS:
                info.all_columns.append(COMMON_COLUMNS[col_name])

        # Set typical row counts
        info.typical_row_count = self._get_typical_row_count(level)

        # Set merge compatibility
        info.can_merge_with = self._get_merge_compatibility(level)

        # Generate examples
        info.example_usage = self._generate_usage_example(level)
        info.example_merge = self._generate_merge_example(level)

        return info

    def _get_typical_row_count(self, level: GroupingLevel) -> str:
        """Get typical row count for a dataset"""
        counts = {
            GroupingLevel.PLAYER_GAME: "~80-100 rows/player/season (1 per game)",
            GroupingLevel.PLAYER_TEAM_GAME: "~80-100 rows/player/season/team",
            GroupingLevel.PLAYER_SEASON: "1 row/player/season",
            GroupingLevel.PLAYER_TEAM_SEASON: "1-2 rows/player/season (if traded)",
            GroupingLevel.TEAM_GAME: "~82 rows/team/season (1 per game)",
            GroupingLevel.TEAM_SEASON: "1 row/team/season",
            GroupingLevel.PLAY_BY_PLAY_PLAYER: "~300-500 events/game",
            GroupingLevel.PLAY_BY_PLAY_TEAM: "~300-500 events/game",
            GroupingLevel.SHOT_CHART_PLAYER: "~15-25 shots/game/player",
            GroupingLevel.SHOT_CHART_TEAM: "~80-100 shots/game/team",
        }
        return counts.get(level, "Varies")

    def _get_merge_compatibility(self, level: GroupingLevel) -> List[str]:
        """Get list of compatible datasets for merging"""
        # Same granularity can merge
        same_gran = [l.value for l in GroupingLevel
                    if l in MERGE_CONFIG_CATALOG
                    and MERGE_CONFIG_CATALOG[l].granularity == MERGE_CONFIG_CATALOG[level].granularity]

        # Also can merge season data onto game data
        if MERGE_CONFIG_CATALOG[level].granularity == GranularityLevel.DAY:
            season_levels = [l.value for l in GroupingLevel
                           if l in MERGE_CONFIG_CATALOG
                           and MERGE_CONFIG_CATALOG[l].granularity == GranularityLevel.SEASON]
            same_gran.extend(season_levels)

        return same_gran

    def _generate_usage_example(self, level: GroupingLevel) -> str:
        """Generate usage example code"""
        examples = {
            GroupingLevel.PLAYER_GAME: """# Fetch player game logs
game_logs = await fetch_grouping(
    "player/game",
    season="2023-24",
    player_id=2544  # LeBron James
)
print(f"Found {len(game_logs)} games")""",

            GroupingLevel.PLAYER_SEASON: """# Fetch player season stats
season_stats = await fetch_grouping(
    "player/season",
    season="2023-24",
    player_id=2544
)
print(f"Season PTS: {season_stats['PTS'].iloc[0]}")""",

            GroupingLevel.TEAM_GAME: """# Fetch team game logs
team_games = await fetch_grouping(
    "team/game",
    season="2023-24",
    team_id=1610612747  # Lakers
)
print(f"Team record: {team_games['W'].sum()}-{team_games['L'].sum()}")""",

            GroupingLevel.SHOT_CHART_PLAYER: """# Fetch shot chart data
shots = get_shot_chart(
    "LeBron James",
    season="2023-24",
    granularity="raw"
)
print(f"Total shots: {len(shots)}")""",
        }
        return examples.get(level, "# Example not available")

    def _generate_merge_example(self, level: GroupingLevel) -> str:
        """Generate merge example code"""
        examples = {
            GroupingLevel.PLAYER_GAME: """# Merge advanced metrics onto game logs
game_logs = await fetch_grouping("player/game", season="2023-24")
merged, stats = merge_with_advanced_metrics(
    game_logs,
    grouping_level="player/game"
)
print(f"Added metrics with {stats['match_rate_pct']:.1f}% match")""",

            GroupingLevel.TEAM_GAME: """# Merge team advanced stats onto game logs
team_games = await fetch_grouping("team/game", season="2023-24")
team_advanced = get_team_advanced_stats("Lakers", season="2023-24")
merged, stats = merge_datasets_by_grouping(
    team_games,
    team_advanced,
    grouping_level="team/game",
    how="left"
)""",
        }
        return examples.get(level, "# Merge example not available")

    def get_dataset_info(self, grouping_level: str) -> Optional[DatasetInfo]:
        """
        Get comprehensive information about a dataset.

        Args:
            grouping_level: Grouping level (e.g., "player/game")

        Returns:
            DatasetInfo object with all details

        Example:
            inspector = DatasetInspector()
            info = inspector.get_dataset_info("player/game")
            print(info.to_markdown())
        """
        return self.datasets.get(grouping_level)

    def list_all_datasets(self) -> List[str]:
        """List all available dataset grouping levels"""
        return list(self.datasets.keys())

    def get_columns_for_dataset(self, grouping_level: str) -> Dict[str, List[str]]:
        """
        Get categorized columns for a dataset.

        Args:
            grouping_level: Grouping level

        Returns:
            Dictionary with column categories

        Example:
            columns = inspector.get_columns_for_dataset("player/game")
            print(f"Identifiers: {columns['identifiers']}")
        """
        info = self.get_dataset_info(grouping_level)
        if not info:
            return {}

        return {
            "identifiers": info.identifier_columns,
            "optional_identifiers": info.optional_identifier_columns,
            "special": info.special_columns,
            "all": [col.name for col in info.all_columns],
        }

    def get_merge_info(self, grouping_level: str) -> Dict[str, Any]:
        """
        Get merge-specific information for a dataset.

        Args:
            grouping_level: Grouping level

        Returns:
            Dictionary with merge compatibility and identifier info

        Example:
            merge_info = inspector.get_merge_info("player/game")
            print(f"Can merge with: {merge_info['compatible_datasets']}")
        """
        info = self.get_dataset_info(grouping_level)
        if not info:
            return {}

        return {
            "identifier_columns": info.identifier_columns,
            "optional_identifier_columns": info.optional_identifier_columns,
            "compatible_datasets": info.can_merge_with,
            "typical_row_count": info.typical_row_count,
            "example_merge": info.example_merge,
        }

    def search_datasets(self, search_term: str) -> List[str]:
        """
        Search for datasets by keyword.

        Args:
            search_term: Term to search for (in name, description, columns)

        Returns:
            List of matching dataset names

        Example:
            results = inspector.search_datasets("shot")
            # Returns: ["shot_chart/player", "shot_chart/team"]
        """
        results = []
        search_lower = search_term.lower()

        for level_name, info in self.datasets.items():
            # Search in name
            if search_lower in level_name.lower():
                results.append(level_name)
                continue

            # Search in description
            if search_lower in info.description.lower():
                results.append(level_name)
                continue

            # Search in columns
            for col in info.all_columns:
                if search_lower in col.name.lower() or search_lower in col.description.lower():
                    results.append(level_name)
                    break

        return results


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

_inspector_instance: Optional[DatasetInspector] = None


def get_inspector() -> DatasetInspector:
    """Get singleton dataset inspector instance"""
    global _inspector_instance
    if _inspector_instance is None:
        _inspector_instance = DatasetInspector()
    return _inspector_instance


def inspect_dataset(grouping_level: str, format: str = "markdown") -> str:
    """
    Get comprehensive information about a dataset.

    Args:
        grouping_level: Grouping level (e.g., "player/game")
        format: Output format ("markdown" or "dict")

    Returns:
        Formatted dataset information

    Example:
        info = inspect_dataset("player/game")
        print(info)
    """
    inspector = get_inspector()
    info = inspector.get_dataset_info(grouping_level)

    if not info:
        return f"Dataset '{grouping_level}' not found"

    if format == "dict":
        import json
        return json.dumps(info.to_dict(), indent=2)
    else:
        return info.to_markdown()


def list_datasets() -> List[str]:
    """
    List all available dataset grouping levels.

    Returns:
        List of dataset names

    Example:
        datasets = list_datasets()
        print(f"Available datasets: {', '.join(datasets)}")
    """
    inspector = get_inspector()
    return inspector.list_all_datasets()


def get_dataset_columns(grouping_level: str) -> Dict[str, List[str]]:
    """
    Get columns for a dataset, categorized by type.

    Args:
        grouping_level: Grouping level

    Returns:
        Dictionary with column categories

    Example:
        columns = get_dataset_columns("player/game")
        print(f"Merge on: {columns['identifiers']}")
    """
    inspector = get_inspector()
    return inspector.get_columns_for_dataset(grouping_level)


def search_datasets(search_term: str) -> List[str]:
    """
    Search for datasets by keyword.

    Args:
        search_term: Search term

    Returns:
        List of matching dataset names

    Example:
        results = search_datasets("lineup")
        # Returns datasets with lineup-related columns
    """
    inspector = get_inspector()
    return inspector.search_datasets(search_term)
