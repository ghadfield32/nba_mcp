# live_nba_endpoints.py

from nba_api.live.nba.endpoints.scoreboard import ScoreBoard
from nba_api.live.nba.endpoints.boxscore import BoxScore
from nba_api.live.nba.endpoints.playbyplay import PlayByPlay
from nba_api.live.nba.endpoints.odds import Odds
from nba_api.stats.endpoints.scoreboardv2 import ScoreboardV2
import json
import pandas as pd
from json import JSONDecodeError

def fetch_game_live_data(
    game_id: str,
    proxy: str = None,
    headers: dict = None,
    timeout: int = 30
) -> dict:
    """
    Fetch and assemble live data for a single game_id.
    Skips games that have no boxscore yet.
    """
    # 1) BOX SCORE
    try:
        box = BoxScore(
            game_id=game_id,
            proxy=proxy,
            headers=headers,
            timeout=timeout,
            get_request=False,        # don’t auto-fetch twice
        )
        box.get_request()            # fetch exactly once
        box_data = box.get_dict()['game']
    except JSONDecodeError:
        # No JSON body yet for this game → skip
        print(f"[DEBUG] No boxscore JSON for game {game_id!r}, skipping.")
        return {}

    # 2) PLAY‑BY‑PLAY
    try:
        pbp = PlayByPlay(
            game_id=game_id,
            proxy=proxy,
            headers=headers,
            timeout=timeout,
            get_request=False
        )
        pbp.get_request()
        pbp_data = pbp.get_dict()['game']
    except JSONDecodeError:
        # no pbp yet? still include boxscore
        pbp_data = {}

    # 3) ODDS
    odds = Odds(
        proxy=proxy,
        headers=headers,
        timeout=timeout,
        get_request=False
    )
    odds.get_request()
    # odds.get_dict() returns { "games": [ … ] }
    all_odds = odds.get_dict().get('games', [])
    odds_for_us = next((g for g in all_odds if g["gameId"] == game_id), {})

    # 4) Assemble
    return {
        "gameId": game_id,
        "boxScore": box_data,
        "playByPlay": pbp_data.get('actions', []),
        "odds": odds_for_us
    }



def fetch_live_boxsc_odds_playbyplaydelayed_livescores(
    game_date: str = None,
    proxy: str = None,
    headers: dict = None,
    timeout: int = 30
) -> dict:
    """
    Fetch live data for today's games or historical games for a specific date.

    Args:
        game_date: 'YYYY-MM-DD'. If provided, uses the Stats API (ScoreboardV2) to fetch a historical snapshot.
    """
    # Determine game list
    if game_date:
        # Historical snapshot via Stats API
        sb2 = ScoreboardV2(day_offset=0, game_date=game_date, league_id='00')
        dfs = sb2.get_data_frames()
        # Identify header and line score DataFrames dynamically
        df_header = next(df for df in dfs if 'GAME_STATUS_TEXT' in df.columns)
        df_line = next(df for df in dfs if 'TEAM_ID' in df.columns)

        games_list = []
        for _, row in df_header.iterrows():
            gid = row['GAME_ID']
            # Extract home team line score, fallback to abbreviation if needed
            try:
                home_line = df_line[df_line['TEAM_ID'] == row['HOME_TEAM_ID']].iloc[0].to_dict()
            except Exception:
                # Fallback: match by team abbreviation
                abbrev = row.get('HOME_TEAM_ABBREVIATION')
                home_line = df_line[df_line['TEAM_ABBREVIATION'] == abbrev].iloc[0].to_dict()
            # Extract away team line score
            try:
                away_line = df_line[df_line['TEAM_ID'] == row['VISITOR_TEAM_ID']].iloc[0].to_dict()
            except Exception:
                abbrev = row.get('VISITOR_TEAM_ABBREVIATION')
                away_line = df_line[df_line['TEAM_ABBREVIATION'] == abbrev].iloc[0].to_dict()

            games_list.append({
                'gameId': gid,
                'gameStatusText': row['GAME_STATUS_TEXT'],
                'period': row.get('LIVE_PERIOD'),
                'gameClock': row.get('LIVE_PC_TIME'),
                'homeTeam': home_line,
                'awayTeam': away_line
            })
        date_label = game_date
    else:
        # Real-time via Live API
        sb = ScoreBoard(proxy=proxy, headers=headers, timeout=timeout, get_request=True)
        games_list = sb.games.get_dict()
        date_label = sb.score_board_date

    # Assemble final payload
    all_data = []
    for game in games_list:
        gid = game['gameId']
        if not game_date:
            details = fetch_game_live_data(
                game_id=gid,
                proxy=proxy,
                headers=headers,
                timeout=timeout
            )
            details['scoreBoardSummary'] = game
        else:
            # historical mode: only summary available
            details = {'scoreBoardSnapshot': game}
        all_data.append(details)

    return {
        'date': date_label,
        'games': all_data
    }


if __name__ == "__main__":
    # Example: real-time fetch
    print("\nReal-time today:\n")
    print(json.dumps(fetch_live_boxsc_odds_playbyplaydelayed_livescores(), indent=2))

    # Example: historical fetch for testing (e.g., April 16, 2025)
    print("\nHistorical snapshot (2025-04-16):\n")
    print(json.dumps(fetch_live_boxsc_odds_playbyplaydelayed_livescores('2025-04-16'), indent=2))

