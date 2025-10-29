# nba_mcp\nba_server.py
# near the top of nba_server.py
import argparse
import json
import os
import sys
import time
import traceback
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from fastmcp import Context
from mcp.server.fastmcp import FastMCP
from nba_api.live.nba.endpoints.scoreboard import ScoreBoard
from nba_api.stats.static import players, teams

# nba_server.py (add near the top)
from pydantic import BaseModel, Field

from nba_mcp.api.client import NBAApiClient
from nba_mcp.api.entity_resolver import (
    get_cache_info,
    resolve_entity,
    suggest_players,
    suggest_teams,
)
from nba_mcp.api.errors import (
    EntityNotFoundError,
    InvalidParameterError,
    NBAMCPError,
    RateLimitError,
    get_circuit_breaker,
    retry_with_backoff,
)

# Import Phase 3 feature modules (shot charts, game context)
from nba_mcp.api.game_context import get_game_context as fetch_game_context

# Import new response models and error handling
from nba_mcp.api.models import (
    EntityReference,
    PlayerComparison,
    PlayerSeasonStats,
    ResponseEnvelope,
    TeamStanding,
    error_response,
    partial_response,
    success_response,
)
from nba_mcp.api.shot_charts import get_shot_chart as fetch_shot_chart
from nba_mcp.api.tools.nba_api_utils import (
    format_game,
    get_player_id,
    get_player_name,
    get_static_lookup_schema,
    get_team_id,
    get_team_name,
    normalize_date,
    normalize_per_mode,
    normalize_season,
    normalize_stat_category,
)

# Import dataset and joins features
from nba_mcp.data.catalog import get_catalog
from nba_mcp.data.dataset_manager import get_manager as get_dataset_manager, initialize_manager, shutdown_manager
from nba_mcp.data.fetch import fetch_endpoint, validate_parameters
from nba_mcp.data.joins import join_tables, join_with_stats, filter_table

# Import Week 4 infrastructure (cache + rate limiting)
from nba_mcp.cache.redis_cache import CacheTier, cached, get_cache, initialize_cache

# Import NLQ pipeline components
from nba_mcp.nlq.pipeline import answer_nba_question as nlq_answer_question
from nba_mcp.nlq.pipeline import (
    get_pipeline_status,
)
from nba_mcp.nlq.tool_registry import initialize_tool_registry

# Import Week 4 observability (metrics + tracing)
from nba_mcp.observability import (
    get_metrics_manager,
    get_tracing_manager,
    initialize_metrics,
    initialize_tracing,
    track_metrics,
    update_infrastructure_metrics,
)
from nba_mcp.rate_limit.token_bucket import (
    get_rate_limiter,
    initialize_rate_limiter,
    rate_limited,
)

# only grab "--mode" here and ignore any other flags
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument(
    "--mode",
    choices=["claude", "local"],
    default="claude",
    help="Which port profile to use",
)
args, _ = parser.parse_known_args()

if args.mode == "claude":
    BASE_PORT = int(os.getenv("NBA_MCP_PORT", "8000"))
else:
    BASE_PORT = int(os.getenv("NBA_MCP_PORT", "8001"))

# python nba_server.py --mode local       # runs on 8001
# python nba_server.py --mode claude      # runs on 8000


# import logger
import logging

logger = logging.getLogger(__name__)


# ── 1) Read configuration up‑front ────────────────────────
HOST = os.getenv("FASTMCP_SSE_HOST", "0.0.0.0")
PATH = os.getenv("FASTMCP_SSE_PATH", "/sse")

# Team to conference mapping (2024-25 season)
TEAM_TO_CONFERENCE = {
    # Eastern Conference
    "ATL": "East", "BOS": "East", "BKN": "East", "CHA": "East", "CHI": "East",
    "CLE": "East", "DET": "East", "IND": "East", "MIA": "East", "MIL": "East",
    "NYK": "East", "ORL": "East", "PHI": "East", "TOR": "East", "WAS": "East",
    # Western Conference
    "DAL": "West", "DEN": "West", "GSW": "West", "HOU": "West", "LAC": "West",
    "LAL": "West", "MEM": "West", "MIN": "West", "NOP": "West", "OKC": "West",
    "PHX": "West", "POR": "West", "SAC": "West", "SAS": "West", "UTA": "West",
}

# ── 2) Create the global server instance for decorator registration ──
mcp_server = FastMCP(name="nba_mcp", host=HOST, port=BASE_PORT)

# ===== ONE‑LINE ADDITION =====
mcp = mcp_server  # Alias so the FastMCP CLI can auto‑discover the server
import socket


def port_available(port: int, host: str = HOST) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        # On Windows, exclusive use prevents collisions
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


from typing import Literal

from pydantic import BaseModel, Field


class LeagueLeadersParams(BaseModel):
    season: Optional[Union[str, List[str]]] = Field(
        None, description="Season in 'YYYY-YY' format or list thereof"
    )
    stat_category: Literal[
        "PTS", "REB", "AST", "STL", "BLK", "FG_PCT", "FG3_PCT", "FT_PCT"
    ] = Field(..., description="Stat code (e.g. 'AST')")
    per_mode: Literal["Totals", "PerGame", "Per48"] = Field(
        ..., description="One of 'Totals', 'PerGame', or 'Per48'"
    )


# ── 3) Load & cache both JSON files once ───────────────────
from pathlib import Path

# Possible locations for documentation files:
_project_root = Path(__file__).resolve().parents[1]
_root_docs = _project_root / "api_documentation"
_pkg_docs = Path(__file__).resolve().parent / "api_documentation"


def _load_cached(filename: str) -> str:
    for base in (_root_docs, _pkg_docs):
        candidate = base / filename
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8")
                # quick validation
                json.loads(text)
                logger.info("Loaded %s from %s", filename, candidate)
                return text
            except Exception as e:
                logger.error("Error parsing %s: %s", candidate, e)
                break
    logger.error(
        "Failed to load %s from either %s or %s", filename, _root_docs, _pkg_docs
    )
    sys.exit(1)


_CACHED_OPENAPI = _load_cached("endpoints.json")
_CACHED_STATIC = _load_cached("static_data.json")


#########################################
# MCP Resources
#########################################
# ── 4) Serve endpoints.json as the OpenAPI spec ────────────
@mcp_server.resource("api-docs://openapi.json")
async def get_openapi_spec() -> str:
    # Use logger.debug instead of printing to stderr
    logger.debug("Serving cached OpenAPI endpoints.json")
    return _CACHED_OPENAPI


@mcp_server.resource("api-docs://static_data.json")
async def get_static_data() -> str:
    logger.debug("Serving cached static_data.json")
    return _CACHED_STATIC


# ── in nba_server.py, alongside your existing @mcp_server.resource defs ──


@mcp_server.resource("nba://player/{player_name}/career/{season}")
async def player_career_stats_resource(player_name: str, season: str):
    """
    Returns raw JSON records (list of dicts) for a player’s career stats in a season.
    """
    client = NBAApiClient()
    # always return list-of‑records
    result = await client.get_player_career_stats(
        player_name, season, as_dataframe=False
    )
    # If error came back as dict, re‑raise it to the client
    if isinstance(result, dict) and "error" in result:
        return result
    # If a friendlier message string came back, wrap it
    if isinstance(result, str):
        return {"message": result}
    # Otherwise it's already a list of dicts
    return {"data": result}


@mcp_server.resource("nba://league/leaders/{stat_category}/{per_mode}/{season}")
async def league_leaders_resource(stat_category: str, per_mode: str, season: str):
    """
    Returns top-10 league leaders as JSON for given season, stat_category, per_mode.
    """
    client = NBAApiClient()
    data = await client.get_league_leaders(
        season=season,
        stat_category=stat_category,
        per_mode=per_mode,
        as_dataframe=False,
    )
    if isinstance(data, str):
        return {"message": data}
    return {"data": data[:10]}


@mcp_server.resource("nba://scores/{target_date}")
async def live_scores_resource(target_date: str):
    """
    Returns live or historical NBA scores for a date as JSON.
    """
    client = NBAApiClient()
    result = await client.get_live_scoreboard(
        target_date=target_date, as_dataframe=False
    )
    if isinstance(result, str):
        return {"message": result}
    return {"data": result}


@mcp_server.resource("nba://games-v2/{game_date}")
async def games_by_date_resource(game_date: str):
    """
    Returns list of games+scores from ScoreboardV2 for a date.
    """
    client = NBAApiClient()
    data = await client.get_games_by_date(target_date=game_date, as_dataframe=False)
    if isinstance(data, dict) and "error" in data:
        return data
    return data


@mcp_server.resource(
    "nba://playbyplay/"
    "{game_date}/"
    "{team}/"
    "{start_period}/"
    "{end_period}/"
    "{start_clock}/"
    "{recent_n}/"
    "{max_lines}"
)
async def playbyplay_resource(
    game_date: str,
    team: str,
    start_period: int = 1,
    end_period: int = 4,
    start_clock: Optional[str] = None,
    recent_n: int = 5,
    max_lines: int = 200,
) -> Dict[str, Any]:
    """
    Unified MCP resource: returns play-by-play Markdown for a given date and team,
    with full control over live vs historical behavior.

    **Path format:**
      `nba://playbyplay/{game_date}/{team}/{start_period}/{end_period}/{start_clock}/{recent_n}/{max_lines}`

    **Parameters (all via path segments):**
      - `game_date` (str): YYYY‑MM‑DD. For live/pregame, use today’s date.
      - `team` (str): Team name or abbreviation (e.g. "Lakers").
      - `start_period` (int): Starting quarter for historical output (1–4).
      - `end_period` (int): Ending quarter for historical output (1–4).
      - `start_clock` (str): Clock ("MM:SS") to begin historical output, or `"None"`.
      - `recent_n` (int): How many recent live plays to include.
      - `max_lines` (int): Max total lines of Markdown to return.

    Internally delegates to your `NBAApiClient.get_play_by_play` method.
    """
    client = NBAApiClient()
    md = await client.get_play_by_play(
        game_date=game_date,
        team=team,
        start_period=start_period,
        end_period=end_period,
        start_clock=None if start_clock in ("", "None") else start_clock,
        recent_n=recent_n,
        max_lines=max_lines,
    )
    return {"markdown": md}


#########################################
# MCP Tools
#########################################


@mcp_server.tool()
async def resolve_nba_entity(
    query: str,
    entity_type: Optional[Literal["player", "team"]] = None,
    return_suggestions: bool = True,
) -> str:
    """
    Universal entity resolver with fuzzy matching and confidence scoring.

    Resolves ambiguous player/team names to specific entities with:
    - Fuzzy string matching
    - Confidence scores (0.0-1.0)
    - Alternative name suggestions
    - Cached lookups (LRU cache, 1000 entries)

    Args:
        query: Player or team name (supports partial names, abbreviations, nicknames)
        entity_type: Optional filter ("player" or "team"). If None, searches both.
        return_suggestions: If True, returns suggestions when no exact match found

    Returns:
        JSON string with resolved entity details:
        - entity_type: "player" or "team"
        - entity_id: NBA API ID
        - name: Full canonical name
        - abbreviation: Team abbreviation (teams only)
        - confidence: Match confidence (0.0-1.0)
        - alternate_names: List of nicknames/abbreviations
        - metadata: Additional entity info

    Examples:
        resolve_nba_entity("LeBron") → LeBron James (confidence: 0.95)
        resolve_nba_entity("LAL", entity_type="team") → Los Angeles Lakers (confidence: 1.0)
        resolve_nba_entity("Durant") → Kevin Durant (confidence: 0.9)

    Raises:
        EntityNotFoundError: If no match found (includes suggestions if available)
    """
    start_time = time.time()

    try:
        # Resolve entity using fuzzy matching
        entity_ref = resolve_entity(
            query=query,
            entity_type=entity_type,
            min_confidence=0.6,
            return_suggestions=return_suggestions,
            max_suggestions=5,
        )

        # Calculate execution time
        execution_time_ms = (time.time() - start_time) * 1000

        # Return success response with entity data
        response = success_response(
            data=entity_ref.model_dump(),
            source="static",
            cache_status="hit",  # LRU cached
            execution_time_ms=execution_time_ms,
        )

        return response.to_json_string()

    except EntityNotFoundError as e:
        # Entity not found - return error with suggestions
        response = error_response(
            error_code=e.code, error_message=e.message, details=e.details
        )
        return response.to_json_string()

    except Exception as e:
        # Unexpected error
        logger.exception("Unexpected error in resolve_nba_entity")
        response = error_response(
            error_code="INTERNAL_ERROR",
            error_message=f"Failed to resolve entity: {str(e)}",
        )
        return response.to_json_string()


