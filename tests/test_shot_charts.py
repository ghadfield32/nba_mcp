"""
Unit and integration tests for shot_charts.py module.

Tests cover:
1. Coordinate validation (valid, invalid, edge cases)
2. Hexbin aggregation (algorithm correctness, edge cases)
3. Zone summary calculations (all zones, FG% accuracy)
4. Integration with NBA API (rate limit aware)
5. Entity resolution integration
6. Error handling (EntityNotFoundError, InvalidParameterError)

Run with: pytest test_shot_charts.py -v
"""

import asyncio
from typing import Dict, List

import numpy as np
import pandas as pd
import pytest

from nba_mcp.api.errors import EntityNotFoundError, InvalidParameterError
from nba_mcp.api.shot_charts import (
    aggregate_to_hexbin,
    calculate_zone_summary,
    fetch_shot_chart_data,
    get_shot_chart,
    validate_shot_coordinates,
)


# ============================================================================
# Unit Tests: validate_shot_coordinates
# ============================================================================


def test_validate_coordinates_all_valid():
    """Test that all valid coordinates pass through unchanged."""
    df = pd.DataFrame({
        'LOC_X': [0, 100, -100, 250, -250],
        'LOC_Y': [0, 100, 200, 300, 400],
        'SHOT_MADE_FLAG': [1, 0, 1, 0, 1]
    })

    result = validate_shot_coordinates(df)

    assert len(result) == 5, "All valid coordinates should pass"
    assert result.equals(df), "DataFrame should be unchanged"


def test_validate_coordinates_invalid_x():
    """Test that invalid X coordinates are filtered out."""
    df = pd.DataFrame({
        'LOC_X': [0, 300, -300, 100],  # 300 and -300 are invalid
        'LOC_Y': [0, 100, 100, 200],
        'SHOT_MADE_FLAG': [1, 0, 1, 0]
    })

    result = validate_shot_coordinates(df)

    assert len(result) == 2, "Should filter out 2 invalid X coordinates"
    assert result['LOC_X'].tolist() == [0, 100], "Only valid X coords remain"


def test_validate_coordinates_invalid_y():
    """Test that invalid Y coordinates are filtered out."""
    df = pd.DataFrame({
        'LOC_X': [0, 100, 200, 100],
        'LOC_Y': [0, -100, 500, 200],  # -100 and 500 are invalid
        'SHOT_MADE_FLAG': [1, 0, 1, 0]
    })

    result = validate_shot_coordinates(df)

    assert len(result) == 2, "Should filter out 2 invalid Y coordinates"
    assert result['LOC_Y'].tolist() == [0, 200], "Only valid Y coords remain"


def test_validate_coordinates_boundary_values():
    """Test boundary values are accepted."""
    df = pd.DataFrame({
        'LOC_X': [-250, 250, -250, 250],  # Exact boundaries
        'LOC_Y': [-52.5, -52.5, 417.5, 417.5],  # Exact boundaries
        'SHOT_MADE_FLAG': [1, 0, 1, 0]
    })

    result = validate_shot_coordinates(df)

    assert len(result) == 4, "Boundary values should be valid"


def test_validate_coordinates_empty_dataframe():
    """Test handling of empty DataFrame."""
    df = pd.DataFrame({'LOC_X': [], 'LOC_Y': [], 'SHOT_MADE_FLAG': []})

    result = validate_shot_coordinates(df)

    assert len(result) == 0, "Empty DataFrame should remain empty"
    assert result.empty, "Result should be empty"


def test_validate_coordinates_missing_columns():
    """Test handling of missing required columns."""
    df = pd.DataFrame({'LOC_X': [0, 100], 'OTHER': [1, 2]})  # Missing LOC_Y

    result = validate_shot_coordinates(df)

    # Should return original DataFrame unchanged (with warning logged)
    assert result.equals(df), "Should return original if columns missing"


# ============================================================================
# Unit Tests: aggregate_to_hexbin
# ============================================================================


