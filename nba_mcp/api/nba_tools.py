from typing import Optional, Dict, Any, Union
import pandas as pd
from datetime import date
import logging

# nba_api imports
from nba_api.live.nba.endpoints import scoreboard
from nba_api.stats.endpoints import (
    playercareerstats,
    LeagueLeaders,
    LeagueGameLog
)
from nba_api.stats.static import players, teams  # <-- import both static lookups

# Set up logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Cache static data at module load to avoid repeated API calls
# ─────────────────────────────────────────────────────────────────────────────

# Cache player and team data at module load
try:
    logger.info("Caching NBA players and teams data...")
    _ALL_PLAYERS = players.get_players()
    _ALL_TEAMS = teams.get_teams()
    logger.info(f"Cached {len(_ALL_PLAYERS)} players and {len(_ALL_TEAMS)} teams")
except Exception as e:
    logger.error(f"Error caching NBA data: {str(e)}")
    # Fallback to empty lists so the module still works
    _ALL_PLAYERS = []
    _ALL_TEAMS = []

# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_player_id_from_name(player_name: str) -> Optional[str]:
    """Return the NBA player_id for a given player name, or None if not found."""
    if not player_name.strip():
        return None

    # Use cached player data instead of making API call
    all_players = _ALL_PLAYERS
    if not all_players:
        # Fallback to API call if cache failed
        logger.warning("Player cache empty, falling back to API call")
        all_players = players.get_players()
        
    name_lower = player_name.lower().strip()

    # exact match
    for p in all_players:
        full = f"{p['first_name']} {p['last_name']}".lower()
        if full == name_lower:
            return str(p['id'])

    # partial match
    partial = [p for p in all_players if name_lower in f"{p['first_name']} {p['last_name']}".lower()]
    if partial:
        # pick shortest name
        partial.sort(key=lambda x: len(x['first_name'] + x['last_name']))
        return str(partial[0]['id'])

    return None


def _get_team_id_from_name(team_name: str) -> Optional[str]:
    """Return the NBA team_id for a given team name (full or partial), or None."""
    if not team_name.strip():
        return None

    # Use cached team data instead of making API call
    all_teams = _ALL_TEAMS
    if not all_teams:
        # Fallback to API call if cache failed
        logger.warning("Team cache empty, falling back to API call")
        all_teams = teams.get_teams()
        
    name_lower = team_name.lower().strip()

    # try exact full_name
    for t in all_teams:
        if t['full_name'].lower() == name_lower or t['abbreviation'].lower() == name_lower:
            return t['id']

    # partial match on full_name
    partial = [t for t in all_teams if name_lower in t['full_name'].lower()]
    if partial:
        # pick shortest full_name
        partial.sort(key=lambda x: len(x['full_name']))
        return partial[0]['id']

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Public API functions
# ─────────────────────────────────────────────────────────────────────────────

def get_live_scoreboard(
    target_date: Optional[date] = None,
    as_dataframe: bool = True
) -> Union[Dict[str, Any], pd.DataFrame]:
    """
    Retrieve live scoreboard data for the given date (defaults to today).
    
    The returned raw data has the following structure:
    {
        "meta": {
            "version": 1,
            "request": "https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/...",
            "time": "2025-04-14 01:23:32.2332",
            "code": 200
        },
        "scoreboard": {
            "gameDate": "2025-04-14",
            "leagueId": "00",
            "leagueName": "National Basketball Association",
            "games": []
        }
    }
    
    Args:
        target_date: Optional specific date to fetch, defaults to today
        as_dataframe: If True, returns games as a DataFrame, otherwise returns raw API data
    
    Returns:
        If as_dataframe is True, returns pandas DataFrame of games
        If as_dataframe is False, returns full raw API response dict
    """
    if target_date is None:
        target_date = date.today()
        
    # Create scoreboard instance for the target date
    sb = scoreboard.ScoreBoard()
    
    # If date is not today, set the date property
    if target_date != date.today():
        sb.game_date = target_date
        
    # Get the raw dictionary data
    data = sb.get_dict()
    
    # If not requesting DataFrame, return the complete raw data
    if not as_dataframe:
        return data
    
    # Extract games for DataFrame conversion
    games = data.get("scoreboard", {}).get("games", [])
    
    # Return as DataFrame
    return pd.DataFrame(games)


def get_player_career_stats(
    player_name_or_id: str,
    as_dataframe: bool = True
) -> Union[Dict[str, Any], pd.DataFrame]:
    """
    Retrieve career stats for an NBA player, given either name or ID.
    """
    if player_name_or_id.isdigit():
        pid = player_name_or_id
    else:
        pid = _get_player_id_from_name(player_name_or_id)
        if not pid:
            raise ValueError(f"No player found matching '{player_name_or_id}'")

    career = playercareerstats.PlayerCareerStats(player_id=pid)
    if as_dataframe:
        return career.get_data_frames()[0]
    return career.get_dict()


def get_league_leaders(
    season: str,
    stat_category: str = "PTS",
    as_dataframe: bool = True
) -> Union[Dict[str, Any], pd.DataFrame]:
    """
    Retrieve league leaders for a specified season and stat category.
    
    Args:
        season: Season in format 'YYYY-YY' (e.g., '2022-23')
        stat_category: Statistical category (PTS, AST, REB, etc.)
        as_dataframe: If True, returns pandas DataFrame, otherwise returns raw dict
        
    Returns:
        League leaders data as DataFrame or dict
    """
    leaders = LeagueLeaders(season=season, stat_category=stat_category)
    if as_dataframe:
        return leaders.get_data_frames()[0]
    return leaders.get_dict()


def get_league_game_log(
    season: str,
    team_name_or_id: Optional[str] = None,
    as_dataframe: bool = True
) -> Union[Dict[str, Any], pd.DataFrame]:
    """
    Retrieve the league game log for a season, optionally filtered by team (name or ID).
    
    Args:
        season: Season in format 'YYYY-YY' (e.g., '2022-23')
        team_name_or_id: Can be either a team name (e.g., "Denver Nuggets") or team ID (e.g., "1610612743")
                         If a name is provided, it will be resolved to an ID using _get_team_id_from_name()
        as_dataframe: If True, returns pandas DataFrame, otherwise returns raw dict
    
    Returns:
        League game log data as DataFrame or dict
        
    Note:
        In client.py implementation, this is called with team_id parameter directly,
        bypassing the name resolution functionality.
    """
    tid: Optional[Union[int, str]] = None
    if team_name_or_id:
        if team_name_or_id.isdigit():
            tid = team_name_or_id
        else:
            tid = _get_team_id_from_name(team_name_or_id)
            if tid is None:
                raise ValueError(f"No team found matching '{team_name_or_id}'")

    # nba_api expects an integer for team_id_nullable
    if tid:
        log = LeagueGameLog(season=season, team_id_nullable=int(tid))
    else:
        log = LeagueGameLog(season=season)

    if as_dataframe:
        return log.get_data_frames()[0]
    return log.get_dict()
