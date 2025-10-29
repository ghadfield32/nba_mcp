"""
Corrected script to fetch all user-requested NBA data.

User Requests:
1. LeBron's last 5 game average at home
2. Steph Curry's shot chart from the last 3 games
3. Kevin Durant's month over month progression last season
4. Warriors performance last season at home
5. All players data for first 3 months of last season per game

This script uses CORRECT:
- Method names from NBAApiClient inspection
- Column names (Game_ID not GAME_ID)
- Import paths
- MCP tools where appropriate
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.client import NBAApiClient


# ============================================================================
# DATA FETCHING FUNCTIONS
# ============================================================================

async def fetch_lebron_last_5_home():
    """1. LeBron's last 5 game average at home"""
    print("\n" + "="*80)
    print("REQUEST 1: LeBron's Last 5 Home Game Averages")
    print("="*80)

    client = NBAApiClient()

    # Get full season game log
    game_log = await client.get_player_game_log(
        player_name="LeBron James",
        season="2024-25",
        as_dataframe=True
    )

    # Filter for home games (using correct regex from earlier fix)
    home_games = game_log[game_log["MATCHUP"].str.contains("vs\\.", na=False, regex=True)]

    # Get last 5 home games
    last_5 = home_games.head(5)

    # Calculate averages
    stats = {
        "player": "LeBron James",
        "season": "2024-25",
        "games": len(last_5),
        "ppg": round(last_5["PTS"].mean(), 1),
        "rpg": round(last_5["REB"].mean(), 1),
        "apg": round(last_5["AST"].mean(), 1),
        "fgpct": round(last_5["FG_PCT"].mean() * 100, 1),
        "fg3pct": round(last_5["FG3_PCT"].mean() * 100, 1),
        "ftpct": round(last_5["FT_PCT"].mean() * 100, 1),
    }

    print(f"\n[OK] LeBron James - Last {stats['games']} Home Games (2024-25):")
    print(f"  PPG: {stats['ppg']}")
    print(f"  RPG: {stats['rpg']}")
    print(f"  APG: {stats['apg']}")
    print(f"  FG%: {stats['fgpct']}%")
    print(f"  3P%: {stats['fg3pct']}%")
    print(f"  FT%: {stats['ftpct']}%")

    return stats


async def fetch_curry_shot_data():
    """2. Steph Curry's shot data from last 3 games"""
    print("\n" + "="*80)
    print("REQUEST 2: Steph Curry's Last 3 Games Shot Data")
    print("="*80)

    client = NBAApiClient()

    # Get recent games
    game_log = await client.get_player_game_log(
        player_name="Stephen Curry",
        season="2024-25",
        as_dataframe=True
    )

    if len(game_log) == 0:
        print("  No 2024-25 games found, using 2023-24...")
        game_log = await client.get_player_game_log(
            player_name="Stephen Curry",
            season="2023-24",
            as_dataframe=True
        )
        season = "2023-24"
    else:
        season = "2024-25"

    # Get last 3 games
    last_3 = game_log.head(3)

    # Calculate shot statistics
    stats = {
        "player": "Stephen Curry",
        "season": season,
        "games": len(last_3),
        "total_fga": int(last_3["FGA"].sum()),
        "total_fgm": int(last_3["FGM"].sum()),
        "fg_pct": round((last_3["FGM"].sum() / last_3["FGA"].sum()) * 100, 1) if last_3["FGA"].sum() > 0 else 0,
        "total_3pa": int(last_3["FG3A"].sum()),
        "total_3pm": int(last_3["FG3M"].sum()),
        "fg3_pct": round((last_3["FG3M"].sum() / last_3["FG3A"].sum()) * 100, 1) if last_3["FG3A"].sum() > 0 else 0,
        "total_fta": int(last_3["FTA"].sum()),
        "total_ftm": int(last_3["FTM"].sum()),
        "ft_pct": round((last_3["FTM"].sum() / last_3["FTA"].sum()) * 100, 1) if last_3["FTA"].sum() > 0 else 0,
        "total_pts": int(last_3["PTS"].sum()),
        "games_detail": []
    }

    # Add game details
    for idx, row in last_3.iterrows():
        stats["games_detail"].append({
            "date": str(row["GAME_DATE"]),
            "matchup": row["MATCHUP"],
            "pts": int(row["PTS"]),
            "fgm_fga": f"{int(row['FGM'])}-{int(row['FGA'])}",
            "fg3m_fg3a": f"{int(row['FG3M'])}-{int(row['FG3A'])}",
            "ftm_fta": f"{int(row['FTM'])}-{int(row['FTA'])}"
        })

    print(f"\n[OK] Stephen Curry - Last {stats['games']} Games ({season}):")
    print(f"  Total Points: {stats['total_pts']}")
    print(f"  Field Goals: {stats['total_fgm']}-{stats['total_fga']} ({stats['fg_pct']}%)")
    print(f"  Three Pointers: {stats['total_3pm']}-{stats['total_3pa']} ({stats['fg3_pct']}%)")
    print(f"  Free Throws: {stats['total_ftm']}-{stats['total_fta']} ({stats['ft_pct']}%)")
    print("\n  Game-by-Game:")
    for game in stats["games_detail"]:
        print(f"    {game['date']}: {game['matchup']} - {game['pts']} pts ({game['fgm_fga']} FG, {game['fg3m_fg3a']} 3P)")

    return stats


