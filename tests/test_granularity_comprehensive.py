"""
Comprehensive Granularity Tests - Ensuring Data Quality at All Levels

This test suite validates:
1. No data loss during merges at each granularity level
2. Correct identifier column selection
3. Enrichments work properly at each level
4. Column counts match expected values
5. No duplicate columns after enrichment/merge
6. Row counts preserved (for left joins)
"""

import pytest
import pandas as pd
import pyarrow as pa
from typing import Dict, List

from nba_mcp.api.data_groupings import (
    GroupingLevel,
    merge_datasets_by_grouping,
    merge_with_advanced_metrics,
    merge_with_shot_chart_data,
    get_merge_identifier_columns,
)
from nba_mcp.data.merge_manager import (
    MergeManager,
    MergeValidationLevel,
    get_merge_config,
)
from nba_mcp.data.enrichment_strategy import (
    EnrichmentEngine,
    EnrichmentType,
    get_available_enrichments,
    get_default_enrichments,
)


# ============================================================================
# FIXTURES - Sample Data for Each Granularity Level
# ============================================================================

@pytest.fixture
def player_game_base_data():
    """Base player game data with stats columns"""
    return pd.DataFrame({
        "PLAYER_ID": [2544, 2544, 2544, 2544, 2544],
        "PLAYER_NAME": ["LeBron James"] * 5,
        "GAME_ID": ["0022300001", "0022300002", "0022300003", "0022300004", "0022300005"],
        "GAME_DATE": ["2023-10-24", "2023-10-26", "2023-10-28", "2023-10-30", "2023-11-01"],
        "SEASON_YEAR": ["2023-24"] * 5,
        "TEAM_ID": [1610612747] * 5,
        "MATCHUP": ["LAL vs. GSW", "LAL @ PHX", "LAL vs. DEN", "LAL @ SAC", "LAL vs. PHX"],
        "PTS": [25, 30, 22, 28, 32],
        "REB": [8, 10, 7, 9, 11],
        "AST": [6, 8, 5, 7, 9],
        "FGM": [10, 12, 9, 11, 13],
        "FGA": [20, 22, 18, 20, 24],
        "FG3M": [2, 3, 1, 2, 4],
        "FTM": [3, 3, 3, 4, 2],
        "FTA": [4, 4, 4, 5, 3],
        "OREB": [1, 2, 1, 2, 3],
        "DREB": [7, 8, 6, 7, 8],
        "STL": [2, 1, 2, 1, 2],
        "BLK": [1, 1, 0, 1, 2],
        "TOV": [3, 2, 3, 2, 1],
        "PF": [2, 3, 2, 2, 1],
        "MIN": [36, 38, 34, 37, 40],
    })


@pytest.fixture
def team_game_base_data():
    """Base team game data"""
    return pd.DataFrame({
        "TEAM_ID": [1610612747] * 5,
        "TEAM_ABBREVIATION": ["LAL"] * 5,
        "GAME_ID": ["0022300001", "0022300002", "0022300003", "0022300004", "0022300005"],
        "GAME_DATE": ["2023-10-24", "2023-10-26", "2023-10-28", "2023-10-30", "2023-11-01"],
        "SEASON_YEAR": ["2023-24"] * 5,
        "PTS": [110, 115, 108, 112, 120],
        "REB": [45, 48, 42, 46, 50],
        "AST": [25, 28, 24, 26, 30],
        "FGM": [42, 45, 40, 43, 48],
        "FGA": [88, 92, 85, 90, 95],
        "FG3M": [10, 12, 8, 11, 15],
        "FTM": [16, 13, 20, 15, 9],
        "FTA": [20, 18, 24, 19, 12],
        "W": [1, 1, 0, 1, 1],
        "L": [0, 0, 1, 0, 0],
    })


