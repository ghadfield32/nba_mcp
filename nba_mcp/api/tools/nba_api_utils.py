# nba_api_utils.py
import unicodedata
import sys
import os
from pathlib import Path
import inspect
import json
from datetime import datetime, date
from typing import Optional, Dict, Union, Any
import pandas as pd
from nba_api.live.nba.endpoints import scoreboard
from nba_api.stats.endpoints import (
    playercareerstats,
    LeagueLeaders,
    LeagueGameLog,
    scoreboardv2
)
from datetime import timedelta
from nba_api.stats.static import teams, players
from dateutil.parser import parse  # Make sure to install python-dateutil if not already installed
import logging

# Create explicit exports for these utility functions
__all__ = [
    'get_player_id', 
    'get_team_id', 
    'get_team_name', 
    'get_player_name',
    'get_static_lookup_schema', 
    'normalize_stat_category', 
    'normalize_per_mode', 
    'normalize_season', 
    'normalize_date',
    'normalize_season_type',
    'format_game',
    'get_team_id_from_abbr'
]

# ---------------------------------------------------
# Load static lookups once and create reverse lookups
# ---------------------------------------------------
# Handle encoding issues by replacing problematic characters in player names
_PLAYER_LOOKUP = {}
_TEAM_LOOKUP = {}

# Pre-load all team and player data for fast lookups
for p in players.get_players():
    try:
        # Use ASCII-compatible representation for player names with special characters
        player_name = f"{p['first_name']} {p['last_name']}"
        _PLAYER_LOOKUP[p["id"]] = player_name.encode('ascii', 'replace').decode('ascii')
    except Exception:
        # Fallback to a safe representation if there are encoding issues
        _PLAYER_LOOKUP[p["id"]] = f"Player {p['id']}"

for t in teams.get_teams():
    _TEAM_LOOKUP[t["id"]] = t["full_name"]

# Create reverse lookups for ID retrieval
_PLAYER_REVLOOKUP = {}
_TEAM_REVLOOKUP = {}

for pid, name in _PLAYER_LOOKUP.items():
    _PLAYER_REVLOOKUP[name.lower()] = pid

for tid, name in _TEAM_LOOKUP.items():
    _TEAM_REVLOOKUP[name.lower()] = tid

# Clean up these debug prints that might cause JSON parsing issues
# Instead log them properly if needed
logger = logging.getLogger(__name__)
logger.debug("Static lookups loaded")
# If needed to examine contents, use proper JSON formatting:
# import json
# logger.debug(f"Team lookup: {json.dumps(list(_TEAM_LOOKUP.items())[:5])}")
# logger.debug(f"Player lookup: {json.dumps(list(_PLAYER_LOOKUP.items())[:5])}")


def format_game(game: dict) -> str:
    """
    Format a game record into a readable string.
    """
    home_team = game["home_team"]["full_name"]
    visitor_team = game["visitor_team"]["full_name"]
    home_score = game["home_team_score"]
    visitor_score = game["visitor_team_score"]
    
    # Add game status information
    status_text = ""
    if game.get("status") == 3:  # Finished game
        status_text = " (Final)"
    elif game.get("period") > 0:
        period = game.get("period", 0)
        time = game.get("time", "")
        status_text = f" (Period {period}, {time})"
    
    return f"{home_team} vs {visitor_team} - Score: {home_score} to {visitor_score}{status_text}"

# Build lookups directly from the nba_api's static players list
_PLAYER_LOOKUP: Dict[int, str] = {}
for p in players.get_players():
    name = p.get("first_name", "").strip()
    if p.get("last_name"):
        name += " " + p["last_name"].strip()
    if p.get("last_suffix"):
        name += " " + p["last_suffix"].strip()
    _PLAYER_LOOKUP[p["id"]] = name or f"Player {p['id']}"

_PLAYER_NAME_TO_ID = { name: pid for pid, name in _PLAYER_LOOKUP.items() }

