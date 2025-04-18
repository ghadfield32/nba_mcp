import time
from requests.exceptions import ReadTimeout
import pandas as pd
from nba_api.stats.endpoints import boxscoreadvancedv3, leaguegamefinder
from nba_api_utils import normalize_season, get_player_id, get_team_id, normalize_date

import time
import requests
from requests.exceptions import (
    ReadTimeout,
    ConnectionError,
    HTTPError,
)
import pandas as pd
from nba_api.stats.endpoints import boxscoreadvancedv3

# --------------------------------------------------------------------------- #
# ──   GLOBAL CALL‑SPACING (simple token‑bucket)                             ──
# --------------------------------------------------------------------------- #
_MIN_INTERVAL = 0.60  # seconds – NBAStats bans bursts; 10 req/s == insta‑ban
_last_call_ts = 0.0   # updated after every successful request


def get_boxscore_advanced(
    game_id: str,
    start_period: int = 1,
    end_period: int = 4,
    start_range: int = 0,
    end_range: int = 0,
    range_type: int = 0,
    retries: int = 5,
    backoff_factor: float = 0.7,
) -> dict[str, pd.DataFrame]:
    """
    Robust pull of advanced box‑score stats for one game.

    Features
    --------
    •   Enforces a 600 ms minimum spacing between *all* NBAStats calls.
    •   Retries (`ReadTimeout`, `ConnectionError`, HTTP 5xx, 429) with
        exponential back‑off *or* server‑provided Retry‑After header.
    •   Adds a desktop‑browser User‑Agent to every request.
    """
    global _last_call_ts

    gid = str(game_id).zfill(10)
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) "
        "Gecko/20100101 Firefox/124.0"
    )
    session = requests.Session()
    session.headers.update({"User-Agent": ua})

    last_exc: Exception | None = None

    for attempt in range(retries):
        # ── rate‑limit ─────────────────────────────────────────────────────────
        elapsed = time.perf_counter() - _last_call_ts
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)

        try:
            resp = boxscoreadvancedv3.BoxScoreAdvancedV3(
                game_id=gid,
                start_period=start_period,
                end_period=end_period,
                start_range=start_range,
                end_range=end_range,
                range_type=range_type,
                session=session,          # ← use our headers / connection pool
            )

            player_df, team_df = resp.get_data_frames()
            player_df.columns = [c.lower() for c in player_df.columns]
            team_df.columns   = [c.lower() for c in team_df.columns]

            _last_call_ts = time.perf_counter()
            return {"player_stats": player_df, "team_stats": team_df}

        # ------------------------------ network / timeout --------------------
        except (ReadTimeout, ConnectionError) as e:
            last_exc = e
            wait = backoff_factor * (2 ** attempt)

        # ------------------------------ HTTP status errors -------------------
        except HTTPError as e:
            last_exc = e
            status = e.response.status_code
            # obey Retry‑After header if server supplies one (secs)
            retry_after = e.response.headers.get("Retry-After")
            if retry_after:
                wait = max(float(retry_after), backoff_factor * (2 ** attempt))
            elif status in (429, 500, 502, 503, 504):
                wait = backoff_factor * (2 ** attempt)
            else:
                # other HTTP errors are unlikely recoverable
                raise

        # --------------------------------------------------------------------
        print(
            f"[NBA API] {type(last_exc).__name__} on {gid} — waiting {wait:.1f}s "
            f"(attempt {attempt+1}/{retries})"
        )
        time.sleep(wait)

    # every attempt failed
    raise last_exc


def get_player_season_advanced(
    player: str | int,
    season: str,
    start_date: str | None = None,
    end_date: str | None = None
) -> pd.DataFrame:
    # … your existing implementation …
    pid = get_player_id(player)
    if pid is None:
        raise ValueError(f"Could not find player ID for '{player}'")
    season_fmt = normalize_season(season)
    finder = leaguegamefinder.LeagueGameFinder(
        player_or_team_abbreviation='P',
        player_id_nullable=pid,
        season_nullable=season_fmt
    )
    games = finder.get_data_frames()[0]
    if start_date:
        sd = normalize_date(start_date)
        games = games[games['GAME_DATE'] >= sd.strftime('%Y-%m-%d')]
    if end_date:
        ed = normalize_date(end_date)
        games = games[games['GAME_DATE'] <= ed.strftime('%Y-%m-%d')]
    game_ids = games['GAME_ID'].astype(str).unique().tolist()
    records = []
    for gid in game_ids:
        adv = get_boxscore_advanced(gid)['player_stats']
        rec = adv[adv['personid'] == pid]
        if not rec.empty:
            records.append(rec)
    if not records:
        raise RuntimeError(f"No advanced stats found for {player} in {season_fmt}")
    season_adv = pd.concat(records, ignore_index=True)
    return season_adv


def get_team_advanced_stats(
    game_id: str, 
    start_period: int = 1, end_period: int = 4,
    start_range: int = 0, end_range: int = 0,
    range_type: int = 0
) -> pd.DataFrame:
    # … unchanged …
    res = boxscoreadvancedv3.BoxScoreAdvancedV3(
        game_id=game_id,
        start_period=start_period,
        end_period=end_period,
        start_range=start_range,
        end_range=end_range,
        range_type=range_type
    )
    return res.team_stats.get_data_frame()


def get_team_season_advanced(
    team: str | int,
    season: str,
    start_date: str | None = None,
    end_date: str | None = None
) -> pd.DataFrame:
    """
    Fetch a team's advanced box‑score stats for every game in a season,
    optionally filtered by date range. Uses LeagueGameFinder so no game_id needed.
    """
    tid = get_team_id(team)
    if tid is None:
        raise ValueError(f"Could not find team ID for '{team}'")
    season_fmt = normalize_season(season)

    finder = leaguegamefinder.LeagueGameFinder(
        player_or_team_abbreviation='T',
        team_id_nullable=tid,
        season_nullable=season_fmt
    )
    games = finder.get_data_frames()[0]

    if start_date:
        sd = normalize_date(start_date)
        games = games[games['GAME_DATE'] >= sd.strftime('%Y-%m-%d')]
    if end_date:
        ed = normalize_date(end_date)
        games = games[games['GAME_DATE'] <= ed.strftime('%Y-%m-%d')]

    game_ids = games['GAME_ID'].astype(str).unique().tolist()
    records = []

    for gid in game_ids:
        # now uses the retry‑enabled get_boxscore_advanced
        team_df = get_boxscore_advanced(gid)['team_stats']
        rec = team_df[team_df['teamid'] == int(tid)]
        if not rec.empty:
            records.append(rec)

    if not records:
        raise RuntimeError(f"No advanced stats found for {team} in {season_fmt}")

    season_adv = pd.concat(records, ignore_index=True)
    season_adv.columns = [c.lower() for c in season_adv.columns]
    return season_adv


if __name__ == "__main__":
    print("Testing player season advanced stats…")
    df_p = get_player_season_advanced("LeBron James", "2024-25")
    print(df_p.shape)

    print("Testing team season advanced stats…")
    df_t = get_team_season_advanced("LAL", "2024-25", start_date="2025-01-01")
    print(df_t[['teamtricode','offensiverating','defensiverating','pace','pie']].head())
