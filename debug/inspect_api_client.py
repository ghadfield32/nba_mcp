"""
Quick inspection script to identify:
1. Available methods in NBAApiClient
2. DataFrame column names
3. Verify correct usage patterns
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.client import NBAApiClient


async def main():
    print("="*80)
    print("NBA API CLIENT INSPECTION")
    print("="*80)

    client = NBAApiClient()

    # 1. List all public methods
    print("\n1. Available Methods in NBAApiClient:")
    print("-" * 80)
    methods = [m for m in dir(client) if not m.startswith('_') and callable(getattr(client, m))]
    for method in sorted(methods):
        print(f"  - {method}()")

    # 2. Check game log DataFrame columns
    print("\n2. Player Game Log Columns:")
    print("-" * 80)
    try:
        game_log = await client.get_player_game_log(
            player_name="LeBron James",
            season="2024-25",
            as_dataframe=True
        )
        print(f"  Total columns: {len(game_log.columns)}")
        print(f"  Columns:")
        for col in sorted(game_log.columns):
            print(f"    - {col}")
    except Exception as e:
        print(f"  Error: {e}")

    # 3. Check if there's a team game log method
    print("\n3. Team-related Methods:")
    print("-" * 80)
    team_methods = [m for m in methods if 'team' in m.lower()]
    if team_methods:
        for method in team_methods:
            print(f"  - {method}()")
    else:
        print("  No team-specific game log method found")
        print("  Available alternatives:")
        for m in methods:
            if 'game' in m.lower() and 'log' in m.lower():
                print(f"    - {m}()")

    # 4. Check for date range methods
    print("\n4. Date Range Methods:")
    print("-" * 80)
    date_methods = [m for m in methods if 'date' in m.lower() or 'range' in m.lower()]
    for method in date_methods:
        print(f"  - {method}()")

    print("\n" + "="*80)
    print("INSPECTION COMPLETE")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