@mcp_server.tool()
async def get_player_career_information(
    player_name: str, season: Optional[str] = None
) -> str:
    logger.debug("get_player_career_information('%s', season=%s)", player_name, season)
    client = NBAApiClient()
    season_str = season or client.get_season_string()

    try:
        # 1) Fetch
        result = await client.get_player_career_stats(
            player_name, season_str, as_dataframe=True
        )
        logger.debug("Raw result type: %s, value: %r", type(result), result)

        # 2) If the client returned an error dict, propagate it
        if isinstance(result, dict) and "error" in result:
            logger.error("API error payload: %s", result)
            return result["error"]

        # 3) If it returned a string (no data / user-friendly), pass it back
        if isinstance(result, str):
            return result

        # 4) If it's not a DataFrame, we have an unexpected payload
        if not isinstance(result, pd.DataFrame):
            logger.error("Unexpected payload type (not DataFrame): %s", type(result))
            return (
                f"Unexpected response format from API tool: "
                f"{type(result).__name__}. Please check server logs."
            )

        # 5) Now we can safely treat it as a DataFrame
        df: pd.DataFrame = result
        if df.empty:
            return f"No career stats found for '{player_name}' in {season_str}."

        # 6) Format a more detailed response with proper stats
        if len(df) == 1:
            # Single season data
            row = df.iloc[0]
            team = row.get("TEAM_ABBREVIATION", "N/A")
            return "\n".join(
                [
                    f"Player: {player_name}",
                    f"Season: {season_str} ({team})",
                    f"Games Played: {row.get('GP', 'N/A')}",
                    f"Minutes Per Game: {row.get('MIN', 'N/A')}",
                    f"Points Per Game: {row.get('PTS', 'N/A')}",
                    f"Rebounds Per Game: {row.get('REB', 'N/A')}",
                    f"Assists Per Game: {row.get('AST', 'N/A')}",
                    f"Steals Per Game: {row.get('STL', 'N/A')}",
                    f"Blocks Per Game: {row.get('BLK', 'N/A')}",
                    f"Field Goal %: {row.get('FG_PCT', 'N/A')}",
                    f"3-Point %: {row.get('FG3_PCT', 'N/A')}",
                    f"Free Throw %: {row.get('FT_PCT', 'N/A')}",
                ]
            )
        else:
            # Multiple seasons - provide a career summary
            # Find the earliest and latest seasons
            if "SEASON_ID" in df.columns:
                seasons = sorted(df["SEASON_ID"].unique())
                season_range = (
                    f"{seasons[0]} to {seasons[-1]}" if seasons else "unknown"
                )
            else:
                season_range = "unknown"

            # Count total games and calculate career averages
            total_games = df["GP"].sum() if "GP" in df.columns else "N/A"

            # Build response with career averages
            return "\n".join(
                [
                    f"Player: {player_name}",
                    f"Seasons: {season_range}",
                    f"Career Games: {total_games}",
                    f"Career Stats:",
                    (
                        f"- Points Per Game: {df['PTS'].mean():.1f}"
                        if "PTS" in df.columns
                        else "- Points Per Game: N/A"
                    ),
                    (
                        f"- Rebounds Per Game: {df['REB'].mean():.1f}"
                        if "REB" in df.columns
                        else "- Rebounds Per Game: N/A"
                    ),
                    (
                        f"- Assists Per Game: {df['AST'].mean():.1f}"
                        if "AST" in df.columns
                        else "- Assists Per Game: N/A"
                    ),
                    (
                        f"- Field Goal %: {df['FG_PCT'].mean():.3f}"
                        if "FG_PCT" in df.columns
                        else "- Field Goal %: N/A"
                    ),
                    (
                        f"- 3-Point %: {df['FG3_PCT'].mean():.3f}"
                        if "FG3_PCT" in df.columns
                        else "- 3-Point %: N/A"
                    ),
                    (
                        f"- Free Throw %: {df['FT_PCT'].mean():.3f}"
                        if "FT_PCT" in df.columns
                        else "- Free Throw %: N/A"
                    ),
                ]
            )

    except Exception as e:
        # 7) Uncaught exception: log full traceback
        logger.exception("Unexpected error in get_player_career_information")
        return f"Unexpected error in get_player_career_information: {e}"


@mcp_server.tool()
async def get_league_leaders_info(
    stat_category: Literal[
        "PTS", "REB", "AST", "STL", "BLK", "FG_PCT", "FG3_PCT", "FT_PCT"
    ],
    season: Optional[Union[str, List[str]]] = None,
    per_mode: Literal["Totals", "PerGame", "Per48"] = "PerGame",
    season_type_all_star: str = "Regular Season",
    limit: int = 10,
    format: Literal["text", "json"] = "text",
    min_games_played: Optional[int] = None,
    conference: Optional[Literal["East", "West"]] = None,
    team: Optional[str] = None,
) -> str:
    """
    Get the league leaders for the requested stat(s) and mode(s).

    Args:
        stat_category: Statistical category (e.g., 'PTS', 'AST', 'REB')
        season: Season in 'YYYY-YY' format or list thereof (None = current season)
        per_mode: Aggregation mode - 'Totals', 'PerGame', or 'Per48'
        season_type_all_star: Season type filter (e.g., 'Regular Season', 'Playoffs')
        limit: Maximum number of leaders to return (default: 10)
        format: Output format - 'text' for human-readable or 'json' for structured data (default: 'text')
        min_games_played: Minimum games played filter (optional)
        conference: Conference filter - 'East' or 'West' (optional)
        team: Team abbreviation filter (e.g., 'LAL', 'BOS') (optional)

    Returns:
        Formatted string with top N leaders (text format) or JSON string with structured data
    """
    # Validate inputs via Pydantic model internally
    params = LeagueLeadersParams(
        season=season,
        stat_category=stat_category,
        per_mode=per_mode
    )

    # Extract validated values
    season = params.season
    stat_category = params.stat_category
    per_mode = params.per_mode

    logger.debug("get_league_leaders_info(stat_category=%s, season=%s, per_mode=%s, season_type=%s)",
                 stat_category, season, per_mode, season_type_all_star)

    client = NBAApiClient()
    result = await client.get_league_leaders(
        season=season,
        stat_category=stat_category,
        per_mode=per_mode,
        season_type_all_star=season_type_all_star,
        as_dataframe=True
    )

    if isinstance(result, str):
        # If result is an error string but JSON format requested, wrap in JSON
        if format == "json":
            from datetime import datetime
            return json.dumps({
                "metadata": {
                    "stat_category": stat_category,
                    "season": season if isinstance(season, str) else list(season) if season else None,
                    "per_mode": per_mode,
                    "season_type": season_type_all_star,
                    "limit": limit,
                    "total_leaders": 0,
                    "query_timestamp": datetime.utcnow().isoformat() + "Z",
                    "error": result
                },
                "leaders": []
            }, indent=2)
        return result

    df: pd.DataFrame = result

    # Apply filters
    if min_games_played is not None:
        if "GP" in df.columns:
            df = df[df["GP"] >= min_games_played]

    if team is not None:
        if "TEAM" in df.columns:
            df = df[df["TEAM"] == team.upper()]

    if conference is not None:
        if "TEAM" in df.columns:
            df = df[df["TEAM"].map(lambda t: TEAM_TO_CONFERENCE.get(t) == conference)]

    if df.empty:
        if format == "json":
            from datetime import datetime
            metadata = {
                "stat_category": stat_category,
                "season": season if isinstance(season, str) else list(season) if season else None,
                "per_mode": per_mode,
                "season_type": season_type_all_star,
                "limit": limit,
                "total_leaders": 0,
                "query_timestamp": datetime.utcnow().isoformat() + "Z"
            }
            if min_games_played is not None:
                metadata["min_games_played"] = min_games_played
            if conference is not None:
                metadata["conference"] = conference
            if team is not None:
                metadata["team"] = team
            return json.dumps({"metadata": metadata, "leaders": []}, indent=2)

        # Build filter description for text format
        filter_desc = []
        if min_games_played is not None:
            filter_desc.append(f"min_games_played={min_games_played}")
        if conference is not None:
            filter_desc.append(f"conference={conference}")
        if team is not None:
            filter_desc.append(f"team={team}")

        filter_str = f" with filters ({', '.join(filter_desc)})" if filter_desc else ""
        return f"No leaders found for '{stat_category}' in season(s) {season}{filter_str}."

    # Return JSON format if requested
    if format == "json":
        from datetime import datetime

        leaders_data = []
        for s, grp in df.groupby("SEASON"):
            for i, (_, r) in enumerate(grp.head(limit).iterrows(), 1):
                leader = {
                    "rank": i,
                    "season": s,
                    "player_id": int(r.get("PLAYER_ID", 0)) if pd.notna(r.get("PLAYER_ID")) else None,
                    "player_name": str(r.get("PLAYER_NAME", r.get("PLAYER", "Unknown"))),
                    "team_id": int(r.get("TEAM_ID", 0)) if pd.notna(r.get("TEAM_ID")) else None,
                    "team": str(r.get("TEAM", r.get("TEAM_ABBREVIATION", "N/A"))),
                    "games_played": int(r.get("GP", 0)) if pd.notna(r.get("GP")) else None,
                    "minutes": float(r.get("MIN", 0)) if pd.notna(r.get("MIN")) else None,
                    "value": float(r.get(stat_category, 0)) if pd.notna(r.get(stat_category)) else None,
                }

                # Add all available stats
                stat_fields = ["FGM", "FGA", "FG_PCT", "FG3M", "FG3A", "FG3_PCT",
                               "FTM", "FTA", "FT_PCT", "OREB", "DREB", "REB",
                               "AST", "STL", "BLK", "TOV", "PTS", "EFF"]
                for field in stat_fields:
                    if field in r.index and pd.notna(r[field]):
                        leader[field.lower()] = float(r[field])

                leaders_data.append(leader)

        metadata = {
            "stat_category": stat_category,
            "season": season if isinstance(season, str) else list(season) if season else None,
            "per_mode": per_mode,
            "season_type": season_type_all_star,
            "limit": limit,
            "total_leaders": len(leaders_data),
            "query_timestamp": datetime.utcnow().isoformat() + "Z"
        }
        # Add filter parameters if specified
        if min_games_played is not None:
            metadata["min_games_played"] = min_games_played
        if conference is not None:
            metadata["conference"] = conference
        if team is not None:
            metadata["team"] = team

        response = {
            "metadata": metadata,
            "leaders": leaders_data
        }
        return json.dumps(response, indent=2)

    # Return text format (default)
    out = []
    for s, grp in df.groupby("SEASON"):
        out.append(f"Top {limit} {stat_category} Leaders ({s}):")
        for i, (_, r) in enumerate(grp.head(limit).iterrows(), 1):
            name = r["PLAYER_NAME"]
            team = r.get("TEAM_NAME", r.get("TEAM_ABBREVIATION", "N/A"))
            stat_cols = [c for c in r.index if stat_category in c]
            value = r[stat_cols[0]] if stat_cols else r.get("STAT_VALUE", "N/A")
            out.append(f"{i}. {name} ({team}): {value}")
        out.append("")
    return "\n".join(out).strip()


