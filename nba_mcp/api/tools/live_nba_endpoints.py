"""
Helpers for combining live NBA API data (box score, play by play) with ESPN odds.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from json import JSONDecodeError
from typing import Dict, List, Optional

import httpx
import pandas as pd
from nba_api.live.nba.endpoints.boxscore import BoxScore
from nba_api.live.nba.endpoints.playbyplay import PlayByPlay
from nba_api.live.nba.endpoints.scoreboard import ScoreBoard
from nba_api.stats.endpoints.scoreboardv2 import ScoreboardV2

# Import ESPN metrics tracking for observability
from nba_mcp.observability.espn_metrics import track_espn_call

logger = logging.getLogger(__name__)

# ESPN's unofficial scoreboard endpoint (provides betting odds when available)
ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
)


# ---------------------------------------------------------------------------
# ESPN helpers
# ---------------------------------------------------------------------------

def _normalize_date_for_espn(date_label: Optional[str]) -> Optional[str]:
    """
    ESPN expects dates as YYYYMMDD; normalize NBA strings when possible.
    """
    if not date_label:
        return None

    try:
        return datetime.strptime(date_label, "%Y-%m-%d").strftime("%Y%m%d")
    except ValueError:
        cleaned = date_label.replace("-", "")
        return cleaned if cleaned.isdigit() and len(cleaned) == 8 else None


def _extract_team_abbr(team_blob: Dict[str, str]) -> Optional[str]:
    """
    Pull a consistent team abbreviation from the scoreboard payload.
    """
    for key in (
        "teamTricode",
        "teamAbbreviation",
        "TEAM_ABBREVIATION",
        "tricode",
        "teamCode",
        "abbreviation",
    ):
        value = team_blob.get(key)
        if value:
            return str(value).upper()
    return None


def _build_odds_key(home_abbr: Optional[str], away_abbr: Optional[str]) -> Optional[str]:
    """
    Generate the lookup key used to join ESPN odds back to NBA scoreboard data.
    """
    if not home_abbr or not away_abbr:
        return None
    return f"{home_abbr}_{away_abbr}"


@track_espn_call
def _fetch_espn_scoreboard(date_label: Optional[str], timeout: int) -> Optional[dict]:
    """
    Invoke ESPN's scoreboard endpoint and return the decoded JSON payload.

    ESPN API calls are automatically tracked for observability (success rate,
    response times, odds coverage). Metrics are collected via the track_espn_call
    decorator for production monitoring.
    """
    params: Dict[str, str] = {}
    normalized = _normalize_date_for_espn(date_label)
    if normalized:
        params["dates"] = normalized

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(ESPN_SCOREBOARD_URL, params=params)
            response.raise_for_status()
            return response.json()
    except Exception as exc:  # pragma: no cover - network failures are expected sometimes
        logger.debug("ESPN odds fetch failed: %s", exc)
        return None


def _extract_odds_map(scoreboard_json: dict) -> Dict[str, dict]:
    """
    Convert ESPN's events list into a {home_away_key: odds_payload} mapping.
    """
    odds_map: Dict[str, dict] = {}

    for event in scoreboard_json.get("events", []):
        competitions = event.get("competitions") or []
        if not competitions:
            continue

        comp = competitions[0]
        competitors = comp.get("competitors") or []
        if len(competitors) < 2:
            continue

        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue

        home_abbr = _extract_team_abbr(home.get("team", {}))
        away_abbr = _extract_team_abbr(away.get("team", {}))
        odds_key = _build_odds_key(home_abbr, away_abbr)
        if not odds_key:
            continue

        odds_list = comp.get("odds") or []
        if not odds_list:
            continue

        odds_entry = odds_list[0]
        odds_map[odds_key] = {
            "provider": odds_entry.get("provider", {}).get("name"),
            "details": odds_entry.get("details"),
            "spread": odds_entry.get("spread"),
            "overUnder": odds_entry.get("overUnder"),
            "homeMoneyline": home.get("moneyline"),
            "awayMoneyline": away.get("moneyline"),
            "lastUpdated": odds_entry.get("lastUpdated"),
            "espnEventId": event.get("id"),
        }

    return odds_map


def _fetch_odds_lookup(
    games_list: List[dict], date_label: Optional[str], timeout: int
) -> Dict[str, dict]:
    """
    Fetch odds once per scoreboard response and build a lookup keyed by team pair.
    """
    if not games_list:
        return {}
    scoreboard_json = _fetch_espn_scoreboard(date_label, timeout)
    if not scoreboard_json:
        return {}
    return _extract_odds_map(scoreboard_json)


# ---------------------------------------------------------------------------
# Live NBA API helpers
# ---------------------------------------------------------------------------

def fetch_game_live_data(
    game_id: str,
    proxy: Optional[str] = None,
    headers: Optional[dict] = None,
    timeout: int = 30,
) -> dict:
    """
    Fetch live box score and play by play for a single game.
    """
    # Box score
    try:
        box = BoxScore(
            game_id=game_id,
            proxy=proxy,
            headers=headers,
            timeout=timeout,
            get_request=False,
        )
        box.get_request()
        box_data = box.get_dict().get("game")
    except JSONDecodeError:
        logger.debug("No box score JSON for game %s (tip-off not reached).", game_id)
        box_data = None
    except Exception as exc:
        logger.debug("Box score fetch failed for %s: %s", game_id, exc)
        box_data = None

    # Play by play
    try:
        pbp = PlayByPlay(
            game_id=game_id,
            proxy=proxy,
            headers=headers,
            timeout=timeout,
            get_request=False,
        )
        pbp.get_request()
        pbp_actions = pbp.get_dict().get("game", {}).get("actions", [])
    except JSONDecodeError:
        pbp_actions = []
    except Exception as exc:
        logger.debug("Play by play fetch failed for %s: %s", game_id, exc)
        pbp_actions = []

    # Odds are injected by the caller (we default to an empty payload here).
    return {
        "gameId": game_id,
        "boxScore": box_data,
        "playByPlay": pbp_actions,
        "odds": {},
    }


def fetch_live_boxsc_odds_playbyplaydelayed_livescores(
    game_date: Optional[str] = None,
    proxy: Optional[str] = None,
    headers: Optional[dict] = None,
    timeout: int = 30,
) -> dict:
    """
    Wrapper returning all games for the provided date (or today when None).

    Live mode enriches each game with box score, play by play, and ESPN odds.
    Historical mode (game_date provided) returns the ScoreboardV2 snapshot only.
    """
    logger.debug(
        "fetch_live_boxsc_odds_playbyplaydelayed_livescores called with game_date=%s",
        game_date,
    )

    if game_date:
        # Historical snapshot via ScoreboardV2
        sb2 = ScoreboardV2(day_offset=0, game_date=game_date, league_id="00")
        dfs = sb2.get_data_frames()
        df_header = next(df for df in dfs if "GAME_STATUS_TEXT" in df.columns)
        df_line = next(df for df in dfs if "TEAM_ID" in df.columns)
        games_list: List[dict] = []

        for _, row in df_header.iterrows():
            gid = row["GAME_ID"]

            def _line_for(team_id_col: str, abbrev_col: str) -> dict:
                # Match by team id; fall back to abbreviation when necessary.
                try:
                    return (
                        df_line[df_line["TEAM_ID"] == row[team_id_col]].iloc[0].to_dict()
                    )
                except Exception:
                    abbrev = row.get(abbrev_col)
                    return (
                        df_line[df_line["TEAM_ABBREVIATION"] == abbrev]
                        .iloc[0]
                        .to_dict()
                    )

            games_list.append(
                {
                    "gameId": gid,
                    "gameStatusText": row.get("GAME_STATUS_TEXT"),
                    "period": row.get("LIVE_PERIOD"),
                    "gameClock": row.get("LIVE_PC_TIME"),
                    "homeTeam": _line_for("HOME_TEAM_ID", "HOME_TEAM_ABBREVIATION"),
                    "awayTeam": _line_for(
                        "VISITOR_TEAM_ID", "VISITOR_TEAM_ABBREVIATION"
                    ),
                }
            )

        date_label = game_date
        odds_lookup: Dict[str, dict] = {}
    else:
        # Live scoreboard does not accept game_date; rely on day_offset and the
        # internal date that comes back in the payload.
        sb = ScoreBoard(proxy=proxy, headers=headers, timeout=timeout, get_request=True)
        games_list = sb.games.get_dict()
        date_label = sb.score_board_date
        odds_lookup = _fetch_odds_lookup(games_list, date_label, timeout)

    all_data: List[dict] = []

    for gmeta in games_list:
        gid = gmeta["gameId"]

        if game_date:
            all_data.append({"scoreBoardSnapshot": gmeta})
            continue

        game_payload = fetch_game_live_data(
            game_id=gid,
            proxy=proxy,
            headers=headers,
            timeout=timeout,
        )

        # Attach the scoreboard summary
        game_payload["scoreBoardSummary"] = gmeta

        # Attach odds from ESPN when they exist
        home_abbr = _extract_team_abbr(gmeta.get("homeTeam", {}))
        away_abbr = _extract_team_abbr(gmeta.get("awayTeam", {}))
        odds_key = _build_odds_key(home_abbr, away_abbr)
        if odds_key:
            game_payload["odds"] = odds_lookup.get(odds_key, {})

        all_data.append(game_payload)

    logger.debug(
        "Returning scoreboard payload for date=%s with total_games=%s",
        date_label,
        len(all_data),
    )
    return {"date": date_label, "games": all_data}


if __name__ == "__main__":  # pragma: no cover - manual debugging helper
    print("\nReal-time today:\n")
    print(json.dumps(fetch_live_boxsc_odds_playbyplaydelayed_livescores(), indent=2))
