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

mcp = FastMCP("nba_mcp")



# --- PARAMETER SCHEMAS ---
class PlayerCareerParams(BaseModel):
    player_name: str = Field(..., description="Full or partial player name")
    season: str | None = Field(None, description="Season in YYYY-YY format; defaults to current season")

class LeagueLeadersParams(BaseModel):
    season: str | None = Field(None, description="Season in YYYY-YY format; defaults to current season")
    stat_category: str = Field("PTS", description="Stat category (e.g. PTS, AST, REB)")
    per_mode: str = Field("Totals", description="Aggregation mode: Totals, PerGame, or Per48")

class LiveScoresParams(BaseModel):
    target_date: str | None = Field(None, description="Date YYYY-MM-DD; defaults to today")

class TeamLogParams(BaseModel):
    season: str = Field(..., description="Season in YYYY-YY format")
    team: str = Field(..., description="Full or partial team name")
    date_from: str | None = Field(None, description="Start date YYYY-MM-DD")
    date_to: str | None = Field(None, description="End date YYYY-MM-DD")

#########################################
# MCP Resources
#########################################
@mcp.resource("api-docs://openapi.json")
async def get_openapi_spec() -> str:
    """
    MCP Resource: Serve the full NBA API documentation JSON
    so the LLM can consult it when generating tool calls.
    """
    docs = await NBAApiClient().get_api_documentation()
    # Return as a JSON string for the LLM’s context
    return json.dumps(docs)

#########################################
# MCP Tools
#########################################

@mcp.tool()
async def get_player_career_information(
    player_name: str,
    season: Optional[str] = None
) -> str:
    """
    MCP tool: Return career stats for a player in a given season.
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


@mcp.tool()
async def get_league_leaders_info(
    season: Optional[str] = None,
    stat_category: str = "PTS",
    per_mode: str = "Totals"
) -> str:
    """
    MCP tool: Return the top 5 league leaders for a stat in a given season.
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

        # Build a Top 5 summary
        summary = [f"Top 5 {stat_category.upper()} Leaders ({season_str}):"]
        for i, (_, row) in enumerate(df.head(5).iterrows(), start=1):
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


@mcp.tool()
async def get_live_scores(target_date: Optional[str] = None) -> str:
    """
    Get live (or by-date) NBA game scores using the ScoreboardV2 helper.
    """
    print(f"DEBUG: Attempting to get live game scores for date: {target_date}", file=sys.stderr)
    client = NBAApiClient()


    # Default to today if nothing provided
    today = datetime.now().strftime("%Y-%m-%d")
    if not target_date:
        target_date = today


    try:
        result = await client.get_live_scoreboard(
            target_date=target_date,
            as_dataframe=True
        )

        # If the client returned an error string (no games or handler message), just pass it through
        if isinstance(result, str):
            return result

        df: pd.DataFrame = result
        if df.empty:
            return f"No games found for {target_date}."

        # Otherwise format each row
        formatted = []
        for _, row in df.iterrows():
            # you have home_team, away_team, home_pts, away_pts, status
            home = row.get("home_team", "Unknown")
            away = row.get("away_team", "Unknown")
            pts_h = row.get("home_pts", 0)
            pts_a = row.get("away_pts", 0)
            status = row.get("status", "")
            # e.g. "Lakers vs Suns – 102-99 (Final)"
            formatted.append(f"{home} vs {away} – {pts_h}-{pts_a} ({status})")

        header = f"NBA Games for {target_date}:\n"
        return header + "\n".join(formatted)

    except Exception as e:
        error_msg = f"Unexpected error in get_live_scores: {e}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return error_msg

@mcp.tool()
async def get_team_game_log(
    season: str,
    team: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> str:
    """
    Get an NBA team's game log for a season, optionally between two dates.
    
    Args:
        season:     Season string 'YYYY-YY'.
        team:       Full or partial team name.
        date_from:  Start date 'YYYY-MM-DD'.
        date_to:    End date 'YYYY-MM-DD'.
    """
    print(f"DEBUG: get_team_game_log(season={season}, team={team}, "
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

        # Format a few columns into human‐readable lines
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
        error_msg = f"Unexpected error in get_team_game_log: {e}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return error_msg

@mcp.tool()
async def play_by_play_info_for_current_games() -> str:
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




#########################################
# Running the Server
#########################################

def main():
    """Entry point for the NBA MCP server."""
    try:
        print("NBA MCP server starting...", file=sys.stderr)
        print("Initializing server transport...", file=sys.stderr)
        mcp.run(transport="stdio")
    except Exception as e:
        print(f"FATAL ERROR: Server crashed unexpectedly: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