@mcp_server.tool()
async def get_live_scores(target_date: Optional[str] = None) -> str:
    """
    Provides live or historical NBA scores for a specified date.

    Parameters:
        target_date (Optional[str]): Date string 'YYYY-MM-DD'; uses today if None.

    Returns:
        str: Formatted game summaries like 'Lakers vs Suns – 102-99 (Final)'.
    """
    client = NBAApiClient()

    # For live scores, pass None to use live API; for historical, use the provided date
    if target_date:
        logger.debug(f"[DEBUG] get_live_scores: Using provided target_date = {target_date} (historical)")
    else:
        logger.debug(f"[DEBUG] get_live_scores: No target_date provided, using live API (target_date=None)")

    try:
        result = await client.get_live_scoreboard(
            target_date=target_date, as_dataframe=False
        )
        # result is either a dict with {date, games} or an error string
        if isinstance(result, str):
            return result

        # Extract date and games from result
        date = result.get("date")
        games = result.get("games", [])

        if not games:
            return f"No games found for {date}."

        # Format each into "Lakers vs Suns – 102-99 (Final)"
        lines = []
        for g in games:
            # Skip if game object is a string (error message)
            if isinstance(g, str):
                logger.warning(f"Skipping invalid game object: {g}")
                continue

            summary = g.get("scoreBoardSummary") or g.get("scoreBoardSnapshot")
            home = summary["homeTeam"]
            away = summary["awayTeam"]

            # Real‑time if the live‑API gave us `teamName`+`score`
            if "teamName" in home:
                home_team = home["teamName"]
                away_team = away["teamName"]
                home_pts = home["score"]
                away_pts = away["score"]
            else:
                # Historical if we got uppercase keys from Stats API
                home_team = home.get("TEAM_ABBREVIATION") or get_team_name(
                    home["TEAM_ID"]
                )
                away_team = away.get("TEAM_ABBREVIATION") or get_team_name(
                    away["TEAM_ID"]
                )
                home_pts = home.get("PTS")
                away_pts = away.get("PTS")

            status = summary.get("gameStatusText", "")
            lines.append(
                f"{home_team} vs {away_team} – {home_pts}-{away_pts} ({status})"
            )

        header = f"NBA Games for {date}:\n"
        return header + "\n".join(lines)

    except Exception as e:
        # Log full traceback via the logger (MCP will strip this out),
        # and return the concise error message to the caller.
        logger.exception("Unexpected error in get_live_scores")
        return f"Unexpected error in get_live_scores: {e}"


# Allowed season types per NBA API; we will always query all
_ALLOWED_SEASON_TYPES = [
    "Regular Season",
    "Playoffs",
    "Pre Season",
    "All Star",
    "All-Star",
]