def get_player_id(player_name: str) -> Optional[int]:
    key = player_name.lower()
    # exact match
    for name, pid in _PLAYER_NAME_TO_ID.items():
        if name.lower() == key:
            return pid
    # partial match
    for name, pid in _PLAYER_NAME_TO_ID.items():
        if key in name.lower():
            return pid
    return None


def get_player_name(player_id: Union[int, str]) -> Optional[str]:
    """Convert player ID to name, using a centralized lookup."""
    return _PLAYER_LOOKUP.get(int(player_id))

def get_team_id(team_name: str) -> Optional[int]:
    """Convert team name to ID, with case-insensitive partial matching."""
    if not team_name:
        return None
    
    team_name_lower = team_name.lower()
    # Try exact match first
    for name, id in _TEAM_REVLOOKUP.items():
        if name == team_name_lower:
            return id
    
    # Try partial match
    for name, id in _TEAM_REVLOOKUP.items():
        if team_name_lower in name:
            return id
    
    return None

def get_team_name(team_id: Union[int, str]) -> Optional[str]:
    """
    Convert a team ID to its full name, using a centralized lookup.
    Accepts either int or str representations of the ID.
    """
    return _TEAM_LOOKUP.get(int(team_id))






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





def normalize_season_type(raw: str) -> str:
    """
    Normalize various user inputs into one of the API's allowed SeasonType values:
      - "Regular Season"
      - "Playoffs"
      - "Pre Season"
      - "All Star"
      - "All-Star"

    Accepts e.g. "regular", "reg season", "playoff", "preseason", "allstar", etc.
    """
    mapping = {
        "regular season":       "Regular Season",
        "regular":              "Regular Season",
        "reg season":           "Regular Season",
        "playoffs":             "Playoffs",
        "playoff":              "Playoffs",
        "postseason":           "Playoffs",
        "pre season":           "Pre Season",
        "pre‑season":           "Pre Season",
        "preseason":            "Pre Season",
        "pre":                  "Pre Season",
        "all star":             "All Star",
        "all‑star":             "All Star",
        "allstar":              "All Star",
        "all-star":             "All Star",
        "all star season":      "All Star",
        "All-Star":             "All Star",
    }
    key = raw.strip().lower()
    if key in mapping:
        return mapping[key]
    raise ValueError(f"Unrecognized season_type: '{raw}'. "
                     f"Expected one of: {sorted(set(mapping.values()))}")
    

def normalize_stat_category(stat_category: str) -> str:
    """
    Normalize various string formats of a stat category to the NBA API's expected abbreviation.
    
    For example:
      - "pts" or "points" -> "PTS"
      - "reb", "rebound", or "rebounds" -> "REB"
    
    Adjust or extend the mapping as needed.
    """
    # Mapping: API abbreviation -> list of possible variants (all in lower-case without spaces)
    mapping = {
        "PTS": ["pts", "points"],
        "REB": ["reb", "rebound", "rebounds", "rebs"],
        "AST": ["ast", "assist", "assists", "asist"],
        "STL": ["stl", "steal", "steals", "stls"],
        "BLK": ["blk", "block", "blocks", "blks"],
        "FGM": ["fgm", "fieldgoalsmade", "fgms"],
        "FGA": ["fga", "fieldgoalattempts", "fgas"],
        "FG_PCT": ["fg_pct", "fieldgoalpercentage", "fgpercentage", "fgpct"],
        "FG3M": ["fg3m", "threepointsmade", "3pm", "3pms"],
        "FG3A": ["fg3a", "threepointsattempted", "3pa", "3pas"],
        "FG3_PCT": ["fg3_pct", "threepointpercentage", "3ppct", "3ppcts"],
        "FTM": ["ftm", "freethrowsmade", "ftms"],
        "FTA": ["fta", "freethrowsattempted", "ftas"],
        "FT_PCT": ["ft_pct", "freethrowpercentage", "ftpct", "ftpcts"],
        "OREB": ["oreb", "offensiverebounds", "orebs"],
        "DREB": ["dreb", "defensiverebounds", "drebs"],
        "EFF": ["eff", "efficiency", "effs"],
        "AST_TOV": ["ast_tov", "assistturnover", "asttov"],
        "STL_TOV": ["stl_tov", "stealturnover", "stlttov"],
    }
    
    # Build a reverse lookup: each synonym maps to the proper abbreviation.
    synonym_lookup = {}
    for abbr, synonyms in mapping.items():
        for syn in synonyms:
            synonym_lookup[syn] = abbr

    # Normalize the input: trim, lowercase, and remove extra spaces
    normalized_key = stat_category.strip().lower().replace(" ", "")
    
    if normalized_key in synonym_lookup:
        return synonym_lookup[normalized_key]
    else:
        raise ValueError(f"Unsupported stat category: {stat_category}")

