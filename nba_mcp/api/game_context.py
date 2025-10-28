"""
Game Context Composition Module
Provides rich game context by composing data from multiple NBA API sources:
- Team standings (conference/division rank, record, games behind)
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from nba_api.stats.endpoints import leaguestandingsv3, teamgamelog

from nba_mcp.api.advanced_stats import (
    get_team_advanced_stats as fetch_team_advanced_stats,
)
from nba_mcp.api.entity_resolver import resolve_entity
from nba_mcp.api.errors import (
    EntityNotFoundError,
    InvalidParameterError,
    NBAApiError,
    PartialDataError,
    retry_with_backoff,
)
from nba_mcp.api.tools.nba_api_client import NBAApiClient
from nba_mcp.api.tools.nba_api_utils import normalize_season

logger = logging.getLogger(__name__)

# Component Fetchers

@retry_with_backoff(max_retries=3)
async def fetch_standings_context(
    team1_id: int, team2_id: int, season: str
) -> Dict[str, Any]:
    """
    Fetch standings for both teams.

    Uses NBA API leaguestandingsv3 endpoint to get current standings.

    Args:
        team1_id: First team ID
        team2_id: Second team ID
        season: Season in YYYY-YY format (e.g., "2023-24")

    Returns:
        {
            "team1": {
                "wins": int,
                "losses": int,
                "win_pct": float,
                "conference_rank": int,
                "division_rank": int,
                "games_behind": float,
                "conference": str,
                "division": str
            },
            "team2": {...}
        }

    Raises:
        NBAApiError: If API call fails
    """
    try:
        logger.info(f"Fetching standings for teams {team1_id}, {team2_id} - {season}")

        # Fetch league standings
        standings_response = leaguestandingsv3.LeagueStandingsV3(season=season)
        standings_df = standings_response.get_data_frames()[0]

        # Find team rows
        team1_row = standings_df[standings_df["TeamID"] == team1_id]
        team2_row = standings_df[standings_df["TeamID"] == team2_id]

        if team1_row.empty or team2_row.empty:
            logger.warning(f"Missing standings data for teams {team1_id} or {team2_id}")
            return {}

        def extract_team_standings(row: pd.Series) -> Dict[str, Any]:
            """Extract standings data from DataFrame row."""
            return {
                "wins": int(row["WINS"].iloc[0]) if "WINS" in row else 0,
                "losses": int(row["LOSSES"].iloc[0]) if "LOSSES" in row else 0,
                "win_pct": float(row["WinPCT"].iloc[0]) if "WinPCT" in row else 0.0,
                "conference_rank": (
                    int(row["Conference"].iloc[0]) if "Conference" in row else 0
                ),
                "division_rank": (
                    int(row["Division"].iloc[0]) if "Division" in row else 0
                ),
                "games_behind": (
                    float(row["STANDINGSDATE"].iloc[0])
                    if "STANDINGSDATE" in row
                    else 0.0
                ),
                "conference": (
                    str(row["ConferenceRecord"].iloc[0])
                    if "ConferenceRecord" in row
                    else ""
                ),
                "division": (
                    str(row["DivisionRecord"].iloc[0])
                    if "DivisionRecord" in row
                    else ""
                ),
            }

        result = {
            "team1": extract_team_standings(team1_row),
            "team2": extract_team_standings(team2_row),
        }

        logger.info(
            f"Standings: Team1 {result['team1']['wins']}-{result['team1']['losses']}, "
            f"Team2 {result['team2']['wins']}-{result['team2']['losses']}"
        )
        return result

    except Exception as e:
        logger.error(f"Error fetching standings: {e}")
        raise NBAApiError(
            message=f"Failed to fetch standings: {str(e)}",
            status_code=getattr(e, "status_code", None),
            endpoint="leaguestandingsv3",
        )

@retry_with_backoff(max_retries=3)
async def fetch_advanced_stats_context(
    team1_id: int, team2_id: int, season: str
) -> Dict[str, Any]:
    """
    Fetch advanced stats for both teams.

    Reuses existing get_team_advanced_stats function.

    Args:
        team1_id: First team ID
        team2_id: Second team ID
        season: Season in YYYY-YY format

    Returns:
        {
            "team1": {
                "off_rtg": float,
                "def_rtg": float,
                "net_rtg": float,
                "pace": float,
                "ts_pct": float
            },
            "team2": {...}
        }

    Raises:
        NBAApiError: If API call fails
    """
    try:
        logger.info(
            f"Fetching advanced stats for teams {team1_id}, {team2_id} - {season}"
        )

        # Fetch advanced stats for both teams in parallel
        team1_stats_task = fetch_team_advanced_stats(team1_id, season)
        team2_stats_task = fetch_team_advanced_stats(team2_id, season)

        team1_stats, team2_stats = await asyncio.gather(
            team1_stats_task, team2_stats_task, return_exceptions=True
        )

        # Handle exceptions
        if isinstance(team1_stats, Exception):
            logger.warning(f"Team1 advanced stats failed: {team1_stats}")
            team1_stats = {}
        if isinstance(team2_stats, Exception):
            logger.warning(f"Team2 advanced stats failed: {team2_stats}")
            team2_stats = {}

        result = {"team1": team1_stats, "team2": team2_stats}

        logger.info(
            f"Advanced stats: Team1 NetRtg={team1_stats.get('net_rtg', 0):.1f}, "
            f"Team2 NetRtg={team2_stats.get('net_rtg', 0):.1f}"
        )
        return result

    except Exception as e:
        logger.error(f"Error fetching advanced stats: {e}")
        raise NBAApiError(
            message=f"Failed to fetch advanced stats: {str(e)}",
            status_code=getattr(e, "status_code", None),
            endpoint="teamdashboardbygeneralsplits",
        )

@retry_with_backoff(max_retries=3)
async def fetch_recent_form(
    team_id: int, season: str, last_n: int = 10
) -> Dict[str, Any]:
    """
    Fetch recent game results for a team.

    Uses teamgamelog endpoint to get last N games.

    Args:
        team_id: Team ID
        season: Season in YYYY-YY format
        last_n: Number of recent games to fetch (default: 10)

    Returns:
        {
            "wins": int,
            "losses": int,
            "record": str (e.g., "7-3"),
            "streak": {
                "type": "W" or "L",
                "length": int
            },
            "games": List[Dict] (last N games with results)
        }

    Raises:
        NBAApiError: If API call fails
    """
    try:
        logger.info(f"Fetching recent form for team {team_id} - last {last_n} games")

        # Fetch team game log
        game_log = teamgamelog.TeamGameLog(team_id=team_id, season=season)
        df = game_log.get_data_frames()[0]

        if df.empty:
            logger.warning(f"No game log data for team {team_id}")
            return {
                "wins": 0,
                "losses": 0,
                "record": "0-0",
                "streak": {"type": "N/A", "length": 0},
                "games": [],
            }

        # Get last N games (most recent first)
        recent_games = df.head(last_n)

        # Calculate record
        wins = (recent_games["WL"] == "W").sum()
        losses = (recent_games["WL"] == "L").sum()

        # Calculate streak (most recent games)
        streak_type = recent_games["WL"].iloc[0] if not recent_games.empty else "N/A"
        streak_length = 1
        for i in range(1, len(recent_games)):
            if recent_games["WL"].iloc[i] == streak_type:
                streak_length += 1
            else:
                break

        # Build games list
        games = []
        for _, game in recent_games.iterrows():
            games.append(
                {
                    "date": str(game.get("GAME_DATE", "")),
                    "opponent": str(game.get("MATCHUP", "")),
                    "result": str(game.get("WL", "")),
                    "score": f"{game.get('PTS', 0)}-{game.get('PTS', 0)}",  # Simplified
                }
            )

        result = {
            "wins": int(wins),
            "losses": int(losses),
            "record": f"{wins}-{losses}",
            "streak": {"type": str(streak_type), "length": int(streak_length)},
            "games": games,
        }

        logger.info(f"Recent form: {result['record']} ({streak_type} {streak_length})")
        return result

    except Exception as e:
        logger.error(f"Error fetching recent form: {e}")
        raise NBAApiError(
            message=f"Failed to fetch recent form: {str(e)}",
            status_code=getattr(e, "status_code", None),
            endpoint="teamgamelog",
        )

@retry_with_backoff(max_retries=3)
async def fetch_head_to_head(
    team1_id: int, team2_id: int, team1_abbrev: str, team2_abbrev: str, season: str
) -> Dict[str, Any]:
    """
    Calculate head-to-head record this season.

    Algorithm:
    1. Fetch team1's game log
    2. Filter for games vs team2 (using MATCHUP field)
    3. Calculate W-L record

    Args:
        team1_id: First team ID
        team2_id: Second team ID
        team1_abbrev: Team1 abbreviation (e.g., "LAL") for matching
        team2_abbrev: Team2 abbreviation (e.g., "GSW") for matching
        season: Season in YYYY-YY format

    Returns:
        {
            "team1_wins": int,
            "team2_wins": int,
            "games_played": int,
            "series_status": str (e.g., "Lakers lead 2-1"),
            "games": List[Dict] (all h2h games this season)
        }

    Returns empty dict if no games played yet.

    Raises:
        NBAApiError: If API call fails
    """
    try:
        logger.info(
            f"Fetching head-to-head: {team1_abbrev} vs {team2_abbrev} - {season}"
        )

        # Fetch team1's game log
        game_log = teamgamelog.TeamGameLog(team_id=team1_id, season=season)
        df = game_log.get_data_frames()[0]

        if df.empty:
            logger.warning(f"No game log for team {team1_id}")
            return {}

        # Filter for games against team2 (check if team2_abbrev in MATCHUP)
        h2h_mask = df["MATCHUP"].str.contains(team2_abbrev, case=False, na=False)
        h2h_games = df[h2h_mask]

        if h2h_games.empty:
            logger.info(
                f"No head-to-head games yet between {team1_abbrev} and {team2_abbrev}"
            )
            return {
                "team1_wins": 0,
                "team2_wins": 0,
                "games_played": 0,
                "series_status": "No games played yet",
                "games": [],
            }

        # Calculate record
        team1_wins = (h2h_games["WL"] == "W").sum()
        team2_wins = (h2h_games["WL"] == "L").sum()
        games_played = len(h2h_games)

        # Series status
        if team1_wins > team2_wins:
            series_status = f"{team1_abbrev} leads {team1_wins}-{team2_wins}"
        elif team2_wins > team1_wins:
            series_status = f"{team2_abbrev} leads {team2_wins}-{team1_wins}"
        else:
            series_status = f"Series tied {team1_wins}-{team2_wins}"

        # Build games list
        games = []
        for _, game in h2h_games.iterrows():
            games.append(
                {
                    "date": str(game.get("GAME_DATE", "")),
                    "matchup": str(game.get("MATCHUP", "")),
                    "result": str(game.get("WL", "")),
                    "score": f"{game.get('PTS', 0)}-{game.get('PTS', 0)}",
                }
            )

        result = {
            "team1_wins": int(team1_wins),
            "team2_wins": int(team2_wins),
            "games_played": int(games_played),
            "series_status": series_status,
            "games": games,
        }

        logger.info(f"Head-to-head: {series_status}")
        return result

    except Exception as e:
        logger.error(f"Error fetching head-to-head: {e}")
        raise NBAApiError(
            message=f"Failed to fetch head-to-head: {str(e)}",
            status_code=getattr(e, "status_code", None),
            endpoint="teamgamelog",
        )

# Narrative Synthesis

def synthesize_narrative(
    team1_name: str,
    team2_name: str,
    standings: Dict[str, Any],
    advanced: Dict[str, Any],
    form1: Dict[str, Any],
    form2: Dict[str, Any],
    h2h: Dict[str, Any],
) -> str:
    """
    Synthesize game context into readable markdown narrative.

    Creates structured narrative with sections:
    1. Matchup header (ranks, records)
    2. Season series (h2h record)
    3. Recent form (last 10 games, streaks)
    4. Statistical edge (net rating comparison)
    5. Key storylines (auto-generated)

    Args:
        team1_name: First team name
        team2_name: Second team name
        standings: Standings context dict
        advanced: Advanced stats context dict
        form1: Team1 recent form dict
        form2: Team2 recent form dict
        h2h: Head-to-head dict

    Returns:
        Markdown-formatted narrative string

    Example Output:
        # Lakers (34-28, 9th West) vs Warriors (32-30, 10th West)

        ## Season Series
        Series tied 2-2

        ## Recent Form
        - Lakers: 7-3 in last 10 (Won 3)
        - Warriors: 4-6 in last 10 (Lost 2)

        ## Statistical Edge
        Lakers hold +3.5 Net Rating advantage
        - Lakers: +2.1 NetRtg (112.5 OffRtg / 110.4 DefRtg)
        - Warriors: -1.4 NetRtg (111.2 OffRtg / 112.6 DefRtg)

        ## Key Storylines
        - Lakers on 3-game win streak
        - Warriors struggling defensively (112.6 DefRtg)
    """
    logger.info(f"Synthesizing narrative for {team1_name} vs {team2_name}")

    narrative_lines = []

    # 1. Matchup Header
    team1_record = standings.get("team1", {})
    team2_record = standings.get("team2", {})

    team1_wins = team1_record.get("wins", 0)
    team1_losses = team1_record.get("losses", 0)
    team1_rank = team1_record.get("conference_rank", "")

    team2_wins = team2_record.get("wins", 0)
    team2_losses = team2_record.get("losses", 0)
    team2_rank = team2_record.get("conference_rank", "")

    narrative_lines.append(
        f"# {team1_name} ({team1_wins}-{team1_losses}, #{team1_rank}) vs "
        f"{team2_name} ({team2_wins}-{team2_losses}, #{team2_rank})"
    )
    narrative_lines.append("")

    # 2. Season Series
    if h2h and h2h.get("games_played", 0) > 0:
        narrative_lines.append("## Season Series")
        narrative_lines.append(h2h.get("series_status", "No games played yet"))
        narrative_lines.append("")
    else:
        narrative_lines.append("## Season Series")
        narrative_lines.append("No games played yet this season")
        narrative_lines.append("")

    # 3. Recent Form
    narrative_lines.append("## Recent Form")
    if form1:
        streak1 = form1.get("streak", {})
        narrative_lines.append(
            f"- {team1_name}: {form1.get('record', '0-0')} in last 10 "
            f"({'Won' if streak1.get('type') == 'W' else 'Lost'} {streak1.get('length', 0)})"
        )
    if form2:
        streak2 = form2.get("streak", {})
        narrative_lines.append(
            f"- {team2_name}: {form2.get('record', '0-0')} in last 10 "
            f"({'Won' if streak2.get('type') == 'W' else 'Lost'} {streak2.get('length', 0)})"
        )
    narrative_lines.append("")

    # 4. Statistical Edge
    narrative_lines.append("## Statistical Edge")
    team1_adv = advanced.get("team1", {})
    team2_adv = advanced.get("team2", {})

    team1_net = team1_adv.get("net_rtg", 0)
    team2_net = team2_adv.get("net_rtg", 0)
    net_diff = team1_net - team2_net

    if abs(net_diff) > 1.0:
        leader = team1_name if net_diff > 0 else team2_name
        narrative_lines.append(
            f"{leader} holds {abs(net_diff):+.1f} Net Rating advantage"
        )
    else:
        narrative_lines.append("Teams statistically even in Net Rating")

    if team1_adv:
        narrative_lines.append(
            f"- {team1_name}: {team1_net:+.1f} NetRtg "
            f"({team1_adv.get('off_rtg', 0):.1f} OffRtg / {team1_adv.get('def_rtg', 0):.1f} DefRtg)"
        )
    if team2_adv:
        narrative_lines.append(
            f"- {team2_name}: {team2_net:+.1f} NetRtg "
            f"({team2_adv.get('off_rtg', 0):.1f} OffRtg / {team2_adv.get('def_rtg', 0):.1f} DefRtg)"
        )
    narrative_lines.append("")

    # 5. Key Storylines (auto-generated)
    narrative_lines.append("## Key Storylines")
    storylines = []

    # Check for win streaks
    if (
        form1.get("streak", {}).get("type") == "W"
        and form1.get("streak", {}).get("length", 0) >= 3
    ):
        storylines.append(
            f"- {team1_name} on {form1['streak']['length']}-game win streak"
        )
    if (
        form2.get("streak", {}).get("type") == "W"
        and form2.get("streak", {}).get("length", 0) >= 3
    ):
        storylines.append(
            f"- {team2_name} on {form2['streak']['length']}-game win streak"
        )

    # Check for losing streaks
    if (
        form1.get("streak", {}).get("type") == "L"
        and form1.get("streak", {}).get("length", 0) >= 3
    ):
        storylines.append(
            f"- {team1_name} lost {form1['streak']['length']} straight games"
        )
    if (
        form2.get("streak", {}).get("type") == "L"
        and form2.get("streak", {}).get("length", 0) >= 3
    ):
        storylines.append(
            f"- {team2_name} lost {form2['streak']['length']} straight games"
        )

    # Check for defensive struggles
    if team1_adv.get("def_rtg", 0) > 115:
        storylines.append(
            f"- {team1_name} struggling defensively ({team1_adv['def_rtg']:.1f} DefRtg)"
        )
    if team2_adv.get("def_rtg", 0) > 115:
        storylines.append(
            f"- {team2_name} struggling defensively ({team2_adv['def_rtg']:.1f} DefRtg)"
        )

    # Check for offensive excellence
    if team1_adv.get("off_rtg", 0) > 118:
        storylines.append(
            f"- {team1_name} elite offense ({team1_adv['off_rtg']:.1f} OffRtg)"
        )
    if team2_adv.get("off_rtg", 0) > 118:
        storylines.append(
            f"- {team2_name} elite offense ({team2_adv['off_rtg']:.1f} OffRtg)"
        )

    if not storylines:
        storylines.append("- Both teams evenly matched entering this matchup")

    narrative_lines.extend(storylines)

    return "\n".join(narrative_lines)

# Main Entry Point

async def get_game_context(
    team1_name: str,
    team2_name: str,
    season: Optional[str] = None,
    date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get comprehensive game context for a matchup.

    Fetches data from multiple sources in parallel:
    1. Team standings (both teams)
    2. Team advanced stats (both teams)
    3. Recent form (last 10 games, both teams)
    4. Head-to-head record (this season)

    Then synthesizes into narrative summary.

    Args:
        team1_name: First team name (fuzzy matching supported)
        team2_name: Second team name (fuzzy matching supported)
        season: Season in YYYY-YY format (defaults to current)
        date: Date in YYYY-MM-DD format (for future use, not yet implemented)

    Returns:
        {
            "matchup": {
                "team1": {"name": str, "id": int, "abbreviation": str},
                "team2": {"name": str, "id": int, "abbreviation": str}
            },
            "standings": Dict,
            "advanced_stats": Dict,
            "recent_form": {
                "team1": Dict,
                "team2": Dict
            },
            "head_to_head": Dict,
            "narrative": str (markdown formatted),
            "metadata": {
                "season": str,
                "components_loaded": List[str],
                "components_failed": List[str]
            }
        }

    Raises:
        EntityNotFoundError: If team not found
        PartialDataError: If some components fail (still returns partial context)

    Note: Uses asyncio.gather with return_exceptions=True for graceful degradation
    """
    # Normalize season
    normalized_seasons = normalize_season(season)
    if normalized_seasons is None:
        # Use current season if None provided
        client = NBAApiClient()
        season_str = client.get_season_string()
    elif isinstance(normalized_seasons, list):
        season_str = normalized_seasons[0]  # Take first season
    else:
        season_str = normalized_seasons

    logger.info(
        f"Fetching game context: {team1_name} vs {team2_name} - Season: {season_str}"
    )

    # Resolve teams
    team1 = resolve_entity(query=team1_name, entity_type="team")
    team2 = resolve_entity(query=team2_name, entity_type="team")

    logger.info(
        f"Resolved teams: {team1.name} (ID: {team1.entity_id}) vs {team2.name} (ID: {team2.entity_id})"
    )

    # Fetch all components in parallel (4-6 API calls)
    components_loaded = []
    components_failed = []

    try:
        # Execute parallel fetches with graceful degradation
        results = await asyncio.gather(
            fetch_standings_context(team1.entity_id, team2.entity_id, season_str),
            fetch_advanced_stats_context(team1.entity_id, team2.entity_id, season_str),
            fetch_recent_form(team1.entity_id, season_str, last_n=10),
            fetch_recent_form(team2.entity_id, season_str, last_n=10),
            fetch_head_to_head(
                team1.entity_id,
                team2.entity_id,
                team1.name[:3].upper(),  # Abbreviation guess
                team2.name[:3].upper(),
                season_str,
            ),
            return_exceptions=True,
        )

        # Unpack results
        standings = results[0] if not isinstance(results[0], Exception) else {}
        advanced_stats = results[1] if not isinstance(results[1], Exception) else {}
        form1 = results[2] if not isinstance(results[2], Exception) else {}
        form2 = results[3] if not isinstance(results[3], Exception) else {}
        h2h = results[4] if not isinstance(results[4], Exception) else {}

        # Track component status
        if not isinstance(results[0], Exception):
            components_loaded.append("standings")
        else:
            components_failed.append("standings")
            logger.warning(f"Standings component failed: {results[0]}")

        if not isinstance(results[1], Exception):
            components_loaded.append("advanced_stats")
        else:
            components_failed.append("advanced_stats")
            logger.warning(f"Advanced stats component failed: {results[1]}")

        if not isinstance(results[2], Exception):
            components_loaded.append("team1_recent_form")
        else:
            components_failed.append("team1_recent_form")
            logger.warning(f"Team1 recent form failed: {results[2]}")

        if not isinstance(results[3], Exception):
            components_loaded.append("team2_recent_form")
        else:
            components_failed.append("team2_recent_form")
            logger.warning(f"Team2 recent form failed: {results[3]}")

        if not isinstance(results[4], Exception):
            components_loaded.append("head_to_head")
        else:
            components_failed.append("head_to_head")
            logger.warning(f"Head-to-head component failed: {results[4]}")

        # Synthesize narrative
        narrative = synthesize_narrative(
            team1_name=team1.name,
            team2_name=team2.name,
            standings=standings,
            advanced=advanced_stats,
            form1=form1,
            form2=form2,
            h2h=h2h,
        )

        # Build response
        result = {
            "matchup": {
                "team1": {
                    "name": team1.name,
                    "id": team1.entity_id,
                    "abbreviation": team1.name[:3].upper(),
                },
                "team2": {
                    "name": team2.name,
                    "id": team2.entity_id,
                    "abbreviation": team2.name[:3].upper(),
                },
            },
            "standings": standings,
            "advanced_stats": advanced_stats,
            "recent_form": {"team1": form1, "team2": form2},
            "head_to_head": h2h,
            "narrative": narrative,
            "metadata": {
                "season": season_str,
                "components_loaded": components_loaded,
                "components_failed": components_failed,
            },
        }

        logger.info(
            f"Game context complete: {len(components_loaded)} components loaded, {len(components_failed)} failed"
        )
        return result

    except Exception as e:
        logger.exception("Fatal error in get_game_context")
        raise NBAApiError(
            message=f"Failed to fetch game context: {str(e)}",
            status_code=getattr(e, "status_code", None),
            endpoint="game_context",
        )
