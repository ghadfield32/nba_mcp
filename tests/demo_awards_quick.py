"""
Quick NBA Awards Demo (Non-Interactive)
Shows key features in automated fashion
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import nba_mcp.nba_server as server


def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'replace').decode('ascii'))


async def quick_demo():
    print("=" * 80)
    print("NBA AWARDS SYSTEM - QUICK DEMO")
    print("=" * 80)

    demos = [
        ("Last 3 MVP Winners", {"award_type": "mvp", "last_n": 3}),
        ("2023-24 Rookie of the Year", {"award_type": "roy", "season": "2023-24"}),
        ("2023-24 All-NBA First Team", {"award_type": "all_nba_first", "season": "2023-24"}),
        ("Last 2 All-Defensive First Teams", {"award_type": "all_defensive_first", "last_n": 2}),
        ("2023-24 All-Rookie First Team", {"award_type": "all_rookie_first", "season": "2023-24"}),
    ]

    for i, (title, params) in enumerate(demos, 1):
        print(f"\n[Demo {i}/{len(demos)}] {title}")
        print("-" * 80)
        result = await server.get_nba_awards(**params)
        safe_print(result)
        print()

    print("=" * 80)
    print("DEMO COMPLETE - All 14 Award Types Available!")
    print("Individual: mvp, finals_mvp, dpoy, roy, smoy, mip, coy")
    print("Teams: all_nba (1st/2nd/3rd), all_defensive (1st/2nd), all_rookie (1st/2nd)")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(quick_demo())
