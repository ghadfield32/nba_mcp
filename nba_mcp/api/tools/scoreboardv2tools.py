# scoreboardv2tools.py
# great for getting live scores and data for today and yesterday or any specific date

from datetime import date, datetime, timedelta
from typing import Optional, Union

import pandas as pd
from nba_api.stats.endpoints import leaguegamelog, scoreboardv2

from nba_mcp.api.tools.nba_api_utils import (
    format_game,
    get_player_id,
    get_player_name,
    get_static_lookup_schema,
    get_team_id,
    get_team_name,
    normalize_date,
    normalize_per_mode,
    normalize_season,
    normalize_stat_category,
)


def fetch_scoreboard_v2_full(
    target_date: Optional[Union[str, date, datetime]] = None,
    day_offset: int = 0,
    league_id: str = "00",
) -> pd.DataFrame:
    """
    Returns one comprehensive row per game including:
      - Header details (IDs, status, tip time, venue, broadcasters)
      - Live clock breakdown
      - Full line score by quarter & OT
      - Totals & shooting splits (FGM/FGA, FG%, 3P, FT)
      - Aggregated box‑score stats (AST, REB splits, STL, BLK, PF, TOV, +/-)
      - Availability flags (play‑by‑play, video)
      - Playoff series info & ticket links
      - Win‑probability timeline
      - Team leaders and last‑meeting summary
    """
    # Fetch data
    d = normalize_date(target_date)
    sb = scoreboardv2.ScoreboardV2(
        game_date=d.strftime("%Y-%m-%d"), day_offset=day_offset, league_id=league_id
    )

    # Load DataFrames
    hdr = sb.game_header.get_data_frame()
    ln = sb.line_score.get_data_frame()
    avail = sb.available.get_data_frame()
    leaders = sb.team_leaders.get_data_frame()
    series = sb.series_standings.get_data_frame()
    tickets = sb.ticket_links.get_data_frame()
    winprob = sb.win_probability.get_data_frame()
    lastmeet = sb.last_meeting.get_data_frame()

    if hdr.empty or ln.empty:
        return pd.DataFrame()

    # Merge header onto line scores (one row per team)
    merged = ln.merge(hdr, on="GAME_ID", suffixes=("", "_hdr"))

    def safe_split_clock(val: Optional[str]) -> tuple[int, int]:
        if isinstance(val, str) and ":" in val:
            m, s = val.split(":", 1)
            try:
                return int(m), int(s)
            except ValueError:
                pass
        return 0, 0

    records: list[dict] = []
    for gid, grp in merged.groupby("GAME_ID"):
        base = grp.iloc[0]
        mins, secs = safe_split_clock(base.get("LIVE_PC_TIME"))

        # Core header fields
        rec: dict = {
            "game_id": gid,
            "status": base.get("GAME_STATUS_TEXT"),
            "date": pd.to_datetime(base.get("GAME_DATE_EST")).date(),
            "arena": base.get("ARENA_NAME"),
            "live_period": base.get("LIVE_PERIOD", 0),
            "live_clock": base.get("LIVE_PC_TIME"),
            "live_clock_minutes": mins,
            "live_clock_seconds": secs,
            "natl_tv": base.get("NATL_TV_BROADCASTER_ABBREVIATION"),
            "home_tv": base.get("HOME_TV_BROADCASTER_ABBREVIATION"),
            "away_tv": base.get("AWAY_TV_BROADCASTER_ABBREVIATION"),
        }

        # Extract stats for a side
        def extract_side(prefix: str, team_id: int) -> dict:
            row = grp[grp["TEAM_ID"] == team_id].iloc[0]
            out = {
                f"{prefix}_team_id": team_id,
                f"{prefix}_team": get_team_name(team_id),
            }
            # Quarter and OT scores
            for q in range(1, 5):
                out[f"{prefix}_q{q}"] = row.get(f"PTS_QTR{q}")
            for ot in range(1, 11):
                out[f"{prefix}_ot{ot}"] = row.get(f"PTS_OT{ot}")
            # Shooting splits and totals
            out.update(
                {
                    f"{prefix}_fgm": row.get("FGM"),
                    f"{prefix}_fga": row.get("FGA"),
                    f"{prefix}_fg_pct": row.get("FG_PCT"),
                    f"{prefix}_fg3m": row.get("FG3M"),
                    f"{prefix}_fg3_pct": row.get("FG3_PCT"),
                    f"{prefix}_ftm": row.get("FTM"),
                    f"{prefix}_fta": row.get("FTA"),
                    f"{prefix}_ft_pct": row.get("FT_PCT"),
                    f"{prefix}_pts": row.get("PTS"),
                    f"{prefix}_ast": row.get("AST"),
                    f"{prefix}_reb": row.get("REB"),
                    f"{prefix}_oreb": row.get("OREB"),
                    f"{prefix}_dreb": row.get("DREB"),
                    f"{prefix}_stl": row.get("STL"),
                    f"{prefix}_blk": row.get("BLK"),
                    f"{prefix}_pf": row.get("PF"),
                    f"{prefix}_tov": row.get("TOV"),
                    f"{prefix}_plus_minus": row.get("PLUS_MINUS"),
                    f"{prefix}_video_available": bool(row.get("VIDEO_AVAILABLE")),
                }
            )
            return out

        home_id = base.get("HOME_TEAM_ID")
        away_id = base.get("VISITOR_TEAM_ID")
        rec.update(extract_side("home", home_id))
        rec.update(extract_side("away", away_id))

        # Play-by-play availability
        p = avail[avail["GAME_ID"] == gid]
        rec["play_by_play"] = bool(p["PT_AVAILABLE"].iat[0]) if not p.empty else False

        # Ticket link extraction
        t = tickets[tickets["GAME_ID"] == gid]
        rec["ticket_link"] = t["LEAG_TIX"].iat[0] if not t.empty else None

        # Series standings
        if not series.empty and gid in series["GAME_ID"].values:
            s = series[series["GAME_ID"] == gid].iloc[0]
            rec.update(
                {
                    "series_leader": s.get("SERIES_LEADER"),
                    "home_series_wins": s.get("HOME_TEAM_WINS"),
                    "home_series_losses": s.get("HOME_TEAM_LOSSES"),
                }
            )

        # Win probability
        if not winprob.empty and gid in winprob["GAME_ID"].values:
            rec["win_probability"] = winprob[winprob["GAME_ID"] == gid].to_dict(
                "records"
            )

        # Team leaders
        tl = leaders[leaders["GAME_ID"] == gid]
        for side, tid in (("home", home_id), ("away", away_id)):
            p = tl[tl["TEAM_ID"] == tid]
            if not p.empty:
                pl = p.iloc[0]
                rec.update(
                    {
                        f"{side}_top_scorer": pl.get("PTS_PLAYER_NAME"),
                        f"{side}_top_scorer_pts": pl.get("PTS"),
                        f"{side}_top_reb": pl.get("REB"),
                        f"{side}_top_ast": pl.get("AST"),
                    }
                )

        # Last meeting
        if not lastmeet.empty and gid in lastmeet["GAME_ID"].values:
            lm = lastmeet[lastmeet["GAME_ID"] == gid].iloc[0]
            rec.update(
                {
                    "last_game_id": lm.get("LAST_GAME_ID"),
                    "last_game_date": pd.to_datetime(
                        lm.get("LAST_GAME_DATE_EST")
                    ).date(),
                    "last_home_pts": lm.get("LAST_GAME_HOME_TEAM_POINTS"),
                    "last_away_pts": lm.get("LAST_GAME_VISITOR_TEAM_POINTS"),
                }
            )

        records.append(rec)

    return pd.DataFrame(records)


if __name__ == "__main__":
    df_live = fetch_scoreboard_v2_full()
    if df_live.empty:
        print("❗ No games scheduled today.")
    else:
        print("🏀 Live Today:")
        print(df_live.head())
        print(df_live.columns.tolist())

    # df_yest = fetch_scoreboard_v2_full(day_offset=-1)
    # print("\n🕒 Yesterday:")
    # print(df_yest.head())

    df_hist = fetch_scoreboard_v2_full("2025-04-15")
    print("\n📅 April 15, 2025:")
    print(df_hist.head())
