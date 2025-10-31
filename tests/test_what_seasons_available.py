"""
Quick test to determine what seasons are currently available in NBA CDN
"""

import asyncio
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.schedule import fetch_nba_schedule_raw, parse_schedule_to_dataframe


async def main():
    print("Fetching all schedule data from NBA CDN...")
    print("=" * 80)

    raw_data = fetch_nba_schedule_raw()
    df = parse_schedule_to_dataframe(raw_data)

    print(f"\nTotal games in NBA CDN: {len(df)}")

    if len(df) > 0:
        # Check what columns we have
        print(f"\nColumns: {', '.join(df.columns.tolist())}")

        # Check season_year values
        print(f"\nSeason year values (unique): {df['season_year'].unique().tolist()}")
        print(f"  Null count: {df['season_year'].isnull().sum()}")

        # Group by season (filter out nulls)
        df_with_season = df[df['season_year'].notnull()]

        if len(df_with_season) > 0:
            season_counts = df_with_season.groupby('season_year').size()
            print(f"\nGames by season year ({len(df_with_season)} games with season_year):")
            for season_year in sorted(season_counts.index):
                count = season_counts[season_year]
                season_str = f"{int(season_year)-1}-{str(int(season_year))[2:]}"
                print(f"  {season_str}: {count} games")
        else:
            print(f"\nNo games have season_year populated")

        # Group by season and stage (if season_year is populated)
        stage_map = {1: "Preseason", 2: "Regular", 4: "Playoffs"}

        if len(df_with_season) > 0:
            print(f"\nGames by season and stage:")

            for season_year in sorted(df_with_season['season_year'].unique()):
                season_str = f"{int(season_year)-1}-{str(int(season_year))[2:]}"
                season_df = df_with_season[df_with_season['season_year'] == season_year]

                print(f"\n  {season_str}:")
                for stage_id in sorted(season_df['season_stage_id'].unique()):
                    stage_name = stage_map.get(stage_id, f"Stage {stage_id}")
                    count = len(season_df[season_df['season_stage_id'] == stage_id])
                    print(f"    - {stage_name}: {count} games")

        # Show date range
        print(f"\nDate range:")
        print(f"  Earliest game: {df['game_date_local'].min()}")
        print(f"  Latest game: {df['game_date_local'].max()}")

        # Show sample game
        print(f"\nSample game (first in dataset):")
        sample = df.iloc[0]
        print(f"  Date: {sample['game_date_local']}")
        print(f"  Matchup: {sample['away_abbr']} @ {sample['home_abbr']}")
        print(f"  Arena: {sample['arena']}")
        print(f"  Status: {sample['game_status']}")

        if pd.notnull(sample['season_year']):
            print(f"  Season: {int(sample['season_year'])-1}-{str(int(sample['season_year']))[2:]}")
        else:
            print(f"  Season: Unknown (season_year is null)")

        print(f"  Stage ID: {sample['season_stage_id']}")
        print(f"  Stage: {stage_map.get(sample['season_stage_id'], f"Unknown stage {sample['season_stage_id']}")}")

    else:
        print("\n[INFO] No games found in NBA CDN")
        print("This is expected if schedules haven't been published yet.")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
