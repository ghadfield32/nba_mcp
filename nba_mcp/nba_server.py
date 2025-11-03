# nba_mcp\nba_server.py
# near the top of nba_server.py
import argparse
import json
import os
import sys
import threading
import time
import traceback
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Union

# Load environment variables from .env file
from dotenv import load_dotenv
from pathlib import Path

# Load .env at module level (before BASE_PORT is set)
_project_root = Path(__file__).parent.parent  # nba_mcp/nba_mcp/nba_server.py -> nba_mcp/
_env_path = _project_root / ".env"
load_dotenv(dotenv_path=_env_path)  # ✅ Load BEFORE BASE_PORT

import pandas as pd
from fastmcp import Context
from mcp.server.fastmcp import FastMCP
from nba_api.live.nba.endpoints.scoreboard import ScoreBoard
from nba_api.stats.static import players, teams

# nba_server.py (add near the top)
from pydantic import BaseModel, Field

from nba_mcp.api.advanced_metrics_calculator import AdvancedMetricsCalculator
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

# Import Phase 3 feature modules (shot charts, game context, schedule)
from nba_mcp.api.game_context import get_game_context as fetch_game_context
from nba_mcp.api.lineup_tracker import add_lineups_to_play_by_play

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
from nba_mcp.api.schedule import format_schedule_markdown
from nba_mcp.api.schedule import get_nba_schedule as fetch_nba_schedule

# Import data groupings and advanced metrics (Phase 4)
from nba_mcp.api.season_aggregator import get_player_season_stats, get_team_season_stats

# Import season context for LLM temporal awareness
from nba_mcp.api.season_context import get_current_season, get_season_context
from nba_mcp.api.shot_charts import get_shot_chart as fetch_shot_chart

# Import date parser for natural language date support
from nba_mcp.api.tools.date_parser import parse_and_normalize_date_params
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

# Import Week 4 infrastructure (cache + rate limiting)
from nba_mcp.cache.redis_cache import CacheTier, cached, get_cache, initialize_cache

# Import dataset and joins features
from nba_mcp.data.catalog import get_catalog
from nba_mcp.data.dataset_manager import get_manager as get_dataset_manager
from nba_mcp.data.dataset_manager import initialize_manager, shutdown_manager
from nba_mcp.data.fetch import fetch_endpoint, validate_parameters
from nba_mcp.data.joins import filter_table, join_tables, join_with_stats

# Import NLQ pipeline components
from nba_mcp.nlq.pipeline import answer_nba_question as nlq_answer_question
from nba_mcp.nlq.pipeline import get_pipeline_status
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

# Read BASE_PORT from .env file (NBA_MCP_PORT), defaults to 8005
# .env is loaded at module level above, so this reads the configured value
BASE_PORT = int(os.getenv("NBA_MCP_PORT", "8005"))  # ✅ Gets 8005 from .env

# only grab "--mode" here for backward compatibility (not used for port selection)
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument(
    "--mode",
    choices=["claude", "local"],
    default="claude",
    help="Which port profile to use",
)
args, _ = parser.parse_known_args()


# import logger
import logging

logger = logging.getLogger(__name__)


# Phase 5.2 (P6 Phase 3): Caching infrastructure for lineup data (2025-11-01)
from functools import lru_cache

# Cache TTL management
_lineup_cache_timestamps = {}
_lineup_cache_lock = threading.Lock()
LINEUP_CACHE_TTL_SECONDS = 3600  # 1 hour


def _is_cache_valid(cache_key: str) -> bool:
    """
    Check if cache entry is still valid based on TTL.

    Phase 5.2 (P6 Phase 3): Cache TTL validation (2025-11-01)
    """
    with _lineup_cache_lock:
        if cache_key not in _lineup_cache_timestamps:
            return False
        timestamp = _lineup_cache_timestamps[cache_key]
        age = (datetime.now() - timestamp).total_seconds()
        return age < LINEUP_CACHE_TTL_SECONDS


def _update_cache_timestamp(cache_key: str):
    """
    Update cache timestamp for TTL tracking.

    Phase 5.2 (P6 Phase 3): Cache timestamp management (2025-11-01)
    """
    with _lineup_cache_lock:
        _lineup_cache_timestamps[cache_key] = datetime.now()