def normalize_per_mode(per_mode: str) -> str:
    """
    Normalize the per_mode parameter to one of the allowed values:
    "Totals", "PerGame", or "Per48".
    
    Accepts variations such as lower or upper case, and common synonyms.
    """
    normalized = per_mode.strip().lower()
    if normalized in ["totals", "total", "total stats", "total per season"]:
        return "Totals"
    elif normalized in ["pergame", "per game", "per game average", "per game average stats", "per game per season"]:
        return "PerGame"
    elif normalized in ["per48", "per 48", "per 48 average", "per 48 average stats", "per 48 per season"]:
        return "Per48"
    else:
        raise ValueError(f"Unsupported per_mode value: {per_mode}")
    
def normalize_season(season: str) -> str:
    """
    Normalize the season parameter to the expected format:
    "YYYY-YY" (e.g. "2024-25").
    
    Handles various inputs:
    - 2-digit year (e.g., "24") - interpreted as 2000s for values < 59
    - 4-digit year (e.g., "2024")
    - Already formatted "YYYY-YY" season
    """
    # Strip any whitespace
    season = season.strip()
    season = season.replace("'", "").replace("_", "")
    
    # Handle 2-digit year (e.g., "24")
    if len(season) == 2 and season.isdigit():
        year = int(season)
        # Interpret years below 59 as 2000s, otherwise as 1900s
        full_year = 2000 + year if year < 59 else 1900 + year
        next_year = str(full_year + 1)[2:]
        return f"{full_year}-{next_year}"
    
    # Handle 4-digit year (e.g., "2024")
    elif len(season) == 4 and season.isdigit():
        year = int(season)
        next_year = str(year + 1)[2:]
        return f"{year}-{next_year}"
    
    # Handle already formatted season (e.g., "2024-25" or "24-25")
    elif "-" in season and len(season.split("-")) == 2:
        parts = season.split("-")
        
        # If it's a short format like "24-25", convert to "2024-25"
        if len(parts[0]) == 2 and parts[0].isdigit():
            year = int(parts[0])
            full_year = 2000 + year if year < 59 else 1900 + year
            return f"{full_year}-{parts[1]}"
        
        # If it's already in "YYYY-YY" format, return as is
        return season
    
    # Unsupported format
    else:
        raise ValueError(f"Unsupported season value: {season}")




# ---------------------------------------------------------------------------
# Any dash‑like character we want to recognise as a hyphen
# (list is not exhaustive – add more if you encounter them)
_DASHES = {
    "\u2010",  # HYPHEN
    "\u2011",  # NO‑BREAK HYPHEN  ← your bug
    "\u2012",  # FIGURE DASH
    "\u2013",  # EN DASH
    "\u2014",  # EM DASH
    "\u2212",  # MINUS
}
def _clean_date_string(s: str) -> str:
    """
    Convert all fancy dash variants to ASCII '-' and strip weird spaces.
    """
    cleaned = []
    for ch in s:
        if ch in _DASHES:
            cleaned.append("-")
        elif unicodedata.category(ch) in {"Zs", "Cf"}:  # space / format chars
            cleaned.append(" ")
        else:
            cleaned.append(ch)
    return "".join(cleaned).strip()

