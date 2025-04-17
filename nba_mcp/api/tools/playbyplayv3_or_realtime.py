import requests
import json
from typing import List, Dict, Any, Optional
import time
from typing import Callable
from datetime import datetime, timezone
import sys

_STATS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://stats.nba.com",
}


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
                "status": game["gameStatusText"]
            }
            for game in payload["scoreboard"]["games"]
        ]
        return games_info

    # Explicitly log unexpected cases:
    print(f"[DEBUG] Unexpected payload structure: {payload}", file=sys.stderr)
    return []  # Always return an empty list if no games



def fetch_json(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 10.0
) -> Dict[str, Any]:
    resp = requests.get(url, headers=headers, params=params, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} from {url!r}")
    try:
        payload = resp.json()
    except ValueError:
        snippet = resp.text[:500].replace("\n"," ")
        raise RuntimeError(f"Non‑JSON response from {url!r}: {snippet}…")
    print(f"[DEBUG] {url!r} → keys: {list(payload.keys())}")
    return payload

def get_playbyplay_v3(
    game_id: str,
    start_period: int,
    end_period: int,
    timeout: float = 10.0
) -> Dict[str, Any]:
    url = "https://stats.nba.com/stats/playbyplayv3"
    params = {
        "GameID": game_id,
        "StartPeriod": start_period,
        "EndPeriod": end_period,
    }
    payload = fetch_json(url, headers=_STATS_HEADERS, params=params, timeout=timeout)

    if "resultSets" in payload:
        data = payload["resultSets"]
        return { ds["name"]: ds["rowSet"] for ds in data }

    if "game" in payload and "actions" in payload["game"]:
        return {"PlayByPlay": payload["game"]["actions"]}

    raise RuntimeError(
        f"Unrecognized payload shape for {game_id}: {list(payload.keys())}"
    )

def get_live_playbyplay(
    game_id: str,
    timeout: float = 5.0
) -> List[Dict[str, Any]]:
    url = f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"
    
    # FIXED: Include required headers explicitly
    payload = fetch_json(url, headers=_STATS_HEADERS, timeout=timeout)

    if "liveData" in payload and "plays" in payload["liveData"]:
        return payload["liveData"]["plays"]["play"]

    if "game" in payload and "actions" in payload["game"]:
        return payload["game"]["actions"]

    raise RuntimeError(f"Unrecognized live‑pbp shape for {game_id}: {list(payload.keys())}")


def get_live_boxscore(
    game_id: str,
    timeout: float = 5.0
) -> Dict[str, Any]:
    """
    Poll the near-real-time boxscore JSON feed.
    Supports both the 'liveData' shape and nba.cloud fallback shapes:
      1) a game['teams'] list
      2) separate game['homeTeam']/game['awayTeam'] fields
    Prints detailed statistics available for each team.
    """
    url = f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
    payload = fetch_json(url, timeout=timeout)

    # 1) Official liveData path
    if "liveData" in payload and "boxscore" in payload["liveData"]:
        boxscore = payload["liveData"]["boxscore"]

        # Debug and display available statistics
        print("[DEBUG] liveData['boxscore'] keys:", list(boxscore.keys()))
        for team_key in ['home', 'away']:
            team_stats = boxscore["teams"][team_key]
            print(f"[DEBUG] Stats for {team_key} team:")
            for stat_category, stat_value in team_stats.items():
                if isinstance(stat_value, (dict, list)):
                    print(f"  - {stat_category}: (complex type, keys: {list(stat_value.keys()) if isinstance(stat_value, dict) else 'list'})")
                else:
                    print(f"  - {stat_category}: {stat_value}")

        return boxscore

    # 2) nba.cloud fallback(s)
    if "game" in payload:
        game_obj = payload["game"]
        print(f"[DEBUG] payload['game'] keys: {list(game_obj.keys())}")

        # 2a) list-based fallback
        if "teams" in game_obj and isinstance(game_obj["teams"], list):
            teams_list = game_obj["teams"]
            print(f"[DEBUG] fallback list boxscore, game['teams'] length: {len(teams_list)}")
            mapped = {"home": None, "away": None}
            for t in teams_list:
                ind = t.get("homeAwayIndicator") or t.get("homeAway") or t.get("side")
                if ind == "H": mapped["home"] = t
                elif ind == "A": mapped["away"] = t
            if mapped["home"] and mapped["away"]:
                print("[DEBUG] Stats in fallback (list-based):", list(mapped["home"].keys()))
                return {"teams": mapped}
            return {"teams": teams_list}

        # 2b) home/away-fields fallback
        if "homeTeam" in game_obj and "awayTeam" in game_obj:
            print("[DEBUG] fallback home/away boxscore path")
            mapped = {
                "home": game_obj["homeTeam"],
                "away": game_obj["awayTeam"]
            }
            print("[DEBUG] Stats in fallback (home/away):", list(mapped["home"].keys()))
            return {"teams": mapped}

    # 3) Unrecognized shape
    raise RuntimeError(f"Unrecognized boxscore shape for {game_id}: {list(payload.keys())}")



