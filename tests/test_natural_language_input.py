"""
Test Natural Language Input Support

Tests the new flexible input system that accepts both IDs and names
for players and teams.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.utils.entity_utils import (
    resolve_player_input,
    resolve_team_input,
    resolve_flexible_input
)


async def test_player_resolution():
    """Test player name and ID resolution"""
    print("\n" + "="*80)
    print("TEST 1: Player Resolution")
    print("="*80)

    # Test ID pass-through
    player_id = resolve_player_input(2544)
    assert player_id == 2544, f"ID pass-through failed: expected 2544, got {player_id}"
    print(f"[OK] ID pass-through: 2544 -> {player_id}")

    # Test name resolution
    player_id = resolve_player_input("LeBron James")
    assert player_id == 2544, f"Name resolution failed: expected 2544, got {player_id}"
    print(f"[OK] Name resolution: 'LeBron James' -> {player_id}")

    # Test partial name
    player_id = resolve_player_input("LeBron")
    assert player_id == 2544, f"Partial name failed: expected 2544, got {player_id}"
    print(f"[OK] Partial name: 'LeBron' -> {player_id}")

    # Test None
    player_id = resolve_player_input(None)
    assert player_id is None, f"None handling failed: expected None, got {player_id}"
    print(f"[OK] None handling: None -> {player_id}")

    print("\n[OK] All player resolution tests passed!")


async def test_team_resolution():
    """Test team name, abbreviation, and ID resolution"""
    print("\n" + "="*80)
    print("TEST 2: Team Resolution")
    print("="*80)

    # Test ID pass-through
    team_id = resolve_team_input(1610612747)
    assert team_id == 1610612747, f"ID pass-through failed"
    print(f"[OK] ID pass-through: 1610612747 -> {team_id}")

    # Test full name
    team_id = resolve_team_input("Los Angeles Lakers")
    assert team_id == 1610612747, f"Full name resolution failed"
    print(f"[OK] Full name: 'Los Angeles Lakers' -> {team_id}")

    # Test abbreviation
    team_id = resolve_team_input("LAL")
    assert team_id == 1610612747, f"Abbreviation resolution failed"
    print(f"[OK] Abbreviation: 'LAL' -> {team_id}")

    # Test partial name
    team_id = resolve_team_input("Lakers")
    assert team_id == 1610612747, f"Partial name resolution failed"
    print(f"[OK] Partial name: 'Lakers' -> {team_id}")

    # Test None
    team_id = resolve_team_input(None)
    assert team_id is None, f"None handling failed"
    print(f"[OK] None handling: None -> {team_id}")

    print("\n[OK] All team resolution tests passed!")


async def test_error_handling():
    """Test error handling for invalid inputs"""
    print("\n" + "="*80)
    print("TEST 3: Error Handling")
    print("="*80)

    # Test invalid player name
    try:
        resolve_player_input("NonexistentPlayer12345")
        print("[FAIL] Should have raised ValueError for invalid player")
        assert False
    except ValueError as e:
        print(f"[OK] Invalid player raises ValueError: {str(e)[:50]}...")

    # Test invalid team name
    try:
        resolve_team_input("NonexistentTeam12345")
        print("[FAIL] Should have raised ValueError for invalid team")
        assert False
    except ValueError as e:
        print(f"[OK] Invalid team raises ValueError: {str(e)[:50]}...")

    # Test invalid type
    try:
        resolve_flexible_input({"invalid": "dict"}, "player", "test")
        print("[FAIL] Should have raised TypeError for invalid type")
        assert False
    except TypeError as e:
        print(f"[OK] Invalid type raises TypeError: {str(e)[:50]}...")

    print("\n[OK] All error handling tests passed!")


async def test_caching():
    """Test that repeated lookups are cached"""
    print("\n" + "="*80)
    print("TEST 4: Caching Performance")
    print("="*80)

    import time

    # First lookup (uncached)
    start = time.time()
    for _ in range(100):
        resolve_player_input("LeBron James")
    time_uncached = time.time() - start

    # Second lookup (cached)
    start = time.time()
    for _ in range(100):
        resolve_player_input("LeBron James")
    time_cached = time.time() - start

    print(f"[OK] 100 lookups (uncached): {time_uncached:.4f}s")
    print(f"[OK] 100 lookups (cached): {time_cached:.4f}s")
    print(f"[OK] Speedup: {time_uncached/time_cached:.1f}x faster with caching")

    # Caching should be significantly faster
    assert time_cached < time_uncached, "Caching should improve performance"
    print("\n[OK] Caching working correctly!")


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("NATURAL LANGUAGE INPUT TEST SUITE")
    print("Testing Flexible Player/Team Input Resolution")
    print("="*80)

    try:
        await test_player_resolution()
        await test_team_resolution()
        await test_error_handling()
        await test_caching()

        print("\n" + "="*80)
        print("ALL TESTS PASSED [OK]")
        print("="*80)
        print("\nNatural language input system working correctly!")
        print("  - Player names: 'LeBron James' -> ID 2544")
        print("  - Team names: 'Lakers' or 'LAL' -> ID 1610612747")
        print("  - IDs: Pass-through for backward compatibility")
        print("  - Caching: LRU cache for fast repeated lookups")
        print("="*80)

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