def normalize_date(
    target_date: Optional[Union[str, date, datetime]]
) -> date:
    """
    Normalise an input into a `datetime.date`.

    * Accepts `date`, `datetime`, or string (almost any human format).
    * Cleans Unicode dashes so strings like '2024‑12‑25' parse correctly.
    * Passing `None` returns **today**.
    """
    # --- 1. Short‑circuits for non‑string types ----------------------------
    if target_date is None:
        return date.today()
    if isinstance(target_date, datetime):
        return target_date.date()
    if isinstance(target_date, date):
        return target_date

    # --- 2. Sanity‑check string input --------------------------------------
    if not isinstance(target_date, str):
        raise TypeError("target_date must be str, datetime, date or None")

    cleaned = _clean_date_string(target_date)

    try:
        return parse(cleaned, fuzzy=True).date()
    except Exception as e:
        raise ValueError(
            f"Unable to parse target_date string after cleaning: {target_date!r}"
        ) from e

def get_team_id_from_abbr(abbr: str) -> Optional[int]:
    """
    Convert a team abbreviation (e.g., 'LAL', 'NYK') to a team ID.
    Handles common NBA team abbreviations.
    
    Returns None if the abbreviation isn't recognized.
    """
    if not abbr:
        return None
    
    # Common NBA team abbreviations to ID mapping
    abbr_to_id = {
        "ATL": 1610612737,  # Atlanta Hawks
        "BOS": 1610612738,  # Boston Celtics
        "BKN": 1610612751,  # Brooklyn Nets
        "CHA": 1610612766,  # Charlotte Hornets
        "CHI": 1610612741,  # Chicago Bulls
        "CLE": 1610612739,  # Cleveland Cavaliers
        "DAL": 1610612742,  # Dallas Mavericks
        "DEN": 1610612743,  # Denver Nuggets
        "DET": 1610612765,  # Detroit Pistons
        "GSW": 1610612744,  # Golden State Warriors
        "HOU": 1610612745,  # Houston Rockets
        "IND": 1610612754,  # Indiana Pacers
        "LAC": 1610612746,  # Los Angeles Clippers
        "LAL": 1610612747,  # Los Angeles Lakers
        "MEM": 1610612763,  # Memphis Grizzlies
        "MIA": 1610612748,  # Miami Heat
        "MIL": 1610612749,  # Milwaukee Bucks
        "MIN": 1610612750,  # Minnesota Timberwolves
        "NOP": 1610612740,  # New Orleans Pelicans
        "NYK": 1610612752,  # New York Knicks
        "OKC": 1610612760,  # Oklahoma City Thunder
        "ORL": 1610612753,  # Orlando Magic
        "PHI": 1610612755,  # Philadelphia 76ers
        "PHX": 1610612756,  # Phoenix Suns
        "POR": 1610612757,  # Portland Trail Blazers
        "SAC": 1610612758,  # Sacramento Kings
        "SAS": 1610612759,  # San Antonio Spurs
        "TOR": 1610612761,  # Toronto Raptors
        "UTA": 1610612762,  # Utah Jazz
        "WAS": 1610612764,  # Washington Wizards
    }
    
    # Try exact match with uppercase
    upper_abbr = abbr.upper()
    if upper_abbr in abbr_to_id:
        return abbr_to_id[upper_abbr]
    
    return None



# ---------------------------------------------------------------------------
# ──  SMALL HELPER (outside the class — tiny, pure)                        ──
# ---------------------------------------------------------------------------

def _resolve_team_ids(label: str) -> set[int]:
    """
    Return every team‑ID that matches an abbreviation or fuzzy name.
    """
    ids: set[int] = set()

    tid = get_team_id_from_abbr(label)
    if tid:
        ids.add(int(tid))

    tid2 = get_team_id(label)
    if tid2:
        ids.add(int(tid2))

    return ids
