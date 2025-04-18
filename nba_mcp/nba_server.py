#nba_server.py
from mcp.server.fastmcp import FastMCP
from nba_mcp.api.client import NBAApiClient
import sys
import traceback
from datetime import datetime, timezone
from typing import Optional, List, Dict, Union
import pandas as pd
from nba_api.stats.static import teams, players
from nba_mcp.api.tools.nba_api_utils import (get_team_id, get_team_name, get_player_name
                           , get_static_lookup_schema, normalize_stat_category, normalize_per_mode, normalize_season, normalize_date, format_game
                           )
from nba_mcp.api.tools.lookup_utils import get_player_id
import json
# nba_server.py (add near the top)
from pydantic import BaseModel, Field
# import logger
import logging
logger = logging.getLogger(__name__)

mcp_server = FastMCP("nba_mcp")


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







#########################################
# MCP Resources
#########################################
@mcp_server.resource("api-docs://openapi.json")
async def get_openapi_spec() -> str:
    """
    Retrieve the complete OpenAPI specification for the NBA API.

    Returns:
        str: JSON string of the OpenAPI spec, consumed by the LLM for tool invocation context.
    """
    docs = await NBAApiClient().get_api_documentation()
    # Return as a JSON string for the LLM's context
    return json.dumps(docs)

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

        # 6) Format a single summary row
        row = df.iloc[0]
        return "\n".join([
            f"Player: {player_name}",
            f"Season: {season_str}",
            f"Games Played: {row.get('GP', 'N/A')}",
            f"Points Per Game: {row.get('PTS', 'N/A')}",
            f"Rebounds Per Game: {row.get('REB', 'N/A')}",
            f"Assists Per Game: {row.get('AST', 'N/A')}",
            f"Field Goal %: {row.get('FG_PCT', 'N/A')}"
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

            # Historical if we got uppercase keys from Stats API
            else:
                home_team = home.get("TEAM_ABBREVIATION") or get_team_name(home["TEAM_ID"])
                away_team = away.get("TEAM_ABBREVIATION") or get_team_name(away["TEAM_ID"])
                home_pts  = home.get("PTS")
                away_pts  = away.get("PTS")

            status = summary.get("gameStatusText", "")
            lines.append(f"{home_team} vs {away_team} – {home_pts}-{away_pts} ({status})")


        header = f"NBA Games for {target_date}:\n"
        return header + "\n".join(lines)

    except Exception as e:
        err = f"Unexpected error in get_live_scores: {e}"
        traceback.print_exc(file=sys.stderr)
        return err



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

# nba_server.py (update the main() function)
def main():
    """Entry point for the NBA MCP server."""
    logger.info("NBA MCP server starting…")
    logger.info("Server version: 0.1.0")
    logger.info("Python version: %s", sys.version)
    logger.info("Initializing server transport…")

    # determine host and base port
    host = os.getenv("FASTMCP_SSE_HOST", "0.0.0.0")
    base_port = int(os.getenv("NBA_MCP_PORT",
                  os.getenv("FASTMCP_SSE_PORT", "8000")))
    path = os.getenv("FASTMCP_SSE_PATH", "/sse")

    logger.info("Starting server with SSE on %s:%s%s", host, base_port, path)

    # try binding up to 3 consecutive ports
    max_tries = 3
    for offset in range(max_tries):
        port = base_port + offset
        os.environ["FASTMCP_SSE_PORT"] = str(port)
        try:
            mcp_server.run(transport="sse")
            # if it returns, clean shutdown
            logger.info("Server shut down normally on port %s", port)
            return
        except SystemExit as se:
            # only catch exit from bind failure, not sys.exit() from other issues
            if se.code == 1 and offset < max_tries - 1:
                logger.warning(
                    "Port %s in use, retrying on port %s", port, port + 1
                )
                continue
            else:
                logger.exception("Caught SystemExit in main(): exit code=%s", se.code)
                raise
        except OSError as oe:
            if oe.errno == 10048 and offset < max_tries - 1:
                logger.warning(
                    "OSError %s binding port %s, retrying on %s",
                    oe.errno, port, port + 1
                )
                continue
            logger.exception("Fatal OSError inside FastMCP.run()")
            raise
    # if we get here, all ports failed
    logger.error(
        "Could not bind to any port in %s–%s. Please free the port or set NBA_MCP_PORT.",
        base_port, base_port + max_tries - 1
    )
    sys.exit(1)





if __name__ == "__main__":
    main()