@mcp_server.tool()
async def get_date_range_game_log_or_team_game_log(
    season: str,
    team: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> str:
    logger.debug(
        "get_date_range_game_log_or_team_game_log(season=%r, team=%r, from=%r, to=%r)",
        season,
        team,
        date_from,
        date_to,
    )

    client = NBAApiClient()
    lines: List[str] = []
    start = date_from or "season start"
    end = date_to or "season end"

    try:
        for st in _ALLOWED_SEASON_TYPES:
            df = await client.get_league_game_log(
                season=season,
                team_name=team,
                season_type=st,
                date_from=date_from,
                date_to=date_to,
                as_dataframe=True,
            )

            if isinstance(df, str):
                lines.append(f"{st}: {df}")
                continue

            if df.empty:
                lines.append(
                    f"{st}: No games for {team or 'all teams'} "
                    f"in {season} {st} {start}→{end}."
                )
                continue

            lines.append(
                f"Game log ({st}) for {team or 'all teams'} "
                f"in {season} from {start} to {end}:"
            )
            for _, r in df.iterrows():
                gd = r.get("GAME_DATE") or r.get("GAME_DATE_EST", "Unknown")
                mu = r.get("MATCHUP", "")
                wl = r.get("WL", "")
                ab = r.get("TEAM_ABBREVIATION", "")
                pts = r.get("PTS", 0)
                mins = r.get("MIN", "")
                stats = (
                    f"{mins} min | FGM {r.get('FGM',0)}-{r.get('FGA',0)} "
                    f"| 3P {r.get('FG3M',0)}-{r.get('FG3A',0)} "
                    f"| FT {r.get('FTM',0)}-{r.get('FTA',0)} "
                    f"| TRB {r.get('REB',0)} | AST {r.get('AST',0)} "
                    f"| STL {r.get('STL',0)} | BLK {r.get('BLK',0)} "
                    f"| TOV {r.get('TOV',0)} | PF {r.get('PF',0)}"
                )
                prefix = f"{gd} • {ab} •" if not team else f"{gd}:"
                lines.append(f"{prefix} {mu} – {wl}, {pts} pts | {stats}")
            lines.append("")

        return "\n".join(lines).strip()

    except Exception as e:
        logger.exception("Unexpected error in get_date_range_game_log_or_team_game_log")
        return f"Unexpected error: {e}"


@mcp_server.tool()
async def play_by_play(
    game_date: Optional[str] = None,
    team: Optional[str] = None,
    start_period: int = 1,
    end_period: int = 4,
    start_clock: Optional[str] = None,
    recent_n: int = 5,
    max_lines: int = 200,
) -> str:
    """
    Unified MCP tool: returns play-by-play for specified date/team,
    or for all games today if no parameters given.
    """
    client = NBAApiClient()
    output_blocks = []

    # If neither date nor team provided, iterate over today's games via client
    if game_date is None or team is None:
        games_df = await client.get_today_games(as_dataframe=True)
        if isinstance(games_df, str):
            return games_df
        if not isinstance(games_df, pd.DataFrame) or games_df.empty:
            return "No NBA games scheduled today."

        today_str = date.today().strftime("%Y-%m-%d")
        for _, row in games_df.iterrows():
            # Use away team name by default
            team_name = row.get("away_team") or row.get("awayTeam")
            header = f"## {row.get('gameId')} | {row.get('awayTeam')} @ {row.get('homeTeam')}"
            md = await client.get_play_by_play(
                game_date=today_str,
                team=team_name,
                start_period=start_period,
                end_period=end_period,
                start_clock=start_clock,
                recent_n=recent_n,
                max_lines=max_lines,
            )
            if isinstance(md, str):
                output_blocks.append(f"{header}\n\n{md}")
            else:
                output_blocks.append(
                    f"{header} Error\n```json\n{json.dumps(md, indent=2)}\n```"
                )

        return "\n\n".join(output_blocks)

    # Single game fetch when both date and team provided
    md = await client.get_play_by_play(
        game_date=game_date,
        team=team,
        start_period=start_period,
        end_period=end_period,
        start_clock=start_clock,
        recent_n=recent_n,
        max_lines=max_lines,
    )
    if isinstance(md, str):
        return md
    return json.dumps(md, indent=2)


@mcp_server.tool()
async def get_team_standings(
    season: Optional[str] = None, conference: Optional[Literal["East", "West"]] = None
) -> str:
    """
    Get NBA team standings with conference/division rankings.

    Provides comprehensive standings data including:
    - Win-Loss records and percentages
    - Games Behind (GB) conference leader
    - Conference and division rankings
    - Home/away records
    - Last 10 games record
    - Current streak (W/L)

    Args:
        season: Season string ('YYYY-YY' format, e.g., '2024-25'). Defaults to current season.
        conference: Filter by conference ('East' or 'West'). None returns both conferences.

    Returns:
        JSON string with ResponseEnvelope containing list of TeamStanding objects

    Examples:
        get_team_standings()  # Current season, all teams
        get_team_standings(season="2023-24", conference="East")  # 2023-24 Eastern Conference
    """
    start_time = time.time()

    try:
        from nba_mcp.api.advanced_stats import get_team_standings as fetch_standings

        standings = await fetch_standings(season=season, conference=conference)

        execution_time_ms = (time.time() - start_time) * 1000

        # Convert to list of dicts for JSON serialization
        standings_data = [s.model_dump() for s in standings]

        response = success_response(
            data=standings_data,
            source="historical",
            cache_status="miss",
            execution_time_ms=execution_time_ms,
        )

        return response.to_json_string()

    except Exception as e:
        logger.exception("Error in get_team_standings")
        response = error_response(
            error_code="NBA_API_ERROR",
            error_message=f"Failed to fetch team standings: {str(e)}",
        )
        return response.to_json_string()


@mcp_server.tool()
async def get_team_advanced_stats(team_name: str, season: Optional[str] = None) -> str:
    """
    Get team advanced statistics (Offensive/Defensive Rating, Pace, Net Rating, Four Factors).

    Provides comprehensive team metrics including:
    - Offensive/Defensive/Net Rating (per 100 possessions)
    - Pace (possessions per 48 minutes)
    - True Shooting % and Effective FG %
    - Four Factors: eFG%, TOV%, OREB%, FTA Rate (offense and defense)

    Args:
        team_name: Team name or abbreviation (e.g., "Lakers", "LAL", "Los Angeles Lakers")
        season: Season string ('YYYY-YY'). Defaults to current season.

    Returns:
        JSON string with ResponseEnvelope containing team advanced stats

    Examples:
        get_team_advanced_stats("Lakers")
        get_team_advanced_stats("BOS", season="2023-24")
    """
    start_time = time.time()

    try:
        from nba_mcp.api.advanced_stats import (
            get_team_advanced_stats as fetch_team_stats,
        )

        stats = await fetch_team_stats(team_name=team_name, season=season)

        execution_time_ms = (time.time() - start_time) * 1000

        response = success_response(
            data=stats,
            source="historical",
            cache_status="miss",
            execution_time_ms=execution_time_ms,
        )

        return response.to_json_string()

    except EntityNotFoundError as e:
        response = error_response(
            error_code=e.code, error_message=e.message, details=e.details
        )
        return response.to_json_string()

    except Exception as e:
        logger.exception("Error in get_team_advanced_stats")
        response = error_response(
            error_code="NBA_API_ERROR",
            error_message=f"Failed to fetch team advanced stats: {str(e)}",
        )
        return response.to_json_string()


@mcp_server.tool()
async def get_player_advanced_stats(
    player_name: str, season: Optional[str] = None
) -> str:
    """
    Get player advanced statistics (Usage%, TS%, eFG%, PER, Offensive/Defensive Rating).

    Provides comprehensive player efficiency metrics including:
    - True Shooting % (TS%)
    - Effective Field Goal % (eFG%)
    - Usage % (percentage of team plays used)
    - Player Impact Estimate (PIE)
    - Offensive/Defensive/Net Rating
    - Assist %, Rebound %, Turnover %

    Args:
        player_name: Player name (e.g., "LeBron James", "LeBron", "James")
        season: Season string ('YYYY-YY'). Defaults to current season.

    Returns:
        JSON string with ResponseEnvelope containing player advanced stats

    Examples:
        get_player_advanced_stats("LeBron James")
        get_player_advanced_stats("Curry", season="2015-16")
    """
    start_time = time.time()

    try:
        from nba_mcp.api.advanced_stats import (
            get_player_advanced_stats as fetch_player_stats,
        )

        stats = await fetch_player_stats(player_name=player_name, season=season)

        execution_time_ms = (time.time() - start_time) * 1000

        response = success_response(
            data=stats,
            source="historical",
            cache_status="miss",
            execution_time_ms=execution_time_ms,
        )

        return response.to_json_string()

    except EntityNotFoundError as e:
        response = error_response(
            error_code=e.code, error_message=e.message, details=e.details
        )
        return response.to_json_string()

    except Exception as e:
        logger.exception("Error in get_player_advanced_stats")
        response = error_response(
            error_code="NBA_API_ERROR",
            error_message=f"Failed to fetch player advanced stats: {str(e)}",
        )
        return response.to_json_string()


@mcp_server.tool()
async def compare_players(
    player1_name: str,
    player2_name: str,
    season: Optional[str] = None,
    normalization: Literal["raw", "per_game", "per_75", "era_adjusted"] = "per_75",
) -> str:
    """
    Compare two players side-by-side with shared metric registry.

    Provides fair player comparison with:
    - Shared metric definitions (identical schema)
    - Per-possession normalization (per-75 by default for fairness)
    - Era adjustment toggle (accounts for pace/scoring environment)
    - Comprehensive advanced stats

    Args:
        player1_name: First player name
        player2_name: Second player name
        season: Season string ('YYYY-YY'). Defaults to current season.
        normalization: Statistical normalization mode:
            - "raw": Total stats (season totals)
            - "per_game": Per-game averages
            - "per_75": Per-75 possessions (DEFAULT - fairest comparison)
            - "era_adjusted": Adjust for pace/era differences

    Returns:
        JSON string with ResponseEnvelope containing PlayerComparison object

    Examples:
        compare_players("LeBron James", "Michael Jordan", season="2012-13")
        compare_players("Curry", "Nash", normalization="per_75")
    """
    start_time = time.time()

    try:
        from nba_mcp.api.advanced_stats import compare_players as do_compare

        comparison = await do_compare(
            player1_name=player1_name,
            player2_name=player2_name,
            season=season,
            normalization=normalization,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        response = success_response(
            data=comparison.model_dump(),
            source="historical",
            cache_status="miss",
            execution_time_ms=execution_time_ms,
        )

        return response.to_json_string()

    except EntityNotFoundError as e:
        response = error_response(
            error_code=e.code, error_message=e.message, details=e.details
        )
        return response.to_json_string()

    except Exception as e:
        logger.exception("Error in compare_players")
        response = error_response(
            error_code="NBA_API_ERROR",
            error_message=f"Failed to compare players: {str(e)}",
        )
        return response.to_json_string()


@mcp_server.tool()
async def compare_players_era_adjusted(
    player1_name: str,
    player2_name: str,
    season1: str,
    season2: str,
) -> str:
    """
    Compare two players across different eras with pace and scoring adjustments.

    Provides fair cross-era player comparison by adjusting for:
    - League-wide pace differences (possessions per game)
    - Scoring environment changes (points per game)
    - Different eras' playing styles

    This allows for fair comparisons like Michael Jordan (1995-96) vs LeBron James (2012-13)
    even though they played in vastly different pace and scoring environments.

    Args:
        player1_name: First player name (e.g., "Michael Jordan")
        player2_name: Second player name (e.g., "LeBron James")
        season1: Season for player 1 in 'YYYY-YY' format (e.g., "1995-96")
        season2: Season for player 2 in 'YYYY-YY' format (e.g., "2012-13")

    Returns:
        Formatted markdown comparison with:
        - Raw stats for both players
        - Era-adjusted stats normalized to modern baseline
        - Side-by-side comparison table
        - Explanation of adjustments

    Examples:
        compare_players_era_adjusted("Michael Jordan", "LeBron James", "1995-96", "2012-13")
        compare_players_era_adjusted("Kobe Bryant", "Luka Doncic", "2005-06", "2023-24")

    Era Adjustments:
        - 1990s: Slower pace, lower scoring (adjust upward)
        - 2000s: Slowest era, defensive focus (adjust upward)
        - 2010s: Gradual pace increase (minor adjustment)
        - 2020s: Fast pace, high scoring (adjust downward)
    """
    start_time = time.time()

    try:
        from nba_mcp.api.era_adjusted import (
            create_adjusted_stats,
            format_era_comparison,
        )

        # Fetch player stats for both seasons
        client = NBAApiClient()

        # Get player 1 stats
        try:
            player1_data = await client.get_player_career_stats(
                player1_name, season1, as_dataframe=True
            )
            if isinstance(player1_data, str) or not isinstance(
                player1_data, pd.DataFrame
            ):
                raise EntityNotFoundError(
                    "player",
                    player1_name,
                    suggestions=[{"name": player1_name, "confidence": 0.5}],
                )
            if player1_data.empty:
                raise EntityNotFoundError("player", player1_name)

            # Extract stats from DataFrame (per-game averages)
            row1 = player1_data.iloc[0]
            stats1 = {
                "ppg": float(row1.get("PTS", 0)),
                "rpg": float(row1.get("REB", 0)),
                "apg": float(row1.get("AST", 0)),
                "spg": float(row1.get("STL", 0)),
                "bpg": float(row1.get("BLK", 0)),
            }
        except EntityNotFoundError:
            raise
        except Exception as e:
            logger.exception(f"Error fetching stats for {player1_name}")
            raise EntityNotFoundError("player", player1_name)

        # Get player 2 stats
        try:
            player2_data = await client.get_player_career_stats(
                player2_name, season2, as_dataframe=True
            )
            if isinstance(player2_data, str) or not isinstance(
                player2_data, pd.DataFrame
            ):
                raise EntityNotFoundError(
                    "player",
                    player2_name,
                    suggestions=[{"name": player2_name, "confidence": 0.5}],
                )
            if player2_data.empty:
                raise EntityNotFoundError("player", player2_name)

            row2 = player2_data.iloc[0]
            stats2 = {
                "ppg": float(row2.get("PTS", 0)),
                "rpg": float(row2.get("REB", 0)),
                "apg": float(row2.get("AST", 0)),
                "spg": float(row2.get("STL", 0)),
                "bpg": float(row2.get("BLK", 0)),
            }
        except EntityNotFoundError:
            raise
        except Exception as e:
            logger.exception(f"Error fetching stats for {player2_name}")
            raise EntityNotFoundError("player", player2_name)

        # Create era-adjusted stats for both players
        adjusted1 = create_adjusted_stats(stats1, season1)
        adjusted2 = create_adjusted_stats(stats2, season2)

        # Format comparison
        comparison_markdown = format_era_comparison(
            player1_name, player2_name, adjusted1, adjusted2
        )

        execution_time_ms = (time.time() - start_time) * 1000

        # Return markdown response (not JSON envelope for readability)
        return comparison_markdown

    except EntityNotFoundError as e:
        response = error_response(
            error_code=e.code, error_message=e.message, details=e.details
        )
        return response.to_json_string()

    except Exception as e:
        logger.exception("Error in compare_players_era_adjusted")
        response = error_response(
            error_code="NBA_API_ERROR",
            error_message=f"Failed to compare players across eras: {str(e)}",
        )
        return response.to_json_string()


@mcp_server.tool()
async def get_shot_chart(
    entity_name: str,
    entity_type: Literal["player", "team"] = "player",
    season: Optional[str] = None,
    season_type: Literal["Regular Season", "Playoffs"] = "Regular Season",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    granularity: Literal["raw", "hexbin", "both", "summary"] = "both",
) -> str:
    """
    Get shot chart data for a player or team.

    Returns shooting data with coordinates and optional hexbin aggregation.
    Perfect for visualizing shooting patterns and hot zones.

    Args:
        entity_name: Player or team name (e.g., "Stephen Curry", "Warriors")
        entity_type: "player" or "team" (default: "player")
        season: Season in 'YYYY-YY' format (e.g., "2023-24"). If None, uses current season.
        season_type: "Regular Season" or "Playoffs" (default: "Regular Season")
        date_from: Start date for filtering shots in 'YYYY-MM-DD' or 'MM/DD/YYYY' format (optional)
        date_to: End date for filtering shots in 'YYYY-MM-DD' or 'MM/DD/YYYY' format (optional)
        granularity: Output format:
            - "raw": Individual shot coordinates (X, Y, make/miss)
            - "hexbin": Aggregated data (50x50 grid with FG% per zone)
            - "both": Both raw and hexbin data (default)
            - "summary": Zone summary (paint, mid-range, three-point stats)

    Returns:
        JSON string with ResponseEnvelope containing shot chart data

    Examples:
        get_shot_chart("Stephen Curry", season="2023-24", granularity="hexbin")
        get_shot_chart("Lakers", entity_type="team", granularity="summary")
        get_shot_chart("Joel Embiid", date_from="2024-01-01", date_to="2024-01-31")
    """
    start_time = time.time()

    try:
        client = NBAApiClient()
        data = await fetch_shot_chart(
            entity_name=entity_name,
            entity_type=entity_type,
            season=season or client.get_season_string(),
            season_type=season_type,
            date_from=date_from,
            date_to=date_to,
            granularity=granularity,
        )

        execution_time_ms = (time.time() - start_time) * 1000
        response = success_response(
            data=data,
            source="historical",
            cache_status="miss",
            execution_time_ms=execution_time_ms,
        )
        return response.to_json_string()

    except (EntityNotFoundError, InvalidParameterError) as e:
        response = error_response(
            error_code=e.code, error_message=e.message, details=e.details
        )
        return response.to_json_string()

    except Exception as e:
        logger.exception("Error in get_shot_chart")
        response = error_response(
            error_code="NBA_API_ERROR",
            error_message=f"Failed to fetch shot chart: {str(e)}",
        )
        return response.to_json_string()


@mcp_server.tool()
async def get_game_context(
    team1_name: str,
    team2_name: str,
    season: Optional[str] = None,
) -> str:
    """
    Get comprehensive game context for a matchup between two teams.

    Fetches and composes multiple data sources in parallel:
    - Team standings (conference/division rank, records, games behind)
    - Advanced statistics (offensive/defensive/net rating, pace)
    - Recent form (last 10 games, win/loss streaks)
    - Head-to-head record (season series)
    - Narrative synthesis (markdown-formatted storylines)

    Perfect for game previews, matchup analysis, and pre-game context.

    Args:
        team1_name: First team name (e.g., "Lakers", "Los Angeles Lakers")
        team2_name: Second team name (e.g., "Warriors", "Golden State Warriors")
        season: Season in 'YYYY-YY' format (e.g., "2023-24"). If None, uses current season.

    Returns:
        JSON string with ResponseEnvelope containing:
        - matchup: Team IDs and names
        - standings: Conference/division ranks, records, win percentage
        - advanced_stats: OffRtg, DefRtg, NetRtg, Pace for both teams
        - recent_form: Last 10 games, W-L record, current streaks
        - head_to_head: Season series record, game results
        - narrative: Markdown-formatted game preview with key storylines
        - metadata: Components loaded/failed status

    Examples:
        get_game_context("Lakers", "Warriors")
        → Full matchup context with all components

        get_game_context("Boston Celtics", "Miami Heat", season="2022-23")
        → Historical matchup context from 2022-23 season

    Features:
        - Parallel API execution (4-6 calls simultaneously)
        - Graceful degradation (returns partial data if some components fail)
        - Auto-generated narrative with storylines
        - Fuzzy team name matching

    Narrative Sections:
        1. Matchup Header: Team records, conference ranks
        2. Season Series: Head-to-head record
        3. Recent Form: Last 10 games, win/loss streaks
        4. Statistical Edge: Net rating comparison
        5. Key Storylines: Auto-generated insights (streaks, defensive struggles, etc.)
    """
    start_time = time.time()

    try:
        client = NBAApiClient()
        data = await fetch_game_context(
            team1_name=team1_name,
            team2_name=team2_name,
            season=season or client.get_season_string(),
        )

        execution_time_ms = (time.time() - start_time) * 1000
        response = success_response(
            data=data,
            source="composed",
            cache_status="miss",
            execution_time_ms=execution_time_ms,
        )
        return response.to_json_string()

    except (EntityNotFoundError, InvalidParameterError) as e:
        response = error_response(
            error_code=e.code, error_message=e.message, details=e.details
        )
        return response.to_json_string()

    except Exception as e:
        logger.exception("Error in get_game_context")
        response = error_response(
            error_code="NBA_API_ERROR",
            error_message=f"Failed to fetch game context: {str(e)}",
        )
        return response.to_json_string()


@mcp_server.tool()
async def answer_nba_question(question: str) -> str:
    """
    Answer natural language questions about NBA data using the NLQ pipeline.

    This tool understands natural language and automatically orchestrates the right
    NBA API calls to answer your question. It returns formatted, human-readable responses.

    Args:
        question: Natural language question about NBA data

    Returns:
        Formatted answer (markdown with tables/narratives)

    Supported Question Types:
        1. Leaders: "Who leads the NBA in assists?", "Top 10 scorers this season"
        2. Player Comparison: "Compare LeBron James and Kevin Durant"
        3. Team Comparison: "Lakers vs Celtics", "Warriors vs Bucks tonight"
        4. Player Stats: "Show me Giannis stats from 2023-24", "How is Luka doing?"
        5. Team Stats: "What is the Warriors offensive rating?", "Celtics defense"
        6. Standings: "Eastern Conference standings", "Western Conference playoff race"
        7. Game Context: "Lakers vs Celtics tonight", "What games are on today?"

    Examples:
        answer_nba_question("Who leads the NBA in assists?")
        → Returns formatted table with top assist leaders

        answer_nba_question("Compare LeBron James and Kevin Durant")
        → Returns side-by-side comparison table

        answer_nba_question("Show me Giannis stats from 2023-24")
        → Returns formatted player stats card

    Note: The NLQ pipeline automatically:
    - Resolves player/team names (fuzzy matching)
    - Extracts relevant stats and time periods
    - Calls the right tools in optimal order
    - Formats results as readable markdown
    """
    start_time = time.time()

    try:
        logger.info(f"NLQ question: '{question}'")

        # Call the NLQ pipeline
        answer = await nlq_answer_question(question, return_metadata=False)

        execution_time_ms = (time.time() - start_time) * 1000
        logger.info(f"NLQ completed in {execution_time_ms:.1f}ms")

        return answer

    except Exception as e:
        logger.exception("Error in answer_nba_question")
        return f"Sorry, I encountered an error processing your question: {str(e)}\n\nPlease try rephrasing your question or being more specific."


@mcp_server.tool()
async def get_metrics_info() -> str:
    """
    Get current metrics and observability information from the NBA MCP server.

    Returns system health, performance metrics, cache statistics, and rate limit status.
    Useful for monitoring and debugging.

    Returns:
        Formatted metrics report with:
        - Server uptime
        - Cache hit rate and size
        - Quota usage and remaining
        - Recent request statistics
        - Metrics endpoint information

    Example:
        get_metrics_info()
        → Returns server metrics and health status
    """
    try:
        from nba_mcp.observability import get_metrics_snapshot

        snapshot = get_metrics_snapshot()

        lines = ["# NBA MCP Server Metrics", ""]

        # Server uptime
        uptime_seconds = snapshot.get("server_uptime_seconds", 0)
        uptime_hours = uptime_seconds / 3600
        lines.append(
            f"**Server Uptime**: {uptime_hours:.2f} hours ({uptime_seconds:.0f} seconds)"
        )
        lines.append("")

        # Cache metrics
        if "cache" in snapshot:
            cache = snapshot["cache"]
            lines.append("## Cache Statistics")
            lines.append(f"- **Hit Rate**: {cache.get('hit_rate', 0):.1%}")
            lines.append(f"- **Hits**: {cache.get('hits', 0)}")
            lines.append(f"- **Misses**: {cache.get('misses', 0)}")
            lines.append(f"- **Stored Items**: {cache.get('stored_items', 0)}")
            lines.append("")

        # Quota metrics
        if "quota" in snapshot:
            quota = snapshot["quota"]
            lines.append("## Daily Quota")
            lines.append(f"- **Used**: {quota.get('used', 0)}/{quota.get('limit', 0)}")
            lines.append(f"- **Remaining**: {quota.get('remaining', 0)}")
            lines.append(f"- **Usage**: {quota.get('usage_percent', 0):.1f}%")
            lines.append("")

        # Metrics endpoint
        import os

        metrics_port = int(os.getenv("METRICS_PORT", 9090))
        lines.append("## Metrics Endpoint")
        lines.append(f"- **URL**: http://localhost:{metrics_port}/metrics")
        lines.append("- **Health Check**: http://localhost:{metrics_port}/health")
        lines.append("")
        lines.append(
            "Use Prometheus to scrape the /metrics endpoint for detailed metrics."
        )

        return "\n".join(lines)

    except Exception as e:
        return f"Error retrieving metrics: {str(e)}\n\nMetrics may not be initialized."


#########################################
# Dataset and Joins Tools
#########################################


@mcp_server.tool()
async def list_endpoints(category: Optional[str] = None) -> str:
    """
    List all available NBA API endpoints with their parameters and schemas.

    Returns comprehensive information about each endpoint including:
    - Parameter requirements
    - Primary keys
    - Sample usage
    - Data categories

    Args:
        category: Optional filter by category:
            - "player_stats": Player statistics
            - "team_stats": Team statistics
            - "game_data": Live and historical game data
            - "league_data": League-wide data
            - "advanced_analytics": Advanced metrics

    Returns:
        Formatted endpoint catalog

    Example:
        list_endpoints()
        → Returns all endpoints

        list_endpoints(category="player_stats")
        → Returns only player statistics endpoints
    """
    try:
        catalog = get_catalog()

        # Parse category if provided
        from nba_mcp.data.catalog import EndpointCategory

        category_filter = None
        if category:
            try:
                category_filter = EndpointCategory(category)
            except ValueError:
                valid_categories = [c.value for c in EndpointCategory]
                return (
                    f"Invalid category: {category}\n\n"
                    f"Valid categories: {', '.join(valid_categories)}"
                )

        # Get endpoints
        endpoints = catalog.list_endpoints(category=category_filter)

        # Format response
        lines = ["# NBA MCP Endpoints", ""]

        if category:
            lines.append(f"**Category**: {category}")
            lines.append("")

        lines.append(f"**Total Endpoints**: {len(endpoints)}")
        lines.append("")

        for endpoint in endpoints:
            lines.append(f"## {endpoint.display_name}")
            lines.append(f"**Name**: `{endpoint.name}`")
            lines.append(f"**Category**: {endpoint.category.value}")
            lines.append(f"**Description**: {endpoint.description}")
            lines.append("")

            if endpoint.parameters:
                lines.append("**Parameters**:")
                for param in endpoint.parameters:
                    required = "**required**" if param.required else "optional"
                    lines.append(
                        f"- `{param.name}` ({param.type}, {required}): {param.description}"
                    )
                    if param.enum:
                        lines.append(f"  - Options: {', '.join(param.enum)}")
                    if param.example:
                        lines.append(f"  - Example: `{param.example}`")
                lines.append("")

            if endpoint.primary_keys:
                lines.append(f"**Primary Keys**: {', '.join(endpoint.primary_keys)}")
                lines.append("")

            if endpoint.sample_params:
                import json

                lines.append("**Sample Usage**:")
                lines.append(
                    f"```python\nfetch('{endpoint.name}', {json.dumps(endpoint.sample_params, indent=2)})\n```"
                )
                lines.append("")

            if endpoint.notes:
                lines.append(f"*Note: {endpoint.notes}*")
                lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        logger.exception("Error in list_endpoints")
        return f"Error listing endpoints: {str(e)}"


@mcp_server.tool()
async def catalog() -> str:
    """
    Get the complete data catalog with schema information and join relationships.

    Returns comprehensive metadata about all endpoints including:
    - Endpoint schemas with parameters and columns
    - Primary and foreign key relationships
    - Join recommendations with examples
    - Complete join workflow examples

    Use this to understand:
    - What data is available
    - How endpoints relate to each other
    - How to join datasets effectively

    Returns:
        Complete data catalog with relationships and examples

    Example:
        catalog()
        → Returns full data dictionary with join guidance
    """
    try:
        cat = get_catalog()
        catalog_dict = cat.to_dict()

        lines = ["# NBA MCP Data Catalog", ""]

        # Summary
        summary = catalog_dict["summary"]
        lines.append("## Summary")
        lines.append(f"- **Total Endpoints**: {summary['total_endpoints']}")
        lines.append(f"- **Categories**: {', '.join(summary['categories'])}")
        lines.append(f"- **Join Relationships**: {summary['total_relationships']}")
        lines.append(f"- **Join Examples**: {summary['total_examples']}")
        lines.append("")

        # Endpoints by category
        lines.append("## Endpoints by Category")
        lines.append("")
        endpoints_by_cat = {}
        for name, endpoint in catalog_dict["endpoints"].items():
            cat_name = endpoint["category"]
            if cat_name not in endpoints_by_cat:
                endpoints_by_cat[cat_name] = []
            endpoints_by_cat[cat_name].append(endpoint)

        for cat_name, endpoints in sorted(endpoints_by_cat.items()):
            lines.append(f"### {cat_name.replace('_', ' ').title()}")
            for endpoint in endpoints:
                lines.append(
                    f"- **{endpoint['display_name']}** (`{endpoint['name']}`)"
                )
                lines.append(f"  - {endpoint['description']}")
                if endpoint["primary_keys"]:
                    lines.append(
                        f"  - Primary Keys: {', '.join(endpoint['primary_keys'])}"
                    )
            lines.append("")

        # Join Relationships
        lines.append("## Join Relationships")
        lines.append("")
        lines.append("Common patterns for joining datasets:")
        lines.append("")

        for rel in catalog_dict["relationships"]:
            lines.append(f"### {rel['from_endpoint']} → {rel['to_endpoint']}")
            lines.append(f"**Join Keys**: {rel['join_keys']}")
            lines.append(f"**Join Type**: {rel['join_type']}")
            lines.append(f"**Description**: {rel['description']}")
            lines.append(f"**Use Case**: {rel['example_use_case']}")
            lines.append("")

        # Join Examples
        lines.append("## Complete Join Examples")
        lines.append("")

        for example in catalog_dict["join_examples"]:
            lines.append(f"### {example['name']}")
            lines.append(f"{example['description']}")
            lines.append("")
            lines.append("**Steps**:")
            for i, step in enumerate(example["steps"], 1):
                import json

                lines.append(f"{i}. {json.dumps(step, indent=2)}")
            lines.append("")
            lines.append(f"**Expected Output**: {example['expected_output']}")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        logger.exception("Error in catalog")
        return f"Error retrieving catalog: {str(e)}"


@mcp_server.tool()
async def fetch(endpoint: str, params: Dict[str, Any]) -> str:
    """
    Fetch raw data from an NBA API endpoint as an Arrow table.

    Returns data in a standardized table format with provenance tracking.
    The dataset is stored in memory and returns a handle for further operations.

    Args:
        endpoint: Endpoint name from catalog (e.g., "player_career_stats")
        params: Parameters dictionary matching endpoint schema

    Returns:
        Dataset handle UUID with metadata (row count, columns, size, etc.)

    Examples:
        fetch("player_career_stats", {"player_name": "LeBron James"})
        → Returns handle with LeBron's career stats

        fetch("team_standings", {"season": "2023-24", "conference": "East"})
        → Returns handle with Eastern Conference standings

        fetch("league_leaders", {"stat_category": "PTS", "season": "2023-24"})
        → Returns handle with scoring leaders
    """
    try:
        # Validate parameters
        validate_parameters(endpoint, params)

        # Check size limits before fetching
        from nba_mcp.data.introspection import get_introspector

        introspector = get_introspector()
        size_check = await introspector.check_size_limit(endpoint, params)

        # Fetch data
        table, provenance = await fetch_endpoint(endpoint, params, as_arrow=True)

        # Store in dataset manager
        manager = get_dataset_manager()
        handle = await manager.store(
            table, name=f"{endpoint}_{datetime.now().strftime('%Y%m%d_%H%M%S')}", provenance=provenance
        )

        # Import limits helper for display
        from nba_mcp.data.limits import get_limits
        limits = get_limits()

        # Format response
        lines = [
            "# Dataset Fetched Successfully",
            "",
            f"**Endpoint**: {endpoint}",
            f"**Dataset Handle**: `{handle.uuid}`",
            "",
        ]

        # Show size limit status prominently
        actual_size_mb = handle.size_bytes / 1024 / 1024
        limit_mb = limits.get_max_fetch_size_mb()

        lines.extend([
            "## Size Information",
            f"- **Dataset Size**: {actual_size_mb:.2f} MB ({handle.size_bytes:,} bytes)",
            f"- **Estimated Size**: {size_check.estimated_mb:.2f} MB (pre-fetch)",
            f"- **Size Limit**: {limit_mb:.0f} MB" if limit_mb > 0 else "- **Size Limit**: Unlimited",
            f"- **Status**: {'✓ Within limit' if size_check.allowed else '⚠️ Exceeded limit (allowed)'}",
            "",
        ])

        # Add size warning if exceeded
        if not size_check.allowed:
            lines.extend([
                "## ⚠️ Size Warning",
                "",
                size_check.warning_message,
                "",
            ])

        lines.extend([
            "## Dataset Info",
            f"- **Rows**: {handle.row_count:,}",
            f"- **Columns**: {handle.column_count}",
            f"- **Expires**: {handle.expires_at}",
            "",
            "## Columns",
        ])

        # Show column names (limit to first 20)
        cols = handle.column_names[:20]
        for col in cols:
            lines.append(f"- {col}")

        if len(handle.column_names) > 20:
            lines.append(f"- ... and {len(handle.column_names) - 20} more")

        lines.append("")
        lines.append("## Provenance")
        lines.append(f"- **NBA API Calls**: {provenance.nba_api_calls}")
        lines.append(f"- **Execution Time**: {provenance.execution_time_ms:.2f}ms")
        lines.append("")
        lines.append("## Next Steps")
        lines.append(f"Use this handle for joins: `join(['{handle.uuid}', ...], on=...)`")
        lines.append(f"Or save to mcp_data/: `save_dataset('{handle.uuid}')`")
        lines.append(f"Or save custom path: `save_dataset('{handle.uuid}', 'path/to/file.parquet')`")

        return "\n".join(lines)

    except Exception as e:
        logger.exception("Error in fetch")
        return f"Error fetching data: {str(e)}"


@mcp_server.tool()
async def join(
    handles: List[str],
    on: Union[str, List[str], Dict[str, str]],
    how: str = "left",
) -> str:
    """
    Join multiple datasets using SQL join operations.

    Performs in-memory joins using DuckDB with automatic validation.
    Returns a new dataset handle with the joined result.

    Args:
        handles: List of dataset UUIDs to join (2 or more)
        on: Join columns:
            - str: Single column name (must exist in all tables)
            - List[str]: Multiple columns (must exist in all tables)
            - Dict[str, str]: Column mapping for 2 tables (e.g., {"TEAM_ID": "ID"})
        how: Join type - "inner", "left", "right", "outer", or "cross"

    Returns:
        New dataset handle with join result and statistics

    Examples:
        # Simple join on single column
        join(
            handles=["uuid1", "uuid2"],
            on="PLAYER_ID",
            how="inner"
        )

        # Join on multiple columns
        join(
            handles=["uuid1", "uuid2"],
            on=["PLAYER_ID", "SEASON"],
            how="left"
        )

        # Join with column mapping
        join(
            handles=["uuid1", "uuid2"],
            on={"TEAM_ID": "ID"},
            how="left"
        )
    """
    try:
        if len(handles) < 2:
            return "Error: At least 2 dataset handles required for join"

        # Validate join type
        valid_types = ["inner", "left", "right", "outer", "cross"]
        if how not in valid_types:
            return (
                f"Error: Invalid join type '{how}'. "
                f"Must be one of: {', '.join(valid_types)}"
            )

        # Retrieve tables from manager
        manager = get_dataset_manager()
        tables = []
        for handle_uuid in handles:
            table = await manager.retrieve(handle_uuid)
            tables.append(table)

        # Perform join with statistics
        result_dict = join_with_stats(tables, on, how)
        result_table = result_dict["result"]
        stats = result_dict["stats"]

        # Store joined result
        from nba_mcp.data.dataset_manager import ProvenanceInfo

        provenance = ProvenanceInfo(
            source_endpoints=["join_operation"],
            operations=["join"],
            parameters={"handles": handles, "on": str(on), "how": how},
            execution_time_ms=stats["execution_time_ms"],
        )

        new_handle = await manager.store(
            result_table,
            name=f"join_{how}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            provenance=provenance,
        )

        # Format response
        lines = [
            "# Join Completed Successfully",
            "",
            f"**New Dataset Handle**: `{new_handle.uuid}`",
            "",
            "## Join Statistics",
            f"- **Join Type**: {stats['join_type']}",
            f"- **Input Tables**: {stats['input_table_count']}",
            f"- **Input Rows**: {', '.join(map(str, stats['input_row_counts']))}",
            f"- **Output Rows**: {stats['output_row_count']:,}",
            f"- **Output Columns**: {stats['output_column_count']}",
            f"- **Execution Time**: {stats['execution_time_ms']:.2f}ms",
            "",
            "## Result Info",
            f"- **Rows**: {new_handle.row_count:,}",
            f"- **Columns**: {new_handle.column_count}",
            f"- **Size**: {new_handle.size_bytes / 1024 / 1024:.2f} MB",
            "",
            "## Next Steps",
            f"- Save to disk: `save_dataset('{new_handle.uuid}', 'joined_data.parquet')`",
            f"- Join with more data: `join(['{new_handle.uuid}', 'other_uuid'], ...)`",
        ]

        return "\n".join(lines)

    except Exception as e:
        logger.exception("Error in join")
        return f"Error performing join: {str(e)}"


@mcp_server.tool()
async def build_dataset(spec: Dict[str, Any]) -> str:
    """
    Build a complete dataset from multiple sources with joins, filters, and column selection.

    Executes a multi-step dataset pipeline in a single call:
    1. Fetch from multiple endpoints
    2. Join datasets
    3. Apply filters
    4. Select columns

    Args:
        spec: Dataset specification with:
            - sources: List of {endpoint, params} dicts
            - joins: List of {on, how} dicts (optional)
            - filters: List of {column, op, value} dicts (optional)
            - select: List of column names to keep (optional)

    Returns:
        Dataset handle with final processed data

    Example:
        build_dataset({
            "sources": [
                {"endpoint": "player_career_stats", "params": {"player_name": "LeBron James"}},
                {"endpoint": "team_standings", "params": {"season": "2023-24"}}
            ],
            "joins": [
                {"on": {"TEAM_ID": "TEAM_ID"}, "how": "left"}
            ],
            "filters": [
                {"column": "PTS", "op": ">", "value": 20}
            ],
            "select": ["PLAYER_NAME", "SEASON", "PTS", "TEAM_NAME", "W", "L"]
        })
    """
    try:
        import time

        start_time = time.time()

        # Validate spec
        if "sources" not in spec or not spec["sources"]:
            return "Error: 'sources' required in spec"

        manager = get_dataset_manager()
        handles = []
        provenance_list = []

        # Step 1: Fetch all sources
        lines = ["# Building Dataset", "", "## Step 1: Fetching Sources", ""]

        for i, source in enumerate(spec["sources"], 1):
            endpoint = source.get("endpoint")
            params = source.get("params", {})

            if not endpoint:
                return f"Error: Source {i} missing 'endpoint'"

            lines.append(f"{i}. Fetching from `{endpoint}`...")

            validate_parameters(endpoint, params)
            table, provenance = await fetch_endpoint(endpoint, params, as_arrow=True)

            handle = await manager.store(table, provenance=provenance)
            handles.append(handle.uuid)
            provenance_list.append(provenance)

            lines.append(
                f"   ✓ {handle.row_count:,} rows, {handle.column_count} columns"
            )

        lines.append("")

        # Step 2: Perform joins if specified
        if spec.get("joins"):
            lines.append("## Step 2: Joining Datasets")
            lines.append("")

            current_handle = handles[0]
            for i, join_spec in enumerate(spec["joins"], 1):
                on = join_spec.get("on")
                how = join_spec.get("how", "left")

                if not on:
                    return f"Error: Join {i} missing 'on'"

                # Join current result with next table
                next_handle = handles[min(i, len(handles) - 1)]

                table1 = await manager.retrieve(current_handle)
                table2 = await manager.retrieve(next_handle)

                result_dict = join_with_stats([table1, table2], on, how)
                result_table = result_dict["result"]
                stats = result_dict["stats"]

                # Store result
                from nba_mcp.data.dataset_manager import ProvenanceInfo

                prov = ProvenanceInfo(
                    source_endpoints=[h for h in handles],
                    operations=["join"],
                    parameters=join_spec,
                )
                current_handle_obj = await manager.store(result_table, provenance=prov)
                current_handle = current_handle_obj.uuid

                lines.append(
                    f"{i}. {how.upper()} join on {on}: {stats['output_row_count']:,} rows"
                )

            lines.append("")
        else:
            current_handle = handles[0]

        # Step 3: Apply filters if specified
        if spec.get("filters"):
            lines.append("## Step 3: Applying Filters")
            lines.append("")

            table = await manager.retrieve(current_handle)
            filtered_table = filter_table(table, spec["filters"])

            from nba_mcp.data.dataset_manager import ProvenanceInfo

            prov = ProvenanceInfo(
                source_endpoints=[h for h in handles],
                operations=["filter"],
                parameters={"filters": spec["filters"]},
            )
            filtered_handle = await manager.store(filtered_table, provenance=prov)
            current_handle = filtered_handle.uuid

            lines.append(
                f"Applied {len(spec['filters'])} filter(s): {filtered_table.num_rows:,} rows remain"
            )
            lines.append("")

        # Step 4: Select columns if specified
        if spec.get("select"):
            lines.append("## Step 4: Selecting Columns")
            lines.append("")

            table = await manager.retrieve(current_handle)
            selected_table = table.select(spec["select"])

            from nba_mcp.data.dataset_manager import ProvenanceInfo

            prov = ProvenanceInfo(
                source_endpoints=[h for h in handles],
                operations=["select"],
                parameters={"select": spec["select"]},
            )
            selected_handle = await manager.store(selected_table, provenance=prov)
            current_handle = selected_handle.uuid

            lines.append(f"Selected {len(spec['select'])} column(s)")
            lines.append("")

        # Final result
        final_handle = await manager.get_handle(current_handle)
        execution_time_ms = (time.time() - start_time) * 1000

        lines.append("## ✓ Dataset Built Successfully")
        lines.append("")
        lines.append(f"**Dataset Handle**: `{final_handle.uuid}`")
        lines.append("")
        lines.append("### Final Dataset")
        lines.append(f"- **Rows**: {final_handle.row_count:,}")
        lines.append(f"- **Columns**: {final_handle.column_count}")
        lines.append(f"- **Size**: {final_handle.size_bytes / 1024 / 1024:.2f} MB")
        lines.append(f"- **Build Time**: {execution_time_ms:.2f}ms")
        lines.append("")
        lines.append("### Next Steps")
        lines.append(
            f"Save the dataset: `save_dataset('{final_handle.uuid}', 'my_dataset.parquet')`"
        )

        return "\n".join(lines)

    except Exception as e:
        logger.exception("Error in build_dataset")
        return f"Error building dataset: {str(e)}"


@mcp_server.tool()
async def save_dataset(
    handle: str, path: Optional[str] = None, format: str = "parquet"
) -> str:
    """
    Save a dataset to disk in various formats.

    Exports a dataset from memory to a file on disk.
    Supports multiple formats with automatic compression.

    When path is not specified, automatically organizes data in mcp_data/ folder
    with structure: mcp_data/YYYY-MM-DD/endpoint_HHMMSS.format

    Args:
        handle: Dataset UUID to save
        path: Output file path (optional - defaults to organized mcp_data/ structure)
        format: Output format - "parquet", "csv", "feather", or "json"

    Returns:
        Save confirmation with file details

    Examples:
        save_dataset("abc123")
        → Saves to mcp_data/2025-10-29/dataset_143052.parquet

        save_dataset("abc123", format="csv")
        → Saves to mcp_data/2025-10-29/dataset_143052.csv

        save_dataset("abc123", "custom/path/data.parquet")
        → Saves to custom/path/data.parquet

        save_dataset("abc123", "data/player_stats.json", "json")
        → Saves to data/player_stats.json
    """
    try:
        # Validate format
        valid_formats = ["parquet", "csv", "feather", "json"]
        if format not in valid_formats:
            return (
                f"Error: Invalid format '{format}'. "
                f"Must be one of: {', '.join(valid_formats)}"
            )

        # Get dataset manager and handle info
        manager = get_dataset_manager()

        # If no path specified, use smart default in mcp_data/ folder
        if path is None:
            from nba_mcp.data.dataset_manager import get_default_save_path

            # Try to get endpoint name from dataset name
            try:
                handle_info = await manager.get_handle(handle)
                endpoint_name = handle_info.name or "dataset"
                # Extract endpoint name (before timestamp)
                if "_" in endpoint_name:
                    endpoint_name = "_".join(endpoint_name.split("_")[:-2])
            except Exception:
                endpoint_name = "dataset"

            path = str(get_default_save_path(endpoint_name, format))

        # Save dataset
        result = await manager.save_to_file(handle, path, format=format)

        # Format response
        lines = [
            "# Dataset Saved Successfully",
            "",
            f"**File**: `{result['path']}`",
            f"**Format**: {result['format']}",
            "",
            "## File Info",
            f"- **Rows**: {result['rows']:,}",
            f"- **Columns**: {result['columns']}",
            f"- **File Size**: {result['file_size_mb']} MB ({result['file_size_bytes']:,} bytes)",
            f"- **Write Time**: {result['execution_time_ms']:.2f}ms",
            "",
            "## Dataset Info",
            f"- **Dataset UUID**: `{result['dataset_uuid']}`",
        ]

        if result.get("dataset_name"):
            lines.append(f"- **Dataset Name**: {result['dataset_name']}")

        lines.append("")

        # Show storage location info
        if "mcp_data" in result['path']:
            lines.append("**Storage**: Organized in mcp_data/ folder structure")
        else:
            lines.append("**Storage**: Custom path specified")

        lines.append("")
        lines.append("The dataset has been successfully saved to disk.")

        return "\n".join(lines)

    except Exception as e:
        logger.exception("Error in save_dataset")
        return f"Error saving dataset: {str(e)}"


@mcp_server.tool()
async def inspect_endpoint(
    endpoint: str, params: Optional[Dict[str, Any]] = None
) -> str:
    """
    Inspect an NBA API endpoint to discover its capabilities and metadata.

    Returns comprehensive information about an endpoint including:
    - Available columns and their data types
    - Estimated row count for the given parameters
    - Supported date ranges (if applicable)
    - Available seasons (if applicable)
    - Recommended chunking strategy for large datasets
    - Notes and warnings

    This tool is useful for understanding what data an endpoint provides
    before fetching it, especially for large datasets.

    Args:
        endpoint: Endpoint name (e.g., "player_career_stats", "shot_chart")
        params: Optional parameters to test with (for size estimation)

    Returns:
        Formatted metadata report with all endpoint capabilities

    Examples:
        inspect_endpoint("shot_chart", {"entity_name": "Stephen Curry"})
        → Returns columns, estimated rows (~15,000), date range (1996-present),
          and recommends date-based chunking

        inspect_endpoint("team_standings", {"season": "2023-24"})
        → Returns columns, estimated rows (30), no chunking needed

        inspect_endpoint("play_by_play", {"game_date": "2024-03-15"})
        → Returns columns, estimated rows (varies), recommends game-based chunking
    """
    try:
        from nba_mcp.data.introspection import get_introspector

        introspector = get_introspector()
        caps = await introspector.inspect_endpoint(endpoint, params or {})

        # Format response
        lines = [
            f"# Endpoint Inspection: {endpoint}",
            "",
            "## Schema Information",
            f"- **Columns**: {len(caps.columns)}",
            f"- **Sample Shape**: {caps.sample_data_shape[0]} rows × {caps.sample_data_shape[1]} columns",
            "",
            "### Available Columns",
        ]

        # Show columns with types (max 20, then summarize)
        if len(caps.columns) <= 20:
            for col in caps.columns:
                col_type = caps.column_types.get(col, "unknown")
                lines.append(f"- `{col}` ({col_type})")
        else:
            for col in caps.columns[:15]:
                col_type = caps.column_types.get(col, "unknown")
                lines.append(f"- `{col}` ({col_type})")
            lines.append(f"- ... and {len(caps.columns) - 15} more columns")

        lines.extend(
            [
                "",
                "## Capabilities",
                f"- **Supports Date Range**: {'Yes' if caps.supports_date_range else 'No'}",
                f"- **Supports Season Filter**: {'Yes' if caps.supports_season_filter else 'No'}",
                f"- **Supports Pagination**: {'Yes' if caps.supports_pagination else 'No'}",
            ]
        )

        # Date range info
        if caps.supports_date_range and caps.min_date and caps.max_date:
            lines.extend(
                [
                    "",
                    "## Date Range",
                    f"- **Min Date**: {caps.min_date}",
                    f"- **Max Date**: {caps.max_date}",
                    f"- **Span**: {(caps.max_date - caps.min_date).days:,} days",
                ]
            )

        # Season info
        if caps.supports_season_filter and caps.available_seasons:
            lines.extend(
                [
                    "",
                    "## Available Seasons",
                    f"- **Count**: {len(caps.available_seasons)} seasons",
                    f"- **Range**: {caps.available_seasons[0]} to {caps.available_seasons[-1]}",
                ]
            )

        # Size estimates
        lines.extend(["", "## Dataset Size"])

        if caps.estimated_row_count:
            lines.append(f"- **Estimated Rows**: {caps.estimated_row_count:,}")

            # Memory estimate (rough: 1KB per row)
            memory_mb = (caps.estimated_row_count * 1024) / (1024 * 1024)
            lines.append(f"- **Estimated Memory**: {memory_mb:.2f} MB")
        else:
            lines.append("- **Estimated Rows**: Unknown")

        # Chunking recommendation
        lines.extend(
            [
                "",
                "## Chunking Strategy",
                f"- **Recommended**: {caps.chunk_strategy}",
            ]
        )

        if caps.chunk_strategy == "date":
            lines.append(
                "- **Reason**: Large time-series dataset, split by date ranges"
            )
        elif caps.chunk_strategy == "season":
            lines.append("- **Reason**: Moderate dataset, split by NBA seasons")
        elif caps.chunk_strategy == "game":
            lines.append("- **Reason**: Game-level data, process one game at a time")
        else:
            lines.append("- **Reason**: Small dataset, no chunking needed")

        # Notes
        if caps.notes:
            lines.extend(["", "## Notes", f"{caps.notes}"])

        return "\n".join(lines)

    except Exception as e:
        logger.exception("Error in inspect_endpoint")
        return f"Error inspecting endpoint: {str(e)}"


@mcp_server.tool()
async def fetch_chunked(
    endpoint: str,
    params: Dict[str, Any],
    chunk_strategy: Optional[str] = None,
    progress: bool = False,
) -> str:
    """
    Fetch a large NBA dataset in chunks to handle any dataset size.

    This tool automatically splits large datasets into manageable chunks
    and returns multiple dataset handles (one per chunk). This enables
    fetching datasets that would be too large to retrieve all at once.

    Chunking strategies:
    - **date**: Split by date ranges (monthly chunks)
    - **season**: Split by NBA seasons
    - **game**: Split by individual games
    - **none**: Fetch all at once (no chunking)
    - **None** (default): Auto-select based on endpoint capabilities

    Args:
        endpoint: Endpoint name to fetch from
        params: Base parameters for the endpoint
        chunk_strategy: Chunking strategy to use (or None for auto)
        progress: If True, show progress information for each chunk

    Returns:
        List of dataset handles, one per chunk, with chunk information

    Examples:
        fetch_chunked("shot_chart", {"entity_name": "Stephen Curry", "season": "2023-24"}, "date")
        → Returns 12 dataset handles (one per month)

        fetch_chunked("team_game_log", {"team": "Lakers", "season": "2023-24"})
        → Auto-selects "none" strategy, returns 1 handle with all 82 games

        fetch_chunked("play_by_play", {"game_date": "2024-03-15"}, "game")
        → Returns multiple handles, one per game on that date
    """
    try:
        from nba_mcp.data.pagination import get_paginator
        from nba_mcp.data.introspection import get_introspector

        paginator = get_paginator()
        manager = get_dataset_manager()
        introspector = get_introspector()

        # Check size (informational - chunking handles large datasets)
        size_check = await introspector.check_size_limit(endpoint, params)

        chunks = []
        total_rows = 0

        # Fetch chunks
        async for table, chunk_info in paginator.fetch_chunked(
            endpoint, params, chunk_strategy, check_size_limit=False  # Already checked
        ):
            # Store chunk
            from nba_mcp.data.dataset_manager import ProvenanceInfo

            provenance = ProvenanceInfo(
                source_endpoints=[endpoint],
                fetch_params=chunk_info.params,
                operations=["fetch_chunked"],
            )

            chunk_name = f"{endpoint}_chunk_{chunk_info.chunk_number}"
            handle = await manager.store(table, chunk_name, provenance)

            chunk_meta = {
                "handle": str(handle.uuid),
                "chunk_number": chunk_info.chunk_number,
                "total_chunks": chunk_info.total_chunks,
                "rows": chunk_info.row_count,
                "params": chunk_info.params,
            }

            if chunk_info.date_range:
                chunk_meta["date_range"] = [
                    str(chunk_info.date_range[0]),
                    str(chunk_info.date_range[1]),
                ]
            if chunk_info.season:
                chunk_meta["season"] = chunk_info.season
            if chunk_info.game_id:
                chunk_meta["game_id"] = chunk_info.game_id

            chunks.append(chunk_meta)
            total_rows += chunk_info.row_count

        # Format response
        lines = [
            f"# Chunked Fetch Complete: {endpoint}",
            "",
            f"**Total Chunks**: {len(chunks)}",
            f"**Total Rows**: {total_rows:,}",
            f"**Strategy**: {chunk_strategy or 'auto'}",
            "",
        ]

        # Add size info if exceeded (informational)
        if not size_check.allowed:
            lines.extend([
                "## 📊 Size Information",
                "",
                f"✓ **Large dataset detected** ({size_check.estimated_mb:.2f} MB)",
                f"- Dataset exceeds single-fetch limit ({size_check.limit_mb:.0f} MB)",
                f"- Chunked fetching automatically handles large datasets",
                f"- Fetched in {len(chunks)} chunk(s) for optimal performance",
                "",
            ])

        lines.extend([
            "## Chunk Details",
            "",
        ])

        for chunk in chunks:
            lines.append(f"### Chunk {chunk['chunk_number']}/{chunk['total_chunks']}")
            lines.append(f"- **Handle**: `{chunk['handle']}`")
            lines.append(f"- **Rows**: {chunk['rows']:,}")

            if "date_range" in chunk:
                lines.append(
                    f"- **Date Range**: {chunk['date_range'][0]} to {chunk['date_range'][1]}"
                )
            if "season" in chunk:
                lines.append(f"- **Season**: {chunk['season']}")
            if "game_id" in chunk:
                lines.append(f"- **Game ID**: {chunk['game_id']}")

            lines.append("")

        lines.extend(
            [
                "## Usage",
                "",
                "To combine all chunks into a single dataset:",
                "```python",
                f"handles = [{', '.join([f'\"{c['handle']}\"' for c in chunks[:3]])}{'...' if len(chunks) > 3 else ''}]",
                'combined = join(handles, on=[], how="union")',
                "```",
                "",
                "Or work with individual chunks:",
                "```python",
                f'chunk1 = fetch_dataset("{chunks[0]['handle']}")',
                "# Process chunk1...",
                "```",
            ]
        )

        return "\n".join(lines)

    except Exception as e:
        logger.exception("Error in fetch_chunked")
        return f"Error fetching chunks: {str(e)}"


@mcp_server.tool()
async def discover_nba_endpoints() -> str:
    """
    Discover all available NBA API endpoints with their capabilities.

    This tool provides a comprehensive directory of all endpoints
    supported by the NBA MCP server, including:
    - Endpoint names and categories
    - Parameter schemas
    - Capabilities (date ranges, seasons, pagination)
    - Typical dataset sizes
    - Recommended use cases

    Use this tool to explore what data is available and how to access it.

    Returns:
        Formatted directory of all endpoints organized by category

    Example:
        discover_nba_endpoints()
        → Returns complete list of all 15+ endpoints with metadata
    """
    try:
        from nba_mcp.data.catalog import get_catalog

        catalog_obj = get_catalog()
        endpoints = catalog_obj.list_endpoints()

        # Group by category
        by_category = {}
        for ep in endpoints:
            cat = ep.category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(ep)

        lines = [
            "# NBA MCP Endpoint Directory",
            "",
            f"**Total Endpoints**: {len(endpoints)}",
            "",
        ]

        # Category emoji mapping
        category_emoji = {
            "player_stats": "👤",
            "team_stats": "🏀",
            "game_data": "📊",
            "league_data": "🏆",
            "advanced_analytics": "📈",
        }

        for category, eps in sorted(by_category.items()):
            emoji = category_emoji.get(category, "📁")
            lines.append(f"## {emoji} {category.replace('_', ' ').title()}")
            lines.append("")

            for ep in eps:
                lines.append(f"### {ep.display_name}")
                lines.append(f"- **Name**: `{ep.name}`")
                lines.append(f"- **Description**: {ep.description}")

                # Parameters
                required_params = [p for p in ep.parameters if p.required]
                optional_params = [p for p in ep.parameters if not p.required]

                if required_params:
                    lines.append(f"- **Required Parameters**: {', '.join([f'`{p.name}`' for p in required_params])}")

                if optional_params:
                    lines.append(f"- **Optional Parameters**: {', '.join([f'`{p.name}`' for p in optional_params])}")

                # Capabilities
                caps = []
                if ep.supports_date_range:
                    caps.append("date ranges")
                if ep.supports_season_filter:
                    caps.append("season filtering")
                if ep.supports_pagination:
                    caps.append("pagination")

                if caps:
                    lines.append(f"- **Capabilities**: {', '.join(caps)}")

                # Size info
                if ep.typical_row_count:
                    lines.append(f"- **Typical Rows**: ~{ep.typical_row_count:,}")

                # Chunking
                if ep.chunk_strategy and ep.chunk_strategy != "none":
                    lines.append(
                        f"- **Recommended Chunking**: {ep.chunk_strategy}-based"
                    )

                # Sample query
                if ep.sample_params:
                    import json

                    lines.append(
                        f"- **Example**: `fetch('{ep.name}', {json.dumps(ep.sample_params)})`"
                    )

                lines.append("")

        lines.extend(
            [
                "## Quick Start",
                "",
                "To inspect an endpoint before fetching:",
                "```python",
                'inspect_endpoint("player_career_stats", {"player_name": "LeBron James"})',
                "```",
                "",
                "To fetch data:",
                "```python",
                'fetch("player_career_stats", {"player_name": "LeBron James"})',
                "```",
                "",
                "To fetch large datasets in chunks:",
                "```python",
                'fetch_chunked("shot_chart", {"entity_name": "Stephen Curry"}, "date")',
                "```",
            ]
        )

        return "\n".join(lines)

    except Exception as e:
        logger.exception("Error in discover_nba_endpoints")
        return f"Error discovering endpoints: {str(e)}"


@mcp_server.tool()
async def configure_limits(
    max_fetch_mb: Optional[float] = None,
    show_current: bool = False,
) -> str:
    """
    Configure dataset size limits for fetch operations.

    Controls the maximum size of datasets that can be fetched in a single
    operation. Helps prevent excessive memory usage and unexpected large downloads.

    Default limit: 1024 MB (1 GB)
    Set to -1 for unlimited (⚠ use with caution)

    Args:
        max_fetch_mb: New maximum fetch size in MB (-1 for unlimited)
        show_current: Just show current limits without changing (default: False)

    Returns:
        Current limit configuration and statistics

    Examples:
        configure_limits(show_current=True)
        → Shows current limit (1024 MB by default)

        configure_limits(max_fetch_mb=2048)
        → Increases limit to 2 GB

        configure_limits(max_fetch_mb=512)
        → Decreases limit to 512 MB

        configure_limits(max_fetch_mb=-1)
        → Sets to unlimited (⚠ use with caution)

    Environment Variable:
        NBA_MCP_MAX_FETCH_SIZE_MB=2048  # Set limit at startup
    """
    try:
        from nba_mcp.data.limits import get_limits

        limits = get_limits()

        # Update limit if provided
        if max_fetch_mb is not None:
            old_limit = limits.get_max_fetch_size_mb()
            limits.set_max_fetch_size_mb(max_fetch_mb)

            if max_fetch_mb == -1:
                action_msg = f"⚠️ Limit set to **UNLIMITED** (was {old_limit:.0f} MB)"
                warning_msg = "\n\n**Warning**: Unlimited mode allows fetching datasets of any size. This may cause:\n- High memory usage\n- Long API response times\n- Potential system instability\n\nRecommendation: Use fetch_chunked() for large datasets instead."
            else:
                action_msg = f"✓ Limit updated: {old_limit:.0f} MB → {max_fetch_mb:.0f} MB"
                warning_msg = ""
        else:
            action_msg = "Current configuration:"
            warning_msg = ""

        # Get current stats
        stats = limits.get_stats()

        # Format response
        lines = [
            "# Fetch Size Limit Configuration",
            "",
            action_msg + warning_msg,
            "",
            "## Current Settings",
            "",
        ]

        if stats["is_unlimited"]:
            lines.extend([
                f"- **Status**: ⚠️ UNLIMITED",
                f"- **Description**: No size restrictions",
                f"- **Recommendation**: Use fetch_chunked() for large datasets",
            ])
        else:
            lines.extend([
                f"- **Max Fetch Size**: {stats['max_fetch_mb']:.0f} MB ({stats['max_fetch_gb']:.2f} GB)",
                f"- **Description**: {stats['description']}",
            ])

        lines.extend([
            "",
            "## What This Controls",
            "",
            "The fetch size limit controls:",
            "- Maximum size for single `fetch()` operations",
            "- Triggers warnings when datasets exceed the limit",
            "- Recommends chunked fetching for large datasets",
            "",
            "**Note**: This limit does NOT apply to `fetch_chunked()`, which handles",
            "datasets of any size by fetching in smaller chunks.",
            "",
            "## Usage Examples",
            "",
            "**Increase limit for one-time large fetch:**",
            "```python",
            "configure_limits(max_fetch_mb=5120)  # 5 GB",
            'fetch("large_dataset", {...})',
            "```",
            "",
            "**Or use chunked fetching (recommended):**",
            "```python",
            'fetch_chunked("large_dataset", {...})  # No size limit needed',
            "```",
            "",
            "**Reset to default:**",
            "```python",
            "configure_limits(max_fetch_mb=1024)  # Reset to 1 GB",
            "```",
        ])

        # Add environment variable info
        env_var = os.getenv("NBA_MCP_MAX_FETCH_SIZE_MB")
        if env_var:
            lines.extend([
                "",
                "## Environment Configuration",
                f"- **NBA_MCP_MAX_FETCH_SIZE_MB**: {env_var}",
                "- Environment variable is set and was used at startup",
            ])
        else:
            lines.extend([
                "",
                "## Environment Configuration",
                "- **NBA_MCP_MAX_FETCH_SIZE_MB**: Not set",
                "- Using default value (1024 MB)",
                "- Set environment variable to configure limit at startup",
            ])

        return "\n".join(lines)

    except Exception as e:
        logger.exception("Error in configure_limits")
        return f"Error configuring limits: {str(e)}"


#########################################
# Running the Server
#########################################


# ------------------------------------------------------------------
# nba_server.py
# ------------------------------------------------------------------
def main():
    """Parse CLI args and start FastMCP server (with fallback)."""
    parser = argparse.ArgumentParser(prog="nba-mcp")
    parser.add_argument(
        "--mode",
        choices=["claude", "local"],
        default="claude",
        help="Which port profile to use",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "websocket"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="MCP transport to use",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MCP_HOST", "127.0.0.1"),
        help="Host to bind for SSE/WebSocket",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "0")) or None,
        help="Port for SSE/WebSocket (None for stdio)",
    )
    args = parser.parse_args()

    # pick port based on mode
    if args.mode == "claude":
        port = int(os.getenv("NBA_MCP_PORT", "8000"))
    else:
        port = int(os.getenv("NBA_MCP_PORT", "8001"))

    transport = args.transport
    host = args.host

    # if they explicitly passed --port, override
    if args.port:
        port = args.port

    # Initialize dataset manager
    logger.info("Initializing dataset manager...")
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(initialize_manager())
    logger.info("✓ Dataset manager initialized")

    # Initialize NLQ tool registry with real MCP tools
    logger.info("Initializing NLQ tool registry...")
    tool_map = {
        "get_league_leaders_info": get_league_leaders_info,
        "compare_players": compare_players,
        "get_team_standings": get_team_standings,
        "get_team_advanced_stats": get_team_advanced_stats,
        "get_player_advanced_stats": get_player_advanced_stats,
        "get_live_scores": get_live_scores,
        "get_player_career_information": get_player_career_information,
    }
    initialize_tool_registry(tool_map)
    logger.info(f"NLQ tool registry initialized with {len(tool_map)} tools")

    # Initialize Week 4 infrastructure (cache + rate limiting)
    logger.info("Initializing Week 4 infrastructure...")

    # Initialize Redis cache
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    redis_db = int(os.getenv("REDIS_DB", "0"))
    try:
        initialize_cache(redis_url=redis_url, db=redis_db)
        logger.info(f"✓ Redis cache initialized (url={redis_url}, db={redis_db})")
    except Exception as e:
        logger.warning(f"Redis cache initialization failed: {e}")
        logger.warning("Continuing without cache (performance may be reduced)")

    # Initialize rate limiter with per-tool limits
    try:
        initialize_rate_limiter()
        limiter = get_rate_limiter()

        # Configure rate limits for different tool categories
        # Live data: 10 requests/min (aggressive rate limiting)
        limiter.add_limit(
            "get_live_scores", capacity=10.0, refill_rate=0.167
        )  # 10/60sec

        # Moderate cost: 60 requests/min
        limiter.add_limit("get_league_leaders_info", capacity=60.0, refill_rate=1.0)
        limiter.add_limit("get_team_standings", capacity=60.0, refill_rate=1.0)
        limiter.add_limit(
            "get_player_career_information", capacity=60.0, refill_rate=1.0
        )

        # Complex queries: 30 requests/min
        limiter.add_limit("compare_players", capacity=30.0, refill_rate=0.5)
        limiter.add_limit("get_team_advanced_stats", capacity=30.0, refill_rate=0.5)
        limiter.add_limit("get_player_advanced_stats", capacity=30.0, refill_rate=0.5)

        # Set global daily quota (10,000 requests/day)
        daily_quota = int(os.getenv("NBA_API_DAILY_QUOTA", "10000"))
        limiter.set_global_quota(daily_limit=daily_quota)

        logger.info(f"✓ Rate limiter initialized (daily quota: {daily_quota})")
    except Exception as e:
        logger.warning(f"Rate limiter initialization failed: {e}")
        logger.warning("Continuing without rate limiting (API quota may be exhausted)")

    logger.info("Week 4 infrastructure initialization complete")

    # Initialize Week 4 observability (metrics + tracing)
    logger.info("Initializing Week 4 observability...")

    # Initialize metrics
    try:
        initialize_metrics()
        metrics = get_metrics_manager()
        metrics.set_server_info(
            version="1.0.0", environment=os.getenv("ENVIRONMENT", "development")
        )
        logger.info("✓ Prometheus metrics initialized")

        # Start periodic metrics update
        import asyncio
        import threading

        def metrics_updater():
            """Background thread to update infrastructure metrics."""
            while True:
                try:
                    update_infrastructure_metrics()
                except Exception as e:
                    logger.debug(f"Metrics update failed: {e}")
                time.sleep(10)  # Update every 10 seconds

        metrics_thread = threading.Thread(target=metrics_updater, daemon=True)
        metrics_thread.start()
        logger.info("✓ Metrics updater started (10s interval)")

    except Exception as e:
        logger.warning(f"Metrics initialization failed: {e}")
        logger.warning("Continuing without metrics")

    # Initialize tracing
    try:
        otlp_endpoint = os.getenv("OTLP_ENDPOINT")  # e.g., "localhost:4317"
        console_export = os.getenv("OTEL_CONSOLE_EXPORT", "false").lower() == "true"

        initialize_tracing(
            service_name="nba-mcp",
            otlp_endpoint=otlp_endpoint,
            console_export=console_export,
        )

        if otlp_endpoint:
            logger.info(
                f"✓ OpenTelemetry tracing initialized (endpoint: {otlp_endpoint})"
            )
        else:
            logger.info("✓ OpenTelemetry tracing initialized (no export endpoint)")

    except Exception as e:
        logger.warning(f"Tracing initialization failed: {e}")
        logger.warning("Continuing without tracing")

    # Start metrics HTTP server (for Prometheus scraping)
    metrics_port = int(os.getenv("METRICS_PORT", port + 1 if port else 9090))
    try:
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class MetricsHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/metrics":
                    try:
                        metrics = get_metrics_manager()
                        data = metrics.get_metrics()
                        self.send_response(200)
                        self.send_header("Content-Type", metrics.get_content_type())
                        self.end_headers()
                        self.wfile.write(data)
                    except Exception as e:
                        self.send_error(500, f"Metrics error: {e}")
                elif self.path == "/health":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status": "healthy"}')
                else:
                    self.send_error(404)

            def log_message(self, format, *args):
                pass  # Suppress HTTP logs

        metrics_server = HTTPServer(("0.0.0.0", metrics_port), MetricsHandler)

        def run_metrics_server():
            metrics_server.serve_forever()

        metrics_thread = threading.Thread(target=run_metrics_server, daemon=True)
        metrics_thread.start()
        logger.info(
            f"✓ Metrics HTTP server started on port {metrics_port} (/metrics, /health)"
        )

    except Exception as e:
        logger.warning(f"Metrics HTTP server failed to start: {e}")
        logger.warning("Metrics will not be available for Prometheus scraping")

    logger.info("Week 4 observability initialization complete")

    # if using network transport, check availability
    if transport != "stdio" and port is not None and not port_available(port, host):
        logger.warning("Port %s:%s not available → falling back to stdio", host, port)
        transport = "stdio"

        mcp_server.host = host
        mcp_server.port = port
    try:
        if transport == "stdio":
            logger.info("Starting FastMCP server on STDIO")
            mcp.run()
        else:
            logger.info("Starting FastMCP server on %s://%s:%s", transport, host, port)
            mcp.run(transport=transport)
    except Exception:
        logger.exception("Failed to start MCP server (transport=%s)", transport)
        sys.exit(1)


if __name__ == "__main__":
    main()
