"""Debug script to check MATCHUP field format"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.client import NBAApiClient


async def check_matchup_format():
    client = NBAApiClient()

    result = await client.get_player_game_log(
        player_name="Giannis Antetokounmpo",
        season="2023-24",
        as_dataframe=True
    )

    if not result.empty:
        print("Sample MATCHUP values:")
        print(result["MATCHUP"].head(10).tolist())
        print("\nUnique MATCHUP patterns:")
        patterns = result["MATCHUP"].str.extract(r'(vs\.|@|vs|at)')[0].unique()
        print(patterns)


if __name__ == "__main__":
    asyncio.run(check_matchup_format())
