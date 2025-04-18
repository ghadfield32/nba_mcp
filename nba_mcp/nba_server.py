#nba_server.py
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

mcp_server = FastMCP("nba_mcp")


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
    """
    Fetches a player's career statistics for a given season.

    Parameters:
        player_name (str): Full or partial name to identify the player.
        season (Optional[str]): Season in 'YYYY-YY' format; if None, defaults to current season.

    Returns:
        str: Formatted lines including Games Played, PPG, RPG, APG, and FG% or an error/message if no data.
    """
    print(f"DEBUG: get_player_career_information('{player_name}', season={season})", file=sys.stderr)
    client = NBAApiClient()

    # Default to current season if not provided
    season_str = season or client.get_season_string()

    try:
        result = await client.get_player_career_stats(
            player_name,
            season_str,
            as_dataframe=True
        )

        # If helper returned a message (no data or error), pass it through
        if isinstance(result, str):
            return result

        df: pd.DataFrame = result
        # Safety check
        if df.empty:
            return f"No career stats found for '{player_name}' in {season_str}."

        # Pick first (and only) row
        row = df.iloc[0]
        # Format the key stats
        lines = [
            f"Player: {player_name}",
            f"Season: {season_str}",
            f"Games Played: {row.get('GP', 'N/A')}",
            f"Points Per Game: {row.get('PTS', 'N/A')}",
            f"Rebounds Per Game: {row.get('REB', 'N/A')}",
            f"Assists Per Game: {row.get('AST', 'N/A')}",
            f"Field Goal %: {row.get('FG_PCT', 'N/A')}",
        ]
        return "\n".join(lines)

    except Exception as e:
        msg = f"Unexpected error in get_player_career_information: {e}"
        print(f"ERROR: {msg}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return msg




@mcp_server.tool()
async def get_league_leaders_info(
    season: Optional[Union[str, List[str]]] = None,
    stat_category: str = "PTS",
    per_mode: str = "Totals"
) -> str:
    """
    Retrieves the top 10 NBA league leaders for one or more seasons.
    """
    client = NBAApiClient()
    # Pass through to client
    result = await client.get_league_leaders(
        season=season,
        stat_category=stat_category,
        per_mode=per_mode,
        as_dataframe=True
    )
    # If error message
    if isinstance(result, str):
        return result

    df: pd.DataFrame = result
    if df.empty:
        return f"No leaders found for '{stat_category}' in season(s) {season}."

    # Build summaries grouped by season
    summaries: List[str] = []
    for s, group in df.groupby("SEASON"):
        summaries.append(f"Top 10 {stat_category.upper()} Leaders ({s}):")
        top10 = group.head(10)
        for i, (_, row) in enumerate(top10.iterrows(), start=1):
            name = row["PLAYER_NAME"]
            team = row.get("TEAM_NAME", row.get("TEAM_ABBREVIATION", ""))
            # value column detection
            val_cols = [c for c in row.index if stat_category.upper() in c]
            value = row[val_cols[0]] if val_cols else row.get("STAT_VALUE", "N/A")
            summaries.append(f"{i}. {name} ({team}): {value}")
        summaries.append("")  # blank line between seasons

    return "\n".join(summaries).strip()



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



@mcp_server.tool()
async def get_date_range_game_log_or_team_game_log(
    season: str,
    season_type: str = "Regular Season",
    team: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> str:
    """
    Retrieves a game log for a given season and season_type:
      • If `team` is provided, returns that team's games (optionally date‑filtered).
      • If `team` is omitted, returns all teams' games in the optional date range.
      Supports any SeasonType ("Regular Season","Playoffs","Pre Season","All Star","All-Star").

    Parameters:
        season (str): Season in 'YYYY-YY'.
        season_type (str): One of "Regular Season","Playoffs","Pre Season","All Star","All-Star".
        team (Optional[str]): Full/partial team name; if None, returns all teams.
        date_from (Optional[str]): Start date 'YYYY-MM-DD'.
        date_to (Optional[str]): End date 'YYYY-MM-DD'.

    Returns:
        str: Lines summarizing each game with rich stats.
    """
    print(f"DEBUG: get_date_range_game_log_or_team_game_log("
          f"season={season!r}, season_type={season_type!r}, "
          f"team={team!r}, from={date_from!r}, to={date_to!r})",
          file=sys.stderr)

    client = NBAApiClient()
    try:
        df = await client.get_league_game_log(
            season=season,
            team_name=team,
            season_type=season_type,
            date_from=date_from,
            date_to=date_to,
            as_dataframe=True
        )
        if isinstance(df, str):
            return df
        if df.empty:
            if team:
                return (f"No games found for '{team}' in {season} "
                        f"{season_type}{' between '+date_from if date_from else ''}"
                        f"{' and '+date_to if date_to else ''}.")
            else:
                return (f"No games found in {season} {season_type}"
                        f"{' between '+date_from if date_from else ''}"
                        f"{' and '+date_to if date_to else ''}.")

        start = date_from or "season start"
        end = date_to or "season end"
        if team:
            header = f"Game log for {team} ({season} {season_type}):\n"
        else:
            header = (f"Game log for all teams in {season} {season_type} "
                      f"from {start} to {end}:\n")

        lines = []
        for _, row in df.iterrows():
            game_date = row.get("GAME_DATE") or row.get("GAME_DATE_EST", "Unknown")
            matchup   = row.get("MATCHUP", "")
            wl        = row.get("WL", "")
            team_abbr = row.get("TEAM_ABBREVIATION", "")
            pts       = row.get("PTS", 0)
            mins      = row.get("MIN", "")
            fgm, fga, fg_pct = row.get("FGM", 0), row.get("FGA", 0), row.get("FG_PCT", 0)
            fg3m, fg3a, fg3_pct = row.get("FG3M", 0), row.get("FG3A", 0), row.get("FG3_PCT", 0)
            ftm, fta, ft_pct = row.get("FTM", 0), row.get("FTA", 0), row.get("FT_PCT", 0)
            reb = row.get("REB", 0)
            ast = row.get("AST", 0)
            stl = row.get("STL", 0)
            blk = row.get("BLK", 0)
            tov = row.get("TOV", 0)
            pf  = row.get("PF", 0)
            plus_minus = row.get("PLUS_MINUS", 0)

            stats_str = (
                f"{mins} min | "
                f"FG {fgm}-{fga} ({fg_pct:.1f}%) | "
                f"3P {fg3m}-{fg3a} ({fg3_pct:.1f}%) | "
                f"FT {ftm}-{fta} ({ft_pct:.1f}%) | "
                f"TRB {reb} | AST {ast} | STL {stl} | BLK {blk} | "
                f"TOV {tov} | PF {pf} | ±{plus_minus}"
            )

            if team:
                lines.append(f"{game_date}: {matchup} – {wl}, {pts} pts | {stats_str}")
            else:
                lines.append(f"{game_date} • {team_abbr} • {matchup} – {wl}, {pts} pts | {stats_str}")

        return header + "\n".join(lines)

    except Exception as e:
        error_msg = (f"Unexpected error in "
                     f"get_date_range_game_log_or_team_game_log: {e}")
        print(f"ERROR: {error_msg}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return error_msg


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

def main():
    """Entry point for the NBA MCP server."""
    try:
        print("NBA MCP server starting...", file=sys.stderr)
        print("Server version: 0.1.0", file=sys.stderr)
        print("Python version: " + sys.version, file=sys.stderr)
        print("Initializing server transport...", file=sys.stderr)
        
        try:
            import mcp.server.fastmcp as fastmcp_module
            print("FastMCP version: " + fastmcp_module.__version__, file=sys.stderr)
        except (ImportError, AttributeError) as e:
            print(f"WARNING: Could not determine FastMCP version: {e}", file=sys.stderr)
        
        # ── Set SSE binding via env vars ──────────────────────────────
        os.environ.setdefault("FASTMCP_SSE_HOST", "0.0.0.0")
        os.environ.setdefault("FASTMCP_SSE_PORT", "8000")
        os.environ.setdefault("FASTMCP_SSE_PATH", "/sse")
        print("Starting server with SSE transport on "
              f"{os.environ['FASTMCP_SSE_HOST']}:"
              f"{os.environ['FASTMCP_SSE_PORT']}"
              f"{os.environ['FASTMCP_SSE_PATH']}",
              file=sys.stderr)

        # ── Only pass transport; host/port/path come from env ─────────
        mcp_server.run(transport="sse")

        print("Server shutdown normally", file=sys.stderr)
    except ModuleNotFoundError as e:
        print(f"ERROR: Missing required module: {e}", file=sys.stderr)
        print("Please make sure all dependencies are installed with 'pip install -r requirements.txt'", file=sys.stderr)
        print("And that the package is installed in development mode with 'pip install -e .'", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"FATAL ERROR: Server crashed unexpectedly: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
