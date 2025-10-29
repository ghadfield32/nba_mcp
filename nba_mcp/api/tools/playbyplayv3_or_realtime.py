from __future__ import annotations

import json
import logging
import re
import sys
import time
from dataclasses import dataclass
from datetime import date
from datetime import date as _date
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Literal, Optional, Tuple, Union

import pandas as pd
import requests

# ── APPLY NBA API PATCHES FIRST (before importing endpoints) ─────────────────────
from nba_mcp.api.nba_api_patches import apply_all_patches
apply_all_patches()

# ── NEW HELPER: build a "snapshot" from a *finished* game ─────────────────────
from nba_api.stats.endpoints import (
    PlayByPlayV3,
)
from nba_api.stats.endpoints import boxscoretraditionalv2 as _BSv2
from nba_api.stats.endpoints import scoreboardv2 as _SBv2
from nba_api.stats.static import teams as _static_teams

from nba_mcp.api.tools.nba_api_utils import (
    _resolve_team_ids,
    format_game,
    get_player_name,
    get_team_id,
    get_team_id_from_abbr,
    get_team_name,
    normalize_date,
)

# (and your existing imports)


# 1) configure the root logger
logging.getLogger("urllib3").setLevel(logging.WARNING)


# 2) ensure your module‐level logger is DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _is_game_live(status_text: str) -> bool:
    """Return True if status_text indicates a live, in-progress game."""
    low = status_text.lower()
    for tok in ("pm et", "am et", "pregame", "final"):
        if tok in low:
            return False
    return True


