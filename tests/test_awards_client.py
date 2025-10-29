"""
Quick test script for NBA Awards client methods.
Tests the three new methods independently before MCP integration.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.client import NBAApiClient


def safe_print(text):
    """Print with ASCII fallback for Windows console"""
    try:
        print(text)
    except UnicodeEncodeError:
        # Fallback to ASCII
        print(text.encode('ascii', 'replace').decode('ascii'))


async def test_client_methods():
    """Test all three awards client methods"""
    print("=" * 80)
    print("TESTING NBA AWARDS CLIENT METHODS")
    print("=" * 80)

    client = NBAApiClient()

    # ═══════════════════════════════════════════════════════════════════════════════
    # Test 1: Load historical awards (static method)
    # ═══════════════════════════════════════════════════════════════════════════════
    print("\n[Test 1] Loading historical awards data...")
    try:
        awards_data = client.load_historical_awards()
        award_types = [k for k in awards_data.keys() if k != 'metadata']
        print(f"[PASS] Loaded {len(award_types)} award types")
        print(f"  Award types: {', '.join(award_types)}")

        # Verify data structure
        assert 'mvp' in awards_data, "MVP data missing"
        assert len(awards_data['mvp']) > 0, "MVP data empty"
        print(f"  MVP winners count: {len(awards_data['mvp'])}")
        safe_print(f"  Latest MVP: {awards_data['mvp'][0]['player_name']} ({awards_data['mvp'][0]['season']})")
    except Exception as e:
        print(f"[FAIL] Test failed: {e}")
        return False

    # ═══════════════════════════════════════════════════════════════════════════════
    # Test 2: Get last N winners
    # ═══════════════════════════════════════════════════════════════════════════════
    print("\n[Test 2] Get last 10 MVP winners...")
    try:
        mvps = client.get_award_winners("mvp", last_n=10)
        print(f"[PASS] Found {len(mvps)} MVP winners")
        for i, mvp in enumerate(mvps[:5], 1):
            safe_print(f"  {i}. {mvp['season']}: {mvp['player_name']} ({mvp['team']})")
        if len(mvps) > 5:
            print(f"  ... and {len(mvps) - 5} more")

        # Verify
        assert len(mvps) == 10, f"Expected 10 MVPs, got {len(mvps)}"
    except Exception as e:
        print(f"[FAIL] FAILED: {e}")
        return False

    # ═══════════════════════════════════════════════════════════════════════════════
    # Test 3: Get season range winners
    # ═══════════════════════════════════════════════════════════════════════════════
    print("\n[Test 3] Get DPOY winners 2018-19 to 2022-23...")
    try:
        dpoy = client.get_award_winners("dpoy", start_season="2018-19", end_season="2022-23")
        print(f"[PASS] Found {len(dpoy)} DPOY winners in range")
        for winner in dpoy:
            safe_print(f"  {winner['season']}: {winner['player_name']} ({winner['team']})")

        # Verify
        assert len(dpoy) == 5, f"Expected 5 DPOY winners, got {len(dpoy)}"
    except Exception as e:
        print(f"[FAIL] FAILED: {e}")
        return False

    # ═══════════════════════════════════════════════════════════════════════════════
    # Test 4: Get specific season winner
    # ═══════════════════════════════════════════════════════════════════════════════
    print("\n[Test 4] Get 2023-24 ROY winner...")
    try:
        roy = client.get_award_winners("roy", last_n=1)
        if roy:
            print(f"[PASS] {roy[0]['season']} Rookie of the Year:")
            safe_print(f"  {roy[0]['player_name']} ({roy[0]['team']})")
            assert roy[0]['player_name'] == "Victor Wembanyama", "Expected Wembanyama as 2023-24 ROY"
    except Exception as e:
        print(f"[FAIL] FAILED: {e}")
        return False

    # ═══════════════════════════════════════════════════════════════════════════════
    # Test 5: Invalid award type error handling
    # ═══════════════════════════════════════════════════════════════════════════════
    print("\n[Test 5] Test invalid award type error handling...")
    try:
        client.get_award_winners("invalid_award")
        print("[FAIL] FAILED: Should have raised ValueError")
        return False
    except ValueError as e:
        print(f"[PASS] Correctly raised ValueError: {str(e)[:60]}...")

    # ═══════════════════════════════════════════════════════════════════════════════
    # Test 6: Get player awards (async, requires API call)
    # ═══════════════════════════════════════════════════════════════════════════════
    print("\n[Test 6] Get LeBron James awards (API call)...")
    try:
        lebron_awards = await client.get_player_awards("LeBron James")
        print(f"[PASS] Found {len(lebron_awards)} total awards for LeBron")

        # Count MVPs
        mvps = lebron_awards[
            lebron_awards['DESCRIPTION'].str.contains('Most Valuable Player', na=False, case=False)
        ]
        print(f"  MVP Awards: {len(mvps)}")

        if len(mvps) > 0:
            mvp_seasons = mvps['SEASON'].tolist()
            print(f"  MVP Seasons: {', '.join(mvp_seasons)}")
            # LeBron has 4 MVPs: 2009, 2010, 2012, 2013
            assert len(mvps) >= 4, f"Expected at least 4 MVP awards, got {len(mvps)}"

    except Exception as e:
        print(f"[FAIL] FAILED: {e}")
        print("  Note: This test requires internet connection and NBA API access")
        return False

    # ═══════════════════════════════════════════════════════════════════════════════
    # Test 7: Player awards with filter
    # ═══════════════════════════════════════════════════════════════════════════════
    print("\n[Test 7] Get Stephen Curry MVP awards with filter...")
    try:
        curry_mvps = await client.get_player_awards("Stephen Curry", award_filter="Most Valuable Player")
        print(f"[PASS] Found {len(curry_mvps)} MVP awards for Curry")

        if len(curry_mvps) > 0:
            seasons = curry_mvps['SEASON'].tolist()
            print(f"  Seasons: {', '.join(seasons)}")
            # Curry has 2 MVPs: 2015, 2016
            assert len(curry_mvps) >= 2, f"Expected at least 2 MVP awards, got {len(curry_mvps)}"

    except Exception as e:
        print(f"[FAIL] FAILED: {e}")
        print("  Note: This test requires internet connection and NBA API access")
        return False

    print("\n" + "=" * 80)
    print("ALL CLIENT METHOD TESTS PASSED [PASS]")
    print("=" * 80)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_client_methods())
    sys.exit(0 if success else 1)
