"""
Test script for era-adjusted player comparison feature.

Validates the core logic of era adjustments without making live API calls.
"""

import sys

sys.path.insert(0, "/home/user/nba_mcp")

from nba_mcp.api.era_adjusted import (
    BASELINE,
    LEAGUE_AVERAGES,
    AdjustedStats,
    EraAdjustment,
    adjust_for_era,
    create_adjusted_stats,
    format_era_comparison,
    get_era_adjustment,
)


def test_era_adjustment_calculation():
    """Test that era adjustment factors are calculated correctly."""
    print("=" * 70)
    print("TEST 1: Era Adjustment Calculation")
    print("=" * 70)

    # Test 1995-96 (MJ's Bulls championship season)
    adj_1996 = get_era_adjustment("1995-96")
    print(f"\n1995-96 Season (Michael Jordan era):")
    print(f"  Pace Factor: {adj_1996.pace_factor:.3f}")
    print(f"  Scoring Factor: {adj_1996.scoring_factor:.3f}")
    print(f"  Era: {adj_1996.era_description}")

    # Verify calculation: BASELINE["pace"] / LEAGUE_AVERAGES["1995-96"]["pace"]
    expected_pace = BASELINE["pace"] / LEAGUE_AVERAGES["1995-96"]["pace"]
    expected_scoring = BASELINE["ppg"] / LEAGUE_AVERAGES["1995-96"]["ppg"]
    print(f"\n  Expected pace: {expected_pace:.3f}")
    print(f"  Expected scoring: {expected_scoring:.3f}")

    assert abs(adj_1996.pace_factor - expected_pace) < 0.001, "Pace factor mismatch!"
    assert (
        abs(adj_1996.scoring_factor - expected_scoring) < 0.001
    ), "Scoring factor mismatch!"
    print("  ✅ Calculations correct!")

    # Test 2012-13 (LeBron's Heat championship)
    adj_2013 = get_era_adjustment("2012-13")
    print(f"\n2012-13 Season (LeBron James era):")
    print(f"  Pace Factor: {adj_2013.pace_factor:.3f}")
    print(f"  Scoring Factor: {adj_2013.scoring_factor:.3f}")
    print(f"  Era: {adj_2013.era_description}")

    # Verify both eras need adjustment (both slower/lower scoring than modern baseline)
    # Note: 2012-13 had lower scoring (98.1 PPG) than 1995-96 (99.5 PPG),
    # so scoring adjustment is actually HIGHER for 2012-13
    assert adj_1996.pace_factor > 1.0, "1995-96 should adjust pace upward"
    assert adj_2013.pace_factor > 1.0, "2012-13 should adjust pace upward"
    assert adj_1996.scoring_factor > 1.0, "1995-96 should adjust scoring upward"
    assert adj_2013.scoring_factor > 1.0, "2012-13 should adjust scoring upward"
    print("  ✅ Relative adjustments correct!")


def test_stat_adjustment():
    """Test that stats are adjusted correctly."""
    print("\n" + "=" * 70)
    print("TEST 2: Stat Adjustment")
    print("=" * 70)

    # Michael Jordan's 1995-96 stats (actual per-game averages)
    mj_stats = {
        "ppg": 30.4,
        "rpg": 6.6,
        "apg": 4.3,
        "spg": 2.2,
        "bpg": 0.5,
    }

    print(f"\nMichael Jordan 1995-96 Raw Stats:")
    print(f"  PPG: {mj_stats['ppg']:.1f}")
    print(f"  RPG: {mj_stats['rpg']:.1f}")
    print(f"  APG: {mj_stats['apg']:.1f}")

    adjusted, adj_info = adjust_for_era(mj_stats, "1995-96")

    print(f"\nEra-Adjusted Stats (normalized to {BASELINE['pace']} pace, {BASELINE['ppg']} PPG):")
    print(f"  PPG: {adjusted['ppg']:.1f}")
    print(f"  RPG: {adjusted['rpg']:.1f}")
    print(f"  APG: {adjusted['apg']:.1f}")

    # Verify adjustments increase stats (1995-96 was slower/lower scoring)
    assert adjusted["ppg"] > mj_stats["ppg"], "PPG should increase!"
    assert adjusted["rpg"] > mj_stats["rpg"], "RPG should increase!"
    assert adjusted["apg"] > mj_stats["apg"], "APG should increase!"
    print("  ✅ Stats adjusted upward as expected!")


def test_adjusted_stats_object():
    """Test AdjustedStats dataclass creation."""
    print("\n" + "=" * 70)
    print("TEST 3: AdjustedStats Object")
    print("=" * 70)

    stats = {"ppg": 30.4, "rpg": 6.6, "apg": 4.3}
    adjusted = create_adjusted_stats(stats, "1995-96")

    print(f"\nCreated AdjustedStats object:")
    print(f"  Season: {adjusted.season}")
    print(f"  Raw PPG: {adjusted.ppg_raw:.1f}")
    print(f"  Adjusted PPG: {adjusted.ppg_adjusted:.1f}")
    print(f"  Pace Factor: {adjusted.pace_factor:.3f}")
    print(f"  Scoring Factor: {adjusted.scoring_factor:.3f}")
    print(f"  Era: {adjusted.era_description}")

    assert adjusted.season == "1995-96", "Season mismatch!"
    assert adjusted.ppg_raw == stats["ppg"], "Raw PPG mismatch!"
    assert adjusted.ppg_adjusted > adjusted.ppg_raw, "Adjusted PPG should be higher!"
    print("  ✅ AdjustedStats object correct!")