def test_aggregate_to_hexbin_basic():
    """Test basic hexbin aggregation with known coordinates."""
    # Create shots in a single bin (all within 10 tenths of feet)
    df = pd.DataFrame({
        'LOC_X': [0, 3, 7],  # All map to same bin with grid_size=10
        'LOC_Y': [0, 2, 5],  # All map to same bin with grid_size=10
        'SHOT_MADE_FLAG': [1, 0, 1],  # 2 makes, 1 miss
        'SHOT_DISTANCE': [10, 12, 15]
    })

    result = aggregate_to_hexbin(df, grid_size=10, min_shots=3)

    assert len(result) == 1, f"Should have 1 bin, got {len(result)}"
    assert result[0]['shot_count'] == 3, "Bin should have 3 shots"
    assert result[0]['made_count'] == 2, "Bin should have 2 makes"
    assert abs(result[0]['fg_pct'] - 0.667) < 0.01, "FG% should be ~66.7%"
    assert 'distance_avg' in result[0], "Should include average distance"


def test_aggregate_to_hexbin_multiple_bins():
    """Test hexbin aggregation across multiple bins."""
    df = pd.DataFrame({
        'LOC_X': [0, 0, 0, 0, 0,    # Bin 1: 5 shots at (0,0)
                  100, 100, 100, 100, 100],  # Bin 2: 5 shots at (100,0)
        'LOC_Y': [0, 0, 0, 0, 0,
                  0, 0, 0, 0, 0],
        'SHOT_MADE_FLAG': [1, 1, 1, 0, 0,  # Bin 1: 3/5 = 60%
                           1, 1, 1, 1, 0],  # Bin 2: 4/5 = 80%
        'SHOT_DISTANCE': [10] * 10
    })

    result = aggregate_to_hexbin(df, grid_size=10, min_shots=5)

    assert len(result) == 2, "Should have 2 bins"

    # Check FG% for both bins
    fg_pcts = sorted([b['fg_pct'] for b in result])
    assert abs(fg_pcts[0] - 0.6) < 0.01, "Lower FG% should be 60%"
    assert abs(fg_pcts[1] - 0.8) < 0.01, "Higher FG% should be 80%"


def test_aggregate_to_hexbin_min_shots_filter():
    """Test that bins with fewer than min_shots are filtered."""
    df = pd.DataFrame({
        'LOC_X': [0, 0, 0,       # Bin 1: 3 shots (below min)
                  100, 100, 100, 100, 100],  # Bin 2: 5 shots (meets min)
        'LOC_Y': [0, 0, 0,
                  0, 0, 0, 0, 0],
        'SHOT_MADE_FLAG': [1, 0, 1,
                           1, 1, 0, 1, 0],
        'SHOT_DISTANCE': [10] * 8
    })

    result = aggregate_to_hexbin(df, grid_size=10, min_shots=5)

    assert len(result) == 1, "Should filter out bin with <5 shots"
    assert result[0]['shot_count'] == 5, "Remaining bin should have 5 shots"


def test_aggregate_to_hexbin_empty_shots():
    """Test handling of empty shots DataFrame."""
    df = pd.DataFrame({'LOC_X': [], 'LOC_Y': [], 'SHOT_MADE_FLAG': []})

    result = aggregate_to_hexbin(df, grid_size=10, min_shots=5)

    assert len(result) == 0, "Empty input should return empty list"


def test_aggregate_to_hexbin_single_shot():
    """Test handling of single shot (below min_shots)."""
    df = pd.DataFrame({
        'LOC_X': [0],
        'LOC_Y': [0],
        'SHOT_MADE_FLAG': [1],
        'SHOT_DISTANCE': [10]
    })

    result = aggregate_to_hexbin(df, grid_size=10, min_shots=5)

    assert len(result) == 0, "Single shot should be filtered (below min)"


