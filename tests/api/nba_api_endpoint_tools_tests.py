"""
Example Script for Pulling NBA Data Using nba_api

This script demonstrates how to use two different kinds of endpoints:

1. NBA Live Data:
   - Live Scoreboard: Retrieves game data from NBA.com in real time.
2. NBA Official Stats:
   - Player Career Stats: Example for Nikola Jokić (player_id '203999').
   - League Leaders: Retrieve season leader statistics.
   - League Game Log: Retrieves game log data for a given season.

The script prints some of the first few rows of each returned DataFrame,
and for the player career stats it also shows how to fetch a JSON snippet.

Ensure you have Python 3.7+ installed.
"""

from typing import Optional, Dict
import pandas as pd
from nba_api.live.nba.endpoints import scoreboard
from nba_api.stats.endpoints import (
    playercareerstats,
    LeagueLeaders,
    LeagueGameLog,
    boxscoretraditionalv2, boxscoreadvancedv2
)
from datetime import date, timedelta
from nba_api.stats.endpoints import scoreboardv2
from nba_api.stats.static import teams, players


# ---------------------------------------------------
# Load static lookups once and create reverse lookups
# ---------------------------------------------------
_TEAM_LOOKUP: Dict[int, str] = {
    t["id"]: t["full_name"] for t in teams.get_teams()
}
_PLAYER_LOOKUP: Dict[int, str] = {
    p["id"]: f"{p['first_name']} {p['last_name']}" for p in players.get_players()
}

# Create reverse lookups (name -> id)
_TEAM_NAME_TO_ID = {name: id for id, name in _TEAM_LOOKUP.items()}
_PLAYER_NAME_TO_ID = {name: id for id, name in _PLAYER_LOOKUP.items()}

print("Static lookups loaded.")
print("team list================", _TEAM_LOOKUP)
print("player list================", _PLAYER_LOOKUP)
print("team list keys ================", _TEAM_LOOKUP.keys())
print("player list keys ================", _PLAYER_LOOKUP.keys())


def get_player_id(player_name: str) -> Optional[int]:
    """Convert player name to ID, with case-insensitive partial matching."""
    if not player_name:
        return None
    
    player_name_lower = player_name.lower()
    # Try exact match first
    for name, id in _PLAYER_NAME_TO_ID.items():
        if name.lower() == player_name_lower:
            return id
    
    # Try partial match
    for name, id in _PLAYER_NAME_TO_ID.items():
        if player_name_lower in name.lower():
            return id
    
    return None

def get_team_id(team_name: str) -> Optional[int]:
    """Convert team name to ID, with case-insensitive partial matching."""
    if not team_name:
        return None
    
    team_name_lower = team_name.lower()
    # Try exact match first
    for name, id in _TEAM_NAME_TO_ID.items():
        if name.lower() == team_name_lower:
            return id
    
    # Try partial match
    for name, id in _TEAM_NAME_TO_ID.items():
        if team_name_lower in name.lower():
            return id
    
    return None








def get_static_lookup_schema() -> Dict:
    """
    Returns a dictionary containing static lookup information for teams and players.
    The output includes a query-friendly SQL-like string for each lookup table.
    For example:
        teams(ID INTEGER, TEAM_NAME TEXT)
        players(ID INTEGER, PLAYER_NAME TEXT)
    Additionally, the actual lookup dictionaries are included under the "data" key.
    """
    # Build friendly table representations
    teams_table = "teams(" + ", ".join(["ID INTEGER", "TEAM_NAME TEXT"]) + ")"
    players_table = "players(" + ", ".join(["ID INTEGER", "PLAYER_NAME TEXT"]) + ")"
    
    return {
        "description": "Static lookup tables for teams and players",
        "tables": {
            "teams": teams_table,
            "players": players_table
        },
        "data": {
            "teams": _TEAM_LOOKUP,
            "players": _PLAYER_LOOKUP
        }
    }





