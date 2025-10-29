"""
Test suite for awards_loader module
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.awards_loader import (
    load_awards_data,
    get_player_awards_for_season,
    get_award_winners,
    format_awards_human_readable,
    get_all_award_types,
    format_award_winners_text,
)


def test_load_awards_data():
    """Test loading awards data from JSON"""
    print("\n" + "="*60)
    print("TEST 1: Load Awards Data")
    print("="*60)

    data = load_awards_data()

    # Check that data was loaded
    assert data is not None, "Data should not be None"
    assert isinstance(data, dict), "Data should be a dictionary"

    # Check for expected award types
    expected_awards = ["mvp", "finals_mvp", "dpoy", "roy", "smoy", "mip", "coy"]
    for award in expected_awards:
        assert award in data, f"Missing award type: {award}"
        assert isinstance(data[award], list), f"{award} should be a list"
        assert len(data[award]) > 0, f"{award} should have winners"

    print(f"[OK] Loaded {len(data)} award types")
    print(f"   Award types: {', '.join([k for k in data.keys() if k != 'metadata'])}")
    print(f"   MVP winners: {len(data['mvp'])}")


def test_get_player_awards_for_season():
    """Test getting awards for a specific player and season"""
    print("\n" + "="*60)
    print("TEST 2: Get Player Awards for Season")
    print("="*60)

    # Test with known MVP winner: Jokić 2023-24
    awards = get_player_awards_for_season(203999, "2023-24")

    assert isinstance(awards, dict), "Awards should be a dictionary"
    assert "mvp" in awards, "Should have MVP key"
    assert awards["mvp"] == True, "Jokić should have won MVP in 2023-24"

    print(f"[OK] Jokić 2023-24 awards:")
    for award_type, won in awards.items():
        if won:
            print(f"   - {award_type}: {won}")

    # Test with non-MVP season
    awards_non_mvp = get_player_awards_for_season(2544, "2020-21")  # LeBron
    print(f"\n[OK] LeBron 2020-21 awards:")
    for award_type, won in awards_non_mvp.items():
        if won:
            print(f"   - {award_type}: {won}")


def test_get_award_winners():
    """Test getting award winners with filtering"""
    print("\n" + "="*60)
    print("TEST 3: Get Award Winners with Filtering")
    print("="*60)

    # Test last N MVPs
    mvp_winners = get_award_winners("mvp", last_n=5)

    assert isinstance(mvp_winners, list), "Should return a list"
    assert len(mvp_winners) <= 5, "Should return at most 5 winners"
    assert all("season" in w for w in mvp_winners), "Each winner should have season"
    assert all("player_name" in w for w in mvp_winners), "Each winner should have player_name"

    print(f"[OK] Last 5 MVP winners:")
    for winner in mvp_winners:
        print(f"   {winner['season']}: {winner['player_name']} ({winner.get('team', 'N/A')})")

    # Test season range filter
    dpoy_range = get_award_winners("dpoy", start_season="2020-21", end_season="2023-24")
    print(f"\n[OK] DPOY winners (2020-21 to 2023-24): {len(dpoy_range)} winners")
    for winner in dpoy_range:
        print(f"   {winner['season']}: {winner['player_name']}")


def test_format_awards_human_readable():
    """Test formatting awards as human-readable list"""
    print("\n" + "="*60)
    print("TEST 4: Format Awards Human Readable")
    print("="*60)

    awards = {"mvp": True, "dpoy": False, "finals_mvp": True, "roy": False}
    formatted = format_awards_human_readable(awards)

    assert isinstance(formatted, list), "Should return a list"
    assert "MVP" in formatted, "Should include MVP"
    assert "Finals MVP" in formatted, "Should include Finals MVP"
    assert "Defensive Player of the Year" not in formatted, "Should not include DPOY"

    print(f"[OK] Formatted awards: {formatted}")


def test_get_all_award_types():
    """Test getting all award types"""
    print("\n" + "="*60)
    print("TEST 5: Get All Award Types")
    print("="*60)

    award_types = get_all_award_types()

    assert isinstance(award_types, list), "Should return a list"
    assert len(award_types) > 0, "Should have award types"
    assert "mvp" in award_types, "Should include MVP"
    assert "metadata" not in award_types, "Should exclude metadata"

    print(f"[OK] Award types: {', '.join(award_types)}")


def test_format_award_winners_text():
    """Test formatting award winners as text"""
    print("\n" + "="*60)
    print("TEST 6: Format Award Winners Text")
    print("="*60)

    winners = get_award_winners("mvp", last_n=3)
    text = format_award_winners_text("mvp", winners)

    assert isinstance(text, str), "Should return a string"
    assert "MVP Winners" in text, "Should have title"
    assert len(text) > 0, "Should have content"

    print(f"[OK] Formatted text:\n{text}")


def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("RUNNING AWARDS LOADER TEST SUITE")
    print("=" * 60)

    tests = [
        test_load_awards_data,
        test_get_player_awards_for_season,
        test_get_award_winners,
        test_format_awards_human_readable,
        test_get_all_award_types,
        test_format_award_winners_text,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {test_func.__name__} FAILED: {e}")
            failed += 1
            import traceback
            traceback.print_exc()

    print("\n" + "="*60)
    print(f"TEST SUMMARY: {passed} passed, {failed} failed")
    print("="*60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
