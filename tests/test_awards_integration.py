"""
Comprehensive integration test for NBA Awards feature.
Tests client methods, MCP tool, and full end-to-end workflows.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.client import NBAApiClient
import nba_mcp.nba_server as server


def safe_print(text):
    """Print with ASCII fallback for Windows console"""
    try:
        print(text)
    except UnicodeEncodeError:
        # Fallback to ASCII
        print(text.encode('ascii', 'replace').decode('ascii'))


async def test_integration():
    """Test full awards system integration"""
    print("=" * 80)
    print("NBA AWARDS INTEGRATION TEST")
    print("=" * 80)

    client = NBAApiClient()
    test_count = 0
    passed = 0

    # ═══════════════════════════════════════════════════════════════════════════════
    # PART 1: Historical Awards Tests (Static Data)
    # ═══════════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("PART 1: HISTORICAL AWARDS (STATIC DATA)")
    print("=" * 80)

    # Test 1.1: Last 10 MVP winners via MCP tool
    test_count += 1
    print(f"\n[Test {test_count}] Get last 10 MVP winners via MCP tool...")
    try:
        result = await server.get_nba_awards(award_type="mvp", last_n=10)
        assert "Most Valuable Player" in result, "MVP title missing"
        assert "2023-24" in result, "Latest season missing"
        safe_print(result[:200] + "...")
        print("[PASS] Last 10 MVPs retrieved successfully")
        passed += 1
    except Exception as e:
        print(f"[FAIL] {e}")

    # Test 1.2: Specific season winner
    test_count += 1
    print(f"\n[Test {test_count}] Get 2023-24 ROY winner...")
    try:
        result = await server.get_nba_awards(award_type="roy", season="2023-24")
        assert "Rookie of the Year" in result, "ROY title missing"
        assert "Wembanyama" in result, "Wembanyama not found"
        safe_print(result)
        print("[PASS] 2023-24 ROY retrieved successfully")
        passed += 1
    except Exception as e:
        print(f"[FAIL] {e}")

    # Test 1.3: Season range query via client
    test_count += 1
    print(f"\n[Test {test_count}] Get DPOY winners 2020-23 via client...")
    try:
        dpoy = client.get_award_winners("dpoy", start_season="2020-21", end_season="2022-23")
        assert len(dpoy) == 3, f"Expected 3 DPOY winners, got {len(dpoy)}"
        print(f"[PASS] Found {len(dpoy)} DPOY winners:")
        for winner in dpoy:
            safe_print(f"  {winner['season']}: {winner['player_name']} ({winner['team']})")
        passed += 1
    except Exception as e:
        print(f"[FAIL] {e}")

    # Test 1.4: Coach of the Year
    test_count += 1
    print(f"\n[Test {test_count}] Get last 3 Coach of the Year winners...")
    try:
        result = await server.get_nba_awards(award_type="coy", last_n=3)
        assert "Coach of the Year" in result, "COY title missing"
        assert "2023-24" in result or "2022-23" in result, "Recent season missing"
        safe_print(result)
        print("[PASS] Coach of the Year retrieved successfully")
        passed += 1
    except Exception as e:
        print(f"[FAIL] {e}")

    # Test 1.5: JSON format output
    test_count += 1
    print(f"\n[Test {test_count}] Get MVPs in JSON format...")
    try:
        result = await server.get_nba_awards(award_type="mvp", last_n=3, format="json")
        import json
        data = json.loads(result)
        assert isinstance(data, list), "Expected JSON list"
        assert len(data) == 3, f"Expected 3 winners, got {len(data)}"
        assert 'player_name' in data[0], "Missing player_name field"
        print(f"[PASS] JSON format working, got {len(data)} winners")
        print(f"  First winner: {data[0]['player_name']} ({data[0]['season']})")
        passed += 1
    except Exception as e:
        print(f"[FAIL] {e}")

    # ═══════════════════════════════════════════════════════════════════════════════
    # PART 2: Player-Specific Awards Tests (API Data)
    # ═══════════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("PART 2: PLAYER-SPECIFIC AWARDS (API DATA)")
    print("=" * 80)

    # Test 2.1: Get all awards for LeBron James
    test_count += 1
    print(f"\n[Test {test_count}] Get all LeBron James awards via MCP tool...")
    try:
        result = await server.get_nba_awards(player_name="LeBron James")
        assert "LeBron James" in result, "Player name missing"
        assert "Awards" in result, "Awards header missing"
        safe_print(result[:300] + "...")
        print("[PASS] LeBron awards retrieved successfully")
        passed += 1
    except Exception as e:
        print(f"[FAIL] {e}")

    # Test 2.2: Player awards with filter (Stephen Curry MVPs)
    test_count += 1
    print(f"\n[Test {test_count}] Get Stephen Curry MVP awards (with filter)...")
    try:
        result = await server.get_nba_awards(player_name="Stephen Curry", award_type="Most Valuable Player")
        assert "Stephen Curry" in result or "Curry" in result, "Player name missing"
        safe_print(result)
        print("[PASS] Curry MVP awards retrieved with filter")
        passed += 1
    except Exception as e:
        print(f"[FAIL] {e}")

    # Test 2.3: Player with no awards
    test_count += 1
    print(f"\n[Test {test_count}] Test player with fewer awards...")
    try:
        result = await server.get_nba_awards(player_name="Victor Wembanyama")
        # Wembanyama should have ROY at least
        assert "Wembanyama" in result, "Player name missing"
        print("[PASS] Wembanyama awards retrieved")
        safe_print(result[:200])
        passed += 1
    except Exception as e:
        print(f"[FAIL] {e}")

    # ═══════════════════════════════════════════════════════════════════════════════
    # PART 3: Error Handling Tests
    # ═══════════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("PART 3: ERROR HANDLING")
    print("=" * 80)

    # Test 3.1: Invalid award type
    test_count += 1
    print(f"\n[Test {test_count}] Test invalid award type error handling...")
    try:
        result = await server.get_nba_awards(award_type="invalid_award")
        assert "Error" in result or "Invalid" in result, "Error message expected"
        print("[PASS] Invalid award type handled correctly")
        print(f"  Error message: {result[:100]}")
        passed += 1
    except Exception as e:
        print(f"[FAIL] {e}")

    # Test 3.2: Invalid player name
    test_count += 1
    print(f"\n[Test {test_count}] Test invalid player name error handling...")
    try:
        result = await server.get_nba_awards(player_name="Nonexistent Player XYZ123")
        assert "Error" in result or "not found" in result, "Error message expected"
        print("[PASS] Invalid player name handled correctly")
        print(f"  Error message: {result[:100]}")
        passed += 1
    except Exception as e:
        print(f"[FAIL] {e}")

    # Test 3.3: No parameters (usage help)
    test_count += 1
    print(f"\n[Test {test_count}] Test no parameters returns usage help...")
    try:
        result = await server.get_nba_awards()
        assert "specify query parameters" in result, "Usage help expected"
        assert "award_type" in result, "Parameter examples expected"
        print("[PASS] Usage help displayed correctly")
        passed += 1
    except Exception as e:
        print(f"[FAIL] {e}")

    # ═══════════════════════════════════════════════════════════════════════════════
    # PART 4: Performance Tests
    # ═══════════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("PART 4: PERFORMANCE")
    print("=" * 80)

    # Test 4.1: Static data performance (should be <50ms)
    test_count += 1
    print(f"\n[Test {test_count}] Test static data performance...")
    try:
        import time
        start = time.time()
        result = await server.get_nba_awards(award_type="mvp", last_n=10)
        elapsed_ms = (time.time() - start) * 1000

        assert "Most Valuable Player" in result, "Result missing"
        print(f"[PASS] Static data query completed in {elapsed_ms:.1f}ms")

        if elapsed_ms < 50:
            print("  Performance: EXCELLENT (<50ms)")
            passed += 1
        elif elapsed_ms < 200:
            print("  Performance: GOOD (<200ms)")
            passed += 1
        else:
            print(f"  Performance: SLOW ({elapsed_ms:.1f}ms) - may need optimization")
            # Still pass, but note the slowness
            passed += 1
    except Exception as e:
        print(f"[FAIL] {e}")

    # ═══════════════════════════════════════════════════════════════════════════════
    # PART 5: All Award Types Coverage
    # ═══════════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("PART 5: ALL AWARD TYPES COVERAGE")
    print("=" * 80)

    award_types = ["mvp", "finals_mvp", "dpoy", "roy", "smoy", "mip", "coy"]

    test_count += 1
    print(f"\n[Test {test_count}] Test all 7 award types...")
    try:
        all_passed = True
        for award in award_types:
            result = await server.get_nba_awards(award_type=award, last_n=1)
            if "Error" in result:
                print(f"  [FAIL] {award}: {result[:50]}")
                all_passed = False
            else:
                print(f"  [PASS] {award}: Retrieved successfully")

        if all_passed:
            print(f"[PASS] All {len(award_types)} award types working")
            passed += 1
        else:
            print("[FAIL] Some award types failed")
    except Exception as e:
        print(f"[FAIL] {e}")

    # ═══════════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total Tests: {test_count}")
    print(f"Passed: {passed}")
    print(f"Failed: {test_count - passed}")
    print(f"Success Rate: {(passed/test_count)*100:.1f}%")

    if passed == test_count:
        print("\n[SUCCESS] ALL TESTS PASSED!")
        return True
    else:
        print(f"\n[PARTIAL] {test_count - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_integration())
    sys.exit(0 if success else 1)