def get_games_by_date(
    target_date: Optional[date] = None,
    max_days_back: int = 7
) -> pd.DataFrame:
    """
    Find the most recent date (up to max_days_back days ago) with NBA games,
    and return a DataFrame with game information including detailed statistics.
    """
    if target_date is None:
        target_date = date.today()

    for days_back in range(max_days_back):
        check_date = target_date - timedelta(days=days_back)
        date_str = check_date.strftime("%m/%d/%Y")

        sb2 = scoreboardv2.ScoreboardV2(game_date=date_str)
        headers = sb2.game_header.get_data_frame()
        lines = sb2.line_score.get_data_frame()

        if headers.empty:
            continue

        # Merge header and line scores
        merged = headers.merge(lines, on="GAME_ID", suffixes=("", "_line"))
        
        # Process each game once
        games_list = []
        for game_id in merged["GAME_ID"].unique():
            game_data = merged[merged["GAME_ID"] == game_id]
            
            # Get home team data
            home_row = game_data[game_data["HOME_TEAM_ID"] == game_data["TEAM_ID"]].iloc[0]
            # Get away team data
            away_row = game_data[game_data["VISITOR_TEAM_ID"] == game_data["TEAM_ID"]].iloc[0]
            
            games_list.append({
                # Basic game info
                "date": pd.to_datetime(home_row["GAME_DATE_EST"]).date(),
                "game_id": game_id,
                "status": home_row["GAME_STATUS_TEXT"],
                
                # Home team stats
                "home_team": _TEAM_LOOKUP.get(int(home_row["TEAM_ID"])),
                "home_pts": home_row["PTS"],
                "home_fg_pct": home_row.get("FG_PCT", 0),
                "home_ft_pct": home_row.get("FT_PCT", 0),
                "home_fg3_pct": home_row.get("FG3_PCT", 0),
                "home_ast": home_row.get("AST", 0),
                "home_reb": home_row.get("REB", 0),
                "home_stl": home_row.get("STEALS", 0),  # Changed from STL to STEALS
                "home_blk": home_row.get("BLOCKS", 0),  # Changed from BLK to BLOCKS
                "home_to": home_row.get("TURNOVERS", 0),  # Changed from TOV to TURNOVERS
                "home_pf": home_row.get("PF", 0),
                "home_plus_minus": home_row.get("PLUS_MINUS", 0),
                
                # Away team stats
                "away_team": _TEAM_LOOKUP.get(int(away_row["TEAM_ID"])),
                "away_pts": away_row["PTS"],
                "away_fg_pct": away_row.get("FG_PCT", 0),
                "away_ft_pct": away_row.get("FT_PCT", 0),
                "away_fg3_pct": away_row.get("FG3_PCT", 0),
                "away_ast": away_row.get("AST", 0),
                "away_reb": away_row.get("REB", 0),
                "away_stl": away_row.get("STEALS", 0),  # Changed from STL to STEALS
                "away_blk": away_row.get("BLOCKS", 0),  # Changed from BLK to BLOCKS
                "away_to": away_row.get("TURNOVERS", 0),  # Changed from TOV to TURNOVERS
                "away_pf": away_row.get("PF", 0),
                "away_plus_minus": away_row.get("PLUS_MINUS", 0),
                
                # Additional game details
                "game_time": home_row.get("GAME_STATUS_TEXT", ""),
                "attendance": home_row.get("ATTENDANCE", 0),
                "game_duration": home_row.get("GAME_TIME", "")
            })
        
        if games_list:
            df = pd.DataFrame(games_list)
            # Convert percentage columns to actual percentages
            pct_columns = [col for col in df.columns if 'pct' in col.lower()]
            for col in pct_columns:
                df[col] = df[col].multiply(100).round(1)
            return df

    # Return empty DataFrame if no games found
    return pd.DataFrame(
        columns=[
            "date", "game_id", "status",
            "home_team", "home_pts", "home_fg_pct", "home_ft_pct", "home_fg3_pct",
            "home_ast", "home_reb", "home_stl", "home_blk", "home_to", "home_pf",
            "home_plus_minus",
            "away_team", "away_pts", "away_fg_pct", "away_ft_pct", "away_fg3_pct",
            "away_ast", "away_reb", "away_stl", "away_blk", "away_to", "away_pf",
            "away_plus_minus",
            "game_time", "attendance", "game_duration"
        ]
    )



def get_live_scoreboard(
    target_date: Optional[date] = None
) -> scoreboard.ScoreBoard:
    """Retrieve live scoreboard data.
    
    If no target_date is provided, today's date is used.
    """
    if target_date is None:
        target_date = date.today()
    formatted_date = target_date.strftime("%m/%d/%Y")
    print(f"Fetching live scoreboard for {formatted_date} ...")
    # Note: The live scoreboard endpoint automatically pulls data for the
    # current game day.
    live_scoreboard = scoreboard.ScoreBoard()
    return live_scoreboard


def get_player_career_stats(player_name: str) -> playercareerstats.PlayerCareerStats:
    """Retrieve career stats for a specific player by name."""
    player_id = get_player_id(player_name)
    if player_id is None:
        raise ValueError(f"Player not found: {player_name}")
    return playercareerstats.PlayerCareerStats(player_id=player_id)


def get_league_leaders(season: str) -> LeagueLeaders:
    """Retrieve league leaders for a specified season.
    
    Season is passed as a string, e.g. '2024-25'
    """
    leaders = LeagueLeaders(season=season)
    return leaders