def test_era_comparison_formatting():
    """Test formatted comparison output."""
    print("\n" + "=" * 70)
    print("TEST 4: Era Comparison Formatting")
    print("=" * 70)

    # MJ 1995-96
    mj_stats = {"ppg": 30.4, "rpg": 6.6, "apg": 4.3}
    mj_adjusted = create_adjusted_stats(mj_stats, "1995-96")

    # LeBron 2012-13
    lbj_stats = {"ppg": 26.8, "rpg": 8.0, "apg": 7.3}
    lbj_adjusted = create_adjusted_stats(lbj_stats, "2012-13")

    comparison = format_era_comparison(
        "Michael Jordan", "LeBron James", mj_adjusted, lbj_adjusted
    )

    print("\nGenerated comparison markdown:")
    print(comparison)

    # Verify key sections exist
    assert "Era-Adjusted Player Comparison" in comparison, "Missing title!"
    assert "Michael Jordan" in comparison, "Missing MJ name!"
    assert "LeBron James" in comparison, "Missing LeBron name!"
    assert "1995-96" in comparison, "Missing MJ season!"
    assert "2012-13" in comparison, "Missing LeBron season!"
    assert "Era-Adjusted Comparison" in comparison, "Missing comparison table!"
    assert "What These Adjustments Mean" in comparison, "Missing explanation!"
    print("\n  ✅ Comparison formatting correct!")


def test_unknown_season_handling():
    """Test handling of seasons not in historical data."""
    print("\n" + "=" * 70)
    print("TEST 5: Unknown Season Handling")
    print("=" * 70)

    # Test with a future season not in LEAGUE_AVERAGES
    adj = get_era_adjustment("2099-00")

    print(f"\n2099-00 Season (unknown):")
    print(f"  Pace Factor: {adj.pace_factor:.3f}")
    print(f"  Scoring Factor: {adj.scoring_factor:.3f}")
    print(f"  Era: {adj.era_description}")

    # Should return 1.0 factors (no adjustment)
    assert adj.pace_factor == 1.0, "Unknown season should have pace_factor=1.0"
    assert adj.scoring_factor == 1.0, "Unknown season should have scoring_factor=1.0"
    assert "Unknown era" in adj.era_description, "Should indicate unknown era"
    print("  ✅ Unknown season handled correctly!")


def test_era_descriptions():
    """Test that era descriptions are correct for different decades."""
    print("\n" + "=" * 70)
    print("TEST 6: Era Descriptions")
    print("=" * 70)

    test_cases = [
        ("1995-96", "1990s"),
        ("2003-04", "2000s"),
        ("2015-16", "2010s"),
        ("2023-24", "2020s"),
    ]

    for season, expected_decade in test_cases:
        adj = get_era_adjustment(season)
        print(f"\n{season}: {adj.era_description}")
        assert (
            expected_decade in adj.era_description
        ), f"{season} should be in {expected_decade}!"

    print("\n  ✅ All era descriptions correct!")


def test_league_averages_data():
    """Test that LEAGUE_AVERAGES data is complete and valid."""
    print("\n" + "=" * 70)
    print("TEST 7: League Averages Data")
    print("=" * 70)

    print(f"\nTotal seasons in LEAGUE_AVERAGES: {len(LEAGUE_AVERAGES)}")
    print(f"Earliest season: {min(LEAGUE_AVERAGES.keys())}")
    print(f"Latest season: {max(LEAGUE_AVERAGES.keys())}")

    # Verify all entries have required keys
    for season, data in LEAGUE_AVERAGES.items():
        assert "ppg" in data, f"{season} missing 'ppg'!"
        assert "pace" in data, f"{season} missing 'pace'!"
        assert isinstance(data["ppg"], (int, float)), f"{season} ppg not numeric!"
        assert isinstance(data["pace"], (int, float)), f"{season} pace not numeric!"

    print("  ✅ All league average entries valid!")


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("ERA-ADJUSTED STATISTICS TEST SUITE")
    print("=" * 70)
    print()

    try:
        test_era_adjustment_calculation()
        test_stat_adjustment()
        test_adjusted_stats_object()
        test_era_comparison_formatting()
        test_unknown_season_handling()
        test_era_descriptions()
        test_league_averages_data()

        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED!")
        print("=" * 70)
        print("\nEra-adjusted statistics feature is working correctly.")
        print("The tool can now:")
        print("  1. Calculate pace and scoring adjustment factors")
        print("  2. Adjust player stats to modern baseline")
        print("  3. Format cross-era comparisons")
        print("  4. Handle unknown seasons gracefully")
        return 0

    except AssertionError as e:
        print("\n" + "=" * 70)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 70)
        return 1

    except Exception as e:
        print("\n" + "=" * 70)
        print(f"❌ UNEXPECTED ERROR: {e}")
        print("=" * 70)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