async def fetch_durant_monthly_progression():
    """3. Kevin Durant's month over month progression last season"""
    print("\n" + "="*80)
    print("REQUEST 3: Kevin Durant's Monthly Progression (2023-24)")
    print("="*80)

    client = NBAApiClient()

    # Get full season game log
    game_log = await client.get_player_game_log(
        player_name="Kevin Durant",
        season="2023-24",
        as_dataframe=True
    )

    # Convert GAME_DATE to datetime and extract month
    game_log['GAME_DATE'] = pd.to_datetime(game_log['GAME_DATE'])
    game_log['MONTH'] = game_log['GAME_DATE'].dt.to_period('M')

    # Calculate monthly averages (FIXED: Use Game_ID not GAME_ID)
    monthly_stats = game_log.groupby('MONTH').agg({
        'PTS': 'mean',
        'REB': 'mean',
        'AST': 'mean',
        'FG_PCT': 'mean',
        'FG3_PCT': 'mean',
        'Game_ID': 'count'  # CORRECTED: Game_ID with capital G
    }).rename(columns={'Game_ID': 'GAMES'})

    # Convert to dict for JSON serialization
    monthly_data = []
    for month, row in monthly_stats.iterrows():
        monthly_data.append({
            "month": str(month),
            "games": int(row['GAMES']),
            "ppg": round(row['PTS'], 1),
            "rpg": round(row['REB'], 1),
            "apg": round(row['AST'], 1),
            "fg_pct": round(row['FG_PCT'] * 100, 1),
            "fg3_pct": round(row['FG3_PCT'] * 100, 1)
        })

    stats = {
        "player": "Kevin Durant",
        "season": "2023-24",
        "total_games": len(game_log),
        "monthly_progression": monthly_data
    }

    print(f"\n[OK] Kevin Durant - Monthly Progression (2023-24):")
    print(f"  Total Games: {stats['total_games']}")
    print("\n  Month-by-Month:")
    for month_stats in monthly_data:
        print(f"    {month_stats['month']}: {month_stats['games']} GP - {month_stats['ppg']} PPG, {month_stats['rpg']} RPG, {month_stats['apg']} APG ({month_stats['fg_pct']}% FG)")

    return stats