def get_league_game_log(
    season: str,
    team_name: Optional[str] = None,
    direction: str = 'DESC',
    season_type: str = 'Regular Season',
    sorter: str = 'DATE',
    date_from: str = '',
    date_to: str = '',
    counter: int = 0
) -> LeagueGameLog:
    """
    Retrieve the league game log for a given season and optionally filter it using a team name.
    If the team_name doesn’t resolve to a valid ID or any rows match by name/matchup,
    returns an object whose get_data_frames()[0] is an empty DataFrame.
    """
    # 1) Fetch the full log
    log = LeagueGameLog(
        counter=counter,
        direction=direction,
        league_id='00',
        player_or_team_abbreviation='T',
        season=season,
        season_type_all_star=season_type,
        sorter=sorter,
        date_from_nullable=date_from,
        date_to_nullable=date_to
    )
    df = log.get_data_frames()[0]

    # 2) If no filter requested, just return the raw log
    if not team_name:
        return log

    # 3) Try by numeric ID first
    team_id = get_team_id(team_name)
    if team_id is not None and 'TEAM_ID' in df.columns:
        mask = df['TEAM_ID'] == team_id
    else:
        # 4) Fallback to name/matchup
        tn = team_name.lower()
        mask = (
            df['TEAM_NAME'].str.lower().str.contains(tn, na=False) |
            df['MATCHUP'].str.lower().str.contains(tn, na=False)
        )

    # 5) If no rows matched, return an empty‐DataFrame log
    filtered = df[mask]
    if filtered.empty:
        # Create a dummy LeagueGameLog that yields an empty DataFrame
        empty_log = log  # reuse the same object
        def _empty_get_frames():
            return [pd.DataFrame(columns=df.columns)]
        # Monkey‐patch its get_data_frames method
        empty_log.get_data_frames = _empty_get_frames  # type: ignore
        return empty_log

    # 6) Otherwise patch the real log to return only filtered rows
    def _filtered_get_frames():
        return [filtered.reset_index(drop=True)]
    log.get_data_frames = _filtered_get_frames  # type: ignore
    return log


def main() -> None:
        
    # ------------------------------
    # Example 1: NBA Live Data – Scoreboard
    # ------------------------------
    try:
        live_score = get_live_scoreboard()
        # Retrieve the live scoreboard data as JSON or dict
        live_data = live_score.get_dict() 
        
        print("\nLive Scoreboard JSON data snippet:")
        # Convert to string before slicing for preview
        import json
        json_preview = json.dumps(live_data, indent=2)[:500]
        print(json_preview)

        if "scoreboard" in live_data and "games" in live_data["scoreboard"]:
            live_games_df = pd.DataFrame(live_data["scoreboard"]["games"])
            print("\nLive Scoreboard DataFrame (first 5 rows):")
            print(live_games_df.head())
        else:
            print("Key 'games' not found in the live scoreboard JSON data.")


    except Exception as e:
        print("Error retrieving live scoreboard data:", str(e))

    
    # ------------------------------
    # Example 2: NBA Official Stats – Player Career Stats
    # ------------------------------
    # Update examples to use names instead of IDs
    print("\nFetching player career stats for Nikola Jokić:")
    try:
        career = get_player_career_stats('Nikola Jokić')
        career_df = career.get_data_frames()[0]
        print("Player Career Stats DataFrame (first 5 rows):")
        print(career_df.head())

        # Also demonstrate how to get the JSON output (print a snippet)
        career_json = career.get_json()
        print("\nPlayer Career Stats JSON snippet (first 500 characters):")
        print(career_json[:500])
    except Exception as e:
        print("Error retrieving player career stats:", e)
    
    # ------------------------------
    # Example 3: NBA Official Stats – League Leaders
    # ------------------------------
    season = "2024-25"
    print(f"\nFetching league leaders for season {season}:")
    try:
        leaders = get_league_leaders(season)
        leaders_df = leaders.get_data_frames()[0]
        print("League Leaders DataFrame (first 5 rows):")
        print(leaders_df.head())
    except Exception as e:
        print("Error retrieving league leaders:", e)
    

    # ------------------------------
    # Example 4: NBA Official Stats – League Game Log
    # ------------------------------
    # Example with team name
    print("\nFetching game log for Boston Celtics:")
    try:
        game_log = get_league_game_log("2024-25", "Boston Celtics")
        game_log_df = game_log.get_data_frames()[0]
        print("Game Log DataFrame (first 5 rows):")
        print(game_log_df.head())
        
        
        # 1) Full season, no filters
        full_log = get_league_game_log("2024-25")
        print(full_log.get_data_frames()[0].shape)  # e.g. (2460, ...)

        # 2) Date‐range only
        april_log = get_league_game_log("2024-25", date_from="04/01/2025", date_to="04/15/2025")
        print(april_log.get_data_frames()[0]['GAME_DATE'].unique())

        # 3) Team + date range
        celtics_april = get_league_game_log(
            "2024-25",
            team_name="Boston Celtics",
            date_from="04/01/2025",
            date_to="04/15/2025"
        )
        df3 = celtics_april.get_data_frames()[0]
        print(df3.shape)           # e.g. (5, ...)
        print(df3['MATCHUP'].tolist())

        # 4) Nonexistent team → empty
        empty_log = get_league_game_log("2024-25", team_name="NotATeam")
        print(empty_log.get_data_frames()[0].empty)  # True

    except Exception as e:
        print("Error retrieving game log:", e)


if __name__ == '__main__':
    main()
    
    # Try today:
    df_today = get_games_by_date()
    print("Today's (or most recent) games:")
    print(df_today)

    # Or for a specific date:
    df_april10 = get_games_by_date(date(2025, 4, 10))
    print("\nGames on 2025-04-10:")
    print(df_april10)