def _camel_to_snake(name: str) -> str:
    """Convert CamelCase or mixedCase to snake_case."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def get_games_on_date(game_date: date) -> list[str]:
    """
    Return all NBA game IDs for a given date.
    game_date: datetime.date object (e.g. date(2025, 4, 16))
    """
    date_str = game_date.strftime("%m/%d/%Y")
    sb = _SBv2.ScoreboardV2(game_date=date_str)
    df = sb.get_data_frames()[0]
    return df["GAME_ID"].astype(str).tolist()


class PlayByPlayFetcher:
    """
    Fetch play‐by‐play via PlayByPlayV3, normalize to snake_case,
    and optionally stream events one by one.
    """

    def __init__(
        self,
        game_id: str,
        start_period: int = 1,
        end_period: Optional[int] = None,
        start_event_idx: int = 0,
    ):
        self.game_id = game_id
        self.start_period = start_period
        self.end_period = end_period or 4
        self.start_event_idx = start_event_idx

    def fetch(self) -> pd.DataFrame:
        """Return a DataFrame of all events between start & end periods,
        with guaranteed 'period' and 'clock' columns."""
        resp = PlayByPlayV3(
            game_id=self.game_id,
            start_period=self.start_period,
            end_period=self.end_period,
        )
        dfs = resp.get_data_frames()

        # debug what came back
        logger.debug(f"[DEBUG fetch] got {len(dfs)} frame(s) from PlayByPlayV3")
        for i, frame in enumerate(dfs):
            logger.debug(f"[DEBUG fetch] frame[{i}] columns:", frame.columns.tolist())

        # pick the frame that actually has period+clock
        pbp_df = None
        for frame in dfs:
            lower_cols = [c.lower() for c in frame.columns]
            if "period" in lower_cols and (
                "clock" in lower_cols or "pctimestring" in lower_cols
            ):
                pbp_df = frame
                break

        if pbp_df is None:
            logger.debug("⚠️ couldn't detect PBP frame; defaulting to dfs[1]")
            if len(dfs) < 2:
                raise RuntimeError(
                    f"Expected ≥2 frames from PlayByPlayV3, got {len(dfs)}"
                )
            pbp_df = dfs[1]

        df = pbp_df.copy()
        df.columns = [_camel_to_snake(c) for c in df.columns]
        df = df.rename(columns={"pctimestring": "clock", "quarter": "period"})

        missing = [c for c in ("period", "clock") if c not in df.columns]
        if missing:
            raise RuntimeError(f"Missing expected column(s) in PBP: {missing}")

        return df

    def stream(self, batch_size: int = 1) -> Any:
        """
        Generator over play‑by‑play events.
        Yields dicts of each event (or lists of events, if batch_size > 1),
        starting at self.start_event_idx.
        """
        df = self.fetch()
        total = len(df)
        idx = self.start_event_idx
        while idx < total:
            chunk = df.iloc[idx : idx + batch_size].to_dict(orient="records")
            yield chunk if batch_size > 1 else chunk[0]
            idx += batch_size


def _snapshot_from_past_game(
    game_id: str,
    pbp_records: list[dict[str, Any]],
    *,
    recent_n: int = 5,
    timeout: float = 10.0,
) -> dict[str, Any]:
    import pandas as pd

    def has_score(r):
        return bool(
            (r.get("scoreHome") or r.get("score_home"))
            and (r.get("scoreAway") or r.get("score_away"))
        )

    last_scored = next(
        (r for r in reversed(pbp_records) if has_score(r)), pbp_records[-1]
    )

    home_score = int(last_scored.get("scoreHome", last_scored.get("score_home", 0)))
    away_score = int(last_scored.get("scoreAway", last_scored.get("score_away", 0)))
    period = last_scored.get("period")

    bs = _BSv2.BoxScoreTraditionalV2(game_id=game_id, timeout=timeout)
    dfs = bs.get_data_frames()
    if len(dfs) < 2:
        raise RuntimeError(
            f"Expected ≥2 frames from BoxScoreTraditionalV2, got {len(dfs)}"
        )
    df_p, df_t = dfs[0], dfs[1]

    def _to_int(v: Any) -> int:
        return 0 if pd.isna(v) else int(v)

    def _team_stats(row):
        # option: debug any missing stats here:
        missing = [
            c for c in ("FGM", "FGA", "REB", "AST", "TO", "PTS") if pd.isna(row.get(c))
        ]
        if missing:
            logger.debug(f"[DEBUG][_team_stats] {row['TEAM_ID']} missing {missing}")
        return {
            "fieldGoalsMade": _to_int(row["FGM"]),
            "fieldGoalsAttempted": _to_int(row["FGA"]),
            "reboundsTotal": _to_int(row["REB"]),
            "assists": _to_int(row["AST"]),
            "turnovers": _to_int(row["TO"]),
            "score": _to_int(row["PTS"]),
        }

    def _players(team_id):
        pl = df_p[df_p["TEAM_ID"] == team_id].sort_values("MIN", ascending=False)
        return [
            {"name": n, "statistics": {"points": _to_int(pts)}}
            for n, pts in zip(pl["PLAYER_NAME"], pl["PTS"])
        ]

    recent = pbp_records[-recent_n:] if len(pbp_records) >= recent_n else pbp_records

    return {
        "status": {
            "period": period,
            "gameClock": "PT00M00.00S",
            "scoreDiff": home_score - away_score,
            "homeScore": home_score,
            "awayScore": away_score,
            "homeName": df_t.iloc[0]["TEAM_NAME"],
            "awayName": df_t.iloc[1]["TEAM_NAME"],
        },
        "teams": {
            "home": _team_stats(df_t.iloc[0]),
            "away": _team_stats(df_t.iloc[1]),
        },
        "players": {
            "home": _players(df_t.iloc[0]["TEAM_ID"]),
            "away": _players(df_t.iloc[1]["TEAM_ID"]),
        },
        "recentPlays": recent,
    }


# --------------------------------------------------------------------------- #
# ──   CONSTANTS / UTILITIES                                                 ──
# --------------------------------------------------------------------------- #
_GAMEID_RE = re.compile(r"^\d{10}$")


# ── internal helpers ──────────────────────────────────────────────────────
def _scoreboard_df(
    gdate: Union[str, pd.Timestamp], timeout: float = 10.0
) -> pd.DataFrame:
    sb = _SBv2.ScoreboardV2(game_date=gdate, timeout=timeout)
    return sb.get_data_frames()[0]  # 'GameHeader'


def _create_game_dict_from_row(row: pd.Series) -> dict:
    """
    …returns a dict for format_game(…) that now shows tip‑off time
    if the game hasn't started yet.
    """
    home_score = visitor_score = 0
    period = 0

    # 1) pre‑game: show scheduled time from GAME_STATUS_TEXT
    if row.get("LIVE_PERIOD", 0) == 0:
        game_time = row.get("GAME_STATUS_TEXT", "")
    else:
        # 2) in‑progress or final: use live clock
        home_score = row.get("HOME_TEAM_SCORE", 0)
        visitor_score = row.get("VISITOR_TEAM_SCORE", 0)
        period = row.get("LIVE_PERIOD", 0)
        game_time = row.get("LIVE_PC_TIME", "")

    return {
        "home_team": {
            "full_name": get_team_name(row["HOME_TEAM_ID"])
            or f"Team {row['HOME_TEAM_ID']}"
        },
        "visitor_team": {
            "full_name": get_team_name(row["VISITOR_TEAM_ID"])
            or f"Team {row['VISITOR_TEAM_ID']}"
        },
        "home_team_score": home_score,
        "visitor_team_score": visitor_score,
        "period": period,
        "time": game_time,  # ← now filled pregame
        "status": row.get("GAME_STATUS_ID", 0),
        "game_id": str(row["GAME_ID"]),
    }


# Import centralized headers from nba_mcp.api.headers
from nba_mcp.api.headers import get_stats_api_headers

# Use centralized headers (replaces old _STATS_HEADERS)
# This ensures we use professional NBA-MCP User-Agent and proper Referer
_STATS_HEADERS = get_stats_api_headers()


def get_today_games(timeout: float = 10.0) -> List[Dict[str, Any]]:
    url = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
    payload = fetch_json(url, timeout=timeout)

    if payload.get("scoreboard") and "games" in payload["scoreboard"]:
        games_info = [
            {
                "gameId": game["gameId"],
                "gameTime": game["gameTimeUTC"],
                "homeTeam": game["homeTeam"]["teamName"],
                "awayTeam": game["awayTeam"]["teamName"],
                "status": game["gameStatusText"],
            }
            for game in payload["scoreboard"]["games"]
        ]
        return games_info

    # Explicitly log unexpected cases:
    logger.debug(f"[DEBUG] Unexpected payload structure: {payload}", file=sys.stderr)
    return []  # Always return an empty list if no games


def fetch_json(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    resp = requests.get(url, headers=headers, params=params, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} from {url!r}")
    try:
        payload = resp.json()
    except ValueError:
        snippet = resp.text[:500].replace("\n", " ")
        raise RuntimeError(f"Non‑JSON response from {url!r}: {snippet}…")
    logger.debug(f"[DEBUG] {url!r} → keys: {list(payload.keys())}")
    return payload


def get_playbyplay_v3(
    game_id: str, start_period: int, end_period: int, timeout: float = 10.0
) -> Dict[str, Any]:
    """
    Wrap the new PlayByPlayFetcher so we get a snake_case
    DataFrame for PlayByPlay, plus the raw AvailableVideo.
    """
    # 1) normalized play-by-play
    df = PlayByPlayFetcher(game_id, start_period, end_period).fetch()

    # 2) still need the AvailableVideo set raw
    resp = PlayByPlayV3(
        game_id=game_id, start_period=start_period, end_period=end_period
    )
    avail_df = resp.get_data_frames()[0]

    # 3) return same dict shape as before
    return {
        "AvailableVideo": avail_df.to_dict("records"),
        "PlayByPlay": df.to_dict("records"),
    }


def get_live_playbyplay(game_id: str, timeout: float = 5.0) -> List[Dict[str, Any]]:
    url = (
        f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"
    )

    # FIXED: Include required headers explicitly
    payload = fetch_json(url, headers=_STATS_HEADERS, timeout=timeout)

    if "liveData" in payload and "plays" in payload["liveData"]:
        return payload["liveData"]["plays"]["play"]

    if "game" in payload and "actions" in payload["game"]:
        return payload["game"]["actions"]

    raise RuntimeError(
        f"Unrecognized live‑pbp shape for {game_id}: {list(payload.keys())}"
    )


def get_live_boxscore(game_id: str, timeout: float = 5.0) -> Dict[str, Any]:
    """
    Poll the near-real-time boxscore JSON feed.
    Supports both the 'liveData' shape and nba.cloud fallback shapes:
      1) a game['teams'] list
      2) separate game['homeTeam']/game['awayTeam'] fields
    Logs detailed statistics available for each team.
    """
    url = f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
    payload = fetch_json(url, timeout=timeout)

    # 1) Official liveData path
    if "liveData" in payload and "boxscore" in payload["liveData"]:
        boxscore = payload["liveData"]["boxscore"]

        # Debug and display available statistics
        logger.debug("liveData['boxscore'] keys: %s", list(boxscore.keys()))
        for team_key in ["home", "away"]:
            team_stats = boxscore["teams"][team_key]
            logger.debug("Stats for %s team:", team_key)
            for stat_category, stat_value in team_stats.items():
                if isinstance(stat_value, (dict, list)):
                    logger.debug(
                        "  - %s: (complex type, keys: %s)",
                        stat_category,
                        (
                            list(stat_value.keys())
                            if isinstance(stat_value, dict)
                            else "list"
                        ),
                    )
                else:
                    logger.debug("  - %s: %s", stat_category, stat_value)

        return boxscore

    # 2) nba.cloud fallback(s)
    if "game" in payload:
        game_obj = payload["game"]
        logger.debug(f"[DEBUG] payload['game'] keys: {list(game_obj.keys())}")

        # 2a) list-based fallback
        if "teams" in game_obj and isinstance(game_obj["teams"], list):
            teams_list = game_obj["teams"]
            logger.debug(
                f"[DEBUG] fallback list boxscore, game['teams'] length: {len(teams_list)}"
            )
            mapped = {"home": None, "away": None}
            for t in teams_list:
                ind = t.get("homeAwayIndicator") or t.get("homeAway") or t.get("side")
                if ind == "H":
                    mapped["home"] = t
                elif ind == "A":
                    mapped["away"] = t
            if mapped["home"] and mapped["away"]:
                logger.debug(
                    "Stats in fallback (list-based): %s", list(mapped["home"].keys())
                )
                return {"teams": mapped}
            return {"teams": teams_list}

        # 2b) home/away-fields fallback
        if "homeTeam" in game_obj and "awayTeam" in game_obj:
            logger.debug("fallback home/away boxscore path")
            mapped = {"home": game_obj["homeTeam"], "away": game_obj["awayTeam"]}
            logger.debug(
                "Stats in fallback (home/away): %s", list(mapped["home"].keys())
            )
            return {"teams": mapped}

    # 3) Unrecognized shape
    raise RuntimeError(
        f"Unrecognized boxscore shape for {game_id}: {list(payload.keys())}"
    )


def measure_update_frequency(
    game_id: str,
    fetch_fn: Callable[[str], Dict[str, Any]],
    timestamp_key_path: List[str],
    samples: int = 5,
    delay: float = 1.0,
) -> List[float]:
    """
    Measure how often a feed updates by sampling its embedded timestamp.

    - fetch_fn: function(game_id) -> raw payload dict
    - timestamp_key_path: nested keys to the ISO timestamp, e.g. ['meta','time'] or ['gameTimeUTC']
    """
    timestamps: List[datetime] = []

    def extract_ts(payload: Dict[str, Any]) -> datetime:
        sub = payload
        for key in timestamp_key_path:
            sub = sub[key]
        # Normalize trailing Z
        return datetime.fromisoformat(sub.replace("Z", "+00:00"))

    for i in range(samples):
        payload = fetch_fn(game_id)
        try:
            ts = extract_ts(payload)
            now = datetime.now(timezone.utc)
            logger.debug(
                f"[DEBUG] sample #{i+1} timestamp: {ts.isoformat()}  (fetched at {now.isoformat()})"
            )
            timestamps.append(ts)
        except Exception as ex:
            logger.debug(f"[DEBUG] failed to extract timestamp on sample #{i+1}: {ex}")
        time.sleep(delay)

    intervals: List[float] = []
    for a, b in zip(timestamps, timestamps[1:]):
        delta = (b - a).total_seconds()
        intervals.append(delta)
        logger.debug(f"[DEBUG] interval: {delta}s")

    return intervals


# ─── 4) EVENT DIFFING ─────────────────────────────────────────────────────────────
def diff_new_events(
    old_events: List[Dict[str, Any]],
    new_events: List[Dict[str, Any]],
    key: str = "actionNumber",
) -> List[Dict[str, Any]]:
    """
    Return only those plays in new_events whose `key` isn't present in old_events.
    Defaults to actionNumber since CDN livePBP uses that uniquely.
    """
    seen = {e[key] for e in old_events if key in e}
    new_filtered = [e for e in new_events if key in e and e[key] not in seen]

    # debug any stray entries missing the key entirely
    missing = [e for e in new_events if key not in e]
    if missing:
        logger.debug(f"[DEBUG] Missing '{key}' on events:", missing)

    return new_filtered


# ─── 5) POLLING LOOP EXAMPLE ──────────────────────────────────────────────────────
def stream_live_pbp(game_id: str, interval: float = 3.0):
    """
    Example generator: yields each new play as it appears in the live JSON feed.
    """
    cache: List[Dict[str, Any]] = []
    while True:
        plays = get_live_playbyplay(game_id)
        new = diff_new_events(cache, plays, key="eventId")
        for evt in new:
            yield evt
        cache = plays
        time.sleep(interval)


import json
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import requests


def get_game_info(game_id: str, timeout: float = 5.0) -> Dict[str, Any]:
    """
    Fetch the raw 'game' object from the liveData boxscore endpoint
    (period, gameClock, statusText, etc.).
    """
    url = f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
    logger.debug(f"[DEBUG get_game_info] GET {url!r} with headers={_STATS_HEADERS}")
    try:
        payload = fetch_json(url, headers=_STATS_HEADERS, timeout=timeout)
    except RuntimeError as e:
        msg = str(e)
        if "403" in msg:
            # boxscore JSON not published yet
            raise RuntimeError(f"Game {game_id} boxscore not yet available (HTTP 403).")
        raise

    # prefer the 'liveData' shape
    if "liveData" in payload and "game" in payload["liveData"]:
        return payload["liveData"]["game"]
    # fallback
    if "game" in payload:
        return payload["game"]

    raise RuntimeError(f"Can't extract raw game info for {game_id}")


def measure_content_changes(
    game_id: str,
    fetch_fn: Callable[[str], Any],
    extractor_fn: Callable[[Any], Any],
    samples: int = 5,
    delay: float = 1.0,
) -> List[float]:
    """
    Poll `fetch_fn(game_id)` and apply `extractor_fn` each time.
    Returns list of seconds between *changes* in the extracted value.
    """
    timestamps: List[datetime] = []
    values: List[Any] = []

    for i in range(samples):
        payload = fetch_fn(game_id)
        val = extractor_fn(payload)
        now = datetime.now(timezone.utc)
        logger.debug(f"[DEBUG] sample #{i+1}: value={val!r} at {now.isoformat()}")
        values.append(val)
        timestamps.append(now)
        time.sleep(delay)

    change_intervals: List[float] = []
    last_val, last_time = values[0], timestamps[0]
    for t, v in zip(timestamps[1:], values[1:]):
        if v != last_val:
            delta = (t - last_time).total_seconds()
            change_intervals.append(delta)
            logger.debug(f"[DEBUG] changed {last_val!r}→{v!r} after {delta}s")
            last_val, last_time = v, t

    return change_intervals


def group_live_game(game_id: str, recent_n: int = 5) -> Dict[str, Any]:
    """
    Bundle game status, team summaries, player box‑score and recent plays.
    Adds the *team names* so downstream markdown can reference them.
    """
    # 1) raw game info (clock, period, names, status text)
    info = get_game_info(game_id)
    status_text = info.get("gameStatusText", "").lower()
    logger.debug(f"[DEBUG] gameStatusText: {status_text}")

    # Skip games that haven't started yet
    if any(tok in status_text for tok in ("pm et", "am et", "pregame")):
        raise RuntimeError(f"Game {game_id} has not started yet ({status_text}).")

    home_name = info["homeTeam"]["teamName"]
    away_name = info["awayTeam"]["teamName"]
    period = info.get("period")
    gameClock = info.get("gameClock")

    # 2) box‑score & scores
    box = get_live_boxscore(game_id)
    teams = box["teams"]
    home_score = int(teams["home"]["score"])
    away_score = int(teams["away"]["score"])

    # 3) recent plays
    pbp = get_live_playbyplay(game_id)
    recent = pbp[-recent_n:] if len(pbp) >= recent_n else pbp

    return {
        "status": {
            "period": period,
            "gameClock": gameClock,
            "scoreDiff": home_score - away_score,
            "homeScore": home_score,
            "awayScore": away_score,
            "homeName": home_name,
            "awayName": away_name,
        },
        "teams": {
            "home": teams["home"]["statistics"],
            "away": teams["away"]["statistics"],
        },
        "players": {
            "home": teams["home"]["players"],
            "away": teams["away"]["players"],
        },
        "recentPlays": recent,
    }


# ─── NEW HELPER #1 ───────────────────────────────────────────────────────────────
def truncate_list(lst: List[Any], max_items: int = 3) -> List[Any]:
    """
    Return the first `max_items` elements of a list and append '…'
    if items were omitted.  Safe for JSON‑serialisable content.
    """
    if len(lst) <= max_items:
        return lst
    return lst[:max_items] + ["…"]


# ─── NEW HELPER #2 ───────────────────────────────────────────────────────────────
import re


def parse_iso_clock(iso: str) -> str:
    """
    Turn an ISO‐8601 duration like 'PT09M28.00S' into '9:28'.
    Falls back to the raw string if it doesn't match.
    """
    m = re.match(r"PT0*(\d+)M0*(\d+)(?:\.\d+)?S", iso)
    if m:
        minutes = int(m.group(1))
        seconds = int(m.group(2))
        return f"{minutes}:{seconds:02d}"
    return iso


def pretty_print_snapshot(
    snapshot: Dict[str, Any], max_players: int = 2, max_plays: int = 2
) -> None:
    """
    Print a condensed view of the grouped snapshot so you can eyeball
    each section quickly from the console.
    """
    status = snapshot["status"]
    logger.debug("\n=== GAME STATUS ===")
    clock = parse_iso_clock(status["gameClock"])
    logger.debug(
        f"Period {status['period']}  |  Clock {clock}  "
        f"|  {status['homeScore']}-{status['awayScore']} "
        f"(diff {status['scoreDiff']})"
    )

    logger.debug("\n=== TEAM STATS (headline) ===")
    for side in ("home", "away"):
        team_stats = snapshot["teams"][side]
        headline = {
            k: team_stats[k]
            for k in (
                "fieldGoalsMade",
                "fieldGoalsAttempted",
                "reboundsTotal",
                "assists",
                "turnovers",
            )
            if k in team_stats
        }
        logger.debug(f"{side.capitalize():5}: {headline}")

    logger.debug("\n=== PLAYERS (first few) ===")
    for side in ("home", "away"):
        players = snapshot["players"][side]
        slist = truncate_list(
            [f"{p['name']} ({p['statistics']['points']} pts)" for p in players],
            max_players,
        )
        logger.debug(f"{side.capitalize():5}: {', '.join(slist)}")

    logger.debug("\n=== RECENT PLAYS ===")
    for play in truncate_list(snapshot["recentPlays"], max_plays):
        desc = play.get("description", play["actionType"])
        clock = parse_iso_clock(play.get("clock", ""))
        period = play.get("period", "?")
        logger.debug(f"[Q{period} {clock}] {desc}")


def generate_tool_output(game_id: str, recent_n: int = 5) -> Dict[str, Any]:
    """
    Gather all raw payloads and the grouped summary into one JSON-friendly dict.
    - raw.pbp_v3: output of stats/playbyplayv3
    - raw.live_pbp: output of CDN playbyplay
    - raw.live_box: output of CDN boxscore
    - raw.game_info: raw 'game' object
    - normalized: the same but passed through your existing helpers
    - summary: the grouped snapshot (status, teams, players, recentPlays)
    """
    # 1) Raw endpoint payloads
    pbp_v3_raw = fetch_json(
        "https://stats.nba.com/stats/playbyplayv3",
        headers=_STATS_HEADERS,
        params={"GameID": game_id, "StartPeriod": 1, "EndPeriod": 4},
    )
    live_pbp_raw = fetch_json(
        f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"
    )
    live_box_raw = fetch_json(
        f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
    )
    game_info = get_game_info(game_id)

    # 2) Normalized data via existing helpers
    pbp_v3 = get_playbyplay_v3(game_id, 1, 4)
    live_pbp = get_live_playbyplay(game_id)
    live_box = get_live_boxscore(game_id)
    summary = group_live_game(game_id, recent_n=recent_n)

    return {
        "raw": {
            "pbp_v3": pbp_v3_raw,
            "live_pbp": live_pbp_raw,
            "live_box": live_box_raw,
            "game_info": game_info,
        },
        "normalized": {
            "pbp_v3": pbp_v3,
            "live_pbp": live_pbp,
            "live_box": live_box,
        },
        "summary": summary,
    }


# ── NEW: markdown_helpers.py ──────────────────────────────────────────────
from typing import Any, Dict, List


def _fg_line(made: int, att: int) -> str:
    """Return `FGM / FGA` convenience string."""
    return f"{made} / {att}"


def format_today_games(games: List[Dict[str, Any]]) -> str:
    """Markdown bullet list of today's games (section 1)."""
    if not games:
        return "_No games scheduled today_"
    lines = ["### 1. Today's Games"]
    for g in games:
        lines.append(
            f"- **{g['gameId']}** {g['awayTeam']} @ {g['homeTeam']} ({g['status']})"
        )
    return "\n".join(lines)


