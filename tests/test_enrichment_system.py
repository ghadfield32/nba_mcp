"""
Comprehensive Test Suite for Data Enrichment System

Tests enrichment at all grouping levels and validates:
- No duplicate columns
- Proper enrichment application
- Default vs custom enrichments
- Data quality after enrichment
"""

import pytest
import pandas as pd
import asyncio
from typing import Dict, List, Set

from nba_mcp.api.data_groupings import (
    GroupingLevel,
    fetch_grouping,
    fetch_grouping_multi_season,
)
from nba_mcp.data.enrichment_strategy import (
    EnrichmentEngine,
    EnrichmentType,
    get_available_enrichments,
    get_default_enrichments,
    get_enrichment_info,
    ENRICHMENT_CATALOG,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_player_game_data():
    """Sample player game log data for testing"""
    return pd.DataFrame({
        "PLAYER_ID": [2544, 2544, 2544],
        "PLAYER_NAME": ["LeBron James", "LeBron James", "LeBron James"],
        "GAME_ID": ["0022300001", "0022300002", "0022300003"],
        "GAME_DATE": ["2023-10-24", "2023-10-26", "2023-10-28"],
        "SEASON_YEAR": ["2023-24", "2023-24", "2023-24"],
        "MATCHUP": ["LAL vs. GSW", "LAL @ PHX", "LAL vs. DEN"],
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


# ============================================================================
# TEST ENRICHMENT CATALOG
# ============================================================================

def test_enrichment_catalog_completeness():
    """Test that all grouping levels have enrichment configs"""
    for grouping_level in GroupingLevel:
        assert grouping_level in ENRICHMENT_CATALOG, \
            f"Missing enrichment config for {grouping_level.value}"


def test_get_available_enrichments():
    """Test getting available enrichments for a grouping level"""
    enrichments = get_available_enrichments(GroupingLevel.PLAYER_GAME)

    assert isinstance(enrichments, list)
    assert len(enrichments) > 0
    assert "advanced_metrics" in enrichments


def test_get_default_enrichments():
    """Test getting default enrichments"""
    defaults = get_default_enrichments(GroupingLevel.PLAYER_GAME)

    assert isinstance(defaults, list)
    # player/game should have advanced_metrics and game_context as defaults
    assert "advanced_metrics" in defaults
    assert "game_context" in defaults


def test_get_enrichment_info():
    """Test getting comprehensive enrichment info"""
    info = get_enrichment_info(GroupingLevel.PLAYER_GAME)

    assert "available_enrichments" in info
    assert "default_enrichments" in info
    assert "typical_columns_added" in info
    assert "estimated_fetch_time_ms" in info


# ============================================================================
# TEST ENRICHMENT ENGINE
# ============================================================================

@pytest.mark.asyncio
async def test_enrichment_engine_basic(sample_player_game_data):
    """Test basic enrichment with default settings"""
    engine = EnrichmentEngine()

    enriched = await engine.enrich(
        sample_player_game_data,
        GroupingLevel.PLAYER_GAME
    )

    # Should have more columns than original
    assert len(enriched.columns) >= len(sample_player_game_data.columns)

    # Should have same number of rows
    assert len(enriched) == len(sample_player_game_data)


@pytest.mark.asyncio
async def test_enrichment_with_advanced_metrics(sample_player_game_data):
    """Test enrichment with advanced metrics"""
    engine = EnrichmentEngine()

    enriched = await engine.enrich(
        sample_player_game_data,
        GroupingLevel.PLAYER_GAME,
        enrichments=[EnrichmentType.ADVANCED_METRICS]
    )

    # Check that advanced metrics columns were added
    expected_columns = ["TRUE_SHOOTING_PCT", "EFFECTIVE_FG_PCT", "GAME_SCORE"]
    for col in expected_columns:
        assert col in enriched.columns, f"Missing column: {col}"


@pytest.mark.asyncio
async def test_enrichment_with_game_context(sample_player_game_data):
    """Test enrichment with game context"""
    engine = EnrichmentEngine()

    enriched = await engine.enrich(
        sample_player_game_data,
        GroupingLevel.PLAYER_GAME,
        enrichments=[EnrichmentType.GAME_CONTEXT]
    )

    # Check that game context columns were added
    assert "IS_HOME" in enriched.columns
    assert "OPPONENT_ABBR" in enriched.columns or "MATCHUP" in enriched.columns


@pytest.mark.asyncio
async def test_enrichment_with_exclusions(sample_player_game_data):
    """Test enrichment with exclusions"""
    engine = EnrichmentEngine()

    # Get default enrichments
    defaults = get_default_enrichments(GroupingLevel.PLAYER_GAME)

    # Enrich with exclusion
    enriched = await engine.enrich(
        sample_player_game_data,
        GroupingLevel.PLAYER_GAME,
        exclude=[EnrichmentType.GAME_CONTEXT]
    )

    # Should still have advanced metrics but not game context
    assert "TRUE_SHOOTING_PCT" in enriched.columns or "EFFECTIVE_FG_PCT" in enriched.columns


# ============================================================================
# TEST NO DUPLICATE COLUMNS
# ============================================================================

@pytest.mark.asyncio
async def test_no_duplicate_columns_player_game(sample_player_game_data):
    """Test that enrichment doesn't create duplicate columns"""
    engine = EnrichmentEngine()

    enriched = await engine.enrich(
        sample_player_game_data,
        GroupingLevel.PLAYER_GAME
    )

    # Check for duplicates
    duplicates = enriched.columns[enriched.columns.duplicated()].tolist()
    assert len(duplicates) == 0, f"Found duplicate columns: {duplicates}"


@pytest.mark.asyncio
async def test_column_uniqueness_after_multiple_enrichments(sample_player_game_data):
    """Test column uniqueness after multiple enrichment passes"""
    engine = EnrichmentEngine()

    # Apply enrichments one by one
    enriched = sample_player_game_data.copy()

    for enrichment_type in [EnrichmentType.ADVANCED_METRICS, EnrichmentType.GAME_CONTEXT]:
        enriched = await engine.enrich(
            enriched,
            GroupingLevel.PLAYER_GAME,
            enrichments=[enrichment_type],
            use_defaults=False
        )

    # Check for duplicates
    duplicates = enriched.columns[enriched.columns.duplicated()].tolist()
    assert len(duplicates) == 0, f"Found duplicate columns after multiple enrichments: {duplicates}"


# ============================================================================
# TEST DATA QUALITY
# ============================================================================

@pytest.mark.asyncio
async def test_enrichment_preserves_data(sample_player_game_data):
    """Test that enrichment preserves original data"""
    engine = EnrichmentEngine()

    enriched = await engine.enrich(
        sample_player_game_data,
        GroupingLevel.PLAYER_GAME
    )

    # Check that original columns are preserved
    for col in sample_player_game_data.columns:
        assert col in enriched.columns, f"Lost column during enrichment: {col}"

    # Check that original values are preserved
    for col in sample_player_game_data.columns:
        if col in enriched.columns:
            # Compare non-null values
            original_values = sample_player_game_data[col].dropna().tolist()
            enriched_values = enriched[col].dropna().tolist()

            # Should have at least the same values (enrichment shouldn't remove data)
            for val in original_values:
                assert val in enriched_values, \
                    f"Value {val} from column {col} lost during enrichment"


@pytest.mark.asyncio
async def test_enrichment_row_count(sample_player_game_data):
    """Test that enrichment doesn't change row count"""
    engine = EnrichmentEngine()

    enriched = await engine.enrich(
        sample_player_game_data,
        GroupingLevel.PLAYER_GAME
    )

    assert len(enriched) == len(sample_player_game_data), \
        "Enrichment changed row count"


# ============================================================================
# TEST INTEGRATION WITH FETCH FUNCTIONS
# ============================================================================

@pytest.mark.skip(reason="Requires live NBA API access")
@pytest.mark.asyncio
async def test_fetch_grouping_with_enrichment():
    """Test fetch_grouping with enrichment (requires API)"""
    # Fetch with default enrichment
    df = await fetch_grouping(
        "player/game",
        season="2023-24",
        player_id=2544,
        last_n_games=5
    )

    # Should have enriched columns
    assert len(df.columns) > 20  # Should have more than basic columns

    # Check for no duplicates
    duplicates = df.columns[df.columns.duplicated()].tolist()
    assert len(duplicates) == 0, f"Found duplicate columns: {duplicates}"


@pytest.mark.skip(reason="Requires live NBA API access")
@pytest.mark.asyncio
async def test_fetch_grouping_without_enrichment():
    """Test fetch_grouping without enrichment (requires API)"""
    # Fetch without enrichment
    df = await fetch_grouping(
        "player/game",
        season="2023-24",
        player_id=2544,
        last_n_games=5,
        enrich=False
    )

    # Should have basic columns only
    # Exact count depends on NBA API response, but should be fewer than enriched
    assert len(df) > 0


# ============================================================================
# VALIDATION SUMMARY
# ============================================================================

def get_column_summary(df: pd.DataFrame) -> Dict[str, any]:
    """Get summary of DataFrame columns"""
    return {
        "total_columns": len(df.columns),
        "duplicate_columns": df.columns[df.columns.duplicated()].tolist(),
        "columns": sorted(df.columns.tolist()),
        "total_rows": len(df),
        "dtypes": df.dtypes.to_dict(),
    }


@pytest.mark.asyncio
async def test_validation_summary_report(sample_player_game_data):
    """Generate validation summary report"""
    engine = EnrichmentEngine()

    # Get summary before enrichment
    before_summary = get_column_summary(sample_player_game_data)

    # Apply enrichment
    enriched = await engine.enrich(
        sample_player_game_data,
        GroupingLevel.PLAYER_GAME
    )

    # Get summary after enrichment
    after_summary = get_column_summary(enriched)

    # Print summary
    print("\n" + "="*80)
    print("ENRICHMENT VALIDATION SUMMARY")
    print("="*80)
    print(f"Before enrichment:")
    print(f"  Columns: {before_summary['total_columns']}")
    print(f"  Rows: {before_summary['total_rows']}")
    print(f"\nAfter enrichment:")
    print(f"  Columns: {after_summary['total_columns']}")
    print(f"  Rows: {after_summary['total_rows']}")
    print(f"  Columns added: {after_summary['total_columns'] - before_summary['total_columns']}")
    print(f"  Duplicate columns: {after_summary['duplicate_columns']}")

    # Get new columns
    new_columns = set(after_summary['columns']) - set(before_summary['columns'])
    print(f"\nNew columns added ({len(new_columns)}):")
    for col in sorted(new_columns):
        print(f"  - {col}")

    print("="*80 + "\n")

    # Assertions
    assert after_summary['total_rows'] == before_summary['total_rows']
    assert len(after_summary['duplicate_columns']) == 0
    assert after_summary['total_columns'] >= before_summary['total_columns']


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
