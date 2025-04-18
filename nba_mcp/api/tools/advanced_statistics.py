import time
import requests
from requests.exceptions import ReadTimeout, ConnectionError, HTTPError
import pandas as pd
from nba_api.stats.endpoints import boxscoreadvancedv3, leaguegamefinder
from nba_api.library.http import NBAStatsHTTP

# ── GLOBAL RATE‑LIMIT TOKEN (NBA bans bursts >10 req/s) ─────────────────────
_MIN_INTERVAL = 0.60   # seconds
_last_call_ts = 0.0    # updated after every successful API hit

# ── PATCH DEFAULT SESSION ONCE: UA + shorter connect/read timeout —──────────
_http = NBAStatsHTTP()
_http.session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) "
            "Gecko/20100101 Firefox/124.0"
        )
    }
)
_http.timeout = 25  # seconds

# ─────────────────────────────────────────────────────────────────────────────
def _nba_stats_request(endpoint_cls, retries: int = 5, backoff: float = 0.7, **kwargs):
    """
    Unified, retry‑aware wrapper around any nba_api *endpoint* class.
    """
    global _last_call_ts
    last_exc: Exception | None = None

    for attempt in range(retries):
        # Rate‑limit
        delta = time.perf_counter() - _last_call_ts
        if delta < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - delta)

        try:
            obj = endpoint_cls(**kwargs)
            _last_call_ts = time.perf_counter()
            return obj  # success → DataFrames live on obj
        # ----------------------- transient network errors -------------------
        except (ReadTimeout, ConnectionError) as e:
            last_exc = e
            wait = backoff * (2 ** attempt)
        # ----------------------- HTTP 429 / 5xx -----------------------------
        except HTTPError as e:
            last_exc = e
            status = e.response.status_code
            if status in (429, 500, 502, 503, 504):
                retry_after = e.response.headers.get("Retry-After")
                wait = max(float(retry_after) if retry_after else 0, backoff * (2 ** attempt))
            else:
                raise      # 404 / 400 etc → propagate immediately
        # -------------------------------------------------------------------
        print(f"[NBA API] {type(last_exc).__name__} on {endpoint_cls.__name__} — "
              f"waiting {wait:.1f}s (attempt {attempt+1}/{retries})")
        time.sleep(wait)

    raise last_exc
# ─────────────────────────────────────────────────────────────────────────────

def get_boxscore_advanced(
    game_id: str,
    start_period: int = 1,
    end_period: int = 4,
    start_range: int = 0,
    end_range: int = 0,
    range_type: int = 0,
) -> dict[str, pd.DataFrame]:
    """
    Fetch advanced box‑score stats for a single game (robust version).
    """
    gid = str(game_id).zfill(10)

    resp = _nba_stats_request(
        boxscoreadvancedv3.BoxScoreAdvancedV3,
        game_id=gid,
        start_period=start_period,
        end_period=end_period,
        start_range=start_range,
        end_range=end_range,
        range_type=range_type,
    )
    player_df, team_df = resp.get_data_frames()
    player_df.columns = [c.lower() for c in player_df.columns]
    team_df.columns   = [c.lower() for c in team_df.columns]
    return {"player_stats": player_df, "team_stats": team_df}


def get_player_season_advanced(
    player: str | int,
    season: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """
    Fetch a player's advanced box‑score stats for every game in a season
    (now uses robust wrapper for BOTH game‑finder and per‑game calls).
    """
    from nba_mcp.api.tools.nba_api_utils import (
        normalize_season,
        get_player_id,
        normalize_date,
    )

    pid = get_player_id(player)
    if pid is None:
        raise ValueError(f"Could not find player ID for '{player}'")
    season_fmt = normalize_season(season)

    finder = _nba_stats_request(
        leaguegamefinder.LeagueGameFinder,
        player_or_team_abbreviation="P",
        player_id_nullable=pid,
        season_nullable=season_fmt,
    )
    games = finder.get_data_frames()[0]

    if start_date:
        sd = normalize_date(start_date)
        games = games[games["GAME_DATE"] >= sd.strftime("%Y-%m-%d")]
    if end_date:
        ed = normalize_date(end_date)
        games = games[games["GAME_DATE"] <= ed.strftime("%Y-%m-%d")]

    game_ids = games["GAME_ID"].astype(str).unique().tolist()
    records = []

    for gid in game_ids:
        adv = get_boxscore_advanced(gid)["player_stats"]
        rec = adv[adv["personid"] == pid]
        if not rec.empty:
            records.append(rec)

    if not records:
        raise RuntimeError(f"No advanced stats found for {player} in {season_fmt}")

    return pd.concat(records, ignore_index=True)



if __name__ == "__main__":
    # manual smoke test
    print("Testing LeagueGameFinder + advanced box-score retrieval...")
    df = get_player_season_advanced("LeBron James", "2024-25")
    print(df.head())
    print(df.shape)