def _leading(players: List[Dict[str, Any]], n: int = 3) -> List[str]:
    """Return first `n` players as 'Name X pts'."""
    out = [f"{p['name']} {p['statistics']['points']} pts" for p in players[:n]]
    return out


def format_snapshot_markdown(
    snapshot: Dict[str, Any], game_id: str, max_players: int = 3, recent_n: int = 3
) -> str:
    """
    Convert the snapshot into sections 2–6 as Markdown.
    Supports both live (camelCase) and historical (snake_case) play dicts.
    """
    from typing import Any, Dict, List

    s = snapshot["status"]
    teams = snapshot["teams"]
    players = snapshot["players"]
    recent = snapshot["recentPlays"][-recent_n:]

    home, away = s["homeName"], s["awayName"]
    diff = abs(s["scoreDiff"])
    leading_team = home if s["scoreDiff"] > 0 else away
    verb = "up"

    parts: List[str] = []

    # 2. Selected game
    parts.append("### 2. Selected Game")
    parts.append(f"- **Game ID:** {game_id}")
    parts.append(f"- **Match-up:** {away} @ {home}\n")

    # 3. Game Status
    parts.append("### 3. Game Status")
    parts.append(f"- **Period:** {s['period']}")
    parts.append(f"- **Clock:** {parse_iso_clock(s['gameClock'])}")
    parts.append(
        f"- **Score:** {away} {s['awayScore']} – {s['homeScore']} {home}  "
        f"({leading_team} {verb} {diff})\n"
    )

    # 4. Team stats
    def _row(side: str, label: str) -> str:
        t = teams[side]
        fg = _fg_line(t["fieldGoalsMade"], t["fieldGoalsAttempted"])
        return f"| {label} | {fg} | {t['reboundsTotal']} | {t['assists']} | {t['turnovers']} |"

    parts.append("### 4. Team Stats")
    parts.append("| Team | FGM-FGA | Reb | Ast | TO |")
    parts.append("|------|---------|-----|-----|----|")
    parts.append(_row("home", home))
    parts.append(_row("away", away))
    parts.append("")

    # 5. Leading scorers
    def _leading(pl: List[Dict[str, Any]]) -> List[str]:
        return [
            f"{p['name']} {p['statistics']['points']} pts" for p in pl[:max_players]
        ]

    parts.append("### 5. Leading Scorers")
    parts.append(f"- **{home}:**  " + " · ".join(_leading(players["home"])))
    parts.append(f"- **{away}:**  " + " · ".join(_leading(players["away"])))
    parts.append("")

    # 6. Recent plays
    parts.append("### 6. Recent Plays")
    parts.append("| Qtr | Clock | Play |")
    parts.append("|-----|-------|------|")
    for p in recent:
        # quarter
        q = p.get("period", "?")

        # clock: live vs. historical
        raw_clock = p.get("clock") or p.get("pc_time_string") or ""
        clk = parse_iso_clock(raw_clock)

        # description cascade
        desc = (
            p.get("description")
            or p.get("actionType")
            or p.get("action_type")
            or p.get("home_description")
            or p.get("visitor_description")
            or p.get("neutral_description")
            or ""
        )

        parts.append(f"| {q} | {clk} | {desc} |")

    return "\n".join(parts)


def print_markdown_summary(
    game_id: str, games_today: List[Dict[str, Any]], snapshot: Dict[str, Any]
) -> None:
    """
    Convenience wrapper: prints full Markdown block 1-6.
    """
    md = []
    md.append(format_today_games(games_today))
    md.append(format_snapshot_markdown(snapshot, game_id))
    print("\n".join(md))


def debug_play_structure(game_id: str) -> None:
    """Fetches play-by-play and prints structure of the first play to find correct fields."""
    plays = get_live_playbyplay(game_id)
    if plays:
        first_play = plays[0]
        logger.debug("[DEBUG] First play structure and data:")
        for key, value in first_play.items():
            logger.debug(f" - {key}: {value}")
    else:
        logger.debug("[DEBUG] No plays found.")


class GameStream:
    def __init__(self, game_id: str):
        self.game_id = game_id
        self.cache = []

    @staticmethod
    def get_today_games(timeout: float = 10.0) -> List[Dict[str, Any]]:
        return get_today_games(timeout=timeout)

    @classmethod
    def from_today(cls, timeout: float = 10.0):
        games = cls.get_today_games(timeout=timeout)
        active_or_finished_games = [
            g
            for g in games
            if not (
                "pm et" in g["status"].lower()
                or "am et" in g["status"].lower()
                or "pregame" in g["status"].lower()
            )
        ]
        if not active_or_finished_games:
            raise RuntimeError("No active or finished games available today.")
        return cls(active_or_finished_games[0]["gameId"]), active_or_finished_games

    def debug_first_play(self) -> None:
        debug_play_structure(self.game_id)

    def fetch_grouped_snapshot(self, recent_n: int = 5) -> Dict[str, Any]:
        return group_live_game(self.game_id, recent_n)

    def print_markdown_summary(
        self, recent_n: int = 3, games_today: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        if games_today is None:
            games_today = self.get_today_games()
        snapshot = self.fetch_grouped_snapshot(recent_n=recent_n)
        print_markdown_summary(self.game_id, games_today, snapshot)

    def safe_fetch_live_pbp(self) -> List[Dict[str, Any]]:
        try:
            return get_live_playbyplay(self.game_id)
        except Exception as e:
            logger.debug(f"[DEBUG] Error fetching live pbp for {self.game_id}: {e}")
            return []

    def stream_new_events(self, interval: float = 3.0):
        while True:
            plays = self.safe_fetch_live_pbp()
            new = diff_new_events(self.cache, plays, key="eventId")
            for evt in new:
                yield evt
            self.cache = plays
            time.sleep(interval)

    def build_payload(
        self, games_today: List[Dict[str, Any]], recent_n: int = 5
    ) -> Dict[str, Any]:
        """
        Return a dict with:
          - markdown: a Markdown snippet for this game
          - snapshot: the JSON summary (status, teams, players, recentPlays)
          - events:   the full list of live plays
        """
        # 1) snapshot & events
        snapshot = self.fetch_grouped_snapshot(recent_n=recent_n)
        events = self.safe_fetch_live_pbp()

        # 2) human Markdown
        #    (we only need the 1-6 blocks for THIS game, so pass [this] as games_today)
        md_today = format_today_games(games_today)
        md_snap = format_snapshot_markdown(
            snapshot, self.game_id, max_players=3, recent_n=recent_n
        )

        payload = {
            "gameId": self.game_id,
            "markdown": "\n\n".join([md_today, md_snap]),
            "snapshot": snapshot,
            "events": events,
        }
        return payload

    def gamestream_to_markdown(
        self,
        recent_n: int = 5,
        max_events: int = 750,
        games_today: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Return the live six‑section markdown (1. Today's Games + 2–6 Snapshot)
        for this game, truncated to at most `max_events` lines.
        """
        if games_today is None:
            games_today = self.get_today_games()

        # Sections 1 + 2–6
        md1 = format_today_games(games_today)
        snapshot = self.fetch_grouped_snapshot(recent_n=recent_n)
        md2 = format_snapshot_markdown(
            snapshot, self.game_id, max_players=3, recent_n=recent_n
        )

        # Combine & split lines
        all_lines = (md1 + "\n\n" + md2).splitlines()

        # Truncate
        if len(all_lines) > max_events:
            all_lines = all_lines[:max_events] + ["…"]

        return "\n".join(all_lines)


# --------------------------------------------------------------------------- #
# ──   MAIN DATA CLASS                                                       ──
# --------------------------------------------------------------------------- #
@dataclass
class PastGamesPlaybyPlay:
    """Easy access to historical play-by-play with fuzzy-friendly search."""

    game_id: str

    _start_period: int = 1
    _start_clock: Optional[str] = None

    @staticmethod
    def normalize_start_period(value: Union[int, str]) -> int:
        """
        Normalize any Quarter input into an int 1–4.
        Accepts things like: 1, "1st", "Quarter 2", "Q3", "third quarter", "quarter one", etc.
        """
        if isinstance(value, int):
            if 1 <= value <= 4:
                return value
            raise ValueError(f"start_period int out of range: {value}")

        text = value.strip().lower()
        # replace common punctuation with spaces
        text = re.sub(r"[^\w\s]", " ", text)

        # 1) look for a digit 1–4
        m = re.search(r"\b([1-4])\b", text)
        if m:
            return int(m.group(1))

        # 2) look for ordinal AND cardinal words
        word_map = {
            "first": 1,
            "1st": 1,
            "one": 1,
            "second": 2,
            "2nd": 2,
            "two": 2,
            "third": 3,
            "3rd": 3,
            "three": 3,
            "fourth": 4,
            "4th": 4,
            "four": 4,
        }
        for key, num in word_map.items():
            if re.search(rf"\b{key}\b", text):
                return num

        # 3) catch shorthand like 'q1', 'quarter 2', 'quarter three'
        for num in range(1, 5):
            if (
                f"q{num}" in text
                or re.search(rf"quarter\s+{num}\b", text)
                or re.search(
                    rf"quarter\s+{list(word_map.keys())[list(word_map.values()).index(num)]}\b",
                    text,
                )
            ):
                return num

        raise ValueError(f"Could not normalize start_period: {value!r}")

    @staticmethod
    def normalize_start_clock(value: str) -> str:
        """
        Normalize any time input into "MM:SS".
        Supports:
          - "7:15", "7.15"
          - "7 m", "7 min", "7 minutes"
          - "30 s", "30 sec", "30 secs", "30 second(s)"
          - Bare digits ("5") → treated as "5:00"
          - Pure seconds ("5 sec", "5 secs") → "0:05"
        Raises ValueError for minutes >12 or seconds ≥60.
        """
        text = value.strip().lower().replace(".", ":")

        # 1) explicit minute patterns
        m_min = re.search(r"(\d+)\s*(?:m|min|minutes?)", text)
        mins = int(m_min.group(1)) if m_min else None

        # 2) explicit second patterns (including 'secs')
        m_sec = re.search(r"(\d+)\s*(?:s|sec|secs|second(?:s)?)", text)
        secs = int(m_sec.group(1)) if m_sec else 0

        # 3) colon-format "M:SS" or "MM:SS"
        if mins is None and ":" in text:
            a, b = text.split(":", 1)
            try:
                mins = int(a)
                secs = int(b)
            except ValueError:
                pass

        # 4) pure-seconds fallback: "5 secs" → mins=0, secs=5
        if mins is None and m_sec:
            mins = 0

        # 5) bare-digit as minutes: "5" → "5:00"
        if mins is None:
            m_digit = re.search(r"\b(\d{1,2})\b", text)
            if m_digit:
                mins = int(m_digit.group(1))

        # 6) still nothing? error out
        if mins is None:
            raise ValueError(f"Could not normalize start_clock: {value!r}")

        # 7) enforce NBA quarter ranges
        if not (0 <= mins <= 12):
            raise ValueError(f"Minute out of range (0–12): {mins}")
        if not (0 <= secs < 60):
            raise ValueError(f"Second out of range (0–59): {secs}")

        # 8) finalize
        return f"{mins}:{secs:02d}"

    @classmethod
    def from_game_id(
        cls,
        game_id: Optional[str] = None,
        *,
        game_date: Optional[Union[str, pd.Timestamp]] = None,
        team: Optional[str] = None,
        start_period: Union[int, str] = 1,
        start_clock: Optional[str] = None,
        show_choices: bool = True,
        timeout: float = 10.0,
    ) -> "PastGamesPlaybyPlay":
        """
        Create a PastGamesPlaybyPlay either from:
          • a 10-digit game_id, or
          • a (game_date, team) pair.
        You can also supply `start_period` and `start_clock` defaults
        for any subsequent streaming calls.
        """
        # 1) If they gave us a real game_id, use it:
        if game_id and _GAMEID_RE.match(game_id):
            gid = game_id

        # 2) Otherwise, they must supply both date+team:
        else:
            if not (game_date and team):
                raise ValueError(
                    "Either a valid `game_id` or both `game_date` and `team` must be provided."
                )
            # normalize the date
            gd = normalize_date(game_date)
            # delegate to your existing from_team_date under the hood
            inst = cls.from_team_date(
                when=gd, team=team, timeout=timeout, show_choices=show_choices
            )
            gid = inst.game_id

        inst = cls(game_id=gid, _start_period=start_period, _start_clock=start_clock)
        # normalize the incoming period/clock before we store them
        norm_period = cls.normalize_start_period(start_period)
        norm_clock = (
            cls.normalize_start_clock(start_clock) if start_clock is not None else None
        )

        inst = cls(game_id=gid, _start_period=norm_period, _start_clock=norm_clock)
        # preserve the date if it was explicitly set
        if game_date:
            inst.set_date(normalize_date(game_date).strftime("%Y-%m-%d"))
        return inst

    @classmethod
    def search(
        cls,
        when: Union[str, pd.Timestamp],
        team: Optional[str] = None,
        home: Optional[str] = None,
        away: Optional[str] = None,
        *,
        timeout: float = 10.0,
        show_choices: bool = True,
    ) -> "PastGamesPlaybyPlay":
        """
        Find a past game by date + (optional) team filters.
        Can use just 'team' to search in both home and away teams,
        or use specific 'home'/'away' for more targeted filtering.

        Team args accept:
        • "Knicks", "NY", "NYK" • 1610612752 • "New York"
        """
        logger.debug(
            f"[DEBUG] Searching for game on {when} with team={team}, home={home}, away={away}"
        )

        # 1) canonical YYYY-MM-DD for the API
        game_date = normalize_date(when)
        logger.debug(f"[DEBUG] Normalized date: {game_date.strftime('%Y-%m-%d')}")

        try:
            games = _scoreboard_df(game_date.strftime("%Y-%m-%d"), timeout)
            logger.debug(
                f"[DEBUG] Found {len(games)} games on {game_date.strftime('%Y-%m-%d')}"
            )

            if games.empty:
                raise RuntimeError(
                    f"No games found on {game_date.strftime('%Y-%m-%d')}"
                )

            # Print available games for debugging
            logger.debug("[DEBUG] Available games:")
            for _, row in games.iterrows():
                home_name = (
                    get_team_name(row["HOME_TEAM_ID"]) or f"Team {row['HOME_TEAM_ID']}"
                )
                away_name = (
                    get_team_name(row["VISITOR_TEAM_ID"])
                    or f"Team {row['VISITOR_TEAM_ID']}"
                )
                logger.debug(
                    f"[DEBUG] GAME_ID: {row['GAME_ID']}, "
                    f"{away_name} ({row['VISITOR_TEAM_ID']}) @ "
                    f"{home_name} ({row['HOME_TEAM_ID']})"
                )

            # Apply team filter (to both home and away)
            if team:
                logger.debug(f"[DEBUG] Filtering for any team matching: {team}")
                team_id = get_team_id_from_abbr(team) or get_team_id(team)

                if team_id:
                    logger.debug(f"[DEBUG] Resolved team ID: {team_id}")
                    team_id_int = int(team_id)
                    filtered_games = games[
                        games["HOME_TEAM_ID"].eq(team_id_int)
                        | games["VISITOR_TEAM_ID"].eq(team_id_int)
                    ]

                    if not filtered_games.empty:
                        games = filtered_games
                        logger.debug(
                            f"[DEBUG] After team filter: {len(games)} games remaining"
                        )
                    else:
                        logger.debug(
                            f"[WARNING] No games found with team ID {team_id_int}"
                        )
                else:
                    logger.debug(f"[WARNING] Could not resolve team ID for '{team}'")
                    # Try text-based search on team names
                    filtered_games = pd.DataFrame()
                    for _, row in games.iterrows():
                        home_name = get_team_name(row["HOME_TEAM_ID"]) or ""
                        away_name = get_team_name(row["VISITOR_TEAM_ID"]) or ""
                        if (
                            team.lower() in home_name.lower()
                            or team.lower() in away_name.lower()
                        ):
                            filtered_games = pd.concat(
                                [filtered_games, row.to_frame().T]
                            )

                    if not filtered_games.empty:
                        games = filtered_games
                        logger.debug(
                            f"[DEBUG] After team name filter: {len(games)} games remaining"
                        )
                    else:
                        logger.debug(
                            f"[WARNING] No games found with team name containing '{team}'"
                        )

            # Apply home filter if provided
            if home:
                logger.debug(f"[DEBUG] Filtering for home team: {home}")
                hid = get_team_id_from_abbr(home) or get_team_id(home)

                if hid:
                    logger.debug(f"[DEBUG] Resolved home team ID: {hid}")
                    hid_int = int(hid)
                    filtered_home = games[games["HOME_TEAM_ID"].eq(hid_int)]

                    if not filtered_home.empty:
                        games = filtered_home
                        logger.debug(
                            f"[DEBUG] After home filter: {len(games)} games remaining"
                        )
                    else:
                        logger.debug(
                            f"[WARNING] No games found with home team ID {hid_int}"
                        )
                        # Try with team name text search
                        for _, row in games.iterrows():
                            home_name = get_team_name(row["HOME_TEAM_ID"]) or ""
                            if home.lower() in home_name.lower():
                                filtered_home = pd.concat(
                                    [filtered_home, row.to_frame().T]
                                )

                        if not filtered_home.empty:
                            games = filtered_home
                            logger.debug(
                                f"[DEBUG] After home name filter: {len(games)} games remaining"
                            )
                        else:
                            logger.debug(
                                f"[WARNING] No games found with home team matching '{home}'"
                            )
                else:
                    logger.debug(
                        f"[WARNING] Could not resolve team ID for home: '{home}'"
                    )

            # Apply away filter if provided
            if away:
                logger.debug(f"[DEBUG] Filtering for away team: {away}")
                aid = get_team_id_from_abbr(away) or get_team_id(away)

                if aid:
                    logger.debug(f"[DEBUG] Resolved away team ID: {aid}")
                    aid_int = int(aid)
                    filtered_away = games[games["VISITOR_TEAM_ID"].eq(aid_int)]

                    if not filtered_away.empty:
                        games = filtered_away
                        logger.debug(
                            f"[DEBUG] After away filter: {len(games)} games remaining"
                        )
                    else:
                        logger.debug(
                            f"[WARNING] No games found with away team ID {aid_int}"
                        )
                        # Try with team name text search
                        for _, row in games.iterrows():
                            away_name = get_team_name(row["VISITOR_TEAM_ID"]) or ""
                            if away.lower() in away_name.lower():
                                filtered_away = pd.concat(
                                    [filtered_away, row.to_frame().T]
                                )

                        if not filtered_away.empty:
                            games = filtered_away
                            logger.debug(
                                f"[DEBUG] After away name filter: {len(games)} games remaining"
                            )
                        else:
                            logger.debug(
                                f"[WARNING] No games found with away team matching '{away}'"
                            )
                else:
                    logger.debug(
                        f"[WARNING] Could not resolve team ID for away: '{away}'"
                    )

            if games.empty:
                raise RuntimeError(
                    f"No games on {game_date.strftime('%Y-%m-%d')} that match the filters"
                )

            if show_choices and len(games) > 1:
                logger.debug(
                    "Multiple games found; pick one by index or refine the filter:"
                )
                for i, (_, row) in enumerate(games.iterrows(), 1):
                    game_dict = _create_game_dict_from_row(row)
                    logger.debug(f"{i:>2}. {format_game(game_dict)}")
                idx = int(input("Choice [1]: ") or 1) - 1
                game_id = str(games.iloc[idx]["GAME_ID"])
            else:
                game_id = str(games.iloc[0]["GAME_ID"])
                logger.debug(f"[DEBUG] Selected game_id: {game_id}")

            instance = cls(game_id)
            instance.set_date(game_date.strftime("%Y-%m-%d"))
            return instance
        except Exception as e:
            logger.debug(f"[ERROR] Error in search method: {e}")
            raise

    # ---------- main fetch ---------------------------------------------------
    def get_pbp(
        self,
        start_period: int = 1,
        end_period: int = 10,
        *,
        as_records: bool = True,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        """
        Fetch historical play-by-play via PlayByPlayFetcher,
        returning either DataFrames or record dicts.
        """
        # 1) normalized PBP
        df = PlayByPlayFetcher(self.game_id, start_period, end_period).fetch()

        # 2) raw AvailableVideo
        resp = PlayByPlayV3(
            game_id=self.game_id, start_period=start_period, end_period=end_period
        )
        avail_df = resp.get_data_frames()[0]

        # 3) return exactly the same API shape
        if as_records:
            return {
                "AvailableVideo": avail_df.to_dict("records"),
                "PlayByPlay": df.to_dict("records"),
            }
        return {"AvailableVideo": avail_df, "PlayByPlay": df}

    # ---------- niceties -----------------------------------------------------
    def describe(self, timeout: float = 10.0) -> None:
        """
        Print detailed information about the game.
        """
        try:
            logger.debug(f"[DEBUG] Looking for game {self.game_id} on date {self.date}")
            hdr = _scoreboard_df(self.date, timeout)

            if hdr.empty:
                logger.debug(f"No games found on {self.date}")
                return

            logger.debug(
                f"[DEBUG] Available GAME_IDs in scoreboard: {hdr['GAME_ID'].tolist()}"
            )

            # Try both integer and string comparison
            for _, row in hdr.iterrows():
                if str(row["GAME_ID"]) == self.game_id:
                    logger.debug(f"[DEBUG] Found match for game_id {self.game_id}")
                    game_dict = _create_game_dict_from_row(row)
                    logger.debug(format_game(game_dict))
                    return

            # If we reach here, no match was found
            logger.debug(f"No game data found for ID {self.game_id} on {self.date}")
            logger.debug("Available games on this date:")
            for _, row in hdr.iterrows():
                game_dict = _create_game_dict_from_row(row)
                logger.debug(
                    f"- GAME_ID: {row['GAME_ID']}, {game_dict['visitor_team']['full_name']} @ {game_dict['home_team']['full_name']}"
                )
        except Exception as e:
            logger.debug(f"Error in describe method: {e}")

    @property
    def date(self) -> str:
        """
        Derive YYYY-MM-DD from the embedded game ID (works post-2001).
        If a date was explicitly set, use that instead.
        """
        # Check if we have a stored date first
        if hasattr(self, "_date") and self._date:
            return self._date

        # Otherwise, extract from game_id
        # Format of game_id: RRYYMMDDRRR, where YY is season year, MMDD is month/day
        try:
            season_fragment = int(self.game_id[3:5])  # e.g. '24'
            month = int(self.game_id[5:7])  # e.g. '12'
            day = int(self.game_id[7:9])  # e.g. '25'

            season_year = (
                2000 + season_fragment
                if season_fragment < 50
                else 1900 + season_fragment
            )

            # Handle case where month/day might be invalid
            try:
                # Try to create a date with the extracted components
                from datetime import date

                game_date = date(season_year, month, day)
                return game_date.strftime("%Y-%m-%d")
            except ValueError:
                # If date is invalid, fall back to default
                logger.debug(
                    f"[DEBUG] Invalid date extracted from game_id: {season_year}-{month}-{day}"
                )
                season_year = 2000 + season_fragment
                return normalize_date(f"{season_year}-10-01").strftime("%Y-%m-%d")
        except Exception as e:
            logger.debug(
                f"[DEBUG] Error extracting date from game_id {self.game_id}: {e}"
            )
            # Default fallback
            season_fragment = (
                int(self.game_id[3:5]) if self.game_id[3:5].isdigit() else 0
            )
            season_year = (
                2000 + season_fragment
                if season_fragment < 50
                else 1900 + season_fragment
            )
            return normalize_date(f"{season_year}-10-01").strftime("%Y-%m-%d")

    def set_date(self, date_str: str) -> "PastGamesPlaybyPlay":
        """
        Explicitly set the date to use for API calls.
        """
        self._date = normalize_date(date_str).strftime("%Y-%m-%d")
        return self

    # ---------------------------------------------------------------------------
    # ──  NEW CONVENIENCE CONSTRUCTOR inside PastGamesPlaybyPlay               ──
    # ---------------------------------------------------------------------------

    @classmethod
    def from_team_date(
        cls,
        when: Union[str, pd.Timestamp],
        team: str,
        *,
        opponent: Optional[str] = None,
        side: Literal["any", "home", "away"] = "any",
        timeout: float = 10.0,
        show_choices: bool = True,
    ) -> "PastGamesPlaybyPlay":
        """
        Find **one** game on the given date where `team` participated.

        • `team` may be abbreviation ("PHX"), nickname ("Suns"), city ("Phoenix"), etc.
        • `opponent` (optional) narrows the search to games that also include that team.
        • `side`   – "home", "away", or "any"  (default "any").

        If more than one game matches the criteria you'll be prompted to choose —
        set `show_choices=False` to auto-pick the first row.
        """
        # 1) canonical date & scoreboard
        game_date = normalize_date(when)
        df = _scoreboard_df(game_date.strftime("%Y-%m-%d"), timeout)
        logger.debug(f"[SEARCH] {len(df)} games on {game_date:%Y-%m-%d}")
        logger.debug("[SEARCH] sample rows:")
        for _, r in df.head(3).iterrows():
            logger.debug(
                f"  • GAME_ID={r.GAME_ID}  HOME={r.HOME_TEAM_ID} VIS={r.VISITOR_TEAM_ID} STATUS={r.GAME_STATUS_TEXT}"
            )

        team_ids = _resolve_team_ids(team)
        logger.debug(f"[SEARCH] resolved '{team}' → team_ids={team_ids!r}")

        # filter for team
        df = df[
            df["HOME_TEAM_ID"].isin(team_ids) | df["VISITOR_TEAM_ID"].isin(team_ids)
        ]
        logger.debug(
            f"[SEARCH] after team filter → {len(df)} rows: {df['GAME_ID'].tolist()}"
        )

        if df.empty:
            raise RuntimeError(f"{team!r} did not play on {game_date:%Y-%m-%d'}")

        # 3) optional opponent filter
        if opponent:
            opp_ids = _resolve_team_ids(opponent)
            if not opp_ids:
                raise ValueError(f"Could not resolve opponent: {opponent!r}")
            df = df[
                df["HOME_TEAM_ID"].isin(opp_ids) | df["VISITOR_TEAM_ID"].isin(opp_ids)
            ]
            if df.empty:
                raise RuntimeError(
                    f"{team} vs {opponent} not found on {game_date:%Y-%m-%d}"
                )

        # 4) optional side restriction
        if side != "any":
            col = "HOME_TEAM_ID" if side == "home" else "VISITOR_TEAM_ID"
            df = df[df[col].isin(team_ids)]
            if df.empty:
                raise RuntimeError(
                    f"{team} were not the {side} team on {game_date:%Y-%m-%d}"
                )

        # 5) choose & return
        if show_choices and len(df) > 1:
            logger.debug("More than one game matches — pick one:")
            for i, (_, row) in enumerate(df.reset_index().iterrows(), 1):
                gd = _create_game_dict_from_row(row)
                logger.debug(f"{i:>2}. {format_game(gd)}  (GAME_ID {row.GAME_ID})")
            idx = int(input("Choice [1]: ") or 1) - 1
            chosen = df.iloc[idx]
        else:
            chosen = df.iloc[0]

        inst = cls(str(chosen["GAME_ID"]))
        # Explicitly store the date so .describe() uses the right day
        inst.set_date(game_date.strftime("%Y-%m-%d"))
        return inst

    def _fmt_top_historical(self, stat: str, summary: dict[str, Any]) -> str:
        """
        Build the '🏀 Top STAT | Home: ... | Away: ...' line
        from a historical summary dict (output of _snapshot_from_past_game).
        """

        def top_for(side: Literal["home", "away"]) -> str:
            players = summary["players"][side]
            pairs = [(p["name"], p["statistics"].get(stat, 0)) for p in players]
            best = sorted(pairs, key=lambda x: x[1], reverse=True)[:3]
            return ", ".join(f"{nm} ({val} {stat})" for nm, val in best)

        return f"🏀 Top {stat.upper():<3} | Home: {top_for('home')}  |  Away: {top_for('away')}"

    # ─── Replace your playbyplay_to_markdown method in PastGamesPlaybyPlay ────
    def playbyplay_to_markdown(
        self,
        max_lines: int = 750,
        batch_size: int = 1,
        *,
        start_period: Optional[int] = None,
        end_period: Optional[int] = None,
        start_clock: Optional[str] = None,
    ) -> str:
        # 0) Override defaults if specified
        if start_period is not None:
            self._start_period = start_period
        if start_clock is not None:
            self._start_clock = start_clock

        # 1) Fetch all the PBP records for that period
        try:
            full = self.get_pbp(
                start_period=self._start_period,
                end_period=end_period or self._start_period,
                as_records=True,
            )
            records = full["PlayByPlay"]
        except Exception as e:
            logger.debug(f"[DEBUG] get_pbp failed for {self.game_id}: {e}")
            return f"_Historical play‑by‑play not available for {self.game_id}._"

        # 2) If we have a start_clock, slice out anything before it
        if self._start_clock:
            try:
                idx = self.find_event_index(
                    period=self._start_period,
                    clock=self._start_clock,
                    start_period=self._start_period,
                    end_period=end_period,
                )
                records = records[idx:]
            except Exception as e:
                logger.debug(f"[DEBUG] find_event_index failed: {e}")

        lines: List[str] = []

        # 3) Build the stat‐leader snapshot
        try:
            summary = _snapshot_from_past_game(self.game_id, records)
            for stat in (
                "points",
                "rebounds",
                "assists",
                "steals",
                "blocks",
                "turnovers",
            ):
                if len(lines) >= max_lines:
                    break
                lines.append(self._fmt_top_historical(stat, summary))
            if len(lines) < max_lines:
                lines.append("")  # blank line separator
        except Exception as e:
            logger.debug(f"[DEBUG] snapshot failed for {self.game_id}: {e}")
            lines.append(
                f"_Stat summary not available for {self.game_id}, showing raw PBP:_"
            )
            lines.append("")

        # 4) Now append the raw play‑by‑play
        count = 0
        for rec in records:
            if count >= max_lines:
                lines.append("…")
                break

            per = rec.get("period") or rec.get("quarter") or "?"
            clk = rec.get("clock") or rec.get("pctimestring") or ""
            try:
                clk = parse_iso_clock(clk)
            except:
                pass

            home = rec.get("score_home") or rec.get("scoreHome") or "0"
            away = rec.get("score_away") or rec.get("scoreAway") or "0"
            desc = rec.get("description") or rec.get("actionType") or ""
            lines.append(f"[Q{per} {clk}] {home}–{away} | {desc}")
            count += 1

        return "\n".join(lines)

    # Helper copied from get_contextual_pbp
    def _fmt_top(self, stat: str) -> str:
        summary = group_live_game(self.game_id, recent_n=5)

        def top_for(side: str) -> str:
            raw = summary["players"][side]
            pairs = [
                (
                    p.get("name") or p.get("playerName") or "?",
                    p.get("statistics", {}).get(stat, 0),
                )
                for p in raw
            ]
            best = sorted(pairs, key=lambda x: x[1], reverse=True)[:3]
            return ", ".join(f"{nm} ({val} {stat})" for nm, val in best)

        return f"🏀 Top {stat.upper():<3} | Home: {top_for('home')}  |  Away: {top_for('away')}"

    @staticmethod
    def get_games_on_date(game_date: date, timeout: float = 10.0) -> list[str]:
        date_str = game_date.strftime("%m/%d/%Y")
        sb = _SBv2.ScoreboardV2(game_date=date_str, timeout=timeout)
        df = sb.get_data_frames()[0]
        return df["GAME_ID"].astype(str).tolist()

    @staticmethod
    def _iso_to_seconds(iso: str) -> float:
        m = re.match(r"PT(\d+)M([\d\.]+)S", iso)
        if not m:
            return 0.0
        minutes, secs = int(m.group(1)), float(m.group(2))
        return minutes * 60 + secs

    def find_event_index(
        self,
        period: int,
        clock: str,
        *,
        start_period: int = 1,
        end_period: Optional[int] = None,
    ) -> int:
        """Locate the first event at or before a given quarter & clock."""
        df = PlayByPlayFetcher(
            game_id=self.game_id, start_period=start_period, end_period=end_period or 4
        ).fetch()

        # debug print (you can remove once you're confident)
        logger.debug("[DEBUG] PBP columns: %s", df.columns.tolist())

        # parse the target time (mm:ss → seconds)
        mins, secs = map(int, clock.split(":"))
        target = mins * 60 + secs

        for idx, row in df.iterrows():
            # now that fetch() guarantees 'period' & 'clock'
            if row["period"] == period and self._iso_to_seconds(row["clock"]) <= target:
                return idx
        return 0

    def _fmt_top(self, stat: str) -> str:
        summary = group_live_game(self.game_id, recent_n=5)

        def top_for(side: str) -> str:
            raw = summary["players"][side]
            pairs = [
                (
                    p.get("name") or p.get("playerName") or "?",
                    p.get("statistics", {}).get(stat, 0),
                )
                for p in raw
            ]
            best = sorted(pairs, key=lambda x: x[1], reverse=True)[:3]
            return ", ".join(f"{nm} ({val} {stat})" for nm, val in best)

        return f"🏀 Top {stat.upper():<3} | Home: {top_for('home')}  |  Away: {top_for('away')}"

    def stream_pbp(
        self,
        *,
        start_period: int = 1,
        end_period: Optional[int] = None,
        start_clock: Optional[str] = None,
        batch_size: int = 1,
    ):
        if start_clock:
            idx = self.find_event_index(
                period=start_period,
                clock=start_clock,
                start_period=start_period,
                end_period=end_period,
            )
        else:
            idx = 0
        fetcher = PlayByPlayFetcher(
            game_id=self.game_id,
            start_period=start_period,
            end_period=end_period,
            start_event_idx=idx,
        )
        yield from fetcher.stream(batch_size=batch_size)

    # ── Updated get_contextual_pbp to honor end_period ─────────────────────────
    def get_contextual_pbp(
        self,
        batch_size: int = 1,
        *,
        start_period: Optional[int] = None,
        end_period: Optional[int] = None,
        start_clock: Optional[str] = None,
    ) -> Iterable[str]:
        """
        1) Yield top‑stat lines.
        2) Blank line.
        3) Stream plays [Q<period> <clock>] … via stream_pbp().
           Honors optional start_period, end_period, start_clock.
        """
        # (unchanged) top‑stat lines
        summary = group_live_game(self.game_id, recent_n=5)
        for stat in ("points", "rebounds", "assists", "steals", "blocks", "turnovers"):
            yield self._fmt_top(stat)
        yield ""

        # Determine which bounds to use
        sp = start_period or getattr(self, "_start_period", 1)
        sc = start_clock or getattr(self, "_start_clock", None)
        ep = end_period  # may be None → stream to end

        # Stream and format each play
        for ev in self.stream_pbp(
            start_period=sp, end_period=ep, start_clock=sc, batch_size=batch_size
        ):
            recs = ev if isinstance(ev, list) else [ev]
            for r in recs:
                # same formatting logic as before...
                clk = parse_iso_clock(r.get("clock", "") or "")
                home = r.get("score_home") or r.get("scoreHome") or "0"
                away = r.get("score_away") or r.get("scoreAway") or "0"
                period = r.get("period", "?")
                # swap last‑name → full name if available
                pid = r.get("person_id") or r.get("personId") or 0
                full = pid and get_player_name(pid) or None
                raw = (r.get("description") or r.get("actionType") or "").strip()
                orig = r.get("player_name") or raw.split(" ", 1)[0] or ""
                desc = (
                    (full + raw[len(orig) :])
                    if (full and orig and raw.startswith(orig))
                    else raw
                )
                yield f"[Q{period} {clk}] {home}–{away} | {desc}"


# ── Orchestrator: date+team → Markdown ─────────────────────────────────────
from datetime import date as _date
from datetime import datetime


def to_markdown_for_date_team(
    when: Union[str, _date],
    team: str,
    *,
    start_period: int = 1,
    end_period: int = 4,
    start_clock: Optional[str] = None,
    recent_n: int = 5,
    max_lines: int = 750,
) -> str:
    """
    Orchestrator:
      - If the game hasn’t started yet → show scheduled tip‑off
      - If in progress            → live gamestream
      - Otherwise (final or past) → historical PBP via PastGamesPlaybyPlay
    """

    # --- Debug: Inputs ---
    logger.debug(
        f"[to_md] called with when={when!r}, team={team!r}, "
        f"start_period={start_period}, end_period={end_period}, start_clock={start_clock}"
    )

    # 1) locate the instance via date+team
    inst = PastGamesPlaybyPlay.from_team_date(when=when, team=team, show_choices=False)
    game_id = inst.game_id

    # 2) compare to today
    raw_date = normalize_date(when)
    game_date = raw_date.date() if isinstance(raw_date, datetime) else raw_date
    today = _date.today()
    logger.debug(f"[to_md] normalized game_date={game_date}  today={today}")

    # assume not pregame until proven otherwise
    is_pregame = False
    status_text = ""

    # ─── Live/pregame logic ─────────────────────────────────────
    if game_date >= today:
        try:
            info = get_game_info(game_id)
            status_text = info.get("gameStatusText", "").lower()
            logger.debug(f"[to_md] liveData status_text={status_text!r}")
        except RuntimeError as e:
            # treat HTTP 403 or future‐date as pregame
            if "403" in str(e) or game_date > today:
                is_pregame = True
                logger.debug(f"[to_md] marking as pregame due to {e}")
            else:
                raise

        # ── Pregame ───────────────────────────────────────────────
        if is_pregame or any(
            tok in status_text for tok in ("pregame", "am et", "pm et")
        ):
            df = _scoreboard_df(game_date.strftime("%Y-%m-%d"))
            row = df[df["GAME_ID"].astype(str) == game_id].iloc[0]
            away_name = get_team_name(row["VISITOR_TEAM_ID"]) or row["VISITOR_TEAM_ID"]
            home_name = get_team_name(row["HOME_TEAM_ID"]) or row["HOME_TEAM_ID"]
            tip_time = row.get("GAME_STATUS_TEXT", "").strip()
            logger.debug(f"[to_md] returning PREGAME tip-off for {game_id}")
            return (
                "### 1. Today's Games\n"
                f"- **{game_id}** {away_name} @ {home_name}  (Tip‑off at {tip_time})"
            )

        # ── Live ─────────────────────────────────────────────────
        if _is_game_live(status_text):
            logger.debug(f"[to_md] returning LIVE gamestream for {game_id}")
            gs = GameStream(game_id)
            games_today = GameStream.get_today_games()
            return gs.gamestream_to_markdown(
                recent_n=recent_n, max_events=max_lines, games_today=games_today
            )

    # ─── Final / Historical ──────────────────────────────────────
    logger.debug(f"[to_md] falling through to HISTORICAL for {game_id}")
    try:
        result = inst.playbyplay_to_markdown(
            max_lines=max_lines,
            batch_size=1,
            start_period=start_period,
            end_period=end_period,
            start_clock=start_clock,
        )
        logger.debug(
            f"[to_md] historical markdown length={len(result.splitlines())} lines"
        )
        return result
    except (IndexError, RuntimeError) as e:
        logger.debug(f"[to_md] Historical PBP failed for {game_id}: {e}")
        return f"_Play‑by‑play not available for finished game {game_id}._"


# tests
# ─── NEW: Historical Smoke-Test Runner via PastGamesPlaybyPlay ─────────────────
# ─── UPDATED: Historical Smoke-Test Runner via PastGamesPlaybyPlay ─────────────────
def run_historical_smoke_tests_via_class():
    """
    Smoke-test a handful of historical scenarios using only (date, team):
      • 1996-97 opener
      • Christmas 2023
      • 1995-96 opener (pre-PBP: expected failure)
    """
    scenarios = [
        {
            "params": {"game_date": "1996-11-01", "team": "Bulls"},
            "description": "1996-97 season opener via date+team (should succeed)",
        },
        {
            "params": {"game_date": "2023-12-25", "team": "PHX"},
            "description": "Christmas Day 2023 via date+team (should succeed)",
        },
        {
            "params": {"game_date": "1995-11-01", "team": "Bulls"},
            "description": "1995-96 opener via date+team (pre-PBP; expected failure)",
        },
    ]

    logger.debug(
        "\n\n# ── HISTORICAL DATA SMOKE TESTS VIA PastGamesPlaybyPlay ─────────────────────────\n"
    )
    for sc in scenarios:
        desc = sc["description"]
        gd, tm = sc["params"]["game_date"], sc["params"]["team"]
        logger.debug(f"\n=== [Date+Team] {desc} (date={gd!r}, team={tm!r}) ===")
        try:
            # build our instance via the class factory
            inst = PastGamesPlaybyPlay.from_game_id(
                game_date=gd, team=tm, show_choices=False  # auto-pick first if multiple
            )
            # fetch only Q1 events
            result = inst.get_pbp(start_period=1, end_period=1, as_records=True)
            plays = result["PlayByPlay"]
            logger.debug(f"✔️  Retrieved {len(plays)} plays")
            if plays:
                logger.debug("Sample columns:", list(plays[0].keys()))
        except Exception as e:
            logger.debug(f"⚠️  Error: {e}")


class PlaybyPlayLiveorPast:
    """
    Orchestrator class for generating markdown based on date and team.
    Combines GameStream for live data and PastGamesPlaybyPlay for historical data.
    """

    def __init__(
        self,
        when: Union[str, _date],
        team: str,
        start_period: int = 1,
        end_period: int = 4,
        start_clock: Optional[str] = None,
        recent_n: int = 5,
        max_lines: int = 750,
    ):
        # Store parameters
        self.when = when
        self.team = team
        self.start_period = start_period
        self.end_period = end_period
        self.start_clock = start_clock
        self.recent_n = recent_n
        self.max_lines = max_lines

        # Instantiate historical PBP handler
        self.inst = PastGamesPlaybyPlay.from_team_date(
            when=self.when, team=self.team, show_choices=False
        )
        self.game_id = self.inst.game_id

    def to_markdown(self) -> str:
        """
        Generate markdown depending on game status:
          - Pregame: scheduled tip-off
          - Live: live game stream
          - Historical: past play-by-play
        """
        logger.debug(
            f"[ToMarkdown] called with when={self.when!r}, team={self.team!r}, "
            f"start_period={self.start_period}, end_period={self.end_period}, "
            f"start_clock={self.start_clock}"
        )

        # Normalize the provided date
        raw_date = normalize_date(self.when)
        game_date = raw_date.date() if isinstance(raw_date, datetime) else raw_date
        today = _date.today()
        logger.debug(f"[ToMarkdown] normalized game_date={game_date}  today={today}")

        # Default to not pregame
        is_pregame = False
        status_text = ""

        # Check future or today for live/pregame
        if game_date >= today:
            try:
                info = get_game_info(self.game_id)
                status_text = info.get("gameStatusText", "").lower()
                logger.debug(f"[ToMarkdown] liveData status_text={status_text!r}")
            except RuntimeError as e:
                # HTTP 403 or future date signals pregame
                if "403" in str(e) or game_date > today:
                    is_pregame = True
                    logger.debug(f"[ToMarkdown] marking as pregame due to {e}")
                else:
                    raise

            # Pregame scenario
            if is_pregame or any(
                tok in status_text for tok in ("pregame", "am et", "pm et")
            ):
                df = _scoreboard_df(game_date.strftime("%Y-%m-%d"))
                row = df[df["GAME_ID"].astype(str) == self.game_id].iloc[0]
                away_name = (
                    get_team_name(row["VISITOR_TEAM_ID"]) or row["VISITOR_TEAM_ID"]
                )
                home_name = get_team_name(row["HOME_TEAM_ID"]) or row["HOME_TEAM_ID"]
                tip_time = row.get("GAME_STATUS_TEXT", "").strip()
                logger.debug(
                    f"[ToMarkdown] returning PREGAME tip-off for {self.game_id}"
                )
                return (
                    "### 1. Today's Games\n"
                    f"- **{self.game_id}** {away_name} @ {home_name}  (Tip‑off at {tip_time})"
                )

            # Live scenario
            if _is_game_live(status_text):
                logger.debug(
                    f"[ToMarkdown] returning LIVE gamestream for {self.game_id}"
                )
                gs = GameStream(self.game_id)
                games_today = GameStream.get_today_games()
                return gs.gamestream_to_markdown(
                    recent_n=self.recent_n,
                    max_events=self.max_lines,
                    games_today=games_today,
                )

        # Fallback to historical PBP
        logger.debug(f"[ToMarkdown] falling through to HISTORICAL for {self.game_id}")
        try:
            result = self.inst.playbyplay_to_markdown(
                max_lines=self.max_lines,
                batch_size=1,
                start_period=self.start_period,
                end_period=self.end_period,
                start_clock=self.start_clock,
            )
            logger.debug(
                f"[ToMarkdown] historical markdown length={len(result.splitlines())} lines"
            )
            return result
        except (IndexError, RuntimeError) as e:
            logger.debug(f"[ToMarkdown] Historical PBP failed for {self.game_id}: {e}")
            return f"_Play‑by‑play not available for finished game {self.game_id}._"


# ─── USAGE ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # --------------------------------------------------------------------------- #
    # ──  REALTIME EXAMPLE USAGE                                                         ──
    # --------------------------------------------------------------------------- #
    # games_today = get_today_games()
    # print("Today's Games:")
    # for g in games_today:
    #     print(f"{g['gameId']} | {g['awayTeam']} @ {g['homeTeam']} | {g['status']}")

    # # 1) Using the new factory:
    # stream, games = GameStream.from_today()
    # stream.debug_first_play()
    # stream.print_markdown_summary()

    # stream, games = GameStream.from_today()
    # md = stream.gamestream_to_markdown(recent_n=3, max_events=100)
    # print(md)
    # --------------------------------------------------------------------------- #
    # ──  Past PlaybyPlay EXAMPLE USAGE                                                         ──
    # --------------------------------------------------------------------------- #

    # midgame style:
    # pbp2 = PastGamesPlaybyPlay.from_game_id(
    #     game_date="2025-04-15",
    #     team="Warriors",
    #     start_period=3,
    #     start_clock="7:15")

    # pbp = PastGamesPlaybyPlay.from_game_id(game_date="2025-04-15", team="Warriors")
    # hist_md = pbp.playbyplay_to_markdown(max_lines=100, batch_size=2)
    # print(hist_md)

    # # stress tests:
    # # should all map to period=1
    # for inp in ["1", "1st Q", "quarter one", "Q1", "First Quarter"]:
    #     assert PastGamesPlaybyPlay.normalize_start_period(inp) == 1

    # assert PastGamesPlaybyPlay.normalize_start_period("quarter one") == 1
    # assert PastGamesPlaybyPlay.normalize_start_period("3rd Q")      == 3
    # assert PastGamesPlaybyPlay.normalize_start_period("Fourth")      == 4
    # assert PastGamesPlaybyPlay.normalize_start_period(2)             == 2

    # # should all map to "7:15"
    # for inp in ["7:15", "7.15", "7 min 15 sec", "7 minutes 15 seconds", "7 m 15 s"]:
    #     assert PastGamesPlaybyPlay.normalize_start_clock(inp) == "7:15"

    # # default seconds
    # assert PastGamesPlaybyPlay.normalize_start_clock("5 secs")     == "0:05"
    # assert PastGamesPlaybyPlay.normalize_start_clock("5 min") == "5:00"

    # # clamp tests
    # assert PastGamesPlaybyPlay.normalize_start_clock("15 minutes") == "12:00"
    # assert PastGamesPlaybyPlay.normalize_start_clock("7:65")      == "7:59"

    # ─── RUN HISTORICAL SMOKE TESTS VIA PastGamesPlaybyPlay ───────────────────────
    # run_historical_smoke_tests_via_class()

    # ── HISTORICAL EXAMPLE ─────────────────────────────────────────────
    # Game on April 15, 2025, Warriors vs. opponent, Q1–Q1 only,
    # up to 100 lines of output:
    live_md = PlaybyPlayLiveorPast(
        when="2025-04-15",
        team="Warriors",
        start_period=3,
        start_clock="7:15",
        max_lines=100,
    ).to_markdown()
    print("=== Live Snapshot ===\n", live_md)

    # ── LIVE EXAMPLE ────────────────────────────────────────────────────
    # Today’s game for the Lakers, show the live snapshot:
    # show 3 recent plays,
    live_md = PlaybyPlayLiveorPast(
        when=_date.today().strftime("%Y-%m-%d"),
        team="Knicks",
        recent_n=3,
        max_lines=100,
    ).to_markdown()
    print("=== Live Snapshot ===\n", live_md)