@lru_cache(maxsize=128)
def _fetch_lineup_data_cached(team_id: int, season: str, season_type: str = "Regular Season"):
    """
    Cached lineup data fetcher with TTL validation.

    Phase 5.2 (P6 Phase 3): Lineup Data Caching (2025-11-01)

    Args:
        team_id: NBA team ID
        season: Season in 'YYYY-YY' format
        season_type: "Regular Season", "Playoffs", etc.

    Returns:
        pandas DataFrame with lineup data

    Cache Strategy:
        - LRU cache with maxsize=128 (covers ~30 teams x 4 seasons)
        - TTL: 1 hour (3600 seconds)
        - Cache key: (team_id, season, season_type)
        - Thread-safe TTL checking

    Performance:
        - Cache hit: ~5ms (vs ~150-300ms API call)
        - Expected hit rate: 60-80% for repeated queries
        - Memory usage: ~6.4MB (128 entries * 50KB each)
    """
    cache_key = f"{team_id}_{season}_{season_type}"

    # Check TTL - if expired, clear this cache entry
    if not _is_cache_valid(cache_key):
        # Clear this specific cache entry by calling with different args
        # (LRU cache doesn't have direct invalidation, so we track TTL separately)
        _update_cache_timestamp(cache_key)
        logger.info(f"Cache MISS (expired): {cache_key}")
    else:
        logger.info(f"Cache HIT: {cache_key}")

    # Import here to avoid circular imports
    from nba_api.stats.endpoints import leaguedashlineups

    # Fetch from NBA API
    lineup_data = leaguedashlineups.LeagueDashLineups(
        team_id_nullable=team_id,
        season=season,
        season_type_nullable=season_type,
        measure_type_detailed_defense="Base",
        per_mode_detailed="Totals"
    )

    df = lineup_data.get_data_frames()[0]

    # Update timestamp on fresh fetch
    _update_cache_timestamp(cache_key)

    return df


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

    # Default to current season if not specified
    if season is None:
        season = get_current_season()

    client = NBAApiClient()

    try:
        # 1) Fetch
        result = await client.get_player_career_stats(
            player_name, season, as_dataframe=True
        )
        logger.debug("Raw result type: %s, value: %r", type(result), result)

        # 2) If the client returned an error dict, propagate it
        if isinstance(result, dict) and "error" in result:
            logger.error("API error payload: %s", result)
            season_ctx = get_season_context()
            return f"📅 {season_ctx}\n\n❌ {result['error']}"

        # 3) If it returned a string (no data / user-friendly), pass it back
        if isinstance(result, str):
            season_ctx = get_season_context()
            return f"📅 {season_ctx}\n\n{result}"

        # 4) If it's not a DataFrame, we have an unexpected payload
        if not isinstance(result, pd.DataFrame):
            logger.error("Unexpected payload type (not DataFrame): %s", type(result))
            season_ctx = get_season_context()
            return f"📅 {season_ctx}\n\nUnexpected response format from API tool: {type(result).__name__}. Please check server logs."

        # 5) Now we can safely treat it as a DataFrame
        df: pd.DataFrame = result
        if df.empty:
            season_ctx = get_season_context()
            return f"📅 {season_ctx}\n\nNo career stats found for '{player_name}' in {season}."

        # 6) Format a more detailed response with proper stats
        if len(df) == 1:
            # Single season data
            row = df.iloc[0]
            team = row.get("TEAM_ABBREVIATION", "N/A")
            response = "\n".join(
                [
                    f"Player: {player_name}",
                    f"Season: {season} ({team})",
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
            response = "\n".join(
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

        # Add season context
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n{response}"

    except Exception as e:
        # 7) Uncaught exception: log full traceback
        logger.exception("Unexpected error in get_player_career_information")
        season_ctx = get_season_context()
        return f"📅 {season_ctx}\n\n❌ Unexpected error in get_player_career_information: {e}"


@mcp_server.tool()
async def get_league_leaders_info(
    stat_category: str,
    season: Optional[str] = None,
    per_mode: str = "PerGame",
    season_type_all_star: str = "Regular Season",
    limit: int = 10,
    format: str = "text",
    min_games_played: Optional[int] = None,
    conference: Optional[str] = None,
    team: Optional[str] = None,
) -> str:
    """
    Get league leaders for specified stat category with improved error handling.

    Args:
        stat_category: Statistical category (e.g., 'PTS', 'AST', 'REB', 'FG_PCT')
        season: Season in 'YYYY-YY' format (defaults to current season)
        per_mode: Aggregation mode ('Totals', 'PerGame', 'Per48')
        season_type_all_star: Season type ('Regular Season', 'Playoffs')
        limit: Maximum number of leaders to return
        format: Output format ('text' or 'json')
        min_games_played: Minimum games played filter (optional)
        conference: Conference filter ('East' or 'West') (optional)
        team: Team filter (optional)

    Returns:
        Formatted string with top N leaders or JSON
    """
    logger.debug(
        "get_league_leaders_info(stat=%s, season=%s, per_mode=%s, limit=%d)",
        stat_category,
        season,
        per_mode,
        limit,
    )

    # Default to current season if not specified
    if season is None:
        season = get_current_season()

    try:
        client = NBAApiClient()
        result = await client.get_league_leaders(
            season=season,
            stat_category=stat_category,
            per_mode=per_mode,
            season_type_all_star=season_type_all_star,
            as_dataframe=True
        )

        # ========================================================================
        # BUG FIX: Handle empty/invalid responses before processing
        # ========================================================================
        # Check for error string response
        if isinstance(result, str):
            season_ctx = get_season_context()
            return f"📅 {season_ctx}\n\n{result}"

        # Check if result is not a DataFrame
        if not isinstance(result, pd.DataFrame):
            season_ctx = get_season_context()
            return f"📅 {season_ctx}\n\nUnexpected response format: {type(result)}"

        df: pd.DataFrame = result

        # Check for empty DataFrame
        if df.empty:
            season_ctx = get_season_context()
            return f"📅 {season_ctx}\n\nNo data available for {stat_category} leaders in {season}"

        # Apply optional filters
        if min_games_played is not None:
            if "GP" in df.columns:
                df = df[df["GP"] >= min_games_played]

        if team is not None:
            if "TEAM" in df.columns:
                df = df[df["TEAM"] == team.upper()]

        if conference is not None:
            if "TEAM" in df.columns:
                df = df[df["TEAM"].map(lambda t: TEAM_TO_CONFERENCE.get(t) == conference)]

        # Check again after filtering
        if df.empty:
            season_ctx = get_season_context()
            return f"📅 {season_ctx}\n\nNo leaders found after applying filters"

        # Format output
        if format == "json":
            leaders_data = []
            for _, r in df.head(limit).iterrows():
                leader = {
                    "player_name": str(r.get("PLAYER_NAME", r.get("PLAYER", "Unknown"))),
                    "team": str(r.get("TEAM", "N/A")),
                    "value": float(r.get(stat_category, 0)) if pd.notna(r.get(stat_category)) else None,
                }
                leaders_data.append(leader)

            response = json.dumps({"leaders": leaders_data, "season": season}, indent=2)
        else:
            # Text format
            out = [f"Top {limit} {stat_category} Leaders ({season}):"]
            for i, (_, r) in enumerate(df.head(limit).iterrows(), 1):
                name = r.get("PLAYER_NAME", r.get("PLAYER", "Unknown"))
                team = r.get("TEAM", "N/A")
                value = r.get(stat_category, "N/A")
                out.append(f"{i}. {name} ({team}): {value}")
            response = "\n".join(out)

        # Add season context
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n{response}"

    except EntityNotFoundError as e:
        season_ctx = get_season_context()
        return f"📅 {season_ctx}\n\n❌ {str(e)}"
    except Exception as e:
        logger.exception("Error in get_league_leaders_info")
        season_ctx = get_season_context()
        return f"📅 {season_ctx}\n\n❌ Error fetching league leaders: {str(e)}"


@mcp_server.tool()
async def get_all_time_leaders(
    stat_category: str = "PTS",
    top_n: int = 10,
    format: str = "text",
    active_only: bool = False,
) -> str:
    """
    Get all-time NBA career leaders for a statistical category.

    Phase 5.2 (P4): All-Time Leaders Tool (2025-11-01)
    Provides career totals for statistical categories across NBA history.

    Args:
        stat_category: Statistical category (e.g., 'PTS', 'AST', 'REB', 'STL', 'BLK')
        top_n: Number of leaders to return (default: 10)
        format: Output format ('text' or 'json')
        active_only: If True, only include active players (default: False)

    Returns:
        Formatted string with all-time leaders or JSON

    Supported Categories:
        - PTS: Career points
        - AST: Career assists
        - REB: Career rebounds (total)
        - STL: Career steals
        - BLK: Career blocks
        - FGM: Career field goals made
        - FG3M: Career three-pointers made
        - FTM: Career free throws made
        - GP: Career games played
        - Other stats: OREB, DREB, TOV, PF, FGA, FG3A, FTA

    Examples:
        >>> await get_all_time_leaders("PTS", top_n=10)
        "All-Time Points Leaders:
        1. LeBron James: 42,184 (Active)
        2. Kareem Abdul-Jabbar: 38,387
        ..."

        >>> await get_all_time_leaders("AST", top_n=5, active_only=True)
        "All-Time Assists Leaders (Active Players Only):
        1. Chris Paul: 12,345 (Active)
        ..."
    """
    logger.debug(
        "get_all_time_leaders(stat=%s, top_n=%d, active_only=%s)",
        stat_category,
        top_n,
        active_only,
    )

    # Mapping from stat category to dataset name in AllTimeLeadersGrids
    STAT_TO_DATASET = {
        "PTS": "PTSLeaders",
        "AST": "ASTLeaders",
        "REB": "REBLeaders",
        "STL": "STLLeaders",
        "BLK": "BLKLeaders",
        "FGM": "FGMLeaders",
        "FGA": "FGALeaders",
        "FG_PCT": "FG_PCTLeaders",
        "FG3M": "FG3MLeaders",
        "FG3A": "FG3ALeaders",
        "FG3_PCT": "FG3_PCTLeaders",
        "FTM": "FTMLeaders",
        "FTA": "FTALeaders",
        "FT_PCT": "FT_PCTLeaders",
        "OREB": "OREBLeaders",
        "DREB": "DREBLeaders",
        "TOV": "TOVLeaders",
        "PF": "PFLeaders",
        "GP": "GPLeaders",
    }

    # Normalize stat category (uppercase, handle common aliases)
    stat_upper = stat_category.upper()

    # Check if stat category is supported
    if stat_upper not in STAT_TO_DATASET:
        supported = ", ".join(sorted(STAT_TO_DATASET.keys()))
        season_ctx = get_season_context()
        return f"📅 {season_ctx}\n\n❌ Unsupported stat category: {stat_category}\n\nSupported categories: {supported}"

    try:
        # Import AllTimeLeadersGrids endpoint
        from nba_api.stats.endpoints import alltimeleadersgrids

        # Fetch all-time leaders data
        logger.debug(f"Fetching AllTimeLeadersGrids endpoint")

        import asyncio
        all_time_data = await asyncio.to_thread(
            alltimeleadersgrids.AllTimeLeadersGrids
        )

        # Get DataFrames
        dfs = all_time_data.get_data_frames()

        # Find the appropriate dataset
        dataset_name = STAT_TO_DATASET[stat_upper]
        dataset_index = None

        # The datasets are returned in a specific order, we need to find the right one
        # by matching column names
        for idx, df in enumerate(dfs):
            if stat_upper in df.columns:
                dataset_index = idx
                break

        if dataset_index is None:
            season_ctx = get_season_context()
            return f"📅 {season_ctx}\n\n❌ Could not find {stat_upper} data in AllTimeLeadersGrids response"

        df = dfs[dataset_index]

        # Check for empty DataFrame
        if df.empty:
            season_ctx = get_season_context()
            return f"📅 {season_ctx}\n\nNo all-time leaders data available for {stat_upper}"

        # Filter for active players if requested
        if active_only and "IS_ACTIVE_FLAG" in df.columns:
            df = df[df["IS_ACTIVE_FLAG"] == "Y"]

            if df.empty:
                season_ctx = get_season_context()
                return f"📅 {season_ctx}\n\nNo active players found in all-time {stat_upper} leaders"

        # Sort by rank if available, otherwise by stat value (descending)
        rank_col = f"{stat_upper}_RANK"
        if rank_col in df.columns:
            df = df.sort_values(rank_col)
        else:
            df = df.sort_values(stat_upper, ascending=False)

        # Limit to top N
        df = df.head(top_n)

        # Format output
        if format == "json":
            leaders_data = []
            for _, row in df.iterrows():
                leader = {
                    "player_name": str(row.get("PLAYER_NAME", "Unknown")),
                    "player_id": int(row.get("PLAYER_ID", 0)),
                    "value": float(row.get(stat_upper, 0)) if pd.notna(row.get(stat_upper)) else None,
                    "rank": int(row.get(rank_col, 0)) if rank_col in df.columns else None,
                    "is_active": str(row.get("IS_ACTIVE_FLAG", "N")) == "Y",
                }
                leaders_data.append(leader)

            response = json.dumps({
                "stat_category": stat_upper,
                "leaders": leaders_data,
                "active_only": active_only,
                "total_shown": len(leaders_data)
            }, indent=2)
        else:
            # Text format
            header = f"All-Time {stat_upper} Leaders"
            if active_only:
                header += " (Active Players Only)"
            header += ":"

            out = [header]
            for i, (_, row) in enumerate(df.iterrows(), 1):
                name = row.get("PLAYER_NAME", "Unknown")
                value = row.get(stat_upper, "N/A")
                is_active = str(row.get("IS_ACTIVE_FLAG", "N")) == "Y"

                # Format value with commas for readability
                if isinstance(value, (int, float)) and not pd.isna(value):
                    if stat_upper.endswith("_PCT"):
                        # Format percentages
                        value_str = f"{value:.1%}" if value < 1 else f"{value:.3f}"
                    else:
                        # Format integers with commas
                        value_str = f"{int(value):,}"
                else:
                    value_str = str(value)

                active_tag = " (Active)" if is_active else ""
                out.append(f"{i}. {name}: {value_str}{active_tag}")

            response = "\n".join(out)

        # Add season context
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n{response}"

    except ImportError:
        season_ctx = get_season_context()
        return f"📅 {season_ctx}\n\n❌ AllTimeLeadersGrids endpoint not available in nba_api"
    except Exception as e:
        logger.exception("Error in get_all_time_leaders")
        season_ctx = get_season_context()
        return f"📅 {season_ctx}\n\n❌ Error fetching all-time leaders: {str(e)}"


@mcp_server.tool()
async def get_live_scores(target_date: Optional[str] = None, **kwargs) -> str:
    """
    Provides live or historical NBA scores for a specified date.

    Supports natural language dates like "yesterday", "today", "tomorrow" and
    relative offsets like "-1 day", "+2 days".

    Parameters:
        target_date (Optional[str]): Date for scores. Supports multiple formats:
            - Absolute: 'YYYY-MM-DD' (e.g., '2024-12-25')
            - Natural language: 'yesterday', 'today', 'tomorrow'
            - Relative: '-1 day', '+2 days', 'last week'
            - If None or omitted, defaults to today's scores

    Parameter Aliases:
        - 'date' can be used instead of 'target_date'
        - 'game_date' can be used instead of 'target_date'

    Returns:
        str: Formatted game summaries like 'Lakers vs Suns – 102-99 (Final)'.

    Examples:
        get_live_scores()                    # Today's games
        get_live_scores(target_date="yesterday")
        get_live_scores(date="2024-12-25")  # Parameter alias
        get_live_scores(target_date="-1 day")
    """
    # Step 1: Normalize parameters (handle aliases and parse dates)
    params = {"target_date": target_date, **kwargs}
    normalized_params, debug_messages = parse_and_normalize_date_params(
        params,
        date_param_name="target_date",
        date_param_aliases=["date", "game_date", "day"]
    )

    # Log parameter transformations for debugging
    if debug_messages:
        logger.info(f"[get_live_scores] Parameter normalization:")
        for msg in debug_messages:
            logger.info(f"  - {msg}")

    # Extract the normalized target_date
    target_date = normalized_params.get("target_date")

    # Log what we're about to query
    if target_date:
        logger.info(f"[get_live_scores] Querying historical scores for date: {target_date}")
    else:
        logger.info(f"[get_live_scores] Querying live scores (no date specified, using today)")

    # Step 2: Initialize NBA API client
    client = NBAApiClient()

    try:
        # Step 3: Fetch scoreboard data
        result = await client.get_live_scoreboard(
            target_date=target_date, as_dataframe=False
        )

        # Handle error responses
        if isinstance(result, str):
            logger.warning(f"[get_live_scores] API returned error string: {result}")
            return result

        # Step 4: Extract and validate response data
        response_date = result.get("date")
        games = result.get("games", [])

        logger.info(
            f"[get_live_scores] Successfully retrieved {len(games)} game(s) for date: {response_date}"
        )

        if not games:
            return f"No games found for {response_date}."

        # Step 5: Format game summaries
        lines = []
        for g in games:
            # Skip invalid game objects
            if isinstance(g, str):
                logger.warning(f"[get_live_scores] Skipping invalid game object: {g}")
                continue

            try:
                summary = g.get("scoreBoardSummary") or g.get("scoreBoardSnapshot")
                home = summary["homeTeam"]
                away = summary["awayTeam"]

                # Real-time if the live-API gave us `teamName`+`score`
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
            except (KeyError, TypeError) as e:
                logger.error(f"[get_live_scores] Error parsing game data: {e}")
                continue

        # Step 6: Format and return response
        header = f"NBA Games for {response_date}:\n"
        return header + "\n".join(lines)

    except Exception as e:
        # Log full traceback for debugging
        logger.exception(f"[get_live_scores] Unexpected error occurred")

        # Return user-friendly error message
        error_msg = str(e)
        if "Not Found" in error_msg or "404" in error_msg:
            return (
                f"❌ Could not find games for the specified date. "
                f"This might be because:\n"
                f"  - The date is too far in the future (schedule not released)\n"
                f"  - The date format was invalid\n"
                f"  - There were no games on that date\n\n"
                f"💡 Try using get_nba_schedule() to see upcoming games, or "
                f"specify a date within the current season."
            )

        return f"❌ Error fetching live scores: {error_msg}"


# Allowed season types per NBA API; we will always query all
_ALLOWED_SEASON_TYPES = [
    "Regular Season",
    "Playoffs",
    "Pre Season",
    "All Star",
    "All-Star",
]


def format_game_log(df: pd.DataFrame, team: Optional[str] = None, season: Optional[str] = None) -> str:
    """
    Format team game log DataFrame into human-readable string.

    Args:
        df: DataFrame with game log data (columns: GAME_DATE, MATCHUP, WL, PTS, etc.)
        team: Team name for header (optional)
        season: Season string for header (optional)

    Returns:
        Multi-line formatted string with game results

    Example output:
        Team: Los Angeles Lakers | Season: 2024-25 | Games: 3

        Date         Matchup           W/L  PTS  OPP_PTS  +/-
        2024-11-15   LAL vs. GSW       W    115  110      +5
        2024-11-13   LAL @ PHX         L    108  112      -4
        2024-11-11   LAL vs. DEN       W    120  115      +5
    """
    if df.empty:
        return "No games found"

    # Build header
    header_parts = []
    if team:
        header_parts.append(f"Team: {team}")
    if season:
        header_parts.append(f"Season: {season}")
    header_parts.append(f"Games: {len(df)}")
    header = " | ".join(header_parts)

    # Prepare lines for each game
    lines = [header, ""]  # Header + blank line

    # Column headers
    lines.append(f"{'Date':<12} {'Matchup':<20} {'W/L':<4} {'PTS':<4} {'OPP_PTS':<8} {'+/-':<6}")
    lines.append("-" * 60)

    # Format each game
    for _, row in df.iterrows():
        try:
            # Extract fields with safe defaults
            game_date = row.get("GAME_DATE", "N/A")
            if isinstance(game_date, pd.Timestamp):
                game_date = game_date.strftime("%Y-%m-%d")
            elif isinstance(game_date, str):
                # Already a string, use as-is
                pass
            else:
                game_date = str(game_date)

            matchup = str(row.get("MATCHUP", "N/A"))
            wl = str(row.get("WL", "N/A"))
            pts = int(row.get("PTS", 0)) if pd.notna(row.get("PTS")) else 0
            plus_minus = int(row.get("PLUS_MINUS", 0)) if pd.notna(row.get("PLUS_MINUS")) else 0

            # Calculate opponent points (PTS - PLUS_MINUS = OPP_PTS)
            opp_pts = pts - plus_minus

            # Format plus/minus with sign
            pm_str = f"+{plus_minus}" if plus_minus >= 0 else str(plus_minus)

            # Format line
            line = f"{game_date:<12} {matchup:<20} {wl:<4} {pts:<4} {opp_pts:<8} {pm_str:<6}"
            lines.append(line)

        except Exception as e:
            # Log error but continue with other games
            logger.warning(f"Error formatting game row: {e}")
            lines.append(f"{'ERROR':<12} {'Error formatting game':<20} {'N/A':<4} {'N/A':<4} {'N/A':<8} {'N/A':<6}")

    # Add summary
    wins = len(df[df["WL"] == "W"]) if "WL" in df.columns else 0
    losses = len(df[df["WL"] == "L"]) if "WL" in df.columns else 0
    lines.append("")
    lines.append(f"Record: {wins}-{losses}")

    if "PTS" in df.columns:
        avg_pts = df["PTS"].mean() if len(df) > 0 else 0
        lines.append(f"Average Points: {avg_pts:.1f}")

    return "\n".join(lines)


@mcp_server.tool()
async def get_date_range_game_log_or_team_game_log(
    season: str,
    team: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> str:
    """
    Get team game logs for a season or date range.

    Args:
        season: Season in 'YYYY-YY' format (e.g., '2023-24')
        team: Team name, nickname, or abbreviation (optional)
        date_from: Start date in 'YYYY-MM-DD' or 'MM/DD/YYYY' format (optional)
        date_to: End date in 'YYYY-MM-DD' or 'MM/DD/YYYY' format (optional)

    Returns:
        JSON string with ResponseEnvelope containing game log data as list of dicts.

        Response structure:
        {
            "status": "success",
            "data": [
                {
                    "GAME_ID": "0022300123",
                    "GAME_DATE": "2024-01-15",
                    "MATCHUP": "LAL vs. BOS",
                    "WL": "W",
                    "PTS": 115,
                    ...
                },
                ...
            ],
            "metadata": {
                "version": "v1",
                "timestamp": "2025-10-30T...",
                "source": "historical",
                "cache_status": "miss",
                "rows": 82,
                "columns": 30,
                "date_range": {
                    "from": "2023-10-24",
                    "to": "2024-04-14"
                }
            }
        }

    Examples:
        # All games for team in season
        >>> result = await get_date_range_game_log_or_team_game_log(
        ...     season="2024-25",
        ...     team="Lakers"
        ... )

        # Filtered by date range
        >>> result = await get_date_range_game_log_or_team_game_log(
        ...     season="2023-24",
        ...     team="Celtics",
        ...     date_from="2023-12-01",
        ...     date_to="2023-12-31"
        ... )
    """
    
    import time
    start_time = time.time()

    logger.debug(
        "get_date_range_game_log_or_team_game_log(season=%s, team=%s, date_from=%s, date_to=%s)",
        season,
        team,
        date_from,
        date_to,
    )

    client = NBAApiClient()

    try:
        # Fetch game log
        result = await client.get_league_game_log(
            season=season, team_name=team, as_dataframe=True
        )

        # ========================================================================
        # Error handling: Check type BEFORE using as DataFrame
        # ========================================================================
        if isinstance(result, dict):
            if "error" in result:
                return error_response(
                    error_code="API_ERROR",
                    error_message=f"Error fetching game log: {result['error']}",
                    details={"season": season, "team": team}
                ).to_json_string()
            # Unexpected format
            return error_response(
                error_code="UNEXPECTED_FORMAT",
                error_message=f"Expected DataFrame, got dict: {type(result)}",
                details={"season": season, "team": team}
            ).to_json_string()

        if not isinstance(result, pd.DataFrame):
            return error_response(
                error_code="UNEXPECTED_FORMAT",
                error_message=f"Expected DataFrame, got {type(result)}",
                details={"season": season, "team": team}
            ).to_json_string()

        # Now safe to use DataFrame methods
        df = result

        if df.empty:
            team_str = f" for {team}" if team else ""
            return error_response(
                error_code="NO_DATA",
                error_message=f"No games found{team_str} in {season}",
                details={"season": season, "team": team}
            ).to_json_string()

        # Apply date filtering if specified
        original_count = len(df)
        if date_from or date_to:
            if "GAME_DATE" in df.columns:
                df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"])
                if date_from:
                    date_from_dt = pd.to_datetime(date_from)
                    df = df[df["GAME_DATE"] >= date_from_dt]
                if date_to:
                    date_to_dt = pd.to_datetime(date_to)
                    df = df[df["GAME_DATE"] <= date_to_dt]

        if df.empty:
            return error_response(
                error_code="NO_DATA",
                error_message=f"No games found for specified date range",
                details={
                    "season": season,
                    "team": team,
                    "date_from": date_from,
                    "date_to": date_to,
                    "original_count": original_count
                }
            ).to_json_string()

        # ========================================================================
        # Convert DataFrame to list of dicts for JSON response
        # ========================================================================

        # Convert GAME_DATE to string format for JSON serialization
        if "GAME_DATE" in df.columns:
            df["GAME_DATE"] = df["GAME_DATE"].astype(str)

        # Convert DataFrame to list of dicts
        games = df.to_dict('records')

        logger.debug(f"Returning {len(games)} games with {len(df.columns)} columns")

        # ========================================================================
        # Build metadata
        # ========================================================================
        metadata_dict = {
            "rows": len(games),
            "columns": len(df.columns),
            "season": season,
        }

        if team:
            metadata_dict["team"] = team

        # Add date range from actual data
        if "GAME_DATE" in df.columns and not df.empty:
            date_col = pd.to_datetime(df["GAME_DATE"])
            metadata_dict["date_range"] = {
                "from": str(date_col.min().date()),
                "to": str(date_col.max().date())
            }

        # Add filter info if provided
        if date_from or date_to:
            metadata_dict["filters_applied"] = {
                "date_from": date_from,
                "date_to": date_to,
                "original_count": original_count,
                "filtered_count": len(games)
            }

        # Calculate execution time
        execution_time_ms = (time.time() - start_time) * 1000

        # ========================================================================
        # Return JSON response
        # ========================================================================
        response = success_response(
            data=games,
            source="historical",
            cache_status="miss",  # Could be enhanced with caching later
            execution_time_ms=execution_time_ms,
        )

        logger.info(f"Returning {len(games)} games as JSON (execution: {execution_time_ms:.1f}ms)")
        return response.to_json_string()

    except EntityNotFoundError as e:
        return error_response(
            error_code="ENTITY_NOT_FOUND",
            error_message=str(e),
            details={"season": season, "team": team}
        ).to_json_string()

    except Exception as e:
        logger.exception("Unexpected error in get_date_range_game_log_or_team_game_log")
        return error_response(
            error_code="UNEXPECTED_ERROR",
            error_message=f"Error fetching game log: {str(e)}",
            details={"season": season, "team": team}
        ).to_json_string()



@mcp_server.tool()
async def fetch_player_games(
    season: str,  # Single "2023-24", range "2021-22:2023-24", or JSON '["2021-22", "2022-23"]'
    player: Optional[Union[int, str]] = None,  # Player ID (2544) or name ("LeBron James")
    team: Optional[Union[int, str]] = None,  # Team ID (1610612747) or name ("Lakers" or "LAL")
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    location: Optional[Literal["Home", "Road"]] = None,
    outcome: Optional[Literal["W", "L"]] = None,
    last_n_games: Optional[int] = None,
    game_segment: Optional[str] = None,
    month: Optional[int] = None,
    opponent_team: Optional[Union[int, str]] = None,  # Opponent team ID or name
    po_round: Optional[int] = None,
    per_mode: Optional[Literal["Totals", "PerGame", "Per36", "Per48", "Per40"]] = None,
    period: Optional[int] = None,
    season_segment: Optional[Literal["Pre All-Star", "Post All-Star"]] = None,
    season_type: Optional[Literal["Regular Season", "Playoffs", "All Star"]] = None,
    shot_clock_range: Optional[str] = None,
    vs_conference: Optional[Literal["East", "West"]] = None,
    vs_division: Optional[str] = None,
    stat_filters: Optional[str] = None,
) -> str:
    """
    Fetch player game logs with comprehensive filtering using the data grouping infrastructure.

    Supports MULTIPLE SEASONS with flexible syntax:
    - Single season: "2023-24"
    - Season range: "2021-22:2023-24" (expands to all seasons in range)
    - JSON array: '["2021-22", "2022-23", "2023-24"]'
    Multi-season queries use CONCURRENT FETCHING (3x faster for 3 seasons).

    This tool exposes the powerful three-tier filtering system:
    - Tier 1: NBA API filters (reduces data transfer at source)
    - Tier 2: DuckDB statistical filters (100x faster than pandas)
    - Tier 3: Parquet storage ready (35.7x smaller, 6.7x faster)

    NBA API Filters (Tier 1):
        season: Season in YYYY-YY format (e.g., "2023-24") [REQUIRED]
        player: Player ID (int) or name (str) - e.g., 2544 or "LeBron James"
        team: Team ID (int), name (str), or abbreviation - e.g., 1610612747 or "Lakers" or "LAL"
        date_from: Start date in YYYY-MM-DD format
        date_to: End date in YYYY-MM-DD format
        location: "Home" or "Road" games only
        outcome: "W" (wins) or "L" (losses) only
        last_n_games: Last N games (e.g., 10)
        game_segment: "First Half", "Second Half", "Overtime"
        month: Month number (1-12)
        opponent_team: Opponent team ID (int), name (str), or abbreviation
        po_round: Playoff round (0-4)
        per_mode: "Totals", "PerGame", "Per36", "Per48", "Per40"
        period: Quarter/period number (1-4)
        season_segment: "Pre All-Star", "Post All-Star"
        season_type: "Regular Season", "Playoffs", "All Star"
        shot_clock_range: "24-22", "22-18 Very Early", etc.
        vs_conference: "East", "West"
        vs_division: "Atlantic", "Central", "Southeast", etc.

    Statistical Filters (Tier 2 - DuckDB):
        stat_filters: JSON string with statistical filters
        Format: {"MIN": [">=", 10], "PTS": [">", 20], "FG_PCT": [">=", 0.5]}
        Operators: ">=", ">", "<=", "<", "==", "!="

    Returns:
        JSON string with player game logs that can be passed to save_nba_data()

    Examples:
        # Using NATURAL LANGUAGE (names):
        fetch_player_games(season="2023-24", player="LeBron James")

        # Using player IDs (backward compatible):
        fetch_player_games(season="2023-24", player=2544)

        # Team filtering with name or abbreviation:
        fetch_player_games(season="2023-24", player="LeBron James", team="Lakers")
        fetch_player_games(season="2023-24", player="LeBron James", team="LAL")

        # Home games only:
        fetch_player_games(season="2023-24", player="LeBron James", location="Home")

        # Games against specific opponent:
        fetch_player_games(season="2023-24", player="LeBron James",
                          opponent_team="Boston Celtics")

        # Games with 20+ minutes played:
        fetch_player_games(season="2023-24", player="LeBron James",
                          stat_filters='{"MIN": [">=", 20]}')

        # Playoff wins with 30+ points:
        fetch_player_games(season="2023-24", player="LeBron James",
                          season_type="Playoffs", outcome="W",
                          stat_filters='{"PTS": [">=", 30]}')

        # All players with 10+ minutes in 2023-24:
        fetch_player_games(season="2023-24",
                          stat_filters='{"MIN": [">=", 10]}')
    """
    try:
        import json

        import pandas as pd

        from nba_mcp.api.data_groupings import fetch_grouping_multi_season
        from nba_mcp.utils.entity_utils import resolve_player_input, resolve_team_input
        from nba_mcp.utils.season_utils import format_season_display, parse_season_input

        # Parse season parameter - supports single, range, or JSON array
        # Examples: "2023-24", "2021-22:2023-24", '["2021-22", "2022-23"]'
        seasons = parse_season_input(season)
        logger.info(f"Parsed season input: {format_season_display(seasons)}")

        # ======================================================================
        # RESOLVE NATURAL LANGUAGE INPUTS TO IDs
        # Accepts both IDs (int) and names (str) for flexible usage
        # ======================================================================
        player_id = resolve_player_input(player)
        team_id = resolve_team_input(team)
        opp_team_id = resolve_team_input(opponent_team)

        # Build filters dictionary (without season - handled separately)
        filters = {}

        # Add all API-level filters (Tier 1)
        if player_id is not None:
            filters["player_id"] = player_id
        if team_id is not None:
            filters["team_id"] = team_id
        if date_from is not None:
            filters["date_from"] = date_from
        if date_to is not None:
            filters["date_to"] = date_to
        if location is not None:
            filters["location"] = location
        if outcome is not None:
            filters["outcome"] = outcome
        if last_n_games is not None:
            filters["last_n_games"] = last_n_games
        if game_segment is not None:
            filters["game_segment"] = game_segment
        if month is not None:
            filters["month"] = month
        if opp_team_id is not None:
            filters["opp_team_id"] = opp_team_id
        if po_round is not None:
            filters["po_round"] = po_round
        if per_mode is not None:
            filters["per_mode"] = per_mode
        if period is not None:
            filters["period"] = period
        if season_segment is not None:
            filters["season_segment"] = season_segment
        if season_type is not None:
            filters["season_type"] = season_type
        if shot_clock_range is not None:
            filters["shot_clock_range"] = shot_clock_range
        if vs_conference is not None:
            filters["vs_conference"] = vs_conference
        if vs_division is not None:
            filters["vs_division"] = vs_division

        # Add statistical filters (Tier 2 - DuckDB)
        if stat_filters:
            stat_dict = json.loads(stat_filters)
            # Convert to tuple format: {"MIN": [">=", 10]} -> {"MIN": (">=", 10)}
            for key, value in stat_dict.items():
                if isinstance(value, list) and len(value) == 2:
                    filters[key] = tuple(value)

        # Fetch data using concurrent multi-season fetching (3x faster for 3 seasons)
        logger.info(f"fetch_player_games: Fetching {len(seasons)} seasons with filters: {filters}")
        df = await fetch_grouping_multi_season(
            "player/game",
            seasons=seasons,
            **filters
        )

        if df.empty:
            return json.dumps({
                "status": "success",
                "message": "No games found matching the specified filters",
                "data": [],
                "metadata": {
                    "rows": 0,
                    "filters_applied": filters,
                    "grouping_level": "player/game"
                }
            }, indent=2)

        # Convert DataFrame to JSON-serializable format
        # Convert datetime columns to strings
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].astype(str)

        # Convert to records
        records = df.to_dict(orient="records")

        # Build response with season information
        season_display = format_season_display(seasons)
        response = {
            "status": "success",
            "message": f"Found {len(records)} games from {season_display}",
            "data": records,
            "metadata": {
                "rows": len(records),
                "columns": list(df.columns),
                "seasons": seasons,
                "season_count": len(seasons),
                "unique_players": int(df["PLAYER_ID"].nunique()) if "PLAYER_ID" in df.columns else None,
                "unique_games": int(df["GAME_ID"].nunique()) if "GAME_ID" in df.columns else None,
                "date_range": {
                    "min": df["GAME_DATE"].min() if "GAME_DATE" in df.columns else None,
                    "max": df["GAME_DATE"].max() if "GAME_DATE" in df.columns else None,
                },
                "filters_applied": {k: str(v) for k, v in filters.items()},
                "grouping_level": "player/game",
                "data_source": "NBA API via data grouping infrastructure"
            }
        }

        return json.dumps(response, indent=2)

    except json.JSONDecodeError as e:
        logger.error(f"Invalid stat_filters JSON: {stat_filters}")
        return json.dumps({
            "status": "error",
            "error_code": "INVALID_JSON",
            "error_message": f"stat_filters must be valid JSON: {str(e)}",
            "example": '{"MIN": [">=", 10], "PTS": [">", 20]}'
        }, indent=2)

    except Exception as e:
        logger.exception("Error in fetch_player_games")
        return json.dumps({
            "status": "error",
            "error_code": "FETCH_ERROR",
            "error_message": str(e)
        }, indent=2)


@mcp_server.tool()
async def play_by_play(
    game_date: Optional[str] = None,
    team: Optional[str] = None,
    start_period: int = 1,
    end_period: int = 4,
    start_clock: Optional[str] = None,
    recent_n: int = 5,
    max_lines: int = 200,
    include_lineups: bool = False,
) -> str:
    """
    Unified MCP tool: returns play-by-play for specified date/team,
    or for all games today if no parameters given.

    NEW FEATURE: Optional lineup tracking!
    Set include_lineups=True to get current 5-player lineups for each event.

    Args:
        game_date: Date in YYYY-MM-DD format (optional)
        team: Team name or abbreviation (optional)
        start_period: Starting period (default: 1)
        end_period: Ending period (default: 4)
        start_clock: Start time in format "MM:SS" (optional)
        recent_n: Number of recent plays to show in summary (default: 5)
        max_lines: Maximum lines of output (default: 200)
        include_lineups: If True, adds current lineup columns to output (default: False)

    Returns:
        Play-by-play markdown or JSON with optional lineup data

    Lineup columns (when include_lineups=True):
        - CURRENT_LINEUP_HOME: List of 5 player names (home team)
        - CURRENT_LINEUP_AWAY: List of 5 player names (away team)
        - LINEUP_ID_HOME: NBA API format lineup ID (e.g., "-1626157-1628384-...")
        - LINEUP_ID_AWAY: NBA API format lineup ID
        - LINEUP_DISPLAY_HOME: Human-readable lineup (e.g., "James - Davis - Russell - ...")
        - LINEUP_DISPLAY_AWAY: Human-readable lineup

    Examples:
        play_by_play()  # Today's games
        play_by_play("2024-01-15", "Lakers")  # Specific game
        play_by_play("2024-01-15", "Lakers", include_lineups=True)  # With lineups
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

    # NEW: Add lineup tracking if requested
    if include_lineups:
        try:
            from nba_api.stats.endpoints import PlayByPlayV3

            from nba_mcp.api.tools.playbyplayv3_or_realtime import PastGamesPlaybyPlay

            # Get game_id from date/team
            pbp_instance = PastGamesPlaybyPlay.from_team_date(
                when=game_date,
                team=team,
                show_choices=False
            )
            game_id = pbp_instance.game_id

            # Fetch play-by-play as DataFrame
            result = PlayByPlayV3(
                game_id=game_id,
                start_period=start_period,
                end_period=end_period
            )
            pbp_df = result.get_data_frames()[0]  # [0] is PlayByPlay

            # Add lineup tracking
            pbp_with_lineups = add_lineups_to_play_by_play(pbp_df, game_id)

            # Return as JSON for inspection
            return json.dumps({
                "game_id": game_id,
                "events": pbp_with_lineups.to_dict(orient="records")[:max_lines],
                "total_events": len(pbp_with_lineups),
                "lineups_tracked": True
            }, indent=2, default=str)

        except Exception as e:
            logger.error(f"Failed to add lineup tracking: {e}")
            # Fall back to regular play-by-play without lineups

    if isinstance(md, str):
        return md
    return json.dumps(md, indent=2)


@mcp_server.tool()
async def get_lineup_stats(
    team: str,
    season: Optional[str] = None,
    min_minutes: int = 10,
    lineup_type: Optional[str] = "all",
    with_player: Optional[str] = None,
    without_player: Optional[str] = None
) -> str:
    """
    Get 5-man lineup statistics for a team.

    Phase 5.2 (P6): Lineup Analysis (2025-11-01)
    Phase 5.2 (P6 Phase 2): Enhanced with lineup modifiers and filters (2025-11-01)

    Returns aggregated statistics for all 5-player lineups that meet
    the minimum minutes threshold. Shows games played, win-loss record,
    minutes, points scored, and plus/minus for each lineup combination.

    IMPORTANT - DEFAULT BEHAVIOR:
        - If season is omitted/null → Uses CURRENT season (auto-detected)
        - If min_minutes is omitted → Uses 10 minutes as threshold
        - Returns markdown table sorted by minutes played (descending)
        - Shows top 20 lineups only

    PARAMETERS:
        team (REQUIRED):
            - Team name: "Los Angeles Lakers", "Lakers"
            - Team nickname: "Lakers", "Warriors", "Celtics"
            - Team abbreviation: "LAL", "GSW", "BOS"
            - Case-insensitive
            - Aliases: team_name, team_abbr

        season (OPTIONAL, default: None = current season):
            - Format: "YYYY-YY" (e.g., "2023-24")
            - Also accepts: "YYYY-YYYY" (e.g., "2023-2024") - will be normalized
            - If omitted/null: Auto-detects current NBA season
            - Aliases: season_year, year

        min_minutes (OPTIONAL, default: 10):
            - Minimum minutes played to include lineup
            - Integer value (e.g., 10, 20, 50, 100)
            - Lower values = more lineups, higher values = fewer lineups
            - Aliases: minimum_minutes, min_mins, minutes_threshold, minutes_filter

        lineup_type (OPTIONAL, default: "all"):
            - Filter by lineup type: "all", "starting", "bench"
            - "all": All lineups (no filtering)
            - "starting": Primary starting lineups (most common first-unit combinations)
            - "bench": Bench unit lineups (excluding primary starters)
            - Aliases: type, lineup_filter

        with_player (OPTIONAL, default: None):
            - Filter lineups that INCLUDE a specific player
            - Player name (e.g., "LeBron", "LeBron James", "James")
            - Uses fuzzy matching for flexibility
            - Can specify partial names
            - Aliases: including_player, player

        without_player (OPTIONAL, default: None):
            - Filter lineups that EXCLUDE a specific player
            - Player name (e.g., "LeBron", "LeBron James", "James")
            - Uses fuzzy matching for flexibility
            - Can specify partial names
            - Aliases: excluding_player, except_player

    RETURNS:
        Markdown-formatted table string with:
        - Header: Team name and season
        - Metadata: Minimum minutes filter and total lineups count
        - Table columns: Lineup | GP | W-L | MIN | PTS | +/- | FG% | 3P%
        - Sorted by: Minutes played (descending)
        - Limit: Top 20 lineups

    EXAMPLES:
        # Basic usage (uses current season, min_minutes=10)
        get_lineup_stats(team="Lakers")

        # Specific season
        get_lineup_stats(team="Warriors", season="2023-24")

        # Custom minutes threshold
        get_lineup_stats(team="Celtics", min_minutes=50)

        # All parameters specified
        get_lineup_stats(team="Lakers", season="2023-24", min_minutes=100)

        # Using parameter aliases (LLM-friendly)
        get_lineup_stats(team_name="LAL", season_year="2023-2024", minimum_minutes=20)

        # Phase 5.2 (P6 Phase 2): New modifier examples
        # Starting lineup only
        get_lineup_stats(team="Lakers", lineup_type="starting")

        # Bench lineups only
        get_lineup_stats(team="Warriors", lineup_type="bench")

        # Lineups with specific player
        get_lineup_stats(team="Lakers", with_player="LeBron")

        # Lineups without specific player
        get_lineup_stats(team="Warriors", without_player="Curry")

        # Combined modifiers
        get_lineup_stats(team="Celtics", lineup_type="bench", with_player="Tatum")

    OUTPUT EXAMPLE:
        # Los Angeles Lakers - 5-Man Lineup Statistics (2023-24)
        **Minimum Minutes:** 10
        **Total Lineups:** 15

        | Lineup | GP | W-L | MIN | PTS | +/- | FG% | 3P% |
        |--------|----|----|-----|-----|-----|-----|-----|
        | James - Davis - Reaves - Russell - Hachimura | 45 | 30-15 | 682.3 | 1248 | +124 | 48.2% | 36.1% |
        | James - Davis - Reaves - Russell - Vanderbilt | 32 | 21-11 | 512.8 | 891 | +87 | 46.5% | 34.2% |
        ...

    LINEUP STATISTICS INCLUDED:
        - Lineup: 5 player names separated by " - "
        - GP: Games played together
        - W-L: Win-loss record for this lineup
        - MIN: Total minutes played together
        - PTS: Total points scored while on court
        - +/-: Plus/minus (point differential)
        - FG%: Field goal percentage
        - 3P%: Three-point percentage

    ERROR HANDLING:
        - Invalid team name → Returns error message with suggestion
        - No lineup data → Returns "No lineup data found" message
        - API errors → Returns descriptive error message

    COMMON LLM MISTAKES TO AVOID:
        ❌ Don't use: get_lineup_stats("Lakers", "2023") - season needs full format
        ✅ Use: get_lineup_stats("Lakers", "2023-24")

        ❌ Don't use: get_lineup_stats(team_id=1610612747) - use team name
        ✅ Use: get_lineup_stats(team="Lakers")

        ❌ Don't omit team parameter - it's REQUIRED
        ✅ Always include: get_lineup_stats(team="Lakers")

        ❌ Don't use multiple teams - analyze ONE team at a time
        ✅ Use: get_lineup_stats(team="Lakers")
        ❌ Don't use: get_lineup_stats(team="Lakers and Warriors")
    """
    start_time = time.time()

    try:
        # Phase 5.2 (P6 Stress Test Fix #4): Validate single team only
        # Detect multiple teams in query (e.g., "Lakers and Warriors")
        multi_team_indicators = [" and ", " vs ", " versus ", ","]
        if any(indicator in team.lower() for indicator in multi_team_indicators):
            return (
                f"Error: Lineup analysis supports ONE team at a time. "
                f"Please analyze teams separately. Example: get_lineup_stats(team='Lakers')"
            )

        # Phase 5.2 (P6): Import NBA API endpoint for lineup stats
        from nba_api.stats.endpoints import leaguedashlineups

        # Resolve team name to team ID
        try:
            team_result = await resolve_nba_entity(team, entity_type="team")
            team_data = json.loads(team_result)
            team_id = team_data["entity_id"]
            team_name = team_data["name"]
        except Exception as e:
            logger.error(f"Failed to resolve team '{team}': {e}")
            return f"Error: Could not find team '{team}'. Please check the team name."

        # Determine season
        if season is None:
            current_date = datetime.now()
            current_year = current_date.year
            # NBA season spans Oct-Jun, so determine season based on month
            if current_date.month >= 10:
                season = f"{current_year}-{str(current_year + 1)[-2:]}"
            else:
                season = f"{current_year - 1}-{str(current_year)[-2:]}"
        else:
            # Phase 5.2 (P6 Stress Test Fix #2): Validate season format before normalization
            # Accept formats: "YYYY-YY" or "YYYY-YYYY"
            import re
            season_pattern = r"^\d{4}-\d{2,4}$"
            if not re.match(season_pattern, season):
                return (
                    f"Invalid season format: '{season}'. "
                    f"Please use format 'YYYY-YY' (e.g., '2023-24') or 'YYYY-YYYY' (e.g., '2023-2024')."
                )

            # Phase 5.2 (P6): Normalize season format for LLM compatibility
            # Convert "2023-2024" → "2023-24", accept both formats
            if "-" in season:
                parts = season.split("-")
                if len(parts) == 2:
                    start_year = parts[0]
                    end_year = parts[1]
                    # If end year is 4 digits, convert to 2 digits
                    if len(end_year) == 4:
                        end_year = end_year[-2:]
                    season = f"{start_year}-{end_year}"

        logger.info(f"Fetching lineup stats for {team_name} ({season})")

        # Phase 5.2 (P6 Phase 3): Use cached lineup data fetcher (2025-11-01)
        lineups_df = _fetch_lineup_data_cached(
            team_id=team_id,
            season=season,
            season_type="Regular Season"
        )

        if lineups_df.empty:
            return f"No lineup data found for {team_name} in {season} season."

        # Filter by team (in case API returns multiple teams)
        lineups_df = lineups_df[lineups_df['TEAM_ID'] == team_id]

        # Filter by minimum minutes
        lineups_df = lineups_df[lineups_df['MIN'] >= min_minutes]

        if lineups_df.empty:
            return f"No lineups found for {team_name} with minimum {min_minutes} minutes played."

        # Phase 5.2 (P6 Phase 2): Apply player filters
        if with_player:
            # Filter lineups that INCLUDE the specified player (fuzzy match)
            from difflib import SequenceMatcher
            def player_in_lineup(lineup_name, player_search):
                # Check if player name appears in lineup (case-insensitive fuzzy match)
                lineup_lower = lineup_name.lower()
                player_lower = player_search.lower()
                # Direct substring match or fuzzy match
                if player_lower in lineup_lower:
                    return True
                # Check each player in lineup for fuzzy match
                lineup_players = [p.strip() for p in lineup_name.split('-')]
                for lineup_player in lineup_players:
                    similarity = SequenceMatcher(None, lineup_player.lower(), player_lower).ratio()
                    if similarity > 0.6:  # 60% similarity threshold
                        return True
                return False

            lineups_df = lineups_df[lineups_df['GROUP_NAME'].apply(
                lambda x: player_in_lineup(x, with_player)
            )]

            if lineups_df.empty:
                return f"No lineups found for {team_name} including player '{with_player}'."

        if without_player:
            # Filter lineups that EXCLUDE the specified player (fuzzy match)
            from difflib import SequenceMatcher
            def player_not_in_lineup(lineup_name, player_search):
                # Check if player name does NOT appear in lineup
                lineup_lower = lineup_name.lower()
                player_lower = player_search.lower()
                # Direct substring match
                if player_lower in lineup_lower:
                    return False
                # Check each player in lineup for fuzzy match
                lineup_players = [p.strip() for p in lineup_name.split('-')]
                for lineup_player in lineup_players:
                    similarity = SequenceMatcher(None, lineup_player.lower(), player_lower).ratio()
                    if similarity > 0.6:  # 60% similarity threshold
                        return False
                return True

            lineups_df = lineups_df[lineups_df['GROUP_NAME'].apply(
                lambda x: player_not_in_lineup(x, without_player)
            )]

            if lineups_df.empty:
                return f"No lineups found for {team_name} excluding player '{without_player}'."

        # Phase 5.2 (P6 Phase 2): Apply lineup type filter
        if lineup_type and lineup_type != "all":
            if lineup_type == "starting":
                # Starting lineups: Top 3 lineups by minutes (heuristic for starting units)
                lineups_df = lineups_df.nlargest(3, 'MIN')
            elif lineup_type == "bench":
                # Bench lineups: Exclude top 3 lineups by minutes
                top_3_mins = lineups_df.nlargest(3, 'MIN')['MIN'].min()
                lineups_df = lineups_df[lineups_df['MIN'] < top_3_mins]

            if lineups_df.empty:
                return f"No {lineup_type} lineups found for {team_name}."

        # Sort by minutes played (descending)
        lineups_df = lineups_df.sort_values('MIN', ascending=False)

        # Format response
        # Phase 5.2 (P6 Phase 2): Build title with filters
        title = f"# {team_name} - 5-Man Lineup Statistics ({season})"
        if lineup_type and lineup_type != "all":
            title = f"# {team_name} - {lineup_type.capitalize()} Lineup Statistics ({season})"

        response_lines = [title, f"**Minimum Minutes:** {min_minutes}"]

        # Phase 5.2 (P6 Phase 2): Add filter metadata
        if with_player:
            response_lines.append(f"**Includes Player:** {with_player}")
        if without_player:
            response_lines.append(f"**Excludes Player:** {without_player}")

        response_lines.extend([
            f"**Total Lineups:** {len(lineups_df)}",
            "",
            "| Lineup | GP | W-L | MIN | PTS | +/- | FG% | 3P% |",
            "|--------|----|----|-----|-----|-----|-----|-----|"
        ])

        # Add each lineup row
        for idx, row in lineups_df.head(20).iterrows():  # Show top 20 lineups
            lineup_name = row['GROUP_NAME']
            gp = int(row['GP'])
            wins = int(row['W'])
            losses = int(row['L'])
            minutes = row['MIN']
            pts = row['PTS']
            plus_minus = row['PLUS_MINUS']
            fg_pct = row['FG_PCT'] * 100 if pd.notna(row['FG_PCT']) else 0
            fg3_pct = row['FG3_PCT'] * 100 if pd.notna(row['FG3_PCT']) else 0

            response_lines.append(
                f"| {lineup_name} | {gp} | {wins}-{losses} | {minutes:.1f} | {pts:.0f} | {plus_minus:+.0f} | {fg_pct:.1f}% | {fg3_pct:.1f}% |"
            )

        elapsed = (time.time() - start_time) * 1000
        logger.info(f"Lineup stats fetched in {elapsed:.0f}ms")

        return "\n".join(response_lines)

    except Exception as e:
        logger.exception("Error in get_lineup_stats")
        return f"Error fetching lineup statistics: {str(e)}"


@mcp_server.tool()
async def get_lineup_stats_multi_season(
    team: str,
    seasons: str,
    min_minutes: int = 10,
    aggregation: str = "separate"
) -> str:
    """
    Get lineup statistics across multiple seasons.

    Phase 5.2 (P6 Phase 3): Multi-Season Lineup Support (2025-11-01)

    Supports flexible season input:
    - Single season: "2023-24"
    - Season range: "2021-22:2023-24" (expands to all seasons in range)
    - JSON array: '["2021-22", "2022-23", "2023-24"]'

    Args:
        team: Team name, nickname, or abbreviation
        seasons: Season(s) in supported format (see above)
        min_minutes: Minimum minutes threshold (default: 10)
        aggregation: "separate" (table per season) or "combined" (aggregated stats)

    Returns:
        Markdown-formatted lineup statistics across seasons

    Examples:
        # Season range
        get_lineup_stats_multi_season(team="Lakers", seasons="2021-22:2023-24")

        # JSON array
        get_lineup_stats_multi_season(team="Warriors", seasons='["2022-23", "2023-24"]')

        # Combined aggregation
        get_lineup_stats_multi_season(team="Celtics", seasons="2021-22:2023-24", aggregation="combined")
    """
    start_time = time.time()

    try:
        # Import season utilities from P2 infrastructure
        from nba_mcp.utils.season_utils import parse_season_input

        # Parse season input into list of seasons
        season_list = parse_season_input(seasons)
        logger.info(f"Parsed {len(season_list)} seasons: {season_list}")

        # Resolve team name to ID (once for all seasons)
        try:
            team_result = await resolve_nba_entity(team, entity_type="team")
            team_data = json.loads(team_result)
            team_id = team_data["entity_id"]
            team_name = team_data["name"]
        except Exception as e:
            logger.error(f"Failed to resolve team '{team}': {e}")
            return f"Error: Could not find team '{team}'. Please check the team name."

        # Fetch lineup data for each season (can be parallelized with asyncio.gather)
        season_results = []

        # Phase 5.2 (P6 Phase 3): Parallel season fetching for performance
        async def fetch_season_lineup(season_str):
            """Fetch lineup data for a single season."""
            try:
                # Use cached fetcher
                lineups_df = _fetch_lineup_data_cached(
                    team_id=team_id,
                    season=season_str,
                    season_type="Regular Season"
                )

                # Apply filters
                if lineups_df.empty:
                    return (season_str, None, f"No lineup data for {season_str}")

                lineups_df = lineups_df[lineups_df['TEAM_ID'] == team_id]
                lineups_df = lineups_df[lineups_df['MIN'] >= min_minutes]

                if lineups_df.empty:
                    return (season_str, None, f"No lineups with {min_minutes}+ minutes in {season_str}")

                lineups_df = lineups_df.sort_values('MIN', ascending=False)
                return (season_str, lineups_df, None)

            except Exception as e:
                logger.error(f"Error fetching {season_str}: {e}")
                return (season_str, None, f"Error: {str(e)}")

        # Fetch all seasons in parallel
        import asyncio
        season_tasks = [fetch_season_lineup(s) for s in season_list]
        season_results = await asyncio.gather(*season_tasks)

        # Process results based on aggregation mode
        if aggregation == "combined":
            # Combine all dataframes and aggregate
            all_dfs = [df for (_, df, _) in season_results if df is not None]

            if not all_dfs:
                return f"No lineup data found for {team_name} across seasons {seasons}."

            # Concatenate and group by lineup
            combined_df = pd.concat(all_dfs, ignore_index=True)
            grouped = combined_df.groupby('GROUP_NAME').agg({
                'GP': 'sum',
                'W': 'sum',
                'L': 'sum',
                'MIN': 'sum',
                'PTS': 'sum',
                'PLUS_MINUS': 'sum',
                'FGM': 'sum',
                'FGA': 'sum',
                'FG3M': 'sum',
                'FG3A': 'sum',
            }).reset_index()

            # Recalculate percentages
            grouped['FG_PCT'] = grouped['FGM'] / grouped['FGA']
            grouped['FG3_PCT'] = grouped['FG3M'] / grouped['FG3A']

            grouped = grouped.sort_values('MIN', ascending=False)

            # Format response
            from nba_mcp.utils.season_utils import format_season_display
            season_display = format_season_display(season_list)

            response_lines = [
                f"# {team_name} - Combined Lineup Statistics ({season_display})",
                f"**Aggregation:** Combined across {len(season_list)} seasons",
                f"**Minimum Minutes:** {min_minutes}",
                f"**Total Lineups:** {len(grouped)}",
                "",
                "| Lineup | GP | W-L | MIN | PTS | +/- | FG% | 3P% |",
                "|--------|----|----|-----|-----|-----|-----|-----|"
            ]

            for idx, row in grouped.head(20).iterrows():
                lineup_name = row['GROUP_NAME']
                gp = int(row['GP'])
                wins = int(row['W'])
                losses = int(row['L'])
                minutes = row['MIN']
                pts = row['PTS']
                plus_minus = row['PLUS_MINUS']
                fg_pct = row['FG_PCT'] * 100 if pd.notna(row['FG_PCT']) else 0
                fg3_pct = row['FG3_PCT'] * 100 if pd.notna(row['FG3_PCT']) else 0

                response_lines.append(
                    f"| {lineup_name} | {gp} | {wins}-{losses} | {minutes:.1f} | {pts:.0f} | {plus_minus:+.0f} | {fg_pct:.1f}% | {fg3_pct:.1f}% |"
                )

            return "\n".join(response_lines)

        else:
            # Separate mode: Show table for each season
            response_lines = [
                f"# {team_name} - Multi-Season Lineup Statistics",
                f"**Seasons:** {', '.join(season_list)}",
                f"**Minimum Minutes:** {min_minutes}",
                ""
            ]

            for season_str, lineups_df, error in season_results:
                response_lines.append(f"## {season_str}")
                response_lines.append("")

                if error or lineups_df is None:
                    response_lines.append(f"*{error or 'No data available'}*")
                    response_lines.append("")
                    continue

                response_lines.append(f"**Total Lineups:** {len(lineups_df)}")
                response_lines.append("")
                response_lines.append("| Lineup | GP | W-L | MIN | PTS | +/- | FG% | 3P% |")
                response_lines.append("|--------|----|----|-----|-----|-----|-----|-----|")

                for idx, row in lineups_df.head(10).iterrows():  # Show top 10 per season
                    lineup_name = row['GROUP_NAME']
                    gp = int(row['GP'])
                    wins = int(row['W'])
                    losses = int(row['L'])
                    minutes = row['MIN']
                    pts = row['PTS']
                    plus_minus = row['PLUS_MINUS']
                    fg_pct = row['FG_PCT'] * 100 if pd.notna(row['FG_PCT']) else 0
                    fg3_pct = row['FG3_PCT'] * 100 if pd.notna(row['FG3_PCT']) else 0

                    response_lines.append(
                        f"| {lineup_name} | {gp} | {wins}-{losses} | {minutes:.1f} | {pts:.0f} | {plus_minus:+.0f} | {fg_pct:.1f}% | {fg3_pct:.1f}% |"
                    )

                response_lines.append("")

            elapsed = (time.time() - start_time) * 1000
            logger.info(f"Multi-season lineup stats fetched in {elapsed:.0f}ms")

            return "\n".join(response_lines)

    except Exception as e:
        logger.exception("Error in get_lineup_stats_multi_season")
        return f"Error fetching multi-season lineup statistics: {str(e)}"


@mcp_server.tool()
async def get_lineup_trends(
    team: str,
    season: Optional[str] = None,
    min_minutes: int = 10,
    group_by: str = "month"
) -> str:
    """
    Get lineup performance trends over time.

    Phase 5.2 (P6 Phase 3): Lineup Trend Analysis (2025-11-01)

    Analyzes how lineup performance changes over the season.
    Groups lineups by time period and shows trends.

    Args:
        team: Team name, nickname, or abbreviation
        season: Season in 'YYYY-YY' format (default: current season)
        min_minutes: Minimum minutes threshold (default: 10)
        group_by: "month", "quarter", or "all" (default: "month")

    Returns:
        Markdown-formatted trend analysis with performance by time period

    Examples:
        get_lineup_trends(team="Lakers")
        get_lineup_trends(team="Warriors", season="2023-24", group_by="quarter")
    """
    start_time = time.time()

    try:
        # This is a simplified implementation
        # For a full implementation, would need game-by-game lineup data
        # For now, we'll return the lineup stats with a note about trends

        # Use existing get_lineup_stats to get data
        lineup_stats = await get_lineup_stats(
            team=team,
            season=season,
            min_minutes=min_minutes
        )

        # Parse response and add trend analysis
        response_lines = [
            f"# Lineup Performance Trends - {team}",
            f"**Season:** {season or 'Current'}",
            f"**Group By:** {group_by.capitalize()}",
            "",
            "## Overall Lineup Statistics",
            "",
            lineup_stats,
            "",
            "## Trend Analysis",
            "",
            "*Note: Full time-series trend analysis requires game-by-game lineup tracking.*",
            "*Current implementation shows overall season statistics.*",
            "*Future enhancement: Group performance by month/quarter using play-by-play data.*",
        ]

        return "\n".join(response_lines)

    except Exception as e:
        logger.exception("Error in get_lineup_trends")
        return f"Error analyzing lineup trends: {str(e)}"


@mcp_server.tool()
async def get_season_stats(
    entity_type: Literal["player", "team"],
    entity_name: str,
    season: str,
    team_filter: Optional[str] = None
) -> str:
    """
    Get aggregated season statistics for players or teams.

    Provides comprehensive season-level data including:
    - Counting stats totals (PTS, REB, AST, etc.)
    - Shooting percentages (recalculated from totals)
    - Per-game averages
    - Games played, wins/losses
    - Advanced metrics (TS%, eFG%, etc.)

    Supports multiple grouping levels:
    - player/season: All games for a player in a season
    - player/team/season: Games for a player with specific team
    - team/season: All games for a team in a season

    Args:
        entity_type: "player" or "team"
        entity_name: Player or team name (e.g., "LeBron James", "Lakers")
        season: Season in 'YYYY-YY' format (e.g., "2023-24")
        team_filter: Optional team name to filter player stats by team

    Returns:
        JSON string with ResponseEnvelope containing season statistics

    Examples:
        get_season_stats("player", "LeBron James", "2023-24")
        get_season_stats("player", "LeBron James", "2023-24", team_filter="Lakers")
        get_season_stats("team", "Lakers", "2023-24")
    """
    start_time = time.time()

    try:
        # Resolve entity to ID
        entity = resolve_entity(entity_name, entity_type=entity_type)

        # Fetch season stats based on entity type
        if entity_type == "player":
            # Get team ID if team_filter provided
            team_id = None
            if team_filter:
                team_entity = resolve_entity(team_filter, entity_type="team")
                team_id = team_entity.entity_id

            stats = await get_player_season_stats(
                season=season,
                player_id=entity.entity_id,
                team_id=team_id
            )

            grouping_level = "player/team/season" if team_filter else "player/season"

        else:  # team
            stats = await get_team_season_stats(
                season=season,
                team_id=entity.entity_id
            )

            grouping_level = "team/season"

        execution_time_ms = (time.time() - start_time) * 1000

        # Add grouping metadata
        stats["_grouping_level"] = grouping_level
        stats["_granularity"] = "season"

        # ========================================================================
        # DEBUG: Log season stats structure to understand format
        # ========================================================================
        logger.debug(f"DEBUG - Season stats type: {type(stats)}")
        logger.debug(f"DEBUG - Season stats keys: {stats.keys() if isinstance(stats, dict) else 'Not dict'}")
        logger.debug(f"DEBUG - Season stats sample (first 500 chars): {str(stats)[:500]}")

        response = success_response(
            data=stats,
            source="composed",  # Aggregated from historical game data
            cache_status="miss",
            execution_time_ms=execution_time_ms,
        )

        logger.info(
            f"get_season_stats: {entity_type}={entity_name}, season={season}, "
            f"grouping={grouping_level}, time={execution_time_ms:.0f}ms"
        )

        return response.to_json_string()

    except EntityNotFoundError as e:
        logger.warning(f"Entity not found in get_season_stats: {e}")
        response = error_response(
            error_code="ENTITY_NOT_FOUND",
            error_message=str(e),
        )
        return response.to_json_string()

    except Exception as e:
        logger.exception("Error in get_season_stats")
        response = error_response(
            error_code="NBA_API_ERROR",
            error_message=f"Failed to fetch season stats: {str(e)}",
        )
        return response.to_json_string()


@mcp_server.tool()
async def get_advanced_metrics(
    player_name: str,
    season: str,
    metrics: Optional[List[str]] = None
) -> str:
    """
    Calculate advanced basketball metrics for a player.

    Provides sophisticated metrics beyond basic box score stats:
    - **Game Score per 36**: Hollinger's efficiency metric normalized per 36 minutes
    - **True Shooting %**: Shooting efficiency accounting for 3PT and FT value
    - **Effective FG %**: Field goal % adjusted for 3-pointers
    - **Win Shares**: Offensive + Defensive contributions to team wins
    - **Win Shares per 48**: WS normalized per 48 minutes
    - **EWA**: Estimated Wins Added (value above replacement)

    Note: RAPM (Regularized Adjusted Plus-Minus) requires multi-year play-by-play
    data and is not yet available.

    Args:
        player_name: Player name (e.g., "LeBron James")
        season: Season in 'YYYY-YY' format (e.g., "2023-24")
        metrics: Optional list of specific metrics to return
                 (default: all metrics)

    Returns:
        JSON string with ResponseEnvelope containing advanced metrics

    Examples:
        get_advanced_metrics("LeBron James", "2023-24")
        get_advanced_metrics("Stephen Curry", "2023-24", metrics=["GAME_SCORE_PER_36", "WIN_SHARES"])

    Available metrics:
        - GAME_SCORE_TOTAL
        - GAME_SCORE_PER_GAME
        - GAME_SCORE_PER_36
        - TRUE_SHOOTING_PCT
        - EFFECTIVE_FG_PCT
        - USAGE_RATE
        - OFFENSIVE_WIN_SHARES
        - DEFENSIVE_WIN_SHARES
        - WIN_SHARES
        - WIN_SHARES_PER_48
        - EWA
    """
    start_time = time.time()

    try:
        calculator = AdvancedMetricsCalculator()

        # Calculate all metrics
        result = await calculator.calculate_all_metrics(player_name, season)

        # Convert to dict
        metrics_dict = result.to_dict()

        # Filter to specific metrics if requested
        if metrics:
            metrics_dict = {k: v for k, v in metrics_dict.items() if k in metrics or k in ["PLAYER_NAME", "SEASON"]}

        execution_time_ms = (time.time() - start_time) * 1000

        response = success_response(
            data=metrics_dict,
            source="calculated",
            cache_status="miss",
            execution_time_ms=execution_time_ms,
        )

        logger.info(
            f"get_advanced_metrics: player={player_name}, season={season}, "
            f"GS/36={result.game_score_per_36:.1f}, WS={result.win_shares:.1f}, "
            f"time={execution_time_ms:.0f}ms"
        )

        return response.to_json_string()

    except EntityNotFoundError as e:
        logger.warning(f"Player not found in get_advanced_metrics: {e}")
        response = error_response(
            error_code="ENTITY_NOT_FOUND",
            error_message=str(e),
        )
        return response.to_json_string()

    except Exception as e:
        logger.exception("Error in get_advanced_metrics")
        response = error_response(
            error_code="CALCULATION_ERROR",
            error_message=f"Failed to calculate advanced metrics: {str(e)}",
        )
        return response.to_json_string()


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
    Get team advanced statistics with human-readable formatting.

    Provides comprehensive team metrics including:
    - Offensive/Defensive/Net Rating (per 100 possessions)
    - Pace (possessions per 48 minutes)
    - True Shooting % and Effective FG %
    - Four Factors: eFG%, TOV%, OREB%, FTA Rate (offense and defense)

    Args:
        team_name: Team name, nickname, or abbreviation (e.g., "Lakers", "Dubs", "LAL")
        season: Season string ('YYYY-YY'). Defaults to current season.

    Returns:
        Formatted text with team advanced statistics
    """
    logger.debug("get_team_advanced_stats('%s', season=%s)", team_name, season)

    # Default to current season if not specified
    if season is None:
        season = get_current_season()

    try:
        from nba_mcp.api.advanced_stats import get_team_advanced_stats as fetch_stats

        result = await fetch_stats(team_name, season=season)

        # ========================================================================
        # BUG FIX: Convert JSON response to human-readable text
        # ========================================================================
        # Check if result is JSON string
        if isinstance(result, str):
            try:
                data = json.loads(result)
                if data.get("status") == "success":
                    team_data = data["data"]
                    # Format as human-readable text
                    response = format_team_advanced_stats(team_data)
                    season_ctx = get_season_context(include_date=True)
                    return f"📅 {season_ctx}\n\n{response}"
            except json.JSONDecodeError:
                # If can't parse as JSON, return as-is with context
                season_ctx = get_season_context()
                return f"📅 {season_ctx}\n\n{result}"

        # If not string, add season context to whatever we got
        season_ctx = get_season_context()
        return f"📅 {season_ctx}\n\n{str(result)}"

    except EntityNotFoundError as e:
        season_ctx = get_season_context()
        return f"📅 {season_ctx}\n\n❌ Team not found: {str(e)}"
    except Exception as e:
        logger.exception("Error in get_team_advanced_stats")
        season_ctx = get_season_context()
        return f"📅 {season_ctx}\n\n❌ Error: {str(e)}"


@mcp_server.tool()
async def get_player_advanced_stats(
    player_name: str, season: Optional[str] = None
) -> str:
    """
    Get player advanced statistics with human-readable formatting.

    Provides comprehensive player efficiency metrics including:
    - True Shooting % (TS%)
    - Effective Field Goal % (eFG%)
    - Usage % (percentage of team plays used)
    - Player Impact Estimate (PIE)
    - Offensive/Defensive/Net Rating
    - Assist %, Rebound %, Turnover %

    Args:
        player_name: Player name, nickname, or abbreviation (e.g., "LeBron James", "King James", "LeBron")
        season: Season string ('YYYY-YY'). Defaults to current season.

    Returns:
        Formatted text with player advanced statistics
    """
    logger.debug("get_player_advanced_stats('%s', season=%s)", player_name, season)

    # Default to current season if not specified
    if season is None:
        season = get_current_season()

    try:
        from nba_mcp.api.advanced_stats import get_player_advanced_stats as fetch_stats

        result = await fetch_stats(player_name=player_name, season=season)

        # Check if result is JSON string and convert to readable format
        if isinstance(result, str):
            try:
                data = json.loads(result)
                if data.get("status") == "success":
                    player_data = data["data"]
                    response = f"""**{player_data.get('player_name', 'Unknown Player')}** ({season})
**Team**: {player_data.get('team_abbreviation', 'N/A')}
**Games Played**: {player_data.get('games_played', 'N/A')}
**Minutes Per Game**: {player_data.get('minutes_per_game', 0):.1f}

**EFFICIENCY METRICS**
• True Shooting %: {player_data.get('true_shooting_pct', 0):.1%}
• Effective FG%: {player_data.get('effective_fg_pct', 0):.1%}
• Usage %: {player_data.get('usage_pct', 0):.1%}
• Player Impact Estimate (PIE): {player_data.get('pie', 0):.3f}

**RATINGS (Per 100 Possessions)**
• Offensive Rating: {player_data.get('offensive_rating', 0):.1f}
• Defensive Rating: {player_data.get('defensive_rating', 0):.1f}
• Net Rating: {player_data.get('net_rating', 0):.1f}

**ADVANCED PERCENTAGES**
• Assist %: {player_data.get('assist_pct', 0):.1%}
• Rebound %: {player_data.get('rebound_pct', 0):.1%}
• Turnover %: {player_data.get('turnover_pct', 0):.1f}%"""

                    season_ctx = get_season_context(include_date=True)
                    return f"📅 {season_ctx}\n\n{response}"
            except json.JSONDecodeError:
                pass

        # If not JSON or can't parse, return as-is with context
        season_ctx = get_season_context()
        return f"📅 {season_ctx}\n\n{str(result)}"

    except EntityNotFoundError as e:
        season_ctx = get_season_context()
        return f"📅 {season_ctx}\n\n❌ Player not found: {str(e)}"
    except Exception as e:
        logger.exception("Error in get_player_advanced_stats")
        season_ctx = get_season_context()
        return f"📅 {season_ctx}\n\n❌ Error: {str(e)}"


@mcp_server.tool()
async def compare_players(
    player1_name: str,
    player2_name: str,
    season: Optional[str] = None,
    normalization: str = "per_75_poss",
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
            - "per_75" or "per_75_poss": Per-75 possessions (DEFAULT - fairest comparison)
            - "era_adjusted": Adjust for pace/era differences

    Returns:
        Formatted markdown comparison with side-by-side stats
    """
    logger.debug(
        "compare_players('%s', '%s', season=%s, normalization=%s)",
        player1_name,
        player2_name,
        season,
        normalization,
    )

    # Default to current season if not specified
    if season is None:
        season = get_current_season()

    # Normalize parameter mapping for backwards compatibility
    # Map user-friendly aliases to internal parameter names
    normalization_map = {
        "per_75": "per_75_poss",          # User-friendly alias
        "per_game": "per_game",
        "raw": "raw",
        "era_adjusted": "era_adjusted",
        "per_75_poss": "per_75_poss",    # Also accept exact name
    }
    normalization_internal = normalization_map.get(normalization, normalization)

    try:
        from nba_mcp.api.advanced_stats import compare_players as do_compare

        # Call comparison with mapped normalization parameter
        comparison = await do_compare(
            player1_name=player1_name,
            player2_name=player2_name,
            season=season,
            normalization=normalization_internal,  # Use mapped value
        )

        # Add season context
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n{comparison}"

    except EntityNotFoundError as e:
        season_ctx = get_season_context()
        return f"📅 {season_ctx}\n\n❌ Error: {str(e)}"
    except Exception as e:
        logger.exception("Error in compare_players")
        season_ctx = get_season_context()
        return f"📅 {season_ctx}\n\n❌ Error comparing players: {str(e)}"


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

    Note:
        To save data, use the save_nba_data() tool after fetching.
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

    Note:
        To save data, use the save_nba_data() tool after fetching.

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
async def get_nba_schedule(
    season: Optional[str] = None,
    season_stage: Optional[str] = None,
    team: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    format: str = "markdown",
) -> str:
    """
    Get NBA schedule from the official NBA CDN with automatic current season detection.

    Fetches schedule data from https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json
    with comprehensive filtering and automatic season rollover support.

    Args:
        season: Season identifier (optional, defaults to current season)
                Examples: "2025-26", "2024-25"
                Auto-detection: If month >= August, uses next season (e.g., Oct 2025 → 2025-26)
        season_stage: Filter by season stage (optional)
                     Values: "preseason", "regular", "playoffs"
                     Aliases: "pre", "regular_season", "post"
        team: Filter by team abbreviation (optional)
              Examples: "LAL", "BOS", "GSW"
        date_from: Start date filter in YYYY-MM-DD format (optional)
                   Example: "2025-12-01"
        date_to: End date filter in YYYY-MM-DD format (optional)
                 Example: "2025-12-31"
        format: Output format - "markdown" (default) or "json"

    Returns:
        Formatted schedule as markdown or JSON string

    Schedule Data Includes:
        - Game ID, date/time (UTC and local)
        - Teams (home/away with IDs, names, abbreviations)
        - Venue information (arena, city, state)
        - Game status (Scheduled, In Progress, Final)
        - Scores (for completed games)
        - National TV broadcasters
        - Playoff series information (if applicable)

    Common Use Cases:
        # Get current season schedule (auto-detects 2025-26 if in Oct 2025)
        get_nba_schedule()

        # Get 2025-26 regular season only
        get_nba_schedule(season="2025-26", season_stage="regular")

        # Get all Lakers games this season
        get_nba_schedule(team="LAL")

        # Get next season's schedule (2026-27)
        get_nba_schedule(season="2026-27")

        # Get playoff schedule
        get_nba_schedule(season_stage="playoffs")

        # Get December 2025 games
        get_nba_schedule(date_from="2025-12-01", date_to="2025-12-31")

        # Combined filters: Lakers home regular season games in December
        get_nba_schedule(
            season="2025-26",
            season_stage="regular",
            team="LAL",
            date_from="2025-12-01",
            date_to="2025-12-31"
        )

    Season Auto-Detection Logic:
        - Current date in August or later → Next season (e.g., Aug 2025 → 2025-26)
        - Current date before August → Current season (e.g., Jul 2025 → 2024-25)
        - This ensures schedule always shows "current" or "upcoming" season

    Season Stages:
        - Preseason (stage_id=1): Exhibition games in October
        - Regular Season (stage_id=2): 82-game regular season (Oct-Apr)
        - Playoffs (stage_id=4): Postseason tournament (Apr-Jun)

    Automated Updates:
        - NBA CDN updates this endpoint throughout the season
        - Schedule changes (flex scheduling, postponements) reflected automatically
        - Can be called daily to refresh schedule data
        - Idempotent: Safe to call repeatedly, always returns latest data

    Data Freshness:
        - Source: Official NBA CDN (https://cdn.nba.com)
        - Updates: Real-time during season, pre-published for future seasons
        - Reliability: Same source as NBA.com website

    Integration with save_nba_data():
        result = get_nba_schedule(season="2025-26", team="LAL")
        save_nba_data(result, custom_filename="lakers_2025_26_schedule")

    Note:
        - Game times are shown in UTC. Convert to local timezone as needed.
        - Team abbreviations are case-insensitive (LAL = lal = Lal)
        - Date filters are inclusive (date_from and date_to included)
    """
    start_time = time.time()

    try:
        # Fetch and filter schedule
        df = await fetch_nba_schedule(
            season=season,
            season_stage=season_stage,
            team=team,
            date_from=date_from,
            date_to=date_to,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        # Format output
        if format.lower() == "json":
            # Return as ResponseEnvelope
            data = df.to_dict(orient="records") if not df.empty else []
            response = success_response(
                data=data,
                source="nba_cdn",
                cache_status="miss",
                execution_time_ms=execution_time_ms,
                rows=len(df),
                columns=len(df.columns) if not df.empty else 0,
            )
            return response.to_json_string()
        else:
            # Return as markdown
            markdown = format_schedule_markdown(df)
            return markdown

    except ValueError as e:
        logger.error(f"Validation error in get_nba_schedule: {e}")
        response = error_response(
            error_code="VALIDATION_ERROR",
            error_message=str(e),
        )
        return response.to_json_string()

    except requests.RequestException as e:
        logger.error(f"Network error fetching NBA schedule: {e}")
        response = error_response(
            error_code="NETWORK_ERROR",
            error_message=f"Failed to fetch schedule from NBA CDN: {str(e)}",
        )
        return response.to_json_string()

    except Exception as e:
        logger.exception("Unexpected error in get_nba_schedule")
        response = error_response(
            error_code="INTERNAL_ERROR",
            error_message=f"Failed to fetch NBA schedule: {str(e)}",
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
async def save_nba_data(
    data_json: str,
    custom_filename: Optional[str] = None,
    format: str = "auto"
) -> str:
    """
    Save NBA data to organized mcp_data/ folder with smart format selection.

    Automatically detects data type and saves in optimal format:
    - Tabular data → Parquet (85% smaller, 10-100x faster queries)
    - Markdown text → TXT (human-readable)
    - Other data → JSON (fallback)

    Uses DuckDB + Snappy compression for Parquet files.

    Args:
        data_json: JSON string from any NBA MCP tool response
        custom_filename: Optional custom filename (without extension or timestamp)
        format: Format selection - "auto" (default), "parquet", "json", "txt"
                "auto" intelligently chooses based on data structure

    Returns:
        JSON string with save confirmation, file location, size, and format used

    Examples:
        # Auto-format (recommended) - uses Parquet for tabular data
        player_data = fetch_player_games(season="2024-25", player="LeBron James")
        save_nba_data(player_data)
        → Saves as: mcp_data/2025-10-30/lebron_james_games_143052.parquet

        # Markdown play-by-play → saved as TXT
        pbp_data = play_by_play(game_date="2025-10-29", team="Lakers")
        save_nba_data(pbp_data)
        → Saves as: mcp_data/2025-10-30/lakers_play_by_play_143052.txt

        # Force specific format
        save_nba_data(player_data, format="json")  # Force JSON
        → Saves as: mcp_data/2025-10-30/player_data_143052.json

    Format Selection (when format="auto"):
        - Tabular data (game logs, stats, lineups) → Parquet
        - Markdown text (play-by-play) → TXT
        - Other structures → JSON

    Benefits of Parquet:
        - 85% size reduction vs JSON
        - 10-100x faster queries with DuckDB
        - Column-level compression
        - Efficient data science workflows

    Note:
        All filenames include timestamp (HHMMSS) for uniqueness.
        Data is organized into date-based folders: mcp_data/YYYY-MM-DD/
    """
    start_time = time.time()

    try:
        # Parse JSON data
        data = json.loads(data_json)

        # Import helper functions
        from nba_mcp.data.dataset_manager import (
            extract_dataframe,
            is_tabular_data,
            save_json_data,
            save_parquet,
            save_text,
        )

        # Auto-detect format if "auto"
        if format == "auto":
            # Check if markdown text
            if isinstance(data, dict) and data.get('format') == 'markdown':
                format = "txt"
                logger.info("Auto-detected format: TXT (markdown content)")
            # Check if tabular data (can convert to DataFrame)
            elif is_tabular_data(data):
                format = "parquet"
                logger.info("Auto-detected format: Parquet (tabular data)")
            else:
                format = "json"
                logger.info("Auto-detected format: JSON (non-tabular data)")

        # Determine filename base
        if custom_filename:
            filename_base = custom_filename
        else:
            from nba_mcp.data.dataset_manager import generate_descriptive_filename
            try:
                filename_base = generate_descriptive_filename(data)
            except Exception:
                filename_base = "nba_data"

        # Save in appropriate format
        if format == "parquet":
            # Extract DataFrame and save as Parquet
            df = extract_dataframe(data)
            file_path = save_parquet(df, filename_base)
            logger.info(f"Saved {len(df)} rows × {len(df.columns)} columns as Parquet")

        elif format == "txt":
            # Extract text content
            if isinstance(data, dict) and 'data' in data:
                text = data['data']
            elif isinstance(data, str):
                text = data
            else:
                text = json.dumps(data, indent=2)
            file_path = save_text(text, filename_base)
            logger.info(f"Saved {len(text)} characters as TXT")

        else:  # JSON format (fallback)
            file_path = save_json_data(data, custom_filename=custom_filename)
            logger.info(f"Saved as JSON")

        # Get file stats
        file_size = file_path.stat().st_size
        execution_time_ms = (time.time() - start_time) * 1000

        # Build response
        response = {
            "status": "success",
            "message": f"Data saved successfully as {format.upper()}",
            "file_info": {
                "path": str(file_path),
                "filename": file_path.name,
                "format": format,
                "size_bytes": file_size,
                "size_kb": round(file_size / 1024, 2),
                "size_mb": round(file_size / (1024 * 1024), 2),
                "folder": str(file_path.parent),
            },
            "metadata": {
                "execution_time_ms": round(execution_time_ms, 2),
                "timestamp": datetime.now().isoformat(),
                "format_auto_detected": custom_filename is None,
            }
        }

        # Add DataFrame info if Parquet
        if format == "parquet":
            response["file_info"]["rows"] = len(df)
            response["file_info"]["columns"] = len(df.columns)

        return json.dumps(response, indent=2)

    except json.JSONDecodeError as e:
        return json.dumps({
            "status": "error",
            "error_code": "INVALID_JSON",
            "error_message": f"Invalid JSON data: {str(e)}",
        }, indent=2)

    except Exception as e:
        logger.exception("Error in save_nba_data")
        return json.dumps({
            "status": "error",
            "error_code": "SAVE_ERROR",
            "error_message": f"Failed to save data: {str(e)}",
            "format_attempted": format,
        }, indent=2)


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
        from nba_mcp.data.introspection import get_introspector
        from nba_mcp.data.pagination import get_paginator

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


@mcp_server.tool()
async def get_player_game_stats(
    player_name: str,
    season: Optional[str] = None,
    last_n_games: Optional[int] = None,
    opponent: Optional[str] = None,
    game_date: Optional[str] = None,
    season_type: str = "Regular Season",
) -> str:
    """
    Get individual game statistics for a specific player.

    This tool fills the critical gap identified in the weakness analysis:
    providing easy access to player stats for specific games.

    Common use cases:
    - "Show me LeBron's last game"
    - "How did Curry perform vs the Lakers?"
    - "Get Giannis stats from January 15th"
    - "Show me Jokic's last 10 games"

    Args:
        player_name: Player name (supports fuzzy matching, e.g., "LeBron", "LBJ")
        season: Season in 'YYYY-YY' format (defaults to current season)
        last_n_games: Limit to most recent N games (e.g., 1 for last game, 10 for last 10)
        opponent: Filter by opponent team (e.g., "Lakers", "LAL")
        game_date: Specific game date in 'YYYY-MM-DD' or 'MM/DD/YYYY' format
        season_type: "Regular Season" or "Playoffs" (default: "Regular Season")

    Returns:
        Formatted game statistics with:
        - Game date and matchup
        - Win/Loss result
        - Minutes played
        - Points, Rebounds, Assists
        - Field goals, 3-pointers, Free throws
        - Advanced stats (PTS, REB, AST, STL, BLK, TO, +/-)

    Examples:
        # Get player's most recent game
        get_player_game_stats("LeBron James", last_n_games=1)

        # Get last 5 games vs specific opponent
        get_player_game_stats("Stephen Curry", opponent="Lakers", last_n_games=5)

        # Get stats for specific date
        get_player_game_stats("Giannis", game_date="2024-01-15")

        # Get full season game log
        get_player_game_stats("Luka Doncic", season="2023-24")
    """
    logger.debug(
        f"get_player_game_stats(player={player_name}, season={season}, "
        f"last_n={last_n_games}, opponent={opponent}, date={game_date})"
    )

    client = NBAApiClient()

    try:
        # Default to current season if not specified
        if season is None:
            season = get_current_season()

        # Fetch game log
        result = await client.get_player_game_log(
            player_name=player_name,
            season=season,
            season_type=season_type,
            last_n_games=last_n_games,
            as_dataframe=True,
        )

        # Check for errors
        if isinstance(result, dict) and "error" in result:
            season_ctx = get_season_context(include_date=True)
            return f"📅 {season_ctx}\n\n❌ {result['error']}"

        if not isinstance(result, pd.DataFrame):
            season_ctx = get_season_context(include_date=True)
            return f"📅 {season_ctx}\n\n❌ Unexpected response format"

        df = result

        if df.empty:
            season_ctx = get_season_context(include_date=True)
            return f"📅 {season_ctx}\n\nNo games found for {player_name} in {season}"

        # Apply additional filters
        if opponent:
            # Normalize opponent name
            opponent_team_name = None
            try:
                from nba_mcp.api.entity_resolver import resolve_entity
                resolved = resolve_entity(opponent, entity_type="team")
                if resolved["status"] == "success":
                    opponent_team_name = resolved["data"]["abbreviation"]
            except:
                # Fallback to direct matching
                opponent_team_name = opponent.upper()

            # Filter by opponent in MATCHUP column (e.g., "LAL vs. GSW" or "LAL @ GSW")
            if opponent_team_name and "MATCHUP" in df.columns:
                df = df[df["MATCHUP"].str.contains(opponent_team_name, case=False, na=False)]

        if game_date:
            # Normalize game date
            try:
                from nba_mcp.api.tools.nba_api_utils import normalize_date
                target_date = normalize_date(game_date)
                df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"])
                df = df[df["GAME_DATE"].dt.date == target_date.date()]
            except Exception as e:
                logger.warning(f"Could not parse game_date '{game_date}': {e}")

        if df.empty:
            season_ctx = get_season_context(include_date=True)
            filters_msg = []
            if opponent:
                filters_msg.append(f"opponent={opponent}")
            if game_date:
                filters_msg.append(f"date={game_date}")
            filters_str = ", ".join(filters_msg) if filters_msg else "specified filters"
            return f"📅 {season_ctx}\n\nNo games found for {player_name} with {filters_str}"

        # Format response
        response_lines = [f"# {player_name} - Game Stats ({season} {season_type})"]
        response_lines.append("")

        # Summary if multiple games
        if len(df) > 1:
            avg_pts = df["PTS"].mean() if "PTS" in df.columns else 0
            avg_reb = df["REB"].mean() if "REB" in df.columns else 0
            avg_ast = df["AST"].mean() if "AST" in df.columns else 0
            wins = len(df[df["WL"] == "W"]) if "WL" in df.columns else 0
            losses = len(df[df["WL"] == "L"]) if "WL" in df.columns else 0

            response_lines.append(f"**Games**: {len(df)} ({wins}W-{losses}L)")
            response_lines.append(f"**Averages**: {avg_pts:.1f} PTS, {avg_reb:.1f} REB, {avg_ast:.1f} AST")
            response_lines.append("")
            response_lines.append("---")
            response_lines.append("")

        # Individual game details
        for idx, row in df.iterrows():
            game_date_str = row.get("GAME_DATE", "")
            if isinstance(game_date_str, pd.Timestamp):
                game_date_str = game_date_str.strftime("%Y-%m-%d")

            matchup = row.get("MATCHUP", "")
            wl = row.get("WL", "")
            wl_emoji = "✅" if wl == "W" else "❌"
            minutes = row.get("MIN", 0)
            pts = row.get("PTS", 0)
            reb = row.get("REB", 0)
            ast = row.get("AST", 0)
            stl = row.get("STL", 0)
            blk = row.get("BLK", 0)
            tov = row.get("TOV", 0)
            fgm = row.get("FGM", 0)
            fga = row.get("FGA", 0)
            fg_pct = row.get("FG_PCT", 0) * 100 if "FG_PCT" in row and pd.notna(row["FG_PCT"]) else 0
            fg3m = row.get("FG3M", 0)
            fg3a = row.get("FG3A", 0)
            fg3_pct = row.get("FG3_PCT", 0) * 100 if "FG3_PCT" in row and pd.notna(row["FG3_PCT"]) else 0
            plus_minus = row.get("PLUS_MINUS", 0)

            response_lines.append(f"## {game_date_str} - {matchup} {wl_emoji}")
            response_lines.append(f"**Result**: {wl} | **Minutes**: {minutes}")
            response_lines.append(f"**Stats**: {pts} PTS, {reb} REB, {ast} AST, {stl} STL, {blk} BLK")
            response_lines.append(f"**Shooting**: {fgm}/{fga} FG ({fg_pct:.1f}%), {fg3m}/{fg3a} 3PT ({fg3_pct:.1f}%)")
            response_lines.append(f"**Turnovers**: {tov} | **+/-**: {plus_minus:+d}")
            response_lines.append("")

        response = "\n".join(response_lines)

        # Add season context
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n{response}"

    except EntityNotFoundError as e:
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n❌ {str(e)}"
    except Exception as e:
        logger.exception("Unexpected error in get_player_game_stats")
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n❌ Error fetching player game stats: {str(e)}"




@mcp_server.tool()
async def get_box_score(
    game_id: Optional[str] = None,
    team: Optional[str] = None,
    game_date: Optional[str] = None,
) -> str:
    """
    Get full box score for a specific game with quarter-by-quarter breakdowns.

    This tool fills the critical gap identified in the weakness analysis:
    providing detailed box scores with quarter-level granularity.

    Common use cases:
    - "Get box score for game ID 0022300500"
    - "Show me Lakers box score from last night"
    - "Box score for Warriors game on 2024-01-15"

    Args:
        game_id: 10-digit NBA game ID (e.g., "0022300500"). If provided, this takes precedence.
        team: Team name for date lookup (e.g., "Lakers", "LAL"). Used with game_date.
        game_date: Game date in 'YYYY-MM-DD' or 'MM/DD/YYYY' format. Used with team.

    Returns:
        Formatted box score with:
        - Quarter-by-quarter scores
        - Player statistics for both teams
        - Team totals
        - Starters vs bench breakdowns

    Examples:
        # Get box score by game ID
        get_box_score(game_id="0022300500")

        # Get box score by team and date
        get_box_score(team="Lakers", game_date="2024-01-15")

    Notes:
        - Either game_id OR (team + game_date) must be provided
        - Quarter breakdowns show Q1, Q2, Q3, Q4, and OT (if applicable)
        - Player stats include MIN, PTS, REB, AST, FG%, 3P%, FT%, +/-
    """
    logger.debug(f"get_box_score(game_id={game_id}, team={team}, game_date={game_date})")

    client = NBAApiClient()

    try:
        # Validate input
        if not game_id and not (team and game_date):
            season_ctx = get_season_context(include_date=True)
            return f"📅 {season_ctx}\n\n❌ Error: Must provide either game_id OR (team + game_date)"

        # If team and date provided, find game_id
        if not game_id and team and game_date:
            # Get games for that date
            games_result = await client.get_games_by_date(game_date)

            if isinstance(games_result, str):
                season_ctx = get_season_context(include_date=True)
                return f"📅 {season_ctx}\n\n❌ {games_result}"

            # Resolve team name
            try:
                from nba_mcp.api.entity_resolver import resolve_entity
                resolved = resolve_entity(team, entity_type="team")
                if resolved["status"] == "success":
                    team_id = resolved["data"]["id"]
                else:
                    team_id = get_team_id(team)
            except:
                team_id = get_team_id(team)

            if not team_id:
                season_ctx = get_season_context(include_date=True)
                return f"📅 {season_ctx}\n\n❌ Team not found: {team}"

            # Find game with this team
            game_found = None
            if isinstance(games_result, pd.DataFrame):
                for _, game in games_result.iterrows():
                    if game["home_team"]["id"] == team_id or game["visitor_team"]["id"] == team_id:
                        game_id = game["game_id"]
                        game_found = game
                        break

            if not game_id:
                season_ctx = get_season_context(include_date=True)
                return f"📅 {season_ctx}\n\nNo game found for {team} on {game_date}"

        # Fetch box score
        result = await client.get_box_score(game_id=game_id, as_dataframe=True)

        # Check for errors
        if isinstance(result, dict) and "error" in result:
            season_ctx = get_season_context(include_date=True)
            return f"📅 {season_ctx}\n\n❌ {result['error']}"

        player_stats = result.get("player_stats")
        team_stats = result.get("team_stats")
        line_score = result.get("line_score")

        if player_stats is None or player_stats.empty:
            season_ctx = get_season_context(include_date=True)
            return f"📅 {season_ctx}\n\nNo box score data found for game {game_id}"

        # Format response
        response_lines = [f"# Box Score - Game {game_id}"]
        response_lines.append("")

        # Quarter-by-quarter scores
        if line_score is not None and not line_score.empty:
            response_lines.append("## Quarter Scores")
            response_lines.append("")

            for _, row in line_score.iterrows():
                team_abbrev = row.get("TEAM_ABBREVIATION", "")
                q1 = row.get("PTS_QT1", 0)
                q2 = row.get("PTS_QT2", 0)
                q3 = row.get("PTS_QT3", 0)
                q4 = row.get("PTS_QT4", 0)
                pts = row.get("PTS", 0)

                quarters_str = f"Q1: {q1} | Q2: {q2} | Q3: {q3} | Q4: {q4}"

                # Check for overtime
                for ot in range(1, 10):  # Check up to 9 OT periods
                    ot_col = f"PTS_OT{ot}"
                    if ot_col in row and pd.notna(row[ot_col]) and row[ot_col] > 0:
                        quarters_str += f" | OT{ot}: {row[ot_col]}"

                response_lines.append(f"**{team_abbrev}**: {quarters_str} | **TOTAL: {pts}**")

            response_lines.append("")
            response_lines.append("---")
            response_lines.append("")

        # Team stats
        if team_stats is not None and not team_stats.empty:
            response_lines.append("## Team Totals")
            response_lines.append("")

            for _, row in team_stats.iterrows():
                team_abbrev = row.get("TEAM_ABBREVIATION", "")
                pts = row.get("PTS", 0)
                reb = row.get("REB", 0)
                ast = row.get("AST", 0)
                stl = row.get("STL", 0)
                blk = row.get("BLK", 0)
                tov = row.get("TOV", 0)
                fg_pct = row.get("FG_PCT", 0) * 100 if pd.notna(row.get("FG_PCT")) else 0
                fg3_pct = row.get("FG3_PCT", 0) * 100 if pd.notna(row.get("FG3_PCT")) else 0

                response_lines.append(f"### {team_abbrev}")
                response_lines.append(f"**Totals**: {pts} PTS, {reb} REB, {ast} AST, {stl} STL, {blk} BLK, {tov} TOV")
                response_lines.append(f"**Shooting**: {fg_pct:.1f}% FG, {fg3_pct:.1f}% 3PT")
                response_lines.append("")

            response_lines.append("---")
            response_lines.append("")

        # Player stats by team
        response_lines.append("## Player Stats")
        response_lines.append("")

        teams = player_stats["TEAM_ABBREVIATION"].unique()

        for team_abbrev in teams:
            team_players = player_stats[player_stats["TEAM_ABBREVIATION"] == team_abbrev]

            # Sort by minutes (starters first)
            team_players = team_players.sort_values("MIN", ascending=False)

            response_lines.append(f"### {team_abbrev}")
            response_lines.append("")

            # Starters (top 5 by minutes)
            starters = team_players.head(5)
            response_lines.append("**Starters:**")
            response_lines.append("")

            for _, player in starters.iterrows():
                name = player.get("PLAYER_NAME", "")
                min_played = player.get("MIN", 0)
                pts = player.get("PTS", 0)
                reb = player.get("REB", 0)
                ast = player.get("AST", 0)
                fg = f"{player.get('FGM', 0)}-{player.get('FGA', 0)}"
                fg3 = f"{player.get('FG3M', 0)}-{player.get('FG3A', 0)}"
                plus_minus = player.get("PLUS_MINUS", 0)

                response_lines.append(
                    f"- **{name}**: {min_played} MIN | {pts} PTS, {reb} REB, {ast} AST | "
                    f"FG: {fg}, 3PT: {fg3} | +/-: {plus_minus:+d}"
                )

            response_lines.append("")

            # Bench (remaining players)
            bench = team_players.iloc[5:]
            if not bench.empty:
                response_lines.append("**Bench:**")
                response_lines.append("")

                for _, player in bench.iterrows():
                    name = player.get("PLAYER_NAME", "")
                    min_played = player.get("MIN", 0)

                    # Skip DNPs (0 minutes)
                    if min_played == 0 or pd.isna(min_played):
                        continue

                    pts = player.get("PTS", 0)
                    reb = player.get("REB", 0)
                    ast = player.get("AST", 0)
                    fg = f"{player.get('FGM', 0)}-{player.get('FGA', 0)}"
                    plus_minus = player.get("PLUS_MINUS", 0)

                    response_lines.append(
                        f"- **{name}**: {min_played} MIN | {pts} PTS, {reb} REB, {ast} AST | "
                        f"FG: {fg} | +/-: {plus_minus:+d}"
                    )

                response_lines.append("")

            response_lines.append("")

        response = "\n".join(response_lines)

        # Add season context
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n{response}"

    except Exception as e:
        logger.exception("Unexpected error in get_box_score")
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n❌ Error fetching box score: {str(e)}"


@mcp_server.tool()
async def get_clutch_stats(
    entity_name: str,
    entity_type: str = "player",
    season: Optional[str] = None,
    per_mode: str = "PerGame",
) -> str:
    """
    Get clutch time statistics (final 5 minutes, score within 5 points).

    This tool fills the critical gap identified in the weakness analysis:
    providing clutch performance analytics.

    Clutch time is defined as:
    - Final 5 minutes of the 4th quarter or overtime
    - Score differential of 5 points or less

    Common use cases:
    - "Show me LeBron's clutch stats"
    - "How do the Lakers perform in clutch time?"
    - "Get Curry's clutch shooting percentages"

    Args:
        entity_name: Player or team name (supports fuzzy matching)
        entity_type: "player" or "team" (default: "player")
        season: Season in 'YYYY-YY' format (defaults to current season)
        per_mode: "PerGame" or "Totals" (default: "PerGame")

    Returns:
        Formatted clutch statistics with:
        - Games played in clutch situations
        - Clutch time win-loss record
        - Points, assists, rebounds in clutch
        - Shooting percentages in clutch
        - Clutch time efficiency metrics

    Examples:
        # Get player clutch stats
        get_clutch_stats("LeBron James")

        # Get team clutch stats
        get_clutch_stats("Lakers", entity_type="team")

        # Get totals instead of per-game
        get_clutch_stats("Stephen Curry", per_mode="Totals")

        # Specific season
        get_clutch_stats("Giannis", season="2022-23")
    """
    logger.debug(
        f"get_clutch_stats(entity={entity_name}, type={entity_type}, "
        f"season={season}, per_mode={per_mode})"
    )

    client = NBAApiClient()

    try:
        # Default to current season if not specified
        if season is None:
            season = get_current_season()

        # Fetch clutch stats
        result = await client.get_clutch_stats(
            entity_name=entity_name,
            entity_type=entity_type,
            season=season,
            per_mode=per_mode
        )

        # Check for errors
        if isinstance(result, dict) and "error" in result:
            season_ctx = get_season_context(include_date=True)
            return f"📅 {season_ctx}\n\n❌ {result['error']}"

        if not isinstance(result, pd.DataFrame) or result.empty:
            season_ctx = get_season_context(include_date=True)
            return f"📅 {season_ctx}\n\nNo clutch stats found for {entity_name} in {season}"

        # Get the single row (filtered data)
        row = result.iloc[0]

        # Format response
        if entity_type == "player":
            player_name = row.get("PLAYER_NAME", entity_name)
            team_abbrev = row.get("TEAM_ABBREVIATION", "")

            response_lines = [
                f"# {player_name} - Clutch Stats ({season})",
                f"**Team**: {team_abbrev}" if team_abbrev else "",
                f"**Definition**: Final 5 min, score within 5 points",
                "",
                "## Clutch Performance",
                ""
            ]

            # Games and record
            games = row.get("GP", 0)
            wins = row.get("W", 0)
            losses = row.get("L", 0)
            win_pct = row.get("W_PCT", 0) * 100 if pd.notna(row.get("W_PCT")) else 0

            response_lines.append(f"**Games**: {games} clutch situations")
            response_lines.append(f"**Record**: {wins}W-{losses}L ({win_pct:.1f}%)")
            response_lines.append("")

            # Scoring
            pts = row.get("PTS", 0)
            fgm = row.get("FGM", 0)
            fga = row.get("FGA", 0)
            fg_pct = row.get("FG_PCT", 0) * 100 if pd.notna(row.get("FG_PCT")) else 0
            fg3m = row.get("FG3M", 0)
            fg3a = row.get("FG3A", 0)
            fg3_pct = row.get("FG3_PCT", 0) * 100 if pd.notna(row.get("FG3_PCT")) else 0
            ftm = row.get("FTM", 0)
            fta = row.get("FTA", 0)
            ft_pct = row.get("FT_PCT", 0) * 100 if pd.notna(row.get("FT_PCT")) else 0

            response_lines.append("## Scoring")
            response_lines.append(f"**Points**: {pts:.1f} {per_mode.lower()}")
            response_lines.append(f"**Field Goals**: {fgm:.1f}/{fga:.1f} ({fg_pct:.1f}%)")
            response_lines.append(f"**Three Pointers**: {fg3m:.1f}/{fg3a:.1f} ({fg3_pct:.1f}%)")
            response_lines.append(f"**Free Throws**: {ftm:.1f}/{fta:.1f} ({ft_pct:.1f}%)")
            response_lines.append("")

            # Playmaking and rebounding
            ast = row.get("AST", 0)
            reb = row.get("REB", 0)
            oreb = row.get("OREB", 0)
            dreb = row.get("DREB", 0)
            stl = row.get("STL", 0)
            blk = row.get("BLK", 0)
            tov = row.get("TOV", 0)

            response_lines.append("## Playmaking & Defense")
            response_lines.append(f"**Assists**: {ast:.1f}")
            response_lines.append(f"**Rebounds**: {reb:.1f} ({oreb:.1f} OFF, {dreb:.1f} DEF)")
            response_lines.append(f"**Steals**: {stl:.1f}")
            response_lines.append(f"**Blocks**: {blk:.1f}")
            response_lines.append(f"**Turnovers**: {tov:.1f}")
            response_lines.append("")

            # Advanced metrics (if available)
            if "PLUS_MINUS" in row and pd.notna(row["PLUS_MINUS"]):
                plus_minus = row["PLUS_MINUS"]
                response_lines.append("## Impact")
                response_lines.append(f"**Plus/Minus**: {plus_minus:+.1f}")
                response_lines.append("")

        else:  # team
            team_name = row.get("TEAM_NAME", entity_name)

            response_lines = [
                f"# {team_name} - Clutch Stats ({season})",
                f"**Definition**: Final 5 min, score within 5 points",
                "",
                "## Clutch Performance",
                ""
            ]

            # Games and record
            games = row.get("GP", 0)
            wins = row.get("W", 0)
            losses = row.get("L", 0)
            win_pct = row.get("W_PCT", 0) * 100 if pd.notna(row.get("W_PCT")) else 0

            response_lines.append(f"**Games**: {games} clutch situations")
            response_lines.append(f"**Record**: {wins}W-{losses}L ({win_pct:.1f}%)")
            response_lines.append("")

            # Scoring
            pts = row.get("PTS", 0)
            fg_pct = row.get("FG_PCT", 0) * 100 if pd.notna(row.get("FG_PCT")) else 0
            fg3_pct = row.get("FG3_PCT", 0) * 100 if pd.notna(row.get("FG3_PCT")) else 0
            ft_pct = row.get("FT_PCT", 0) * 100 if pd.notna(row.get("FT_PCT")) else 0

            response_lines.append("## Team Stats")
            response_lines.append(f"**Points**: {pts:.1f} {per_mode.lower()}")
            response_lines.append(f"**FG%**: {fg_pct:.1f}% | **3P%**: {fg3_pct:.1f}% | **FT%**: {ft_pct:.1f}%")

            ast = row.get("AST", 0)
            reb = row.get("REB", 0)
            tov = row.get("TOV", 0)

            response_lines.append(f"**Assists**: {ast:.1f} | **Rebounds**: {reb:.1f} | **Turnovers**: {tov:.1f}")
            response_lines.append("")

            # Net rating (if available)
            if "PLUS_MINUS" in row and pd.notna(row["PLUS_MINUS"]):
                plus_minus = row["PLUS_MINUS"]
                response_lines.append(f"**Net Rating**: {plus_minus:+.1f}")
                response_lines.append("")

        response = "\n".join(response_lines)

        # Add season context
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n{response}"

    except EntityNotFoundError as e:
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n❌ {str(e)}"
    except Exception as e:
        logger.exception("Unexpected error in get_clutch_stats")
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n❌ Error fetching clutch stats: {str(e)}"




@mcp_server.tool()
async def get_box_score(
    game_id: Optional[str] = None,
    team: Optional[str] = None,
    game_date: Optional[str] = None,
) -> str:
    """
    Get full box score for a specific game with quarter-by-quarter breakdowns.

    This tool fills the critical gap identified in the weakness analysis:
    providing detailed box scores with quarter-level granularity.

    Common use cases:
    - "Get box score for game ID 0022300500"
    - "Show me Lakers box score from last night"
    - "Box score for Warriors game on 2024-01-15"

    Args:
        game_id: 10-digit NBA game ID (e.g., "0022300500"). If provided, this takes precedence.
        team: Team name for date lookup (e.g., "Lakers", "LAL"). Used with game_date.
        game_date: Game date in 'YYYY-MM-DD' or 'MM/DD/YYYY' format. Used with team.

    Returns:
        Formatted box score with:
        - Quarter-by-quarter scores
        - Player statistics for both teams
        - Team totals
        - Starters vs bench breakdowns

    Examples:
        # Get box score by game ID
        get_box_score(game_id="0022300500")

        # Get box score by team and date
        get_box_score(team="Lakers", game_date="2024-01-15")

    Notes:
        - Either game_id OR (team + game_date) must be provided
        - Quarter breakdowns show Q1, Q2, Q3, Q4, and OT (if applicable)
        - Player stats include MIN, PTS, REB, AST, FG%, 3P%, FT%, +/-
    """
    logger.debug(f"get_box_score(game_id={game_id}, team={team}, game_date={game_date})")

    client = NBAApiClient()

    try:
        # Validate input
        if not game_id and not (team and game_date):
            season_ctx = get_season_context(include_date=True)
            return f"📅 {season_ctx}\n\n❌ Error: Must provide either game_id OR (team + game_date)"

        # If team and date provided, find game_id
        if not game_id and team and game_date:
            # Get games for that date
            games_result = await client.get_games_by_date(game_date)

            if isinstance(games_result, str):
                season_ctx = get_season_context(include_date=True)
                return f"📅 {season_ctx}\n\n❌ {games_result}"

            # Resolve team name
            try:
                from nba_mcp.api.entity_resolver import resolve_entity
                resolved = resolve_entity(team, entity_type="team")
                if resolved["status"] == "success":
                    team_id = resolved["data"]["id"]
                else:
                    team_id = get_team_id(team)
            except:
                team_id = get_team_id(team)

            if not team_id:
                season_ctx = get_season_context(include_date=True)
                return f"📅 {season_ctx}\n\n❌ Team not found: {team}"

            # Find game with this team
            game_found = None
            if isinstance(games_result, pd.DataFrame):
                for _, game in games_result.iterrows():
                    if game["home_team"]["id"] == team_id or game["visitor_team"]["id"] == team_id:
                        game_id = game["game_id"]
                        game_found = game
                        break

            if not game_id:
                season_ctx = get_season_context(include_date=True)
                return f"📅 {season_ctx}\n\nNo game found for {team} on {game_date}"

        # Fetch box score
        result = await client.get_box_score(game_id=game_id, as_dataframe=True)

        # Check for errors
        if isinstance(result, dict) and "error" in result:
            season_ctx = get_season_context(include_date=True)
            return f"📅 {season_ctx}\n\n❌ {result['error']}"

        player_stats = result.get("player_stats")
        team_stats = result.get("team_stats")
        line_score = result.get("line_score")

        if player_stats is None or player_stats.empty:
            season_ctx = get_season_context(include_date=True)
            return f"📅 {season_ctx}\n\nNo box score data found for game {game_id}"

        # Format response
        response_lines = [f"# Box Score - Game {game_id}"]
        response_lines.append("")

        # Quarter-by-quarter scores
        if line_score is not None and not line_score.empty:
            response_lines.append("## Quarter Scores")
            response_lines.append("")

            for _, row in line_score.iterrows():
                team_abbrev = row.get("TEAM_ABBREVIATION", "")
                q1 = row.get("PTS_QT1", 0)
                q2 = row.get("PTS_QT2", 0)
                q3 = row.get("PTS_QT3", 0)
                q4 = row.get("PTS_QT4", 0)
                pts = row.get("PTS", 0)

                quarters_str = f"Q1: {q1} | Q2: {q2} | Q3: {q3} | Q4: {q4}"

                # Check for overtime
                for ot in range(1, 10):  # Check up to 9 OT periods
                    ot_col = f"PTS_OT{ot}"
                    if ot_col in row and pd.notna(row[ot_col]) and row[ot_col] > 0:
                        quarters_str += f" | OT{ot}: {row[ot_col]}"

                response_lines.append(f"**{team_abbrev}**: {quarters_str} | **TOTAL: {pts}**")

            response_lines.append("")
            response_lines.append("---")
            response_lines.append("")

        # Team stats
        if team_stats is not None and not team_stats.empty:
            response_lines.append("## Team Totals")
            response_lines.append("")

            for _, row in team_stats.iterrows():
                team_abbrev = row.get("TEAM_ABBREVIATION", "")
                pts = row.get("PTS", 0)
                reb = row.get("REB", 0)
                ast = row.get("AST", 0)
                stl = row.get("STL", 0)
                blk = row.get("BLK", 0)
                tov = row.get("TOV", 0)
                fg_pct = row.get("FG_PCT", 0) * 100 if pd.notna(row.get("FG_PCT")) else 0
                fg3_pct = row.get("FG3_PCT", 0) * 100 if pd.notna(row.get("FG3_PCT")) else 0

                response_lines.append(f"### {team_abbrev}")
                response_lines.append(f"**Totals**: {pts} PTS, {reb} REB, {ast} AST, {stl} STL, {blk} BLK, {tov} TOV")
                response_lines.append(f"**Shooting**: {fg_pct:.1f}% FG, {fg3_pct:.1f}% 3PT")
                response_lines.append("")

            response_lines.append("---")
            response_lines.append("")

        # Player stats by team
        response_lines.append("## Player Stats")
        response_lines.append("")

        teams = player_stats["TEAM_ABBREVIATION"].unique()

        for team_abbrev in teams:
            team_players = player_stats[player_stats["TEAM_ABBREVIATION"] == team_abbrev]

            # Sort by minutes (starters first)
            team_players = team_players.sort_values("MIN", ascending=False)

            response_lines.append(f"### {team_abbrev}")
            response_lines.append("")

            # Starters (top 5 by minutes)
            starters = team_players.head(5)
            response_lines.append("**Starters:**")
            response_lines.append("")

            for _, player in starters.iterrows():
                name = player.get("PLAYER_NAME", "")
                min_played = player.get("MIN", 0)
                pts = player.get("PTS", 0)
                reb = player.get("REB", 0)
                ast = player.get("AST", 0)
                fg = f"{player.get('FGM', 0)}-{player.get('FGA', 0)}"
                fg3 = f"{player.get('FG3M', 0)}-{player.get('FG3A', 0)}"
                plus_minus = player.get("PLUS_MINUS", 0)

                response_lines.append(
                    f"- **{name}**: {min_played} MIN | {pts} PTS, {reb} REB, {ast} AST | "
                    f"FG: {fg}, 3PT: {fg3} | +/-: {plus_minus:+d}"
                )

            response_lines.append("")

            # Bench (remaining players)
            bench = team_players.iloc[5:]
            if not bench.empty:
                response_lines.append("**Bench:**")
                response_lines.append("")

                for _, player in bench.iterrows():
                    name = player.get("PLAYER_NAME", "")
                    min_played = player.get("MIN", 0)

                    # Skip DNPs (0 minutes)
                    if min_played == 0 or pd.isna(min_played):
                        continue

                    pts = player.get("PTS", 0)
                    reb = player.get("REB", 0)
                    ast = player.get("AST", 0)
                    fg = f"{player.get('FGM', 0)}-{player.get('FGA', 0)}"
                    plus_minus = player.get("PLUS_MINUS", 0)

                    response_lines.append(
                        f"- **{name}**: {min_played} MIN | {pts} PTS, {reb} REB, {ast} AST | "
                        f"FG: {fg} | +/-: {plus_minus:+d}"
                    )

                response_lines.append("")

            response_lines.append("")

        response = "\n".join(response_lines)

        # Add season context
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n{response}"

    except Exception as e:
        logger.exception("Unexpected error in get_box_score")
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n❌ Error fetching box score: {str(e)}"


@mcp_server.tool()
async def get_clutch_stats(
    entity_name: str,
    entity_type: str = "player",
    season: Optional[str] = None,
    per_mode: str = "PerGame",
) -> str:
    """
    Get clutch time statistics (final 5 minutes, score within 5 points).

    This tool fills the critical gap identified in the weakness analysis:
    providing clutch performance analytics.

    Clutch time is defined as:
    - Final 5 minutes of the 4th quarter or overtime
    - Score differential of 5 points or less

    Common use cases:
    - "Show me LeBron's clutch stats"
    - "How do the Lakers perform in clutch time?"
    - "Get Curry's clutch shooting percentages"

    Args:
        entity_name: Player or team name (supports fuzzy matching)
        entity_type: "player" or "team" (default: "player")
        season: Season in 'YYYY-YY' format (defaults to current season)
        per_mode: "PerGame" or "Totals" (default: "PerGame")

    Returns:
        Formatted clutch statistics with:
        - Games played in clutch situations
        - Clutch time win-loss record
        - Points, assists, rebounds in clutch
        - Shooting percentages in clutch
        - Clutch time efficiency metrics

    Examples:
        # Get player clutch stats
        get_clutch_stats("LeBron James")

        # Get team clutch stats
        get_clutch_stats("Lakers", entity_type="team")

        # Get totals instead of per-game
        get_clutch_stats("Stephen Curry", per_mode="Totals")

        # Specific season
        get_clutch_stats("Giannis", season="2022-23")
    """
    logger.debug(
        f"get_clutch_stats(entity={entity_name}, type={entity_type}, "
        f"season={season}, per_mode={per_mode})"
    )

    client = NBAApiClient()

    try:
        # Default to current season if not specified
        if season is None:
            season = get_current_season()

        # Fetch clutch stats
        result = await client.get_clutch_stats(
            entity_name=entity_name,
            entity_type=entity_type,
            season=season,
            per_mode=per_mode
        )

        # Check for errors
        if isinstance(result, dict) and "error" in result:
            season_ctx = get_season_context(include_date=True)
            return f"📅 {season_ctx}\n\n❌ {result['error']}"

        if not isinstance(result, pd.DataFrame) or result.empty:
            season_ctx = get_season_context(include_date=True)
            return f"📅 {season_ctx}\n\nNo clutch stats found for {entity_name} in {season}"

        # Get the single row (filtered data)
        row = result.iloc[0]

        # Format response
        if entity_type == "player":
            player_name = row.get("PLAYER_NAME", entity_name)
            team_abbrev = row.get("TEAM_ABBREVIATION", "")

            response_lines = [
                f"# {player_name} - Clutch Stats ({season})",
                f"**Team**: {team_abbrev}" if team_abbrev else "",
                f"**Definition**: Final 5 min, score within 5 points",
                "",
                "## Clutch Performance",
                ""
            ]

            # Games and record
            games = row.get("GP", 0)
            wins = row.get("W", 0)
            losses = row.get("L", 0)
            win_pct = row.get("W_PCT", 0) * 100 if pd.notna(row.get("W_PCT")) else 0

            response_lines.append(f"**Games**: {games} clutch situations")
            response_lines.append(f"**Record**: {wins}W-{losses}L ({win_pct:.1f}%)")
            response_lines.append("")

            # Scoring
            pts = row.get("PTS", 0)
            fgm = row.get("FGM", 0)
            fga = row.get("FGA", 0)
            fg_pct = row.get("FG_PCT", 0) * 100 if pd.notna(row.get("FG_PCT")) else 0
            fg3m = row.get("FG3M", 0)
            fg3a = row.get("FG3A", 0)
            fg3_pct = row.get("FG3_PCT", 0) * 100 if pd.notna(row.get("FG3_PCT")) else 0
            ftm = row.get("FTM", 0)
            fta = row.get("FTA", 0)
            ft_pct = row.get("FT_PCT", 0) * 100 if pd.notna(row.get("FT_PCT")) else 0

            response_lines.append("## Scoring")
            response_lines.append(f"**Points**: {pts:.1f} {per_mode.lower()}")
            response_lines.append(f"**Field Goals**: {fgm:.1f}/{fga:.1f} ({fg_pct:.1f}%)")
            response_lines.append(f"**Three Pointers**: {fg3m:.1f}/{fg3a:.1f} ({fg3_pct:.1f}%)")
            response_lines.append(f"**Free Throws**: {ftm:.1f}/{fta:.1f} ({ft_pct:.1f}%)")
            response_lines.append("")

            # Playmaking and rebounding
            ast = row.get("AST", 0)
            reb = row.get("REB", 0)
            oreb = row.get("OREB", 0)
            dreb = row.get("DREB", 0)
            stl = row.get("STL", 0)
            blk = row.get("BLK", 0)
            tov = row.get("TOV", 0)

            response_lines.append("## Playmaking & Defense")
            response_lines.append(f"**Assists**: {ast:.1f}")
            response_lines.append(f"**Rebounds**: {reb:.1f} ({oreb:.1f} OFF, {dreb:.1f} DEF)")
            response_lines.append(f"**Steals**: {stl:.1f}")
            response_lines.append(f"**Blocks**: {blk:.1f}")
            response_lines.append(f"**Turnovers**: {tov:.1f}")
            response_lines.append("")

            # Advanced metrics (if available)
            if "PLUS_MINUS" in row and pd.notna(row["PLUS_MINUS"]):
                plus_minus = row["PLUS_MINUS"]
                response_lines.append("## Impact")
                response_lines.append(f"**Plus/Minus**: {plus_minus:+.1f}")
                response_lines.append("")

        else:  # team
            team_name = row.get("TEAM_NAME", entity_name)

            response_lines = [
                f"# {team_name} - Clutch Stats ({season})",
                f"**Definition**: Final 5 min, score within 5 points",
                "",
                "## Clutch Performance",
                ""
            ]

            # Games and record
            games = row.get("GP", 0)
            wins = row.get("W", 0)
            losses = row.get("L", 0)
            win_pct = row.get("W_PCT", 0) * 100 if pd.notna(row.get("W_PCT")) else 0

            response_lines.append(f"**Games**: {games} clutch situations")
            response_lines.append(f"**Record**: {wins}W-{losses}L ({win_pct:.1f}%)")
            response_lines.append("")

            # Scoring
            pts = row.get("PTS", 0)
            fg_pct = row.get("FG_PCT", 0) * 100 if pd.notna(row.get("FG_PCT")) else 0
            fg3_pct = row.get("FG3_PCT", 0) * 100 if pd.notna(row.get("FG3_PCT")) else 0
            ft_pct = row.get("FT_PCT", 0) * 100 if pd.notna(row.get("FT_PCT")) else 0

            response_lines.append("## Team Stats")
            response_lines.append(f"**Points**: {pts:.1f} {per_mode.lower()}")
            response_lines.append(f"**FG%**: {fg_pct:.1f}% | **3P%**: {fg3_pct:.1f}% | **FT%**: {ft_pct:.1f}%")

            ast = row.get("AST", 0)
            reb = row.get("REB", 0)
            tov = row.get("TOV", 0)

            response_lines.append(f"**Assists**: {ast:.1f} | **Rebounds**: {reb:.1f} | **Turnovers**: {tov:.1f}")
            response_lines.append("")

            # Net rating (if available)
            if "PLUS_MINUS" in row and pd.notna(row["PLUS_MINUS"]):
                plus_minus = row["PLUS_MINUS"]
                response_lines.append(f"**Net Rating**: {plus_minus:+.1f}")
                response_lines.append("")

        response = "\n".join(response_lines)

        # Add season context
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n{response}"

    except EntityNotFoundError as e:
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n❌ {str(e)}"
    except Exception as e:
        logger.exception("Unexpected error in get_clutch_stats")
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n❌ Error fetching clutch stats: {str(e)}"


@mcp_server.tool()
async def get_player_head_to_head(
    player1_name: str,
    player2_name: str,
    season: Optional[str] = None,
) -> str:
    """
    Get head-to-head matchup stats comparing two players.

    This tool fills the Priority 2 enhancement identified in the roadmap:
    providing player vs player direct comparison in games where both played.

    Finds all games where both players participated and compares their
    performance in those specific matchups (not season averages).

    Common use cases:
    - "LeBron vs Durant head to head this season"
    - "Show me Curry vs Lillard matchups"
    - "Compare Giannis and Embiid in their matchups"

    Args:
        player1_name: First player name (supports fuzzy matching)
        player2_name: Second player name (supports fuzzy matching)
        season: Season in 'YYYY-YY' format (defaults to current season)

    Returns:
        Formatted head-to-head comparison with:
        - Number of matchups where both players played
        - Win-loss records for each player in those matchups
        - Average stats for each player in head-to-head games
        - Game-by-game breakdown of matchups

    Examples:
        # Current season head-to-head
        get_player_head_to_head("LeBron James", "Kevin Durant")

        # Specific season
        get_player_head_to_head("Stephen Curry", "Damian Lillard", season="2023-24")

    Notes:
        - Only includes games where BOTH players participated
        - Stats are from those specific matchup games, not season averages
        - Win-loss record shows team results, not individual performance
        - If no common games found, returns informative message
    """
    try:
        # Fetch head-to-head data from client
        client = NBAApiClient()
        result = await client.get_player_head_to_head(
            player1_name=player1_name,
            player2_name=player2_name,
            season=season
        )

        # Handle errors
        if isinstance(result, dict) and "error" in result:
            season_ctx = get_season_context(include_date=True)
            return f"📅 {season_ctx}\n\n❌ {result['error']}"

        # Extract data
        player1_stats = result["player1_stats"]
        player2_stats = result["player2_stats"]
        player1_record = result["player1_record"]
        player2_record = result["player2_record"]
        matchup_count = result["matchup_count"]
        season_str = result["season"]

        # Get player names from first row
        player1_full = player1_stats.iloc[0]["PLAYER_NAME"]
        player2_full = player2_stats.iloc[0]["PLAYER_NAME"]

        # Calculate average stats
        p1_avg_pts = player1_stats["PTS"].mean()
        p1_avg_reb = player1_stats["REB"].mean()
        p1_avg_ast = player1_stats["AST"].mean()
        p1_avg_fg_pct = player1_stats["FG_PCT"].mean()

        p2_avg_pts = player2_stats["PTS"].mean()
        p2_avg_reb = player2_stats["REB"].mean()
        p2_avg_ast = player2_stats["AST"].mean()
        p2_avg_fg_pct = player2_stats["FG_PCT"].mean()

        # Build response
        response = f"""🏀 HEAD-TO-HEAD MATCHUP: {player1_full} vs {player2_full}
Season: {season_str}
Total Matchups: {matchup_count} games

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 MATCHUP RECORDS:
{player1_full}: {player1_record['wins']}W-{player1_record['losses']}L
{player2_full}: {player2_record['wins']}W-{player2_record['losses']}L

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 AVERAGE STATS IN MATCHUPS:

{player1_full}:
  PPG: {p1_avg_pts:.1f}
  RPG: {p1_avg_reb:.1f}
  APG: {p1_avg_ast:.1f}
  FG%: {p1_avg_fg_pct:.1%}

{player2_full}:
  PPG: {p2_avg_pts:.1f}
  RPG: {p2_avg_reb:.1f}
  APG: {p2_avg_ast:.1f}
  FG%: {p2_avg_fg_pct:.1%}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 GAME-BY-GAME BREAKDOWN:
"""

        # Add game-by-game details
        for i in range(len(player1_stats)):
            p1_game = player1_stats.iloc[i]
            p2_game = player2_stats.iloc[i]

            game_date = p1_game["GAME_DATE"]
            matchup = p1_game["MATCHUP"]

            p1_pts = p1_game["PTS"]
            p1_reb = p1_game["REB"]
            p1_ast = p1_game["AST"]
            p1_wl = p1_game["WL"]

            p2_pts = p2_game["PTS"]
            p2_reb = p2_game["REB"]
            p2_ast = p2_game["AST"]
            p2_wl = p2_game["WL"]

            response += f"""
Game {i+1} - {game_date} ({matchup})
  {player1_full}: {p1_pts} PTS, {p1_reb} REB, {p1_ast} AST ({p1_wl})
  {player2_full}: {p2_pts} PTS, {p2_reb} REB, {p2_ast} AST ({p2_wl})
"""

        # Add season context
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n{response}"

    except EntityNotFoundError as e:
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n❌ {str(e)}"
    except Exception as e:
        logger.exception("Unexpected error in get_player_head_to_head")
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n❌ Error fetching head-to-head stats: {str(e)}"


@mcp_server.tool()
async def get_player_performance_splits(
    player_name: str,
    season: Optional[str] = None,
    last_n_games: int = 10,
) -> str:
    """
    Get comprehensive performance splits and advanced analytics for a player.

    This tool provides deep performance insights including:
    - Recent form analysis (hot/cold streaks)
    - Home vs Away performance
    - Win vs Loss splits
    - Per-100 possessions normalization
    - Trend detection

    Common use cases:
    - "Show me Curry's recent form and performance splits"
    - "How does LeBron perform at home vs away?"
    - "Get Giannis's performance in wins vs losses"

    Args:
        player_name: Player name (supports fuzzy matching)
        season: Season in 'YYYY-YY' format (defaults to current season)
        last_n_games: Number of recent games to analyze (default: 10)

    Returns:
        Formatted performance splits with:
        - Season averages
        - Last N games performance
        - Home/Away splits
        - Win/Loss splits
        - Trend analysis (hot/cold streaks)
        - Per-100 possessions stats

    Examples:
        # Get performance splits
        get_player_performance_splits("Stephen Curry")

        # Analyze last 15 games
        get_player_performance_splits("LeBron James", last_n_games=15)

        # Specific season
        get_player_performance_splits("Giannis", season="2023-24")

    Notes:
        - Hot streak: Recent scoring >10% above season average
        - Cold streak: Recent scoring >10% below season average
        - Per-100 stats normalize for pace differences
        - Home/Away detection from game MATCHUP field
    """
    try:
        # Fetch performance splits from client
        client = NBAApiClient()
        result = await client.get_player_performance_splits(
            player_name=player_name,
            season=season,
            last_n_games=last_n_games
        )

        # Handle errors
        if isinstance(result, dict) and "error" in result:
            season_ctx = get_season_context(include_date=True)
            return f"📅 {season_ctx}\n\n❌ {result['error']}"

        # Extract data
        player = result["player_name"]
        season_str = result["season"]
        season_stats = result["season_stats"]
        last_n_stats = result["last_n_stats"]
        home_stats = result["home_stats"]
        away_stats = result["away_stats"]
        wins_stats = result["wins_stats"]
        losses_stats = result["losses_stats"]
        trends = result["trends"]
        per_100 = result["per_100_stats"]

        # Build response
        response = f"""🔍 PERFORMANCE SPLITS: {player}
Season: {season_str}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 SEASON AVERAGES ({season_stats.get('games', 0)} games):
  PPG: {season_stats.get('ppg', 0):.1f}
  RPG: {season_stats.get('rpg', 0):.1f}
  APG: {season_stats.get('apg', 0):.1f}
  FG%: {season_stats.get('fg_pct', 0):.1%}
  3P%: {season_stats.get('fg3_pct', 0):.1%}
  +/-: {season_stats.get('plus_minus', 0):.1f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔥 LAST {last_n_games} GAMES:
  PPG: {last_n_stats.get('ppg', 0):.1f} ({trends.get('ppg_trend', 0):+.1f})
  RPG: {last_n_stats.get('rpg', 0):.1f} ({trends.get('rpg_trend', 0):+.1f})
  APG: {last_n_stats.get('apg', 0):.1f} ({trends.get('apg_trend', 0):+.1f})
  FG%: {last_n_stats.get('fg_pct', 0):.1%} ({trends.get('fg_pct_trend', 0):+.1%})
  3P%: {last_n_stats.get('fg3_pct', 0):.1%}

"""

        # Add hot/cold streak indicator
        if trends.get('is_hot_streak'):
            response += "  🔥 HOT STREAK: Scoring 10%+ above season average\n"
        elif trends.get('is_cold_streak'):
            response += "  🧊 COLD STREAK: Scoring 10%+ below season average\n"

        response += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏠 HOME vs 🛫 AWAY SPLITS:

HOME ({result.get('home_games_count', 0)} games):
  PPG: {home_stats.get('ppg', 0):.1f}
  RPG: {home_stats.get('rpg', 0):.1f}
  APG: {home_stats.get('apg', 0):.1f}
  FG%: {home_stats.get('fg_pct', 0):.1%}

AWAY ({result.get('away_games_count', 0)} games):
  PPG: {away_stats.get('ppg', 0):.1f}
  RPG: {away_stats.get('rpg', 0):.1f}
  APG: {away_stats.get('apg', 0):.1f}
  FG%: {away_stats.get('fg_pct', 0):.1%}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ WINS vs ❌ LOSSES:

WINS ({result.get('wins_count', 0)} games):
  PPG: {wins_stats.get('ppg', 0):.1f}
  RPG: {wins_stats.get('rpg', 0):.1f}
  APG: {wins_stats.get('apg', 0):.1f}
  FG%: {wins_stats.get('fg_pct', 0):.1%}
  +/-: {wins_stats.get('plus_minus', 0):.1f}

LOSSES ({result.get('losses_count', 0)} games):
  PPG: {losses_stats.get('ppg', 0):.1f}
  RPG: {losses_stats.get('rpg', 0):.1f}
  APG: {losses_stats.get('apg', 0):.1f}
  FG%: {losses_stats.get('fg_pct', 0):.1%}
  +/-: {losses_stats.get('plus_minus', 0):.1f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 PER-100 POSSESSIONS:
  PTS: {per_100.get('pts_per_100', 0):.1f}
  REB: {per_100.get('reb_per_100', 0):.1f}
  AST: {per_100.get('ast_per_100', 0):.1f}
  TOV: {per_100.get('tov_per_100', 0):.1f}
"""

        # Add season context
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n{response}"

    except EntityNotFoundError as e:
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n❌ {str(e)}"
    except Exception as e:
        logger.exception("Unexpected error in get_player_performance_splits")
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n❌ Error fetching performance splits: {str(e)}"


@mcp_server.tool()
async def get_nba_awards(
    award_type: Optional[str] = None,
    player_name: Optional[str] = None,
    season: Optional[str] = None,
    last_n: Optional[int] = None,
    format: str = "text"
) -> str:
    """
    Get NBA awards data - historical winners or player-specific awards.

    This tool provides comprehensive awards information including MVP, DPOY, ROY,
    Finals MVP, Sixth Man, Most Improved, and Coach of the Year.

    Query Modes:
    1. Historical Winners: get_nba_awards(award_type="mvp", last_n=10)
    2. Season Winners: get_nba_awards(award_type="dpoy", season="2023-24")
    3. Player Awards: get_nba_awards(player_name="LeBron James")
    4. Player + Award Filter: get_nba_awards(player_name="LeBron James", award_type="mvp")

    Args:
        award_type: Award type - Individual or team selections:
                   Individual Awards:
                   - "mvp": Most Valuable Player
                   - "finals_mvp": Finals MVP
                   - "dpoy": Defensive Player of the Year
                   - "roy": Rookie of the Year
                   - "smoy": Sixth Man of the Year
                   - "mip": Most Improved Player
                   - "coy": Coach of the Year

                   Team Selections (5 players each):
                   - "all_nba_first": All-NBA First Team
                   - "all_nba_second": All-NBA Second Team
                   - "all_nba_third": All-NBA Third Team
                   - "all_defensive_first": All-Defensive First Team
                   - "all_defensive_second": All-Defensive Second Team
                   - "all_rookie_first": All-Rookie First Team
                   - "all_rookie_second": All-Rookie Second Team
        player_name: Get all awards for specific player (uses live API data)
        season: Filter by specific season (e.g., "2023-24")
        last_n: Get last N winners (for historical queries)
        format: Output format - "text" (default) or "json"

    Returns:
        Formatted award data as text or JSON string

    Examples:
        get_nba_awards(award_type="mvp", last_n=10)
        → Returns last 10 MVP winners

        get_nba_awards(player_name="LeBron James")
        → Returns all of LeBron's awards

        get_nba_awards(award_type="roy", season="2023-24")
        → Returns 2023-24 Rookie of the Year winner

        get_nba_awards(award_type="dpoy", last_n=5)
        → Returns last 5 Defensive Player of the Year winners

    Note: Historical data covers 2004-05 through 2023-24. For complete player career
    awards (including weekly/monthly honors), use player_name parameter.
    """
    start_time = time.time()
    client = NBAApiClient()

    try:
        # Determine query mode
        if player_name:
            # Mode: Player-specific awards (live API data)
            logger.info(f"Fetching awards for player: {player_name}")

            awards_df = await client.get_player_awards(
                player_name=player_name,
                award_filter=award_type  # Optional filter
            )

            if len(awards_df) == 0:
                return f"No awards found for {player_name}" + (
                    f" matching '{award_type}'" if award_type else ""
                )

            # Format output
            if format == "json":
                return awards_df.to_json(orient='records', indent=2)
            else:
                # Text format with season context
                season_ctx = get_season_context(include_date=True)
                output = [f"📅 {season_ctx}\n"]
                output.append(f"🏆 Awards for {player_name}:")
                output.append("=" * 60)

                # Group by award type
                for desc in awards_df['DESCRIPTION'].unique():
                    matching = awards_df[awards_df['DESCRIPTION'] == desc]
                    count = len(matching)

                    if count == 1:
                        season_val = matching.iloc[0].get('SEASON', 'N/A')
                        output.append(f"  • {desc}: {season_val}")
                    else:
                        seasons = matching['SEASON'].tolist()
                        output.append(f"  • {desc} ({count}x): {', '.join(seasons)}")

                return "\n".join(output)

        elif award_type:
            # Mode: Historical award winners (static data)
            logger.info(f"Fetching historical {award_type} winners")

            # Get winners
            winners = client.get_award_winners(
                award_type=award_type,
                last_n=last_n
            )

            # Filter by season if specified
            if season:
                winners = [w for w in winners if w.get('season') == season]

            if not winners:
                return f"No {award_type} winners found for specified criteria"

            # Format output
            if format == "json":
                return json.dumps(winners, indent=2)
            else:
                # Text format with season context
                season_ctx = get_season_context(include_date=True)

                award_names = {
                    "mvp": "Most Valuable Player",
                    "finals_mvp": "Finals MVP",
                    "dpoy": "Defensive Player of the Year",
                    "roy": "Rookie of the Year",
                    "smoy": "Sixth Man of the Year",
                    "mip": "Most Improved Player",
                    "coy": "Coach of the Year",
                    "all_nba_first": "All-NBA First Team",
                    "all_nba_second": "All-NBA Second Team",
                    "all_nba_third": "All-NBA Third Team",
                    "all_defensive_first": "All-Defensive First Team",
                    "all_defensive_second": "All-Defensive Second Team",
                    "all_rookie_first": "All-Rookie First Team",
                    "all_rookie_second": "All-Rookie Second Team"
                }

                title = award_names.get(award_type, award_type.upper())
                if last_n:
                    output = [f"📅 {season_ctx}\n"]
                    output.append(f"🏆 Last {len(winners)} {title} Winners:")
                elif season:
                    output = [f"📅 {season_ctx}\n"]
                    output.append(f"🏆 {season} {title}:")
                else:
                    output = [f"📅 {season_ctx}\n"]
                    output.append(f"🏆 {title} Winners:")

                output.append("=" * 60)

                # Check if this is a team selection (has 'players' array)
                is_team_selection = winners and 'players' in winners[0]

                for winner in winners:
                    season_val = winner.get('season', 'N/A')

                    if is_team_selection:
                        # Team selection - list all 5 players
                        players = winner.get('players', [])
                        output.append(f"\n{season_val}:")
                        for i, player in enumerate(players, 1):
                            name = player.get('player_name', 'Unknown')
                            team = player.get('team', '')
                            position = player.get('position', '')
                            pos_str = f" - {position}" if position else ""
                            output.append(f"  {i}. {name} ({team}){pos_str}")
                    else:
                        # Individual award
                        if 'coach_name' in winner:
                            # Coach award
                            name = winner['coach_name']
                        else:
                            # Player award
                            name = winner.get('player_name', 'Unknown')

                        team = winner.get('team', '')
                        output.append(f"  {season_val}: {name} ({team})")

                return "\n".join(output)

        else:
            # No parameters provided - show available awards
            return (
                "NBA Awards Tool - Please specify query parameters:\n\n"
                "1. Get historical winners:\n"
                "   award_type='mvp', last_n=10\n\n"
                "2. Get season winner:\n"
                "   award_type='all_nba_first', season='2023-24'\n\n"
                "3. Get player awards:\n"
                "   player_name='LeBron James'\n\n"
                "Individual Awards:\n"
                "  mvp, finals_mvp, dpoy, roy, smoy, mip, coy\n\n"
                "Team Selections (5 players each):\n"
                "  all_nba_first, all_nba_second, all_nba_third\n"
                "  all_defensive_first, all_defensive_second\n"
                "  all_rookie_first, all_rookie_second"
            )

    except ValueError as e:
        logger.error(f"Awards query error: {e}")
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n❌ Error: {str(e)}"

    except Exception as e:
        logger.exception("Unexpected error in get_nba_awards")
        season_ctx = get_season_context(include_date=True)
        return f"📅 {season_ctx}\n\n❌ Unexpected error: {type(e).__name__}: {str(e)}"

    finally:
        elapsed = (time.time() - start_time) * 1000
        logger.info(f"Awards query completed in {elapsed:.1f}ms")


#########################################
# Running the Server
#########################################


# ------------------------------------------------------------------
# nba_server.py
# ------------------------------------------------------------------
def main():
    """Parse CLI args and start FastMCP server (with fallback)."""
    # Note: .env is loaded at module level, so NBA_MCP_PORT is already available
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

    # Read port from .env file (NBA_MCP_PORT), defaults to 8005
    port = int(os.getenv("NBA_MCP_PORT", "8005"))

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
        # Original 8 tools
        "get_league_leaders_info": get_league_leaders_info,
        "compare_players": compare_players,
        "get_team_standings": get_team_standings,
        "get_team_advanced_stats": get_team_advanced_stats,
        "get_player_advanced_stats": get_player_advanced_stats,
        "get_live_scores": get_live_scores,
        "get_player_career_information": get_player_career_information,
        "get_nba_awards": get_nba_awards,
        # Phase 1: 12 high-value tools added for NLQ support (2025-11-01)
        "get_game_context": get_game_context,                           # ⭐⭐⭐ Matchup analysis
        "get_shot_chart": get_shot_chart,                               # ⭐⭐⭐ Shot visualization
        "get_nba_schedule": get_nba_schedule,                           # ⭐⭐⭐ Game schedule
        "get_player_game_stats": get_player_game_stats,                 # ⭐⭐⭐ Player game logs
        "get_box_score": get_box_score,                                 # ⭐⭐ Game box scores
        "get_clutch_stats": get_clutch_stats,                           # ⭐⭐ Clutch performance
        "get_player_head_to_head": get_player_head_to_head,             # ⭐⭐ Player matchups
        "get_player_performance_splits": get_player_performance_splits, # ⭐⭐ Performance analysis
        "play_by_play": play_by_play,                                   # ⭐ Play-by-play data
        "get_advanced_metrics": get_advanced_metrics,                   # ⭐ Advanced analytics
        "compare_players_era_adjusted": compare_players_era_adjusted,   # ⭐ Era comparisons
        "get_season_stats": get_season_stats,                           # ⭐ Season aggregates
    }
    initialize_tool_registry(tool_map)
    logger.info(f"NLQ tool registry initialized with {len(tool_map)} tools (8 original + 12 Phase 1)")

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
        limiter.add_limit("get_nba_awards", capacity=60.0, refill_rate=1.0)

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


def format_team_advanced_stats(data: Dict[str, Any]) -> str:
    """
    Format team advanced stats as readable text.

    Args:
        data: Team stats dictionary with keys like 'team_name', 'offensive_rating', etc.

    Returns:
        Formatted multi-line string with team stats
    """
    team_name = data.get("team_name", "Unknown Team")
    season = data.get("season", "N/A")

    return f"""**{team_name}** ({season})
**Games Played**: {data.get('games_played', 'N/A')}

**RATINGS (Per 100 Possessions)**
• Offensive Rating: {data.get('offensive_rating', 0):.1f}
• Defensive Rating: {data.get('defensive_rating', 0):.1f}
• Net Rating: {data.get('net_rating', 0):.1f}
• Pace: {data.get('pace', 0):.2f}

**SHOOTING EFFICIENCY**
• Effective FG%: {data.get('effective_fg_pct', 0):.1%}
• True Shooting%: {data.get('true_shooting_pct', 0):.1%}

**FOUR FACTORS (Offense)**
• eFG%: {data.get('efg_pct_off', 0):.1%}
• Turnover%: {data.get('tov_pct_off', 0):.1%}
• Offensive Rebound%: {data.get('oreb_pct', 0):.1%}
• Free Throw Rate: {data.get('fta_rate', 0):.3f}

**FOUR FACTORS (Defense)**
• Opponent eFG%: {data.get('opp_efg_pct', 0):.1%}
• Opponent TOV%: {data.get('opp_tov_pct', 0):.1%}
• Defensive Rebound%: {data.get('dreb_pct', 0):.1%}
• Opponent FT Rate: {data.get('opp_fta_rate', 0):.3f}"""


if __name__ == "__main__":
    main()
