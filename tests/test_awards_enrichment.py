"""
Test suite for awards enrichment in season stats
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.season_aggregator import get_player_season_stats


async def test_backward_compatibility():
    """Test that season stats work WITHOUT include_awards (backward compatibility)"""
    print("\n" + "="*60)
    print("TEST 1: Backward Compatibility (NO awards)")
    print("="*60)

    # Get Jokic's 2023-24 stats WITHOUT awards
    stats = await get_player_season_stats("2023-24", player_id=203999)

    # Verify basic stats exist
    assert stats is not None, "Stats should not be None"
    assert "SEASON_YEAR" in stats, "Should have SEASON_YEAR"
    assert "PLAYER_ID" in stats, "Should have PLAYER_ID"
    assert "GP" in stats, "Should have games played"
    assert "PPG" in stats, "Should have PPG"

    # Verify awards fields are NOT present (backward compatibility)
    assert "AWARDS" not in stats, "AWARDS should NOT be present without include_awards=True"
    assert "AWARDS_WON" not in stats, "AWARDS_WON should NOT be present"
    assert "AWARDS_COUNT" not in stats, "AWARDS_COUNT should NOT be present"

    print(f"[OK] Player: {stats.get('PLAYER_NAME', 'Unknown')}")
    print(f"[OK] Season: {stats.get('SEASON_YEAR')}")
    print(f"[OK] GP: {stats.get('GP')}, PPG: {stats.get('PPG'):.1f}")
    print(f"[OK] NO awards fields present (backward compatible)")


async def test_with_awards_mvp_winner():
    """Test that season stats work WITH include_awards for known MVP winner"""
    print("\n" + "="*60)
    print("TEST 2: With Awards - MVP Winner (Jokic 2023-24)")
    print("="*60)

    # Get Jokic's 2023-24 stats WITH awards (he won MVP)
    stats = await get_player_season_stats("2023-24", player_id=203999, include_awards=True)

    # Verify basic stats exist
    assert stats is not None, "Stats should not be None"
    assert "GP" in stats, "Should have games played"
    assert "PPG" in stats, "Should have PPG"

    # Verify awards fields ARE present
    assert "AWARDS" in stats, "AWARDS should be present with include_awards=True"
    assert "AWARDS_WON" in stats, "AWARDS_WON should be present"
    assert "AWARDS_COUNT" in stats, "AWARDS_COUNT should be present"

    # Verify Jokic won MVP in 2023-24
    assert isinstance(stats["AWARDS"], dict), "AWARDS should be a dictionary"
    assert stats["AWARDS"].get("mvp") == True, "Jokic should have won MVP in 2023-24"

    # Verify awards won list
    assert isinstance(stats["AWARDS_WON"], list), "AWARDS_WON should be a list"
    assert "MVP" in stats["AWARDS_WON"], "MVP should be in AWARDS_WON list"

    # Verify awards count
    assert stats["AWARDS_COUNT"] >= 1, "Should have at least 1 award (MVP)"

    print(f"[OK] Player: {stats.get('PLAYER_NAME', 'Unknown')}")
    print(f"[OK] Season: {stats.get('SEASON_YEAR')}")
    print(f"[OK] GP: {stats.get('GP')}, PPG: {stats.get('PPG'):.1f}")
    print(f"[OK] MVP: {stats['AWARDS']['mvp']}")
    print(f"[OK] Awards Won: {', '.join(stats['AWARDS_WON'])}")
    print(f"[OK] Awards Count: {stats['AWARDS_COUNT']}")


async def test_with_awards_non_mvp():
    """Test that season stats work WITH include_awards for non-MVP winner"""
    print("\n" + "="*60)
    print("TEST 3: With Awards - Non-MVP Winner (LeBron 2023-24)")
    print("="*60)

    # Get LeBron's 2023-24 stats WITH awards (he did NOT win MVP)
    stats = await get_player_season_stats("2023-24", player_id=2544, include_awards=True)

    # Verify basic stats exist
    assert stats is not None, "Stats should not be None"

    # Verify awards fields ARE present
    assert "AWARDS" in stats, "AWARDS should be present with include_awards=True"
    assert "AWARDS_WON" in stats, "AWARDS_WON should be present"
    assert "AWARDS_COUNT" in stats, "AWARDS_COUNT should be present"

    # Verify LeBron did NOT win MVP in 2023-24
    assert stats["AWARDS"].get("mvp") == False, "LeBron should NOT have won MVP in 2023-24"

    print(f"[OK] Player: {stats.get('PLAYER_NAME', 'Unknown')}")
    print(f"[OK] Season: {stats.get('SEASON_YEAR')}")
    print(f"[OK] GP: {stats.get('GP')}, PPG: {stats.get('PPG'):.1f}")
    print(f"[OK] MVP: {stats['AWARDS']['mvp']} (correct - did not win)")
    print(f"[OK] Awards Won: {', '.join(stats['AWARDS_WON']) if stats['AWARDS_WON'] else 'None'}")
    print(f"[OK] Awards Count: {stats['AWARDS_COUNT']}")


async def test_historical_mvp():
    """Test awards enrichment for historical MVP (LeBron 2012-13)"""
    print("\n" + "="*60)
    print("TEST 4: Historical MVP (LeBron 2012-13)")
    print("="*60)

    # Get LeBron's 2012-13 stats WITH awards (he won MVP)
    stats = await get_player_season_stats("2012-13", player_id=2544, include_awards=True)

    # Verify LeBron won MVP in 2012-13
    assert stats["AWARDS"].get("mvp") == True, "LeBron should have won MVP in 2012-13"
    assert "MVP" in stats["AWARDS_WON"], "MVP should be in AWARDS_WON list"

    print(f"[OK] Player: {stats.get('PLAYER_NAME', 'Unknown')}")
    print(f"[OK] Season: {stats.get('SEASON_YEAR')}")
    print(f"[OK] MVP: {stats['AWARDS']['mvp']} (correct - won MVP)")
    print(f"[OK] Awards Won: {', '.join(stats['AWARDS_WON'])}")


async def run_all_tests():
    """Run all awards enrichment tests"""
    print("\n" + "="*60)
    print("RUNNING AWARDS ENRICHMENT TEST SUITE")
    print("="*60)

    tests = [
        ("Backward Compatibility", test_backward_compatibility),
        ("With Awards - MVP Winner", test_with_awards_mvp_winner),
        ("With Awards - Non-MVP", test_with_awards_non_mvp),
        ("Historical MVP", test_historical_mvp),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            await test_func()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {test_name} FAILED: {e}")
            failed += 1
            import traceback
            traceback.print_exc()

    print("\n" + "="*60)
    print(f"TEST SUMMARY: {passed} passed, {failed} failed")
    print("="*60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
