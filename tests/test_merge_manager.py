"""
Comprehensive Test Suite for Merge Manager

Tests merge operations at all grouping levels with validation.
"""

import pytest
import pandas as pd
import pyarrow as pa
from typing import Dict, Any

from nba_mcp.api.data_groupings import (
    GroupingLevel,
    merge_with_advanced_metrics,
    merge_with_shot_chart_data,
    merge_datasets_by_grouping,
    get_merge_identifier_columns,
    list_all_merge_configs,
)
from nba_mcp.data.merge_manager import (
    MergeManager,
    MergeValidationLevel,
    MergeValidationResult,
    MergeStatistics,
    get_merge_config,
    MERGE_CONFIG_CATALOG,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_player_game_data():
    """Sample player game log data"""
    return pd.DataFrame({
        "PLAYER_ID": [2544, 2544, 2544],
        "PLAYER_NAME": ["LeBron James", "LeBron James", "LeBron James"],
        "GAME_ID": ["0022300001", "0022300002", "0022300003"],
        "GAME_DATE": ["2023-10-24", "2023-10-26", "2023-10-28"],
        "SEASON_YEAR": ["2023-24", "2023-24", "2023-24"],
        "PTS": [25, 30, 22],
        "REB": [8, 10, 7],
        "AST": [6, 8, 5],
        "FGM": [10, 12, 9],
        "FGA": [20, 22, 18],
        "FG3M": [2, 3, 1],
        "FTM": [3, 3, 3],
        "FTA": [4, 4, 4],
        "OREB": [1, 2, 1],
        "DREB": [7, 8, 6],
        "STL": [2, 1, 2],
        "BLK": [1, 1, 0],
        "TOV": [3, 2, 3],
        "PF": [2, 3, 2],
        "MIN": [36, 38, 34],
    })


@pytest.fixture
def sample_advanced_metrics():
    """Sample advanced metrics data"""
    return pd.DataFrame({
        "PLAYER_ID": [2544, 2544, 2544],
        "GAME_ID": ["0022300001", "0022300002", "0022300003"],
        "TRUE_SHOOTING_PCT": [0.580, 0.620, 0.550],
        "EFFECTIVE_FG_PCT": [0.550, 0.590, 0.528],
        "GAME_SCORE": [18.5, 22.3, 15.8],
    })


@pytest.fixture
def sample_shot_chart_data():
    """Sample shot chart data"""
    return pd.DataFrame({
        "PLAYER_ID": [2544, 2544, 2544, 2544, 2544, 2544],
        "GAME_ID": ["0022300001", "0022300001", "0022300001",
                    "0022300002", "0022300002", "0022300002"],
        "GAME_EVENT_ID": [1, 2, 3, 4, 5, 6],
        "LOC_X": [10, 20, 150, 15, 25, 180],
        "LOC_Y": [50, 100, 200, 60, 110, 220],
        "SHOT_MADE_FLAG": [1, 0, 1, 1, 1, 0],
        "SHOT_ZONE_BASIC": ["Paint", "Mid-Range", "Three Point",
                           "Paint", "Mid-Range", "Three Point"],
        "SHOT_DISTANCE": [5, 12, 24, 6, 13, 25],
    })


@pytest.fixture
def sample_team_game_data():
    """Sample team game log data"""
    return pd.DataFrame({
        "TEAM_ID": [1610612747, 1610612747, 1610612747],
        "TEAM_ABBREVIATION": ["LAL", "LAL", "LAL"],
        "GAME_ID": ["0022300001", "0022300002", "0022300003"],
        "GAME_DATE": ["2023-10-24", "2023-10-26", "2023-10-28"],
        "SEASON_YEAR": ["2023-24", "2023-24", "2023-24"],
        "PTS": [110, 115, 108],
        "REB": [45, 48, 42],
        "AST": [25, 28, 24],
        "W": [1, 1, 0],
        "L": [0, 0, 1],
    })


@pytest.fixture
def sample_player_season_data():
    """Sample player season aggregated data"""
    return pd.DataFrame({
        "PLAYER_ID": [2544, 203999],
        "PLAYER_NAME": ["LeBron James", "Nikola Jokic"],
        "SEASON_YEAR": ["2023-24", "2023-24"],
        "GP": [70, 79],
        "PTS": [1750, 1896],
        "REB": [560, 790],
        "AST": [525, 711],
    })


# ============================================================================
# TEST MERGE CONFIGURATION
# ============================================================================

def test_merge_config_catalog_completeness():
    """Test that all grouping levels have merge configs"""
    # Check that all defined grouping levels have configs
    for grouping_level in GroupingLevel:
        assert grouping_level in MERGE_CONFIG_CATALOG, \
            f"Missing merge config for {grouping_level.value}"


def test_get_merge_config():
    """Test retrieving merge config for a grouping level"""
    config = get_merge_config(GroupingLevel.PLAYER_GAME)

    assert config.grouping_level == GroupingLevel.PLAYER_GAME
    assert "PLAYER_ID" in config.identifier_columns
    assert "GAME_ID" in config.identifier_columns


def test_get_merge_identifier_columns():
    """Test getting identifier columns for merging"""
    identifiers = get_merge_identifier_columns("player/game")

    assert "required" in identifiers
    assert "optional" in identifiers
    assert "PLAYER_ID" in identifiers["required"]
    assert "GAME_ID" in identifiers["required"]


def test_list_all_merge_configs():
    """Test listing all merge configurations"""
    configs = list_all_merge_configs()

    assert len(configs) > 0
    assert "player/game" in configs
    assert "team/season" in configs

    # Check structure
    player_game_config = configs["player/game"]
    assert "identifier_columns" in player_game_config
    assert "granularity" in player_game_config


# ============================================================================
# TEST BASIC MERGE OPERATIONS
# ============================================================================

def test_merge_player_game_with_advanced_metrics(sample_player_game_data, sample_advanced_metrics):
    """Test merging advanced metrics onto player game data"""
    manager = MergeManager(validation_level=MergeValidationLevel.WARN)

    result, stats = manager.merge(
        base_data=sample_player_game_data,
        merge_data=sample_advanced_metrics,
        grouping_level=GroupingLevel.PLAYER_GAME,
        how="left",
    )

    # Check that merge completed successfully
    assert isinstance(result, pd.DataFrame)
    assert len(result) == len(sample_player_game_data)

    # Check that advanced metrics columns were added
    assert "TRUE_SHOOTING_PCT" in result.columns
    assert "EFFECTIVE_FG_PCT" in result.columns
    assert "GAME_SCORE" in result.columns

    # Check statistics
    assert stats.left_rows == 3
    assert stats.right_rows == 3
    assert stats.result_rows == 3
    assert stats.match_rate == 100.0


def test_merge_with_missing_identifier():
    """Test that merge fails gracefully when identifier columns are missing"""
    base_data = pd.DataFrame({
        "PLAYER_ID": [2544],
        "PTS": [25],
    })

    merge_data = pd.DataFrame({
        "DIFFERENT_ID": [2544],
        "TS_PCT": [0.580],
    })

    manager = MergeManager(validation_level=MergeValidationLevel.STRICT)

    with pytest.raises(ValueError):
        manager.merge(
            base_data=base_data,
            merge_data=merge_data,
            grouping_level=GroupingLevel.PLAYER_GAME,
            how="left",
        )


def test_merge_different_join_types(sample_player_game_data, sample_advanced_metrics):
    """Test different join types (inner, left, right, outer)"""
    manager = MergeManager(validation_level=MergeValidationLevel.WARN)

    # Test inner join
    result_inner, stats_inner = manager.merge(
        base_data=sample_player_game_data,
        merge_data=sample_advanced_metrics,
        grouping_level=GroupingLevel.PLAYER_GAME,
        how="inner",
    )
    assert stats_inner.join_type == "inner"
    assert len(result_inner) == 3

    # Test left join
    result_left, stats_left = manager.merge(
        base_data=sample_player_game_data,
        merge_data=sample_advanced_metrics,
        grouping_level=GroupingLevel.PLAYER_GAME,
        how="left",
    )
    assert stats_left.join_type == "left"
    assert len(result_left) == 3


# ============================================================================
# TEST VALIDATION
# ============================================================================

def test_validation_null_identifiers():
    """Test validation warns about null identifier values"""
    base_data = pd.DataFrame({
        "PLAYER_ID": [2544, None, 2544],
        "GAME_ID": ["0022300001", "0022300002", "0022300003"],
        "PTS": [25, 30, 22],
    })

    merge_data = pd.DataFrame({
        "PLAYER_ID": [2544, 2544, 2544],
        "GAME_ID": ["0022300001", "0022300002", "0022300003"],
        "TS_PCT": [0.580, 0.620, 0.550],
    })

    manager = MergeManager(validation_level=MergeValidationLevel.WARN)

    # Should warn but not fail
    result, stats = manager.merge(
        base_data=base_data,
        merge_data=merge_data,
        grouping_level=GroupingLevel.PLAYER_GAME,
        how="left",
    )

    assert isinstance(result, pd.DataFrame)


def test_validation_duplicate_identifiers():
    """Test validation warns about duplicate identifier rows"""
    base_data = pd.DataFrame({
        "PLAYER_ID": [2544, 2544, 2544],
        "GAME_ID": ["0022300001", "0022300001", "0022300002"],  # Duplicate
        "PTS": [25, 25, 30],
    })

    merge_data = pd.DataFrame({
        "PLAYER_ID": [2544, 2544],
        "GAME_ID": ["0022300001", "0022300002"],
        "TS_PCT": [0.580, 0.620],
    })

    manager = MergeManager(validation_level=MergeValidationLevel.WARN)

    # Should warn about duplicates
    result, stats = manager.merge(
        base_data=base_data,
        merge_data=merge_data,
        grouping_level=GroupingLevel.PLAYER_GAME,
        how="left",
    )

    assert isinstance(result, pd.DataFrame)


def test_validation_data_loss_detection():
    """Test validation detects unexpected data loss"""
    base_data = pd.DataFrame({
        "PLAYER_ID": [2544, 2544, 2544],
        "GAME_ID": ["0022300001", "0022300002", "0022300003"],
        "PTS": [25, 30, 22],
    })

    # Only 2 games in merge data
    merge_data = pd.DataFrame({
        "PLAYER_ID": [2544, 2544],
        "GAME_ID": ["0022300001", "0022300002"],
        "TS_PCT": [0.580, 0.620],
    })

    manager = MergeManager(validation_level=MergeValidationLevel.WARN)

    # Inner join should lose one row
    result, stats = manager.merge(
        base_data=base_data,
        merge_data=merge_data,
        grouping_level=GroupingLevel.PLAYER_GAME,
        how="inner",
    )

    assert stats.data_loss == 1
    assert len(result) == 2


# ============================================================================
# TEST TEAM-LEVEL MERGES
# ============================================================================

def test_merge_team_game_data(sample_team_game_data):
    """Test merging team-level data"""
    # Create some team advanced stats
    team_advanced = pd.DataFrame({
        "TEAM_ID": [1610612747, 1610612747, 1610612747],
        "GAME_ID": ["0022300001", "0022300002", "0022300003"],
        "OFF_RTG": [115.2, 118.5, 112.3],
        "DEF_RTG": [108.5, 110.2, 109.8],
        "PACE": [99.5, 100.2, 98.8],
    })

    manager = MergeManager(validation_level=MergeValidationLevel.WARN)

    result, stats = manager.merge(
        base_data=sample_team_game_data,
        merge_data=team_advanced,
        grouping_level=GroupingLevel.TEAM_GAME,
        how="left",
    )

    assert len(result) == 3
    assert "OFF_RTG" in result.columns
    assert "DEF_RTG" in result.columns
    assert stats.match_rate == 100.0


def test_merge_team_season_data(sample_player_season_data):
    """Test merging team season-level data"""
    # Create team season data (should have one row per team-season combination)
    team_season = pd.DataFrame({
        "TEAM_ID": [1610612747],
        "SEASON_YEAR": ["2023-24"],
        "W": [47],
        "L": [35],
        "WIN_PCT": [0.573],
    })

    # Create player team season data with matching team
    player_team_season = pd.DataFrame({
        "PLAYER_ID": [2544, 203999],
        "TEAM_ID": [1610612747, 1610612747],
        "SEASON_YEAR": ["2023-24", "2023-24"],
        "GP": [70, 79],
        "PTS": [1750, 1896],
    })

    manager = MergeManager(validation_level=MergeValidationLevel.WARN)

    # When merging team-level data onto player-team-level data,
    # explicitly specify identifier columns (TEAM_ID, SEASON_YEAR only)
    result, stats = manager.merge(
        base_data=player_team_season,
        merge_data=team_season,
        grouping_level=GroupingLevel.PLAYER_TEAM_SEASON,
        identifier_columns=["TEAM_ID", "SEASON_YEAR"],
        how="left",
    )

    assert len(result) == 2
    assert "WIN_PCT" in result.columns


# ============================================================================
# TEST CONVENIENCE FUNCTIONS
# ============================================================================

def test_merge_datasets_by_grouping(sample_player_game_data, sample_advanced_metrics):
    """Test convenience function for generic merge"""
    result, stats_dict = merge_datasets_by_grouping(
        base_data=sample_player_game_data,
        merge_data=sample_advanced_metrics,
        grouping_level="player/game",
        how="left",
    )

    assert isinstance(result, pd.DataFrame)
    assert isinstance(stats_dict, dict)
    assert "match_rate_pct" in stats_dict
    assert stats_dict["match_rate_pct"] == 100.0


def test_merge_with_advanced_metrics_convenience(sample_player_game_data):
    """Test convenience function for merging advanced metrics"""
    result, stats_dict = merge_with_advanced_metrics(
        game_data=sample_player_game_data,
        grouping_level="player/game",
        how="left",
    )

    assert isinstance(result, pd.DataFrame)
    assert "TRUE_SHOOTING_PCT" in result.columns or "EFFECTIVE_FG_PCT" in result.columns


def test_merge_with_shot_chart_convenience(sample_player_game_data, sample_shot_chart_data):
    """Test convenience function for merging shot chart data"""
    result, stats_dict = merge_with_shot_chart_data(
        game_data=sample_player_game_data,
        shot_chart_data=sample_shot_chart_data,
        grouping_level="player/game",
        aggregation="count",
        how="left",
    )

    assert isinstance(result, pd.DataFrame)
    assert "SHOT_COUNT" in result.columns


# ============================================================================
# TEST PYARROW TABLE SUPPORT
# ============================================================================

def test_merge_with_pyarrow_tables(sample_player_game_data, sample_advanced_metrics):
    """Test that merge works with PyArrow tables"""
    # Convert to PyArrow tables
    base_table = pa.Table.from_pandas(sample_player_game_data)
    merge_table = pa.Table.from_pandas(sample_advanced_metrics)

    manager = MergeManager(validation_level=MergeValidationLevel.WARN)

    result, stats = manager.merge(
        base_data=base_table,
        merge_data=merge_table,
        grouping_level=GroupingLevel.PLAYER_GAME,
        how="left",
    )

    # Result should be PyArrow table since input was
    assert isinstance(result, pa.Table)
    assert result.num_rows == 3


def test_merge_mixed_formats(sample_player_game_data, sample_advanced_metrics):
    """Test merge with mixed DataFrame and PyArrow formats"""
    # Base as DataFrame, merge as PyArrow
    merge_table = pa.Table.from_pandas(sample_advanced_metrics)

    manager = MergeManager(validation_level=MergeValidationLevel.WARN)

    result, stats = manager.merge(
        base_data=sample_player_game_data,  # DataFrame
        merge_data=merge_table,              # PyArrow
        grouping_level=GroupingLevel.PLAYER_GAME,
        how="left",
    )

    # Result should match base format (DataFrame)
    assert isinstance(result, pd.DataFrame)


# ============================================================================
# TEST SPECIAL GROUPING LEVELS
# ============================================================================

def test_merge_config_for_play_by_play():
    """Test merge config includes special columns for play-by-play"""
    config = get_merge_config(GroupingLevel.PLAY_BY_PLAY_PLAYER)

    assert "CURRENT_LINEUP_HOME" in config.special_columns
    assert "CURRENT_LINEUP_AWAY" in config.special_columns
    assert "LINEUP_ID_HOME" in config.special_columns
    assert "LINEUP_ID_AWAY" in config.special_columns


def test_merge_config_for_shot_chart():
    """Test merge config includes spatial columns for shot charts"""
    config = get_merge_config(GroupingLevel.SHOT_CHART_PLAYER)

    assert "LOC_X" in config.special_columns
    assert "LOC_Y" in config.special_columns
    assert "SHOT_ZONE_BASIC" in config.special_columns


# ============================================================================
# TEST ERROR HANDLING
# ============================================================================

def test_merge_with_invalid_grouping_level():
    """Test that invalid grouping level raises error"""
    with pytest.raises(ValueError):
        merge_datasets_by_grouping(
            base_data=pd.DataFrame(),
            merge_data=pd.DataFrame(),
            grouping_level="invalid/level",
            how="left",
        )


def test_merge_with_strict_validation_failure():
    """Test that strict validation fails on errors"""
    base_data = pd.DataFrame({
        "PLAYER_ID": [2544],
        "PTS": [25],
    })

    merge_data = pd.DataFrame({
        "WRONG_COLUMN": [2544],
        "TS_PCT": [0.580],
    })

    # Strict mode should raise error
    with pytest.raises(ValueError):
        merge_datasets_by_grouping(
            base_data=base_data,
            merge_data=merge_data,
            grouping_level="player/game",
            how="left",
            validation_level="strict",
        )


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