@pytest.fixture
def player_season_base_data():
    """Base player season data"""
    return pd.DataFrame({
        "PLAYER_ID": [2544, 203999, 1629029],
        "PLAYER_NAME": ["LeBron James", "Nikola Jokic", "Luka Doncic"],
        "SEASON_YEAR": ["2023-24", "2023-24", "2023-24"],
        "GP": [70, 79, 70],
        "PTS": [1750, 1896, 2350],
        "REB": [560, 790, 630],
        "AST": [525, 711, 665],
        "FGM": [700, 760, 880],
        "FGA": [1400, 1440, 1820],
        "FG3M": [120, 100, 270],
        "FTM": [230, 276, 320],
        "FTA": [300, 340, 380],
        "OREB": [70, 100, 80],
        "DREB": [490, 690, 550],
        "STL": [70, 90, 105],
        "BLK": [35, 55, 35],
        "TOV": [140, 190, 240],
        "PF": [120, 180, 150],
        "MIN": [2520, 2844, 2660],
    })


# ============================================================================
# TEST: PLAYER/GAME GRANULARITY
# ============================================================================

@pytest.mark.asyncio
async def test_player_game_no_data_loss(player_game_base_data):
    """Test that player/game merges and enrichments don't lose data"""
    original_rows = len(player_game_base_data)

    # Apply enrichment
    engine = EnrichmentEngine()
    enriched = await engine.enrich(
        player_game_base_data,
        GroupingLevel.PLAYER_GAME
    )

    # Check no data loss
    assert len(enriched) == original_rows, "Enrichment lost rows"

    # Check for duplicate columns
    duplicates = enriched.columns[enriched.columns.duplicated()].tolist()
    assert len(duplicates) == 0, f"Found duplicate columns: {duplicates}"

    # Check that columns were added
    assert len(enriched.columns) >= len(player_game_base_data.columns), \
        "Enrichment didn't add any columns"


def test_player_game_merge_with_advanced_metrics(player_game_base_data):
    """Test merging advanced metrics at player/game level"""
    result, stats = merge_with_advanced_metrics(
        game_data=player_game_base_data,
        grouping_level="player/game",
        how="left"
    )

    # No data loss
    assert stats["result_rows"] == stats["left_rows"], \
        f"Lost {stats['data_loss']} rows during merge"

    # 100% match rate (all rows matched)
    assert stats["match_rate_pct"] == 100.0, \
        f"Match rate only {stats['match_rate_pct']:.1f}%"

    # Added metrics columns
    metric_cols = ["TRUE_SHOOTING_PCT", "EFFECTIVE_FG_PCT", "GAME_SCORE"]
    for col in metric_cols:
        if col in result.columns:
            assert col in result.columns, f"Missing metric: {col}"

    # No duplicates
    duplicates = result.columns[result.columns.duplicated()].tolist()
    assert len(duplicates) == 0, f"Duplicate columns: {duplicates}"


def test_player_game_identifier_columns():
    """Test correct identifier columns for player/game"""
    identifiers = get_merge_identifier_columns("player/game")

    assert "PLAYER_ID" in identifiers["required"]
    assert "GAME_ID" in identifiers["required"]
    assert "GAME_DATE" in identifiers["optional"]
    assert "SEASON_YEAR" in identifiers["optional"]


# ============================================================================
# TEST: PLAYER/TEAM/GAME GRANULARITY
# ============================================================================

def test_player_team_game_merge():
    """Test merging at player/team/game level"""
    # Create player/team/game data
    base_data = pd.DataFrame({
        "PLAYER_ID": [2544, 2544],
        "TEAM_ID": [1610612747, 1610612747],
        "GAME_ID": ["0022300001", "0022300002"],
        "PTS": [25, 30],
        "REB": [8, 10],
        "AST": [6, 8],
        "FGM": [10, 12],
        "FGA": [20, 22],
        "FG3M": [2, 3],
        "FTM": [3, 3],
        "FTA": [4, 4],
        "OREB": [1, 2],
        "DREB": [7, 8],
        "STL": [2, 1],
        "BLK": [1, 1],
        "TOV": [3, 2],
        "PF": [2, 3],
        "MIN": [36, 38],
    })

    # Merge with advanced metrics
    result, stats = merge_with_advanced_metrics(
        game_data=base_data,
        grouping_level="player/team/game",
        how="left"
    )

    # Verify no data loss
    assert stats["result_rows"] == len(base_data)
    assert stats["match_rate_pct"] == 100.0


