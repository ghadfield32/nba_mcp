"""Quick inspection of league game log columns"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.client import NBAApiClient


async def main():
    client = NBAApiClient()

    # Get league game log
    league_log = await client.get_league_game_log(
        season="2023-24",
        season_type="Regular Season",
        as_dataframe=True
    )

    print("League Game Log Columns:")
    print("=" * 80)
    for col in sorted(league_log.columns):
        print(f"  - {col}")

    print("\nSample row for Warriors:")
    print("=" * 80)
    warriors_rows = league_log[league_log.astype(str).apply(lambda row: 'Warriors' in ' '.join(row.values.astype(str)), axis=1)]
    if len(warriors_rows) > 0:
        print(warriors_rows.iloc[0].to_dict())
    else:
        print("No Warriors rows found")


if __name__ == "__main__":
    asyncio.run(main())
