"""
Comprehensive Test Suite for Name Variations

Tests all team variations, player nicknames, and alternate spellings
to ensure maximum coverage and ease of use.
"""

import asyncio
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.entity_resolver import resolve_team, resolve_player
from nba_mcp.api.name_variations import get_variations_stats


def remove_diacritics(text: str) -> str:
    """Remove diacritical marks from Unicode text for comparison"""
    # Normalize to NFD (decomposed form) and remove combining characters
    nfd = unicodedata.normalize('NFD', text)
    return ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')


async def test_team_variations():
    """Test comprehensive team name variations"""
    print("\n" + "="*80)
    print("TEST 1: Team Name Variations")
    print("="*80)

    test_cases = [
        # Golden State Warriors
        ("Dubs", "Golden State Warriors", "GSW"),
        ("Warriors", "Golden State Warriors", "GSW"),
        ("Golden State", "Golden State Warriors", "GSW"),
        ("GSW", "Golden State Warriors", "GSW"),

        # Los Angeles Lakers
        ("Lakers", "Los Angeles Lakers", "LAL"),
        ("LAL", "Los Angeles Lakers", "LAL"),
        ("Lake Show", "Los Angeles Lakers", "LAL"),
        ("LakeShow", "Los Angeles Lakers", "LAL"),

        # LA Clippers
        ("Clippers", "LA Clippers", "LAC"),
        ("Clips", "LA Clippers", "LAC"),
        ("LAC", "LA Clippers", "LAC"),

        # Philadelphia 76ers
        ("Sixers", "Philadelphia 76ers", "PHI"),
        ("76ers", "Philadelphia 76ers", "PHI"),
        ("PHI", "Philadelphia 76ers", "PHI"),
        ("Philly", "Philadelphia 76ers", "PHI"),

        # Dallas Mavericks
        ("Mavs", "Dallas Mavericks", "DAL"),
        ("Mavericks", "Dallas Mavericks", "DAL"),
        ("DAL", "Dallas Mavericks", "DAL"),

        # Portland Trail Blazers
        ("Blazers", "Portland Trail Blazers", "POR"),
        ("Trail Blazers", "Portland Trail Blazers", "POR"),
        ("Rip City", "Portland Trail Blazers", "POR"),

        # Memphis Grizzlies
        ("Grizz", "Memphis Grizzlies", "MEM"),
        ("Grizzlies", "Memphis Grizzlies", "MEM"),

        # Boston Celtics
        ("Celtics", "Boston Celtics", "BOS"),
        ("Celts", "Boston Celtics", "BOS"),
        ("C's", "Boston Celtics", "BOS"),

        # New Orleans Pelicans
        ("Pels", "New Orleans Pelicans", "NOP"),
        ("Pelicans", "New Orleans Pelicans", "NOP"),

        # Minnesota Timberwolves
        ("Wolves", "Minnesota Timberwolves", "MIN"),
        ("TWolves", "Minnesota Timberwolves", "MIN"),
        ("Timberwolves", "Minnesota Timberwolves", "MIN"),

        # Historical teams
        ("Sonics", "Oklahoma City Thunder", "OKC"),  # Seattle SuperSonics
        ("Seattle", "Oklahoma City Thunder", "OKC"),
        ("Bobcats", "Charlotte Hornets", "CHA"),  # Charlotte Bobcats
        ("Bullets", "Washington Wizards", "WAS"),  # Washington Bullets
    ]

    passed = 0
    failed = 0

    for query, expected_name, expected_abbrev in test_cases:
        try:
            result = resolve_team(query, min_confidence=0.6)
            if result and result.abbreviation == expected_abbrev:
                print(f"[OK] '{query}' -> {result.abbreviation} ({result.name})")
                passed += 1
            else:
                print(f"[FAIL] '{query}' expected {expected_abbrev}, got {result.abbreviation if result else 'None'}")
                failed += 1
        except Exception as e:
            print(f"[FAIL] '{query}' raised error: {e}")
            failed += 1

    print(f"\nTeam Variations: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    return passed, failed


async def test_player_nicknames():
    """Test player nickname resolution"""
    print("\n" + "="*80)
    print("TEST 2: Player Nicknames")
    print("="*80)

    test_cases = [
        # Active stars
        ("King James", "LeBron James"),
        ("The King", "LeBron James"),
        ("Greek Freak", "Giannis Antetokounmpo"),
        ("The Beard", "James Harden"),
        ("The Process", "Joel Embiid"),
        ("The Joker", "Nikola Jokic"),
        ("Dame", "Damian Lillard"),
        ("Steph", "Stephen Curry"),
        ("Chef Curry", "Stephen Curry"),
        ("KD", "Kevin Durant"),
        ("The Slim Reaper", "Kevin Durant"),
        ("AD", "Anthony Davis"),
        ("The Brow", "Anthony Davis"),
        ("CP3", "Chris Paul"),
        ("Luka", "Luka Doncic"),
        ("Spida", "Donovan Mitchell"),

        # Legends
        ("Mamba", "Kobe Bryant"),
        ("Shaq", "Shaquille O'Neal"),
        ("MJ", "Michael Jordan"),
        ("Air Jordan", "Michael Jordan"),
        ("Magic", "Magic Johnson"),
        ("The Dream", "Hakeem Olajuwon"),
        ("The Admiral", "David Robinson"),
    ]

    passed = 0
    failed = 0

    for nickname, expected_name in test_cases:
        try:
            result = resolve_player(nickname, min_confidence=0.6)
            # Remove diacritics for comparison (č → c, ć → c, etc.)
            result_name_normalized = remove_diacritics(result.name).lower() if result else ''
            expected_name_normalized = remove_diacritics(expected_name).lower()

            if result and result_name_normalized == expected_name_normalized:
                # Use ASCII-safe printing for Windows console
                try:
                    print(f"[OK] '{nickname}' -> {result.name}")
                except UnicodeEncodeError:
                    print(f"[OK] '{nickname}' -> {result.name.encode('ascii', errors='replace').decode('ascii')}")
                passed += 1
            else:
                result_name = result.name if result else 'None'
                try:
                    print(f"[FAIL] '{nickname}' expected '{expected_name}', got '{result_name}'")
                except UnicodeEncodeError:
                    print(f"[FAIL] '{nickname}' expected '{expected_name}', got '{result_name.encode('ascii', errors='replace').decode('ascii') if result else 'None'}'")
                failed += 1
        except Exception as e:
            print(f"[FAIL] '{nickname}' raised error: {e}")
            failed += 1

    print(f"\nPlayer Nicknames: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    return passed, failed


async def test_alternate_spellings():
    """Test alternate spellings for international names"""
    print("\n" + "="*80)
    print("TEST 3: Alternate Spellings (International Names)")
    print("="*80)

    test_cases = [
        ("Luka Doncic", "Luka"),  # ASCII version
        ("Nikola Jokic", "Nikola Jokic"),  # ASCII version
        ("Bogdan Bogdanovic", "Bogdan Bogdanovic"),
        ("Bojan Bogdanovic", "Bojan Bogdanovic"),
        ("Nikola Vucevic", "Nikola Vucevic"),
    ]

    passed = 0
    failed = 0

    for query, expected_partial in test_cases:
        try:
            result = resolve_player(query, min_confidence=0.6)
            # Remove diacritics for comparison (č → c, ć → c, etc.)
            result_name_normalized = remove_diacritics(result.name).lower() if result else ''
            expected_partial_normalized = remove_diacritics(expected_partial).lower()

            if result and expected_partial_normalized in result_name_normalized:
                # Use ASCII-safe printing for Windows console
                try:
                    print(f"[OK] '{query}' -> {result.name}")
                except UnicodeEncodeError:
                    print(f"[OK] '{query}' -> {result.name.encode('ascii', errors='replace').decode('ascii')}")
                passed += 1
            else:
                result_name = result.name if result else 'None'
                try:
                    print(f"[FAIL] '{query}' expected name containing '{expected_partial}', got '{result_name}'")
                except UnicodeEncodeError:
                    print(f"[FAIL] '{query}' expected name containing '{expected_partial}', got '{result_name.encode('ascii', errors='replace').decode('ascii') if result else 'None'}'")
                failed += 1
        except Exception as e:
            print(f"[FAIL] '{query}' raised error: {e}")
            failed += 1

    print(f"\nAlternate Spellings: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    return passed, failed


async def test_backward_compatibility():
    """Test that original queries still work"""
    print("\n" + "="*80)
    print("TEST 4: Backward Compatibility")
    print("="*80)

    test_cases = [
        # Teams - original queries should still work
        ("Los Angeles Lakers", "LAL"),
        ("Boston Celtics", "BOS"),
        ("LAL", "LAL"),
        ("BOS", "BOS"),

        # Players - original queries should still work
        ("LeBron James", "LeBron James"),
        ("Stephen Curry", "Stephen Curry"),
        ("Giannis Antetokounmpo", "Giannis Antetokounmpo"),
    ]

    passed = 0
    failed = 0

    for query, expected in test_cases:
        try:
            # Try team first
            result = resolve_team(query, min_confidence=0.6)
            if result and result.abbreviation == expected:
                print(f"[OK] Team: '{query}' -> {result.abbreviation}")
                passed += 1
                continue

            # Try player
            result = resolve_player(query, min_confidence=0.6)
            if result and result.name == expected:
                print(f"[OK] Player: '{query}' -> {result.name}")
                passed += 1
                continue

            print(f"[FAIL] '{query}' expected '{expected}', got '{result.name if result else 'None'}'")
            failed += 1
        except Exception as e:
            print(f"[FAIL] '{query}' raised error: {e}")
            failed += 1

    print(f"\nBackward Compatibility: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    return passed, failed


async def test_coverage_stats():
    """Display coverage statistics"""
    print("\n" + "="*80)
    print("COVERAGE STATISTICS")
    print("="*80)

    stats = get_variations_stats()
    print(f"Total team variations: {stats['total_team_variations']}")
    print(f"Unique teams covered: {stats['unique_teams_covered']}/30")
    print(f"Total player nicknames: {stats['total_player_nicknames']}")
    print(f"Total alternate spellings: {stats['total_alternate_spellings']}")
    print()


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("COMPREHENSIVE NAME VARIATIONS TEST SUITE")
    print("="*80)

    try:
        # Run all tests
        team_passed, team_failed = await test_team_variations()
        player_passed, player_failed = await test_player_nicknames()
        spelling_passed, spelling_failed = await test_alternate_spellings()
        compat_passed, compat_failed = await test_backward_compatibility()

        # Summary
        total_passed = team_passed + player_passed + spelling_passed + compat_passed
        total_failed = team_failed + player_failed + spelling_failed + compat_failed
        total_tests = total_passed + total_failed

        print("\n" + "="*80)
        print("FINAL SUMMARY")
        print("="*80)
        print(f"Total tests: {total_tests}")
        print(f"Passed: {total_passed} ({100*total_passed//total_tests if total_tests > 0 else 0}%)")
        print(f"Failed: {total_failed}")
        print("="*80)

        # Coverage stats
        await test_coverage_stats()

        if total_failed == 0:
            print("\n[OK] ALL TESTS PASSED!")
            print("Name variation system is comprehensive and working correctly.")
        else:
            print(f"\n[WARNING] {total_failed} tests failed - review output above")

        return total_failed == 0

    except Exception as e:
        print(f"\n[FAIL] TEST SUITE FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