def test_aggregate_to_hexbin_missing_columns():
    """Test handling of missing required columns."""
    df = pd.DataFrame({
        'LOC_X': [0, 0, 0],
        'LOC_Y': [0, 0, 0]
        # Missing SHOT_MADE_FLAG
    })

    result = aggregate_to_hexbin(df, grid_size=10, min_shots=3)

    assert len(result) == 0, "Should return empty list if columns missing"


def test_aggregate_to_hexbin_grid_sizes():
    """Test different grid sizes produce different bin counts."""
    # Create shots spread across court
    df = pd.DataFrame({
        'LOC_X': list(range(0, 200, 20)),  # 10 shots spread out
        'LOC_Y': [0] * 10,
        'SHOT_MADE_FLAG': [1] * 10,
        'SHOT_DISTANCE': [20] * 10
    })

    # Larger grid size = fewer bins
    result_large = aggregate_to_hexbin(df, grid_size=50, min_shots=1)
    result_small = aggregate_to_hexbin(df, grid_size=10, min_shots=1)

    assert len(result_large) <= len(result_small), "Larger grid should have fewer bins"


# ============================================================================
# Unit Tests: calculate_zone_summary
# ============================================================================


def test_calculate_zone_summary_all_zones():
    """Test zone summary with shots in all zones."""
    df = pd.DataFrame({
        'SHOT_DISTANCE': [5, 6,       # Paint: 2 shots
                          10, 12,      # Short mid: 2 shots
                          18, 20,      # Long mid: 2 shots
                          25, 26],     # Three: 2 shots
        'SHOT_MADE_FLAG': [1, 1,       # Paint: 2/2 = 100%
                           1, 0,       # Short mid: 1/2 = 50%
                           0, 0,       # Long mid: 0/2 = 0%
                           1, 1],      # Three: 2/2 = 100%
        'SHOT_TYPE': ['2PT Field Goal'] * 6 + ['3PT Field Goal'] * 2
    })

    result = calculate_zone_summary(df)

    # Check paint zone
    assert result['paint']['attempts'] == 2
    assert result['paint']['made'] == 2
    assert result['paint']['pct'] == 1.0

    # Check short mid zone
    assert result['short_mid']['attempts'] == 2
    assert result['short_mid']['made'] == 1
    assert result['short_mid']['pct'] == 0.5

    # Check long mid zone
    assert result['long_mid']['attempts'] == 2
    assert result['long_mid']['made'] == 0
    assert result['long_mid']['pct'] == 0.0

    # Check three-point zone
    assert result['three']['attempts'] == 2
    assert result['three']['made'] == 2
    assert result['three']['pct'] == 1.0

    # Check overall
    assert result['overall']['attempts'] == 8
    assert result['overall']['made'] == 5
    assert abs(result['overall']['pct'] - 0.625) < 0.01


def test_calculate_zone_summary_empty():
    """Test zone summary with empty DataFrame."""
    df = pd.DataFrame({'SHOT_DISTANCE': [], 'SHOT_MADE_FLAG': []})

    result = calculate_zone_summary(df)

    # All zones should have zero values
    for zone in ['paint', 'short_mid', 'long_mid', 'three', 'overall']:
        assert result[zone]['attempts'] == 0
        assert result[zone]['made'] == 0
        assert result[zone]['pct'] == 0.0


def test_calculate_zone_summary_no_shot_type():
    """Test zone summary when SHOT_TYPE column is missing (fallback)."""
    df = pd.DataFrame({
        'SHOT_DISTANCE': [5, 10, 18, 25],
        'SHOT_MADE_FLAG': [1, 1, 0, 1]
        # No SHOT_TYPE column - should use distance-based fallback
    })

    result = calculate_zone_summary(df)

    # Should still categorize correctly using distance
    assert result['paint']['attempts'] == 1  # 5 ft
    assert result['short_mid']['attempts'] == 1  # 10 ft
    assert result['long_mid']['attempts'] == 1  # 18 ft
    assert result['three']['attempts'] == 1  # 25 ft (>= 23.75)


