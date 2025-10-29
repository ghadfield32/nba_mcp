"""
Simplified awards API exploration with hardcoded player IDs.
"""

from nba_api.stats.endpoints import playerawards
import pandas as pd

# Known player IDs
LEBRON_ID = 2544
JOKIC_ID = 203999
EMBIID_ID = 203954
GIANNIS_ID = 203507

print("="*80)
print("NBA PLAYER AWARDS API EXPLORATION")
print("="*80)

# Test with LeBron (known to have many awards)
print(f"\nFetching awards for LeBron James (ID: {LEBRON_ID})...")
try:
    awards_response = playerawards.PlayerAwards(player_id=LEBRON_ID)
    awards_df = awards_response.get_data_frames()[0]

    print(f"Total Awards: {len(awards_df)}")
    print(f"\nColumns: {list(awards_df.columns)}")
    print(f"\nDataTypes:\n{awards_df.dtypes}")

    print(f"\nFirst 5 awards:")
    print(awards_df.head().to_string())

    print(f"\nUnique Award Types:")
    if 'DESCRIPTION' in awards_df.columns:
        unique_awards = awards_df['DESCRIPTION'].value_counts()
        print(unique_awards)

    print(f"\nMVP Awards Only:")
    mvp_awards = awards_df[awards_df['DESCRIPTION'].str.contains('Most Valuable Player', na=False, case=False)]
    if len(mvp_awards) > 0:
        print(mvp_awards.to_string())
    else:
        print("No MVP awards found (check filter)")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
print("EXPLORATION COMPLETE")
print("="*80)
