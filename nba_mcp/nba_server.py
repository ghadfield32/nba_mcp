#nba_mcp\nba_server.py
import os
from mcp.server.fastmcp import FastMCP
from nba_mcp.api.client import NBAApiClient
import sys
import traceback
from datetime import datetime, timezone, date
from typing import Optional, List, Dict, Union, Any
import pandas as pd
from nba_api.stats.static import teams, players
from nba_mcp.api.tools.nba_api_utils import (get_player_id, get_team_id, get_team_name, get_player_name
                           , get_static_lookup_schema, normalize_stat_category, normalize_per_mode, normalize_season, normalize_date, format_game
                           )
import json
# nba_server.py (add near the top)
from pydantic import BaseModel, Field
# near the top of nba_server.py
import argparse
from fastmcp import Context

# only grab “--mode” here and ignore any other flags
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument(
    "--mode", choices=["claude", "local"], default="claude",
    help="Which port profile to use"
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
HOST      = os.getenv("FASTMCP_SSE_HOST", "0.0.0.0")
PATH      = os.getenv("FASTMCP_SSE_PATH", "/sse")

# ── 2) Create the global server instance for decorator registration ──
mcp_server = FastMCP(
    name="nba_mcp",
    host=HOST,
    port=BASE_PORT,
    path=PATH
)

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





from pydantic import BaseModel, Field
from typing import Literal

class LeagueLeadersParams(BaseModel):
    season: Optional[Union[str, List[str]]] = Field(
        None,
        description="Season in 'YYYY-YY' format or list thereof"
    )
    stat_category: Literal["PTS","REB","AST","STL","BLK","FG_PCT","FG3_PCT","FT_PCT"] = Field(
        ...,
        description="Stat code (e.g. 'AST')"
    )
    per_mode: Literal["Totals","PerGame","Per48"] = Field(
        ...,
        description="One of 'Totals', 'PerGame', or 'Per48'"
    )




# ── 3) Load & cache both JSON files once ───────────────────
from pathlib import Path

# Possible locations for documentation files:
_project_root = Path(__file__).resolve().parents[1]
_root_docs    = _project_root / "api_documentation"
_pkg_docs     = Path(__file__).resolve().parent / "api_documentation"

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
        "Failed to load %s from either %s or %s",
        filename, _root_docs, _pkg_docs
    )
    sys.exit(1)

_CACHED_OPENAPI = _load_cached("endpoints.json")
_CACHED_STATIC  = _load_cached("static_data.json")



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
    result = await client.get_player_career_stats(player_name, season, as_dataframe=False)
    # If error came back as dict, re‑raise it to the client
    if isinstance(result, dict) and "error" in result:
        return result
    # If a friendlier message string came back, wrap it
    if isinstance(result, str):
        return {"message": result}
    # Otherwise it's already a list of dicts
    return {"data": result}

@mcp_server.resource("nba://league/leaders/{stat_category}/{per_mode}/{season}")
async def league_leaders_resource(
    stat_category: str, per_mode: str, season: str
):
    """
    Returns top-10 league leaders as JSON for given season, stat_category, per_mode.
    """
    client = NBAApiClient()
    data = await client.get_league_leaders(
        season=season,
        stat_category=stat_category,
        per_mode=per_mode,
        as_dataframe=False
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
        target_date=target_date,
        as_dataframe=False
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
    data = await client.get_games_by_date(
        target_date=game_date,
        as_dataframe=False
    )
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
    max_lines: int = 200
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
        max_lines=max_lines
    )
    return {"markdown": md}



#########################################
# MCP Tools
#########################################

