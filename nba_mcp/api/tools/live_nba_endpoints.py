# live_nba_endpoints.py

from nba_api.live.nba.endpoints.scoreboard import ScoreBoard
from nba_api.live.nba.endpoints.boxscore import BoxScore
from nba_api.live.nba.endpoints.playbyplay import PlayByPlay
from nba_api.live.nba.endpoints.odds import Odds
from nba_api.stats.endpoints.scoreboardv2 import ScoreboardV2
import json
import pandas as pd
from json import JSONDecodeError
# --------------------------------------------------------------------------- #
# ──   HELPERS                                                               ──
# --------------------------------------------------------------------------- #
import logging
logger = logging.getLogger(__name__)


def fetch_game_live_data(
    game_id: str,
    proxy: str | None = None,
    headers: dict | None = None,
    timeout: int = 30,
) -> dict:
    """
    Fetch **live** box‑score, play‑by‑play and odds for a single game.

    Always returns the same top‑level keys so that callers do not need to
    branch on "data missing vs. data present".

    Keys:
        * gameId       – the 10‑digit game code
        * boxScore     – dict | None           (None when not yet available)
        * playByPlay   – list[dict]            (empty list when not yet available)
        * odds         – dict                  ({} when no odds for this game)
    """
    # ---------- 1) Box‑score -------------------------------------------------
    try:
        box = BoxScore(
            game_id=game_id,
            proxy=proxy,
            headers=headers,
            timeout=timeout,
            get_request=False,
        )
        box.get_request()
        box_data: dict | None = box.get_dict()["game"]
    except JSONDecodeError:
        # Endpoint has no body yet (game not started)
        logger.debug("No box‑score JSON for game %s – tip‑off not reached.", game_id)
        box_data = None  # explicit "missing" marker

    # ---------- 2) Play‑by‑play ---------------------------------------------
    try:
        pbp = PlayByPlay(
            game_id=game_id,
            proxy=proxy,
            headers=headers,
            timeout=timeout,
            get_request=False,
        )
        pbp.get_request()
        pbp_actions: list[dict] = pbp.get_dict()["game"].get("actions", [])
    except JSONDecodeError:
        pbp_actions = []  # same rationale as box‑score

    # ---------- 3) Odds ------------------------------------------------------
    odds_ep = Odds(proxy=proxy, headers=headers, timeout=timeout, get_request=False)
    odds_ep.get_request()
    odds_all = odds_ep.get_dict().get("games", [])
    odds_for_us = next((g for g in odds_all if g["gameId"] == game_id), {})

    # ---------- 4) Assemble --------------------------------------------------
    return {
        "gameId": game_id,
        "boxScore": box_data,
        "playByPlay": pbp_actions,
        "odds": odds_for_us,
    }


def fetch_live_boxsc_odds_playbyplaydelayed_livescores(
    game_date: str | None = None,
    proxy: str | None = None,
    headers: dict | None = None,
    timeout: int = 30,
) -> dict:
    """
    Wrapper returning *all* games for a date.

    * When `game_date` is **None** → use Live API (today).
    * When `game_date` is  'YYYY‑MM‑DD' → use historical ScoreboardV2 snapshot.

    For **live** mode, each game dict now *always* contains:
        - gameId, boxScore, playByPlay, odds, scoreBoardSummary
    For **historical** mode, structure is unchanged (scoreBoardSnapshot only).
    """
    # ---------------- 1) Which API to hit? ----------------------------------
    if game_date:
        sb2 = ScoreboardV2(day_offset=0, game_date=game_date, league_id="00")
        dfs = sb2.get_data_frames()
        df_header = next(df for df in dfs if "GAME_STATUS_TEXT" in df.columns)
        df_line   = next(df for df in dfs if "TEAM_ID"          in df.columns)
        games_list: list[dict] = []

        for _, row in df_header.iterrows():
            gid = row["GAME_ID"]

            def _line_for(team_id_col: str, abbrev_col: str) -> dict:
                try:
                    return df_line[df_line["TEAM_ID"] == row[team_id_col]].iloc[0].to_dict()
                except Exception:
                    abbrev = row.get(abbrev_col)
                    return df_line[df_line["TEAM_ABBREVIATION"] == abbrev].iloc[0].to_dict()

            games_list.append(
                {
                    "gameId":      gid,
                    "gameStatusText": row["GAME_STATUS_TEXT"],
                    "period":         row.get("LIVE_PERIOD"),
                    "gameClock":      row.get("LIVE_PC_TIME"),
                    "homeTeam": _line_for("HOME_TEAM_ID", "HOME_TEAM_ABBREVIATION"),
                    "awayTeam": _line_for("VISITOR_TEAM_ID", "VISITOR_TEAM_ABBREVIATION"),
                }
            )
        date_label = game_date
    else:
        # Live ScoreBoard doesn't accept game_date parameter, only day_offset
        sb = ScoreBoard(proxy=proxy, headers=headers, timeout=timeout, get_request=True)
        games_list = sb.games.get_dict()
        date_label = sb.score_board_date

    # ---------------- 2) Per‑game enrichment --------------------------------
    all_data: list[dict] = []
    for gmeta in games_list:
        gid = gmeta["gameId"]
        if game_date:
            all_data.append({"scoreBoardSnapshot": gmeta})
        else:
            game_payload = fetch_game_live_data(
                game_id=gid,
                proxy=proxy,
                headers=headers,
                timeout=timeout,
            )
            # Will *always* succeed because fetch_game_live_data never returns {}
            game_payload["scoreBoardSummary"] = gmeta
            all_data.append(game_payload)

    # ---------------- 3) Return ---------------------------------------------
    return {"date": date_label, "games": all_data}



if __name__ == "__main__":
    # Example: real-time fetch
    print("\nReal-time today:\n")
    print(json.dumps(fetch_live_boxsc_odds_playbyplaydelayed_livescores(), indent=2))

    # # Example: historical fetch for testing (e.g., April 16, 2025)
    # print("\nHistorical snapshot (2025-04-16):\n")
    # print(json.dumps(fetch_live_boxsc_odds_playbyplaydelayed_livescores('2025-04-16'), indent=2))