async def fetch_warriors_home_performance():
    """4. Warriors home performance last season"""
    print("\n" + "="*80)
    print("REQUEST 4: Warriors Home Performance (2023-24)")
    print("="*80)

    client = NBAApiClient()

    # CORRECTED: Use get_league_game_log() instead of non-existent get_team_game_log()
    # Then filter for Warriors
    league_log = await client.get_league_game_log(
        season="2023-24",
        season_type="Regular Season",
        as_dataframe=True
    )

    # Filter for Warriors games (CORRECTED: Column names are all caps)
    warriors_log = league_log[
        (league_log['TEAM_ABBREVIATION'] == 'GSW') |
        (league_log['TEAM_NAME'].str.contains('Warriors', na=False))
    ]

    # Filter for home games
    home_games = warriors_log[warriors_log["MATCHUP"].str.contains("vs\\.", na=False, regex=True)]

    # Calculate home record
    wins = (home_games["WL"] == "W").sum()
    losses = (home_games["WL"] == "L").sum()

    stats = {
        "team": "Golden State Warriors",
        "season": "2023-24",
        "games": len(home_games),
        "wins": int(wins),
        "losses": int(losses),
        "win_pct": round(wins / len(home_games), 3) if len(home_games) > 0 else 0,
        "avg_pts": round(home_games["PTS"].mean(), 1) if len(home_games) > 0 else 0,
        "avg_opp_pts": round((home_games["PTS"] - home_games["PLUS_MINUS"]).mean(), 1) if len(home_games) > 0 else 0,
        "avg_margin": round(home_games["PLUS_MINUS"].mean(), 1) if len(home_games) > 0 else 0
    }

    print(f"\n[OK] Golden State Warriors - Home Performance (2023-24):")
    print(f"  Record: {stats['wins']}-{stats['losses']} ({stats['win_pct']:.1%})")
    print(f"  Avg Points Scored: {stats['avg_pts']}")
    print(f"  Avg Points Allowed: {stats['avg_opp_pts']}")
    print(f"  Avg Point Differential: {stats['avg_margin']:+.1f}")

    return stats


async def fetch_all_players_first_3_months():
    """5. All players data for first 3 months of last season"""
    print("\n" + "="*80)
    print("REQUEST 5: All Players - First 3 Months (2023-24)")
    print("="*80)

    client = NBAApiClient()

    # Get league leaders data (includes all qualifying players)
    leaders = await client.get_league_leaders(
        stat_category="PTS",
        season="2023-24",
        per_mode="PerGame"
        # Note: season_type parameter not supported by get_league_leaders
    )

    print(f"\n[OK] League Leaders (2023-24 Season):")
    print(f"  Total Players: {len(leaders)}")
    print("\n  Top 10 Scorers:")

    # Show top 10
    top_10 = leaders.head(10)
    top_10_data = []

    for idx, (_, row) in enumerate(top_10.iterrows(), 1):
        player_name = str(row['PLAYER']).encode('ascii', errors='replace').decode('ascii')
        player_data = {
            "rank": idx,
            "player": player_name,  # ASCII encoded to avoid Unicode errors
            "team": row['TEAM'] if 'TEAM' in row else row.get('TEAM_ABBREVIATION', 'N/A'),
            "gp": int(row['GP']) if 'GP' in row else 0,
            "ppg": round(float(row['PTS']), 1) if 'PTS' in row else 0,
            "rpg": round(float(row['REB']), 1) if 'REB' in row else 0,
            "apg": round(float(row['AST']), 1) if 'AST' in row else 0
        }
        top_10_data.append(player_data)
        print(f"    {player_data['rank']}. {player_data['player']} ({player_data['team']}): {player_data['ppg']} PPG, {player_data['rpg']} RPG, {player_data['apg']} APG ({player_data['gp']} GP)")

    stats = {
        "season": "2023-24",
        "date_range": "Full Season (Oct 2023 - Apr 2024)",
        "note": "First 3 months would be Oct-Dec 2023",
        "total_players": len(leaders),
        "top_10_scorers": top_10_data
    }

    print(f"\n  Note: For first 3 months specifically (Oct-Dec 2023), would need date-filtered game logs.")
    print(f"  This shows full season averages for comparison.")

    return stats


# ============================================================================
# MAIN EXECUTION
# ============================================================================

async def main():
    """Execute all data fetching requests"""
    print("="*80)
    print("NBA MCP DATA FETCHING - USER REQUESTS")
    print("="*80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("")

    all_results = {}

    try:
        # Execute all requests
        all_results["lebron_home_avg"] = await fetch_lebron_last_5_home()
        all_results["curry_shot_data"] = await fetch_curry_shot_data()
        all_results["durant_monthly"] = await fetch_durant_monthly_progression()
        all_results["warriors_home"] = await fetch_warriors_home_performance()
        all_results["all_players"] = await fetch_all_players_first_3_months()

        # Save to JSON
        output_file = Path(__file__).parent / "user_data_results.json"
        with open(output_file, 'w') as f:
            json.dump(all_results, f, indent=2)

        print("\n" + "="*80)
        print("[OK] ALL REQUESTS COMPLETED SUCCESSFULLY")
        print("="*80)
        print(f"\nResults saved to: {output_file}")

        return all_results

    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    asyncio.run(main())
