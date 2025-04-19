#nba_server.py
import os
from mcp.server.fastmcp import FastMCP
from nba_mcp.api.client import NBAApiClient
import sys
import traceback
from datetime import datetime, timezone
from typing import Optional, List, Dict, Union
import pandas as pd
from nba_api.stats.static import teams, players
from nba_mcp.api.tools.nba_api_utils import (get_player_id, get_team_id, get_team_name, get_player_name
                           , get_static_lookup_schema, normalize_stat_category, normalize_per_mode, normalize_season, normalize_date, format_game
                           )
import json
# nba_server.py (add near the top)
from pydantic import BaseModel, Field
# import logger
import logging
logger = logging.getLogger(__name__)


# ── 1) Read configuration up‑front ────────────────────────
HOST      = os.getenv("FASTMCP_SSE_HOST", "0.0.0.0")
BASE_PORT = int(os.getenv("NBA_MCP_PORT", os.getenv("FASTMCP_SSE_PORT", "8000")))
PATH      = os.getenv("FASTMCP_SSE_PATH", "/sse")

# ── 2) Create the global server instance for decorator registration ──
mcp_server = FastMCP(
    name="nba_mcp",
    host=HOST,
    port=BASE_PORT,
    path=PATH
)


import socket

def port_available(port: int, host: str = HOST) -> bool:
    """
    Return True if no other process is listening on (host, port).
    We set SO_REUSEADDR so that ports in TIME_WAIT on Windows are
    treated as unavailable—just like the real server socket.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        # Mirror Uvicorn's reuse flags on Windows
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


from fastmcp.prompts.base import UserMessage, AssistantMessage

@mcp_server.prompt()
def ask_review(code_snippet: str) -> str:
    """Generates a standard code review request."""
    return f"Please review the following code snippet for potential bugs and style issues:\n```python\n{code_snippet}\n```"

@mcp_server.prompt()
def debug_session_start(error_message: str) -> list[Message]:
    """Initiates a debugging help session."""
    return [
        UserMessage(f"I encountered an error:\n{error_message}"),
        AssistantMessage("Okay, I can help with that. Can you provide the full traceback and tell me what you were trying to do?")
    ]

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
async def play_by_play_info_for_current_games() -> str:
    """
    Only for Live Games, get the current NBA games and their play-by-play data.
    """
    client = NBAApiClient()
    games_df = await client.get_today_games(as_dataframe=True)

    # ── guardrails ──────────────────────────────────────────────
    if isinstance(games_df, str):
        return games_df
    if not isinstance(games_df, pd.DataFrame) or games_df.empty:
        return "No NBA games scheduled today."

    all_payloads = []
    for _, row in games_df.iterrows():
        gid = row["gameId"]
        result = await client.get_game_stream(gid)
        if isinstance(result, str):
            # error for this game
            all_payloads.append({ "gameId": gid, "error": result })
        else:
            all_payloads.append(result)

    # one big combined JSON
    combined = {
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "games": all_payloads
    }
    return json.dumps(combined, indent=2)

@mcp_server.tool()
async def get_past_play_by_play(
    game_id: Optional[str] = None,
    game_date: Optional[str] = None,
    team: Optional[str] = None,
    start_period: int = 1,
    end_period: int = 4,
    start_clock: Optional[str] = None
) -> str:
    """
    MCP tool: Retrieve historical play‑by‑play for a given game.

    You must supply **either**:
      • `game_id` (10‑digit NBA game code), or
      • both `game_date` (YYYY‑MM‑DD) and `team` (full or partial name/abbreviation).

    **start_period** (default `1`) accepts any of the following, all normalized to an integer 1–4:
      • Integers: `1`, `2`, `3`, `4`
      • Ordinal/cardinal text: `"1st"`, `"2nd"`, `"third quarter"`, `"Quarter 4"`, `"Q3"`, etc.
      • Written words: `"one"`, `"two"`, `"three"`, `"fourth"`

    **start_clock** (default `None`) accepts any of the following, all normalized to `"MM:SS"`:
      • Colon or dot notation: `"7:15"`, `"7.15"`
      • Minutes only: `"7 m"`, `"7 min"`, `"7 minutes"` → `"7:00"`
      • Seconds only: `"30 s"`, `"30 sec"`, `"30 secs"` → `"0:30"`
      • Combined: `"7 min 15 sec"`, `"7 minutes 15 seconds"` → `"7:15"`
      • Bare digits: `"5"` → `"5:00"`

    Inputs outside of the NBA quarter‑clock ranges (minutes > 12 or seconds ≥ 60) will raise a validation error.

    You may also supply **end_period** (default `4`) to cap the quarter range.

    Returns a JSON string of the form:
    {
      "AvailableVideo": [...],
      "PlayByPlay":    [...]
    }

    **Data availability**: NBA play‑by‑play goes back to the **1996–97** season.
    Requests for seasons before 1996–97 will result in an error.
    """
    client = NBAApiClient()
    result = await client.get_past_play_by_play(
        game_id=game_id,
        game_date=game_date,
        team=team,
        start_period=start_period,
        end_period=end_period,
        start_clock=start_clock
    )
    if isinstance(result, dict):
        return json.dumps(result)
    return result




#########################################
# Running the Server
#########################################

# nba_server.py (excerpt)

import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Optional, List, Dict, Union
import pandas as pd
import json
class PortBindingError(RuntimeError):
    """Raised when FastMCP cannot bind to any candidate port."""
# --- Add near other helpers ---

def _pid_of_listener(port: int, host: str = HOST) -> str | None:
    """
    Return 'pid:exe' of a listening process on (host, port) using psutil,
    or None if unavailable.
    """
    try:
        import psutil
        for c in psutil.net_connections(kind="inet"):
            if c.laddr.port == port and c.status == psutil.CONN_LISTEN:
                proc = psutil.Process(c.pid)
                return f"{c.pid}:{proc.name()}"
    except Exception:
        pass
    return None

# nba_server.py (update the main() function)
# --- Replace ENTIRE main() ---
# ---------------------------------------------------------------------
# nba_server.py  (replace the entire end‑of‑file main function)
def main() -> None:
    logger.info("NBA MCP server starting…")
    host, path = HOST, PATH
    max_tries = int(os.getenv("NBA_MCP_MAX_PORT_TRIES", "10"))

    if rng := os.getenv("NBA_MCP_PORT_RANGE"):
        start, end = map(int, rng.split("-", 1))
        ports = list(range(start, end + 1))
    elif (p := os.getenv("NBA_MCP_PORT")) is not None:
        base = int(p)
        ports = list(range(base, base + max_tries))
    else:
        ports = list(range(BASE_PORT, BASE_PORT + max_tries))

    logger.debug("Candidate ports: %s", ports)

    # Use the global server instance directly
    global mcp_server
    
    # Try each port in order
    for idx, port in enumerate(ports, start=1):
        logger.info("🔌  Attempt %d/%d — port %d", idx, len(ports), port)
        if not port_available(port):
            logger.warning("Port %d busy, skipping.", port)
            continue

        # safe to bind here
        mcp_server.port = port
        logger.info("Starting NBA MCP server on port %d", port)
        mcp_server.run(transport="sse")
        logger.info("✅  Serving on http://%s:%d%s", host, port, path)
        return


    # ---- no success, use random free port ----------------------------
    hint = f" – first listener {_pid_of_listener(ports[0])}" or ""
    logger.warning("All preferred ports busy%s. Falling back to OS‑assigned port.", hint)

    # Update to use port 0 (OS-assigned)
    mcp_server.port = 0
    
    # Start the server
    logger.info("Starting NBA MCP server on random port")
    mcp_server.run(transport="sse")
    
    # Get the actual port assigned by the OS - may need to be adjusted based on FastMCP's API
    # This line may need modification based on how FastMCP exposes the actual port
    try:
        actual = mcp_server._server.servers[0].sockets[0].getsockname()[1]
        logger.info("✅  Serving on http://%s:%d%s", host, actual, path)
    except (AttributeError, IndexError):
        logger.info("✅  Serving on http://%s:[DYNAMIC_PORT]%s", host, path)





if __name__ == "__main__":
    main()
