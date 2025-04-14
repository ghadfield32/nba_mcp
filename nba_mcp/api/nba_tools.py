from typing import Optional, Dict, Any, Union
import pandas as pd
from datetime import date

# nba_api imports
from nba_api.live.nba.endpoints import scoreboard
from nba_api.stats.endpoints import (
    playercareerstats,
    LeagueLeaders,
    LeagueGameLog
)


def get_live_scoreboard(
    target_date: Optional[date] = None,
    as_dataframe: bool = True
) -> Union[Dict[str, Any], pd.DataFrame]:
    """
    Retrieve live scoreboard data for the given date (defaults to today).

    Args:
        target_date (optional): datetime.date object. Defaults to today.
        as_dataframe (bool): If True, return a pandas DataFrame. 
            Otherwise, return the raw dictionary from the scoreboard endpoint.

    Returns:
        Either a pandas DataFrame (default) or a Python dict of scoreboard data.
    
    Example usage:
        >>> df = get_live_scoreboard()
        >>> # or 
        >>> data = get_live_scoreboard(as_dataframe=False)
    """
    if target_date is None:
        target_date = date.today()
    formatted_date = target_date.strftime("%m/%d/%Y")
    print(f"Fetching live scoreboard for {formatted_date} ...")

    # nba_api.live.nba.endpoints.scoreboard
    sb = scoreboard.ScoreBoard()  # date for scoreboard automatically today
    data = sb.get_dict()  # full scoreboard in JSON/dict

    # If as_dataframe=False, just return the dict
    if not as_dataframe:
        return data

    # Otherwise, convert the "games" portion to a DataFrame
    # Example path: data["scoreboard"]["games"]
    try:
        games = data["scoreboard"]["games"]
        return pd.DataFrame(games)
    except KeyError:
        # If "games" is missing
        print("No 'games' key found in live scoreboard data.")
        return pd.DataFrame()  # empty DataFrame


def get_player_career_stats(
    player_id: str,
    as_dataframe: bool = True
) -> Union[Dict[str, Any], pd.DataFrame]:
    """
    Retrieve career stats for a specific player by player_id (e.g. '203999' for Jokic).

    Args:
        player_id (str): NBA player ID in string form.
        as_dataframe (bool): If True, return a DataFrame, else return raw JSON/dict.

    Returns:
        A pandas DataFrame or dictionary with the player's career stats.
    """
    career = playercareerstats.PlayerCareerStats(player_id=player_id)
    if as_dataframe:
        return career.get_data_frames()[0]
    return career.get_dict()


def get_league_leaders(
    season: str,
    as_dataframe: bool = True
) -> Union[Dict[str, Any], pd.DataFrame]:
    """
    Retrieve league leaders for a specified season.

    Args:
        season (str): e.g. '2024-25'
        as_dataframe (bool): If True, return a DataFrame, else return raw JSON/dict.

    Returns:
        A pandas DataFrame or dictionary with league leader stats.
    """
    leaders = LeagueLeaders(season=season)
    if as_dataframe:
        return leaders.get_data_frames()[0]
    return leaders.get_dict()


def get_league_game_log(
    season: str,
    team_id: Optional[str] = None,
    as_dataframe: bool = True
) -> Union[Dict[str, Any], pd.DataFrame]:
    """
    Retrieve the league game log for a given season. Optionally filter by team_id.

    Args:
        season (str): e.g. '2024-25'
        team_id (str, optional): e.g. '1610612743' for Denver Nuggets
        as_dataframe (bool): If True, return a DataFrame, else return raw JSON/dict.

    Returns:
        A pandas DataFrame or dictionary with league game log data.
    """
    if team_id:
        log = LeagueGameLog(season=season, team_id_nullable=team_id)
    else:
        log = LeagueGameLog(season=season)

    if as_dataframe:
        return log.get_data_frames()[0]
    return log.get_dict() 