def measure_update_frequency(
    game_id: str,
    fetch_fn: Callable[[str], Dict[str, Any]],
    timestamp_key_path: List[str],
    samples: int = 5,
    delay: float = 1.0
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
        return datetime.fromisoformat(sub.replace('Z', '+00:00'))

    for i in range(samples):
        payload = fetch_fn(game_id)
        try:
            ts = extract_ts(payload)
            now = datetime.now(timezone.utc)
            print(f"[DEBUG] sample #{i+1} timestamp: {ts.isoformat()}  (fetched at {now.isoformat()})")
            timestamps.append(ts)
        except Exception as ex:
            print(f"[DEBUG] failed to extract timestamp on sample #{i+1}: {ex}")
        time.sleep(delay)

    intervals: List[float] = []
    for a, b in zip(timestamps, timestamps[1:]):
        delta = (b - a).total_seconds()
        intervals.append(delta)
        print(f"[DEBUG] interval: {delta}s")

    return intervals






# ─── 4) EVENT DIFFING ─────────────────────────────────────────────────────────────
def diff_new_events(
    old_events: List[Dict[str, Any]],
    new_events: List[Dict[str, Any]],
    key: str = "actionNumber"
) -> List[Dict[str, Any]]:
    """
    Return only those plays in new_events whose `key` isn’t present in old_events.
    Defaults to actionNumber since CDN livePBP uses that uniquely.
    """
    seen = { e[key] for e in old_events if key in e }
    new_filtered = [ e for e in new_events if key in e and e[key] not in seen ]

    # debug any stray entries missing the key entirely
    missing = [e for e in new_events if key not in e]
    if missing:
        print(f"[DEBUG] Missing '{key}' on events:", missing)

    return new_filtered



# ─── 5) POLLING LOOP EXAMPLE ──────────────────────────────────────────────────────
def stream_live_pbp(
    game_id: str,
    interval: float = 3.0
):
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



import requests, json, time
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime


def get_game_info(
    game_id: str,
    timeout: float = 5.0
) -> Dict[str, Any]:
    """
    Fetch the raw 'game' object from the liveData boxscore endpoint,
    so we can pull out period, gameClock, etc.
    """
    url = f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
    payload = fetch_json(url, timeout=timeout)
    # prefer the 'liveData' shape if present
    if "liveData" in payload and "game" in payload["liveData"]:
        return payload["liveData"]["game"]
    # fallback to payload["game"]
    if "game" in payload:
        return payload["game"]
    raise RuntimeError(f"Can't extract raw game info for {game_id}")


def measure_content_changes(
    game_id: str,
    fetch_fn: Callable[[str], Any],
    extractor_fn: Callable[[Any], Any],
    samples: int = 5,
    delay: float = 1.0
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
        print(f"[DEBUG] sample #{i+1}: value={val!r} at {now.isoformat()}")
        values.append(val)
        timestamps.append(now)
        time.sleep(delay)

    change_intervals: List[float] = []
    last_val, last_time = values[0], timestamps[0]
    for t, v in zip(timestamps[1:], values[1:]):
        if v != last_val:
            delta = (t - last_time).total_seconds()
            change_intervals.append(delta)
            print(f"[DEBUG] changed {last_val!r}→{v!r} after {delta}s")
            last_val, last_time = v, t

    return change_intervals


def group_live_game(game_id: str, recent_n: int = 5) -> Dict[str, Any]:
    """
    Bundle game status, team summaries, player box‑score and recent plays.
    Adds the *team names* so downstream markdown can reference them.
    """
    # 1) raw game info (clock, period, names, status text)
    info        = get_game_info(game_id)
    status_text = info.get("gameStatusText", "").lower()
    print(f"[DEBUG] gameStatusText: {status_text}")

    # Skip games that haven’t started yet
    if any(tok in status_text for tok in ("pm et", "am et", "pregame")):
        raise RuntimeError(f"Game {game_id} has not started yet ({status_text}).")

    home_name = info["homeTeam"]["teamName"]
    away_name = info["awayTeam"]["teamName"]
    period    = info.get("period")
    gameClock = info.get("gameClock")

    # 2) box‑score & scores
    box   = get_live_boxscore(game_id)
    teams = box["teams"]
    home_score = int(teams["home"]["score"])
    away_score = int(teams["away"]["score"])

    # 3) recent plays
    pbp    = get_live_playbyplay(game_id)
    recent = pbp[-recent_n:] if len(pbp) >= recent_n else pbp

    return {
        "status": {
            "period":     period,
            "gameClock":  gameClock,
            "scoreDiff":  home_score - away_score,
            "homeScore":  home_score,
            "awayScore":  away_score,
            "homeName":   home_name,
            "awayName":   away_name,
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
    Falls back to the raw string if it doesn’t match.
    """
    m = re.match(r"PT0*(\d+)M0*(\d+)(?:\.\d+)?S", iso)
    if m:
        minutes = int(m.group(1))
        seconds = int(m.group(2))
        return f"{minutes}:{seconds:02d}"
    return iso



def pretty_print_snapshot(
    snapshot: Dict[str, Any],
    max_players: int = 2,
    max_plays: int = 2
) -> None:
    """
    Print a condensed view of the grouped snapshot so you can eyeball
    each section quickly from the console.
    """
    status = snapshot["status"]
    print("\n=== GAME STATUS ===")
    clock = parse_iso_clock(status["gameClock"])
    print(f"Period {status['period']}  |  Clock {clock}  "
          f"|  {status['homeScore']}-{status['awayScore']} "
          f"(diff {status['scoreDiff']})")

    print("\n=== TEAM STATS (headline) ===")
    for side in ("home", "away"):
        team_stats = snapshot["teams"][side]
        headline = {k: team_stats[k] for k in (
            "fieldGoalsMade",
            "fieldGoalsAttempted",
            "reboundsTotal",
            "assists",
            "turnovers"
        ) if k in team_stats}
        print(f"{side.capitalize():5}: {headline}")

    print("\n=== PLAYERS (first few) ===")
    for side in ("home", "away"):
        players = snapshot["players"][side]
        slist = truncate_list(
            [f"{p['name']} ({p['statistics']['points']} pts)" for p in players],
            max_players
        )
        print(f"{side.capitalize():5}: {', '.join(slist)}")


    print("\n=== RECENT PLAYS ===")
    for play in truncate_list(snapshot["recentPlays"], max_plays):
        desc   = play.get("description", play["actionType"])
        clock  = parse_iso_clock(play.get("clock", ""))
        period = play.get("period", "?")
        print(f"[Q{period} {clock}] {desc}")

def generate_tool_output(
    game_id: str,
    recent_n: int = 5
) -> Dict[str, Any]:
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
    pbp_v3_raw   = fetch_json(
        "https://stats.nba.com/stats/playbyplayv3",
        headers=_STATS_HEADERS,
        params={"GameID": game_id, "StartPeriod": 1, "EndPeriod": 4}
    )
    live_pbp_raw = fetch_json(
        f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"
    )
    live_box_raw = fetch_json(
        f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
    )
    game_info    = get_game_info(game_id)

    # 2) Normalized data via existing helpers
    pbp_v3   = get_playbyplay_v3(game_id, 1, 4)
    live_pbp = get_live_playbyplay(game_id)
    live_box = get_live_boxscore(game_id)
    summary  = group_live_game(game_id, recent_n=recent_n)

    return {
        "raw": {
            "pbp_v3":    pbp_v3_raw,
            "live_pbp":  live_pbp_raw,
            "live_box":  live_box_raw,
            "game_info": game_info,
        },
        "normalized": {
            "pbp_v3":    pbp_v3,
            "live_pbp":  live_pbp,
            "live_box":  live_box,
        },
        "summary": summary
    }




# ── NEW: markdown_helpers.py ──────────────────────────────────────────────
from typing import List, Dict, Any

def _fg_line(made: int, att: int) -> str:
    """Return `FGM / FGA` convenience string."""
    return f"{made} / {att}"

def format_today_games(games: List[Dict[str, Any]]) -> str:
    """Markdown bullet list of today’s games (section 1)."""
    if not games:
        return "_No games scheduled today_"
    lines = ["### 1. Today’s Games"]
    for g in games:
        lines.append(
            f"- **{g['gameId']}** {g['awayTeam']} @ {g['homeTeam']} ({g['status']})"
        )
    return "\n".join(lines)

def _leading(players: List[Dict[str, Any]], n: int = 3) -> List[str]:
    """Return first `n` players as 'Name X pts'."""
    out = [f"{p['name']} {p['statistics']['points']} pts" for p in players[:n]]
    return out

def format_snapshot_markdown(snapshot: Dict[str, Any],
                             game_id: str,
                             max_players: int = 3,
                             recent_n: int = 3) -> str:
    """
    Convert the snapshot into sections 2‑6 with clearer team context.
    """
    s       = snapshot["status"]
    teams   = snapshot["teams"]
    players = snapshot["players"]
    recent  = snapshot["recentPlays"][-recent_n:]

    home, away   = s["homeName"], s["awayName"]
    diff         = abs(s["scoreDiff"])
    leading_team = home if s["scoreDiff"] > 0 else away
    trailing_team= away if leading_team == home else home
    verb         = "up" if s["scoreDiff"] > 0 else "up"  # same word, but kept for clarity

    parts: List[str] = []

    # 2. Selected game
    parts.append("### 2. Selected Game")
    parts.append(f"- **Game ID:** {game_id}")
    parts.append(f"- **Match‑up:** {away} @ {home}\n")

    # 3. Game status
    parts.append("### 3. Game Status")
    parts.append(f"- **Period:** {s['period']}")
    parts.append(f"- **Clock:** {parse_iso_clock(s['gameClock'])}")
    parts.append(
        f"- **Score:** {away} {s['awayScore']} – {s['homeScore']} {home}  "
        f"({leading_team} {verb} {diff})\n"
    )

    # 4. Team stats table
    def _row(side: str, label: str) -> str:
        t  = teams[side]
        fg = _fg_line(t['fieldGoalsMade'], t['fieldGoalsAttempted'])
        return f"| {label} | {fg} | {t['reboundsTotal']} | {t['assists']} | {t['turnovers']} |"

    parts.append("### 4. Team Stats")
    parts.append("| Team | FGM‑FGA | Reb | Ast | TO |")
    parts.append("|------|---------|-----|-----|----|")
    parts.append(_row("home", home))
    parts.append(_row("away", away))
    parts.append("")

    # 5. Leading scorers
    def _leading(pl: List[Dict[str, Any]]) -> List[str]:
        return [f"{p['name']} {p['statistics']['points']} pts" for p in pl[:max_players]]

    parts.append("### 5. Leading Scorers")
    parts.append(f"- **{home}:**  " + " · ".join(_leading(players["home"])))
    parts.append(f"- **{away}:**  " + " · ".join(_leading(players["away"])))
    parts.append("")

    # 6. Recent plays
    parts.append("### 6. Recent Plays")
    parts.append("| Qtr | Clock | Play |")
    parts.append("|-----|-------|------|")
    for p in recent:
        q    = p.get("period", "?")
        clk  = parse_iso_clock(p.get("clock", ""))
        desc = p.get("description", p["actionType"])
        parts.append(f"| {q} | {clk} | {desc} |")

    return "\n".join(parts)


def print_markdown_summary(game_id: str,
                           games_today: List[Dict[str, Any]],
                           snapshot: Dict[str, Any]) -> None:
    """
    Convenience wrapper: prints full Markdown block 1‑6.
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
        print("[DEBUG] First play structure and data:")
        for key, value in first_play.items():
            print(f" - {key}: {value}")
    else:
        print("[DEBUG] No plays found.")



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
            g for g in games if not ("pm et" in g["status"].lower() or "am et" in g["status"].lower() or "pregame" in g["status"].lower())
        ]
        if not active_or_finished_games:
            raise RuntimeError("No active or finished games available today.")
        return cls(active_or_finished_games[0]['gameId']), active_or_finished_games

    def debug_first_play(self) -> None:
        debug_play_structure(self.game_id)

    def fetch_grouped_snapshot(self, recent_n: int = 5) -> Dict[str, Any]:
        return group_live_game(self.game_id, recent_n)

    def print_markdown_summary(
        self,
        recent_n: int = 3,
        games_today: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        if games_today is None:
            games_today = self.get_today_games()
        snapshot = self.fetch_grouped_snapshot(recent_n=recent_n)
        print_markdown_summary(self.game_id, games_today, snapshot)

    def safe_fetch_live_pbp(self) -> List[Dict[str, Any]]:
        try:
            return get_live_playbyplay(self.game_id)
        except Exception as e:
            print(f"[DEBUG] Error fetching live pbp for {self.game_id}: {e}")
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
        self,
        games_today: List[Dict[str, Any]],
        recent_n: int = 5
    ) -> Dict[str, Any]:
        """
        Return a dict with:
          - markdown: a Markdown snippet for this game
          - snapshot: the JSON summary (status, teams, players, recentPlays)
          - events:   the full list of live plays
        """
        # 1) snapshot & events
        snapshot = self.fetch_grouped_snapshot(recent_n=recent_n)
        events   = self.safe_fetch_live_pbp()

        # 2) human Markdown
        #    (we only need the 1‑6 blocks for THIS game, so pass [this] as games_today)
        md_today = format_today_games(games_today)
        md_snap  = format_snapshot_markdown(snapshot, self.game_id,
                                            max_players=3,
                                            recent_n=recent_n)

        payload = {
            "gameId":   self.game_id,
            "markdown": "\n\n".join([md_today, md_snap]),
            "snapshot": snapshot,
            "events":   events
        }
        return payload




# ─── USAGE ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
        
    games_today = get_today_games()
    print("Today's Games:")
    for g in games_today:
        print(f"{g['gameId']} | {g['awayTeam']} @ {g['homeTeam']} | {g['status']}")


    # 1) Using the new factory:
    stream, games = GameStream.from_today()
    stream.debug_first_play()
    stream.print_markdown_summary()