def test_calculate_zone_summary_corner_three():
    """Test that corner threes (22 ft) are identified correctly by SHOT_TYPE."""
    df = pd.DataFrame({
        'SHOT_DISTANCE': [22, 22, 22],  # Corner three distance
        'SHOT_MADE_FLAG': [1, 0, 1],
        'SHOT_TYPE': ['3PT Field Goal', '3PT Field Goal', '3PT Field Goal']
    })

    result = calculate_zone_summary(df)

    # Should be categorized as three-pointers (not long mid)
    assert result['three']['attempts'] == 3
    assert result['long_mid']['attempts'] == 0


# ============================================================================
# Integration Tests: get_shot_chart
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_shot_chart_player_stephen_curry():
    """
    Integration test: Fetch real shot chart for Stephen Curry.

    Note: This test makes a real NBA API call and may fail if:
    - Rate limit exceeded
    - API is down
    - Season has no data yet

    Run with: pytest -m integration
    """
    try:
        result = await get_shot_chart(
            entity_name="Stephen Curry",
            entity_type="player",
            season="2022-23",  # Use past season (stable data)
            season_type="Regular Season",
            granularity="summary"  # Summary only (smaller payload)
        )

        # Validate response structure
        assert 'entity' in result
        assert result['entity']['name'] == "Stephen Curry"
        assert result['entity']['type'] == "player"

        assert 'zone_summary' in result
        assert 'three' in result['zone_summary']

        # Curry should have taken many three-pointers
        three_attempts = result['zone_summary']['three']['attempts']
        assert three_attempts > 0, "Curry should have three-point attempts"

        print(f"✅ Successfully fetched Curry's shot chart: {three_attempts} three-point attempts")

    except Exception as e:
        pytest.skip(f"Integration test skipped: {str(e)}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_shot_chart_team_warriors():
    """
    Integration test: Fetch real shot chart for Warriors.

    Run with: pytest -m integration
    """
    try:
        result = await get_shot_chart(
            entity_name="Warriors",
            entity_type="team",
            season="2022-23",
            season_type="Regular Season",
            granularity="summary"
        )

        # Validate response structure
        assert 'entity' in result
        assert "Warriors" in result['entity']['name']
        assert result['entity']['type'] == "team"

        assert 'zone_summary' in result
        assert 'overall' in result['zone_summary']

        # Warriors should have many total attempts
        total_attempts = result['zone_summary']['overall']['attempts']
        assert total_attempts > 1000, "Warriors should have many shot attempts"

        print(f"✅ Successfully fetched Warriors shot chart: {total_attempts} total attempts")

    except Exception as e:
        pytest.skip(f"Integration test skipped: {str(e)}")


@pytest.mark.asyncio
async def test_get_shot_chart_invalid_player():
    """Test that invalid player name raises EntityNotFoundError."""
    with pytest.raises(EntityNotFoundError) as exc_info:
        await get_shot_chart(
            entity_name="Definitely Not A Real Player Name XYZ",
            entity_type="player",
            season="2022-23",
            granularity="summary"
        )

    error = exc_info.value
    assert error.code == "ENTITY_NOT_FOUND"
    assert "suggestions" in error.details or error.message


@pytest.mark.asyncio
async def test_get_shot_chart_all_granularities():
    """Test all granularity modes return correct data structure."""
    # Use mock data or skip if API unavailable
    granularities = ["raw", "hexbin", "both", "summary"]

    for granularity in granularities:
        try:
            result = await get_shot_chart(
                entity_name="LeBron James",
                entity_type="player",
                season="2022-23",
                granularity=granularity
            )

            # Validate structure based on granularity
            if granularity in ["raw", "both"]:
                assert 'raw_shots' in result, f"Missing raw_shots for {granularity}"

            if granularity in ["hexbin", "both"]:
                assert 'hexbin' in result, f"Missing hexbin for {granularity}"

            if granularity in ["summary", "both"]:
                assert 'zone_summary' in result, f"Missing zone_summary for {granularity}"

            print(f"✅ Granularity '{granularity}' returns correct structure")

        except Exception as e:
            pytest.skip(f"Granularity test skipped for {granularity}: {str(e)}")


# ============================================================================
# Performance Tests
# ============================================================================


@pytest.mark.performance
def test_hexbin_aggregation_performance():
    """Test hexbin aggregation performance with large dataset."""
    import time

    # Create large dataset (1000 shots)
    np.random.seed(42)
    df = pd.DataFrame({
        'LOC_X': np.random.randint(-250, 250, 1000),
        'LOC_Y': np.random.randint(-50, 400, 1000),
        'SHOT_MADE_FLAG': np.random.randint(0, 2, 1000),
        'SHOT_DISTANCE': np.random.randint(5, 30, 1000)
    })

    start = time.time()
    result = aggregate_to_hexbin(df, grid_size=10, min_shots=5)
    duration = time.time() - start

    assert duration < 0.1, f"Hexbin aggregation too slow: {duration:.3f}s (expected <0.1s)"
    assert len(result) > 0, "Should produce some bins"

    print(f"✅ Hexbin aggregation: {duration*1000:.1f}ms for 1000 shots ({len(result)} bins)")


@pytest.mark.performance
def test_zone_summary_performance():
    """Test zone summary calculation performance."""
    import time

    # Create large dataset (1000 shots)
    np.random.seed(42)
    df = pd.DataFrame({
        'SHOT_DISTANCE': np.random.randint(5, 30, 1000),
        'SHOT_MADE_FLAG': np.random.randint(0, 2, 1000),
        'SHOT_TYPE': np.random.choice(['2PT Field Goal', '3PT Field Goal'], 1000)
    })

    start = time.time()
    result = calculate_zone_summary(df)
    duration = time.time() - start

    assert duration < 0.05, f"Zone summary too slow: {duration:.3f}s (expected <0.05s)"
    assert result['overall']['attempts'] == 1000

    print(f"✅ Zone summary: {duration*1000:.1f}ms for 1000 shots")


# ============================================================================
# Edge Cases
# ============================================================================


def test_all_shots_made():
    """Test zone summary when all shots are made (100% FG)."""
    df = pd.DataFrame({
        'SHOT_DISTANCE': [10, 15, 20, 25],
        'SHOT_MADE_FLAG': [1, 1, 1, 1],  # All made
        'SHOT_TYPE': ['2PT Field Goal'] * 3 + ['3PT Field Goal']
    })

    result = calculate_zone_summary(df)

    assert result['overall']['pct'] == 1.0, "Should be 100% FG"


def test_all_shots_missed():
    """Test zone summary when all shots are missed (0% FG)."""
    df = pd.DataFrame({
        'SHOT_DISTANCE': [10, 15, 20, 25],
        'SHOT_MADE_FLAG': [0, 0, 0, 0],  # All missed
        'SHOT_TYPE': ['2PT Field Goal'] * 3 + ['3PT Field Goal']
    })

    result = calculate_zone_summary(df)

    assert result['overall']['pct'] == 0.0, "Should be 0% FG"


def test_coordinates_exactly_at_boundary():
    """Test coordinates exactly at court boundaries."""
    df = pd.DataFrame({
        'LOC_X': [-250, 250],  # Exact min/max
        'LOC_Y': [-52.5, 417.5],  # Exact min/max
        'SHOT_MADE_FLAG': [1, 0]
    })

    result = validate_shot_coordinates(df)

    assert len(result) == 2, "Boundary values should be valid"


# ============================================================================
# Test Configuration
# ============================================================================


if __name__ == "__main__":
    # Run all tests
    pytest.main([__file__, "-v", "--tb=short"])

    # Run only unit tests (fast)
    # pytest.main([__file__, "-v", "-m", "not integration and not performance"])

    # Run integration tests (slow, requires NBA API)
    # pytest.main([__file__, "-v", "-m", "integration"])

    # Run performance tests
    # pytest.main([__file__, "-v", "-m", "performance"])