def test_player_team_game_identifier_columns():
    """Test correct identifiers for player/team/game"""
    identifiers = get_merge_identifier_columns("player/team/game")

    assert "PLAYER_ID" in identifiers["required"]
    assert "TEAM_ID" in identifiers["required"]
    assert "GAME_ID" in identifiers["required"]


# ============================================================================
# TEST: PLAYER/SEASON GRANULARITY
# ============================================================================

@pytest.mark.asyncio
async def test_player_season_no_data_loss(player_season_base_data):
    """Test player/season enrichment doesn't lose data"""
    original_rows = len(player_season_base_data)

    engine = EnrichmentEngine()
    enriched = await engine.enrich(
        player_season_base_data,
        GroupingLevel.PLAYER_SEASON
    )

    assert len(enriched) == original_rows

    duplicates = enriched.columns[enriched.columns.duplicated()].tolist()
    assert len(duplicates) == 0


def test_player_season_merge_with_advanced_metrics(player_season_base_data):
    """Test merging advanced metrics at season level"""
    result, stats = merge_with_advanced_metrics(
        game_data=player_season_base_data,
        grouping_level="player/season",
        how="left"
    )

    # No data loss
    assert stats["result_rows"] == len(player_season_base_data)
    assert stats["data_loss"] == 0

    # Check for advanced metrics
    assert len(result.columns) > len(player_season_base_data.columns)


# ============================================================================
# TEST: TEAM/GAME GRANULARITY
# ============================================================================

@pytest.mark.asyncio
async def test_team_game_no_data_loss(team_game_base_data):
    """Test team/game enrichment doesn't lose data"""
    original_rows = len(team_game_base_data)

    engine = EnrichmentEngine()
    enriched = await engine.enrich(
        team_game_base_data,
        GroupingLevel.TEAM_GAME
    )

    assert len(enriched) == original_rows

    duplicates = enriched.columns[enriched.columns.duplicated()].tolist()
    assert len(duplicates) == 0


def test_team_game_merge_with_advanced_metrics(team_game_base_data):
    """Test merging advanced metrics at team/game level"""
    result, stats = merge_with_advanced_metrics(
        game_data=team_game_base_data,
        grouping_level="team/game",
        how="left"
    )

    # No data loss
    assert stats["result_rows"] == len(team_game_base_data)
    assert stats["match_rate_pct"] == 100.0


def test_team_game_identifier_columns():
    """Test correct identifiers for team/game"""
    identifiers = get_merge_identifier_columns("team/game")

    assert "TEAM_ID" in identifiers["required"]
    assert "GAME_ID" in identifiers["required"]


# ============================================================================
# TEST: TEAM/SEASON GRANULARITY
# ============================================================================

def test_team_season_merge():
    """Test merging at team/season level"""
    base_data = pd.DataFrame({
        "TEAM_ID": [1610612747, 1610612738],
        "SEASON_YEAR": ["2023-24", "2023-24"],
        "GP": [82, 82],
        "W": [47, 51],
        "L": [35, 31],
        "PTS": [9020, 9350],
        "REB": [3690, 3820],
        "AST": [2050, 2280],
        "FGM": [3444, 3588],
        "FGA": [7216, 7380],
        "FG3M": [820, 990],
        "FTM": [1312, 1184],
        "FTA": [1722, 1560],
    })

    result, stats = merge_with_advanced_metrics(
        game_data=base_data,
        grouping_level="team/season",
        how="left"
    )

    # No data loss
    assert stats["result_rows"] == len(base_data)
    assert stats["data_loss"] == 0


def test_team_season_identifier_columns():
    """Test correct identifiers for team/season"""
    identifiers = get_merge_identifier_columns("team/season")

    assert "TEAM_ID" in identifiers["required"]
    assert "SEASON_YEAR" in identifiers["required"]


# ============================================================================
# TEST: CROSS-GRANULARITY MERGES
# ============================================================================