@mcp_server.tool()
async def get_player_career_information(
    player_name: str,
    season: Optional[str] = None
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
            logger.error(
                "Unexpected payload type (not DataFrame): %s", type(result)
            )
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
            team = row.get('TEAM_ABBREVIATION', 'N/A')
            return "\n".join([
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
                f"Free Throw %: {row.get('FT_PCT', 'N/A')}"
            ])
        else:
            # Multiple seasons - provide a career summary
            # Find the earliest and latest seasons
            if 'SEASON_ID' in df.columns:
                seasons = sorted(df['SEASON_ID'].unique())
                season_range = f"{seasons[0]} to {seasons[-1]}" if seasons else "unknown"
            else:
                season_range = "unknown"
                
            # Count total games and calculate career averages
            total_games = df['GP'].sum() if 'GP' in df.columns else 'N/A'
            
            # Build response with career averages
            return "\n".join([
                f"Player: {player_name}",
                f"Seasons: {season_range}",
                f"Career Games: {total_games}",
                f"Career Stats:",
                f"- Points Per Game: {df['PTS'].mean():.1f}" if 'PTS' in df.columns else "- Points Per Game: N/A",
                f"- Rebounds Per Game: {df['REB'].mean():.1f}" if 'REB' in df.columns else "- Rebounds Per Game: N/A",
                f"- Assists Per Game: {df['AST'].mean():.1f}" if 'AST' in df.columns else "- Assists Per Game: N/A", 
                f"- Field Goal %: {df['FG_PCT'].mean():.3f}" if 'FG_PCT' in df.columns else "- Field Goal %: N/A",
                f"- 3-Point %: {df['FG3_PCT'].mean():.3f}" if 'FG3_PCT' in df.columns else "- 3-Point %: N/A",
                f"- Free Throw %: {df['FT_PCT'].mean():.3f}" if 'FT_PCT' in df.columns else "- Free Throw %: N/A"
            ])

    except Exception as e:
        # 7) Uncaught exception: log full traceback
        logger.exception("Unexpected error in get_player_career_information")
        return f"Unexpected error in get_player_career_information: {e}"






@mcp_server.tool()
async def get_league_leaders_info(params: LeagueLeadersParams) -> str:
    """
    Get the top-10 league leaders for the requested stat(s) and mode(s).
    Inputs are validated and coerced via LeagueLeadersParams.
    """
    # 1) Extract and normalize already-validated inputs
    season       = params.season
    stat_category = params.stat_category
    per_mode      = params.per_mode

    logger.debug(
        "get_league_leaders_info(params=%r)", params.dict()
    )

    client = NBAApiClient()
    result = await client.get_league_leaders(
        season=season,
        stat_category=stat_category,
        per_mode=per_mode,
        as_dataframe=True
    )

    if isinstance(result, str):
        return result

    df: pd.DataFrame = result
    if df.empty:
        return f"No leaders found for '{stat_category}' in season(s) {season}."

    out = []
    for s, grp in df.groupby("SEASON"):
        out.append(f"Top 10 {stat_category} Leaders ({s}):")
        for i, (_, r) in enumerate(grp.head(10).iterrows(), 1):
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
    # Normalize date or default to today
    if not target_date:
        target_date = datetime.now().strftime("%Y-%m-%d")

    try:
        result = await client.get_live_scoreboard(
            target_date=target_date,
            as_dataframe=False
        )
        # result is either a list of dicts or an error string
        if isinstance(result, str):
            return result

        games = result  # list of game dicts
        if not games:
            return f"No games found for {target_date}."

        # Format each into "Lakers vs Suns – 102-99 (Final)"
        lines = []
        for g in games:
            summary = g.get("scoreBoardSummary") or g.get("scoreBoardSnapshot")
            home = summary["homeTeam"]
            away = summary["awayTeam"]

            # Real‑time if the live‑API gave us `teamName`+`score`
            if "teamName" in home:
                home_team = home["teamName"]
                away_team = away["teamName"]
                home_pts  = home["score"]
                away_pts  = away["score"]
            else:
                # Historical if we got uppercase keys from Stats API
                home_team = home.get("TEAM_ABBREVIATION") or get_team_name(home["TEAM_ID"])
                away_team = away.get("TEAM_ABBREVIATION") or get_team_name(away["TEAM_ID"])
                home_pts  = home.get("PTS")
                away_pts  = away.get("PTS")

            status = summary.get("gameStatusText", "")
            lines.append(f"{home_team} vs {away_team} – {home_pts}-{away_pts} ({status})")

        header = f"NBA Games for {target_date}:\n"
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
    "All-Star"
]

@mcp_server.tool()
async def get_date_range_game_log_or_team_game_log(
    season: str,
    team: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> str:
    logger.debug(
        "get_date_range_game_log_or_team_game_log(season=%r, team=%r, from=%r, to=%r)",
        season, team, date_from, date_to
    )

    client = NBAApiClient()
    lines: List[str] = []
    start = date_from or "season start"
    end = date_to or "season end"

    try:
        for st in _ALLOWED_SEASON_TYPES:
            df = await client.get_league_game_log(
                season=season, team_name=team,
                season_type=st, date_from=date_from,
                date_to=date_to, as_dataframe=True
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
    max_lines: int = 200
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
                max_lines=max_lines
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
        max_lines=max_lines
    )
    if isinstance(md, str):
        return md
    return json.dumps(md, indent=2)






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
        help="Which port profile to use"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "websocket"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="MCP transport to use"
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MCP_HOST", "127.0.0.1"),
        help="Host to bind for SSE/WebSocket"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "0")) or None,
        help="Port for SSE/WebSocket (None for stdio)"
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
            logger.info("Starting FastMCP server on %s://%s:%s",
                        transport, host, port)
            mcp.run(transport=transport)
    except Exception:
        logger.exception("Failed to start MCP server (transport=%s)", transport)
        sys.exit(1)

if __name__ == "__main__":
    main()
