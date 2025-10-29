"""
Research script to explore NBA Awards API endpoints.

This will help us understand:
1. What awards data is available
2. Data structure and format
3. Historical coverage
4. How to query efficiently
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_api.stats.endpoints import playerawards
from nba_mcp.api.client import NBAApiClient
import pandas as pd


async def explore_player_awards():
    """Explore PlayerAwards endpoint with known MVP winners"""
    print("="*80)
    print("EXPLORING NBA PLAYER AWARDS API")
    print("="*80)

    # Test with recent MVP winners
    test_players = [
        {"name": "Nikola Jokic", "expected": "MVP 2021, 2022, 2024"},
        {"name": "Joel Embiid", "expected": "MVP 2023"},
        {"name": "Giannis Antetokounmpo", "expected": "MVP 2019, 2020"},
        {"name": "LeBron James", "expected": "MVP 2009, 2010, 2012, 2013"},
    ]

    client = NBAApiClient()

    for player_info in test_players:
        print(f"\n{'='*80}")
        print(f"Player: {player_info['name']}")
        print(f"Expected Awards: {player_info['expected']}")
        print(f"{'='*80}")

        try:
            # Resolve player ID
            player = await client.resolve_player_name(player_info['name'])
            player_id = player['id']
            print(f"Player ID: {player_id}")

            # Fetch awards
            awards_response = playerawards.PlayerAwards(player_id=player_id)
            awards_df = awards_response.get_data_frames()[0]

            print(f"\nTotal Awards: {len(awards_df)}")
            print(f"Columns: {awards_df.columns.tolist()}")

            if len(awards_df) > 0:
                print(f"\nAwards Data:")
                print(awards_df.to_string())

                # Check for MVP specifically
                mvp_awards = awards_df[awards_df['DESCRIPTION'].str.contains('Most Valuable Player', na=False, case=False)]
                if len(mvp_awards) > 0:
                    print(f"\nMVP Awards Found: {len(mvp_awards)}")
                    print(mvp_awards[['PERSON_ID', 'DESCRIPTION', 'ALL_NBA_TEAM_NUMBER', 'SEASON', 'MONTH', 'WEEK', 'CONFERENCE', 'TYPE', 'SUBTYPE1', 'SUBTYPE2', 'SUBTYPE3']].to_string())
            else:
                print("No awards found!")

        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()


async def explore_awards_structure():
    """Understand the full structure of awards data"""
    print("\n" + "="*80)
    print("EXPLORING AWARDS DATA STRUCTURE")
    print("="*80)

    # Get LeBron's ID (known to have many awards)
    client = NBAApiClient()
    lebron = await client.resolve_player_name("LeBron James")
    lebron_id = lebron['id']

    print(f"\nFetching all awards for LeBron James (ID: {lebron_id})...")
    awards_response = playerawards.PlayerAwards(player_id=lebron_id)
    awards_df = awards_response.get_data_frames()[0]

    print(f"\nTotal Awards: {len(awards_df)}")
    print(f"\nColumn Data Types:")
    print(awards_df.dtypes)

    print(f"\nUnique Award Types:")
    if 'DESCRIPTION' in awards_df.columns:
        unique_awards = awards_df['DESCRIPTION'].unique()
        for award in sorted(unique_awards):
            count = len(awards_df[awards_df['DESCRIPTION'] == award])
            print(f"  - {award}: {count}x")

    print(f"\nSample Award Records:")
    print(awards_df.head(10).to_string())

    # Check if we can filter by award type
    print(f"\nFiltering for MVP Awards:")
    mvp_awards = awards_df[awards_df['DESCRIPTION'].str.contains('Most Valuable Player', na=False, case=False)]
    print(mvp_awards.to_string())


async def main():
    """Run all exploration tests"""
    await explore_player_awards()
    await explore_awards_structure()

    print("\n" + "="*80)
    print("EXPLORATION COMPLETE")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