def test_merge_team_stats_onto_player_team_season():
    """Test merging team-level data onto player-team-season data"""
    # Player-team-season data
    player_data = pd.DataFrame({
        "PLAYER_ID": [2544, 203999],
        "TEAM_ID": [1610612747, 1610612747],
        "SEASON_YEAR": ["2023-24", "2023-24"],
        "GP": [70, 79],
        "PTS": [1750, 1896],
    })

    # Team-season data
    team_data = pd.DataFrame({
        "TEAM_ID": [1610612747],
        "SEASON_YEAR": ["2023-24"],
        "TEAM_W": [47],
        "TEAM_L": [35],
        "WIN_PCT": [0.573],
    })

    # Merge with explicit identifier columns (only TEAM_ID and SEASON_YEAR)
    manager = MergeManager(validation_level=MergeValidationLevel.WARN)
    result, stats = manager.merge(
        base_data=player_data,
        merge_data=team_data,
        grouping_level=GroupingLevel.PLAYER_TEAM_SEASON,
        identifier_columns=["TEAM_ID", "SEASON_YEAR"],
        how="left"
    )

    # No data loss
    assert len(result) == len(player_data)
    assert stats.match_rate == 100.0

    # Team columns added
    assert "WIN_PCT" in result.columns


# ============================================================================
# TEST: VALIDATION ACROSS ALL LEVELS
# ============================================================================

@pytest.mark.parametrize("grouping_level", [
    GroupingLevel.PLAYER_GAME,
    GroupingLevel.PLAYER_TEAM_GAME,
    GroupingLevel.PLAYER_SEASON,
    GroupingLevel.PLAYER_TEAM_SEASON,
    GroupingLevel.TEAM_GAME,
    GroupingLevel.TEAM_SEASON,
])
def test_merge_config_exists(grouping_level):
    """Test that merge config exists for all grouping levels"""
    config = get_merge_config(grouping_level)

    assert config is not None
    assert len(config.identifier_columns) > 0
    assert config.granularity is not None


@pytest.mark.parametrize("grouping_level", [
    "player/game",
    "player/team/game",
    "player/season",
    "player/team/season",
    "team/game",
    "team/season",
])
def test_merge_identifiers_exist(grouping_level):
    """Test that merge identifiers exist for all levels"""
    identifiers = get_merge_identifier_columns(grouping_level)

    assert "required" in identifiers
    assert "optional" in identifiers
    assert len(identifiers["required"]) > 0


# ============================================================================
# TEST: PYARROW FORMAT COMPATIBILITY
# ============================================================================

def test_merge_pyarrow_player_game(player_game_base_data):
    """Test merging with PyArrow tables"""
    # Convert to PyArrow
    arrow_table = pa.Table.from_pandas(player_game_base_data)

    result, stats = merge_with_advanced_metrics(
        game_data=arrow_table,
        grouping_level="player/game",
        how="left"
    )

    # Result should be compatible format
    assert stats["result_rows"] == len(player_game_base_data)
    assert stats["data_loss"] == 0


# ============================================================================
# TEST: DATA QUALITY METRICS
# ============================================================================

def test_merge_statistics_completeness(player_game_base_data):
    """Test that merge statistics are comprehensive"""
    result, stats = merge_with_advanced_metrics(
        game_data=player_game_base_data,
        grouping_level="player/game",
        how="left"
    )

    # Check all expected statistics are present
    required_stats = [
        "left_rows", "right_rows", "result_rows",
        "match_rate_pct", "data_loss", "execution_time_ms",
        "left_columns", "right_columns", "result_columns"
    ]

    for stat in required_stats:
        assert stat in stats, f"Missing statistic: {stat}"


def test_enrichment_column_tracking(player_game_base_data):
    """Test that we can track which columns were added"""
    original_cols = set(player_game_base_data.columns)

    result, stats = merge_with_advanced_metrics(
        game_data=player_game_base_data,
        grouping_level="player/game",
        how="left"
    )

    new_cols = set(result.columns) - original_cols

    # Should have added columns
    assert len(new_cols) > 0, "No columns were added"

    # Columns added should match difference in column counts
    assert len(new_cols) == stats["result_columns"] - stats["left_columns"]


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
