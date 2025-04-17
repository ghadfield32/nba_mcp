#nba_server.py
from mcp.server.fastmcp import FastMCP
from nba_mcp.api.client import NBAApiClient
import sys
import traceback
from datetime import datetime, timezone
from typing import Optional, List, Dict
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
    season: Optional[str] = None,
    stat_category: str = "PTS",
    per_mode: str = "Totals"
) -> str:
    """
    Retrieves the top 10 NBA league leaders for a specified statistic.

    Parameters:
        season (Optional[str]): Season in 'YYYY-YY'; defaults to current season.
        stat_category (str): Statistic abbreviation (e.g., 'PTS', 'REB', 'AST').
        per_mode (str): Aggregation mode (Totals, PerGame, Per48).

    Returns:
        str: A numbered list of the top 10 leaders with player name, team, and value.
    """
    print(f"DEBUG: get_league_leaders_info(season={season}, stat={stat_category}, mode={per_mode})", file=sys.stderr)
    client = NBAApiClient()

    season_str = season or client.get_season_string()

    try:
        result = await client.get_league_leaders(
            season=season_str,
            stat_category=stat_category,
            per_mode=per_mode,
            as_dataframe=True
        )

        if isinstance(result, str):
            return result

        df: pd.DataFrame = result
        if df.empty:
            return f"No leaders found for '{stat_category}' in season {season_str}."

        # Build a Top 10 summary
        summary = [f"Top 10 {stat_category.upper()} Leaders ({season_str}):"]
        for i, (_, row) in enumerate(df.head(10).iterrows(), start=1):
            name = row.get("PLAYER_NAME", "Unknown")
            team = row.get("TEAM_NAME", row.get("TEAM_ABBREVIATION", ""))
            # find the first column containing our category
            val_cols = [c for c in row.index if stat_category.upper() in c]
            value = row[val_cols[0]] if val_cols else row.get("STAT_VALUE", "N/A")
            summary.append(f"{i}. {name} ({team}): {value}")

        return "\n".join(summary)

    except Exception as e:
        msg = f"Unexpected error in get_league_leaders_info: {e}"
        print(f"ERROR: {msg}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return msg


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
            home = summary["homeTeam"]["teamName"]
            away = summary["awayTeam"]["teamName"]
            pts_h = summary["homeTeam"]["score"]
            pts_a = summary["awayTeam"]["score"]
            status = summary.get("gameStatusText", "")
            lines.append(f"{home} vs {away} – {pts_h}-{pts_a} ({status})")

        header = f"NBA Games for {target_date}:\n"
        return header + "\n".join(lines)

    except Exception as e:
        err = f"Unexpected error in get_live_scores: {e}"
        traceback.print_exc(file=sys.stderr)
        return err


@mcp_server.tool()
async def get_date_range_game_log_or_team_game_log(
    season: str,
    team: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> str:
    """
    Retrieves a game log for a given season, team or date range, with optional date filtering
    
    Parameters:
        season (str): Season in 'YYYY-YY'.
        team (Optional[str]): Full or partial team name. If not provided, returns all games for the season.
        date_from (Optional[str]): Start date 'YYYY-MM-DD'.
        date_to (Optional[str]): End date 'YYYY-MM-DD'.

    Returns:
        str: Lines summarizing each game date, matchup, win/loss, and points.
    """
    print(f"DEBUG: get_date_range_game_log_or_team_game_log(season={season}, team={team}, "
          f"from={date_from}, to={date_to})", file=sys.stderr)
    client = NBAApiClient()
    try:
        result = await client.get_league_game_log(
            season=season,
            team_name=team,
            date_from=date_from,
            date_to=date_to,
            as_dataframe=True
        )
        # Pass through messages or errors
        if isinstance(result, str):
            return result

        df: pd.DataFrame = result
        if df.empty:
            return f"No games found for {team} in {season} between {date_from or 'start'} and {date_to or 'end'}."

        # Format a few columns into human-readable lines
        lines = []
        for _, row in df.iterrows():
            d = row.get("GAME_DATE", row.get("GAME_DATE_EST", "Unknown"))
            matchup = row.get("MATCHUP", "")
            pts = row.get("PTS", 0)
            wl  = row.get("WL", "")
            lines.append(f"{d}: {matchup} – {wl} ({pts} pts)")

        header = f"Game log for {team} ({season}):\n"
        return header + "\n".join(lines)

    except Exception as e:
        error_msg = f"Unexpected error in get_date_range_game_log_or_team_game_log: {e}"
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
        
        print("Starting server with stdio transport...", file=sys.stderr)
        mcp_server.run(transport="stdio")
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
