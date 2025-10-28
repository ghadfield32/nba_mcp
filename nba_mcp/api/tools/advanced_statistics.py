import pandas as pd
from nba_api.stats.endpoints import boxscoreadvancedv3, leaguegamefinder
from nba_mcp.api.tools.nba_api_utils import (
    normalize_season,
    get_player_id,
    normalize_date,
)


def get_boxscore_advanced(
    game_id: str,
    start_period: int = 1,
    end_period: int = 4,
    start_range: int = 0,
    end_range: int = 0,
    range_type: int = 0,
) -> dict[str, pd.DataFrame]:
    """
    Fetch advanced box-score stats for a single game.

    Returns a dict with:
      - 'player_stats': DataFrame of all players
      - 'team_stats':   DataFrame of both teams
    """
    # normalize 10-digit game ID
    gid = str(game_id).zfill(10)

    # use lowercase snake_case argument names per endpoint signature
    resp = boxscoreadvancedv3.BoxScoreAdvancedV3(
        game_id=gid,
        start_period=start_period,
        end_period=end_period,
        start_range=start_range,
        end_range=end_range,
        range_type=range_type,
    )
    player_df, team_df = resp.get_data_frames()

    # snake-case column names for consistency
    player_df.columns = [c.lower() for c in player_df.columns]
    team_df.columns = [c.lower() for c in team_df.columns]

    return {"player_stats": player_df, "team_stats": team_df}


def get_player_season_advanced(
    player: str | int,
    season: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """
    Fetch a player's advanced box-score stats for every game in a season,
    optionally filtered by date range.

    Uses LeagueGameFinder to avoid manual game_id lookups.

    Args:
        player: Player name or ID
        season: Season string (e.g. '2024-25', '24')
        start_date: Inclusive filter (any parseable date)
        end_date: Inclusive filter (any parseable date)

    Returns:
        DataFrame of per-game advanced stats for that player.
    """
    # resolve player to ID and normalize season
    pid = get_player_id(player)
    if pid is None:
        raise ValueError(f"Could not find player ID for '{player}'")
    season_fmt = normalize_season(season)

    # find all games in season for player via LeagueGameFinder
    finder = leaguegamefinder.LeagueGameFinder(
        player_or_team_abbreviation="P",
        player_id_nullable=pid,
        season_nullable=season_fmt,
    )
    games = finder.get_data_frames()[0]

    # apply optional date filters
    if start_date:
        sd = normalize_date(start_date)
        games = games[games["GAME_DATE"] >= sd.strftime("%Y-%m-%d")]
    if end_date:
        ed = normalize_date(end_date)
        games = games[games["GAME_DATE"] <= ed.strftime("%Y-%m-%d")]

    # gather unique game IDs
    game_ids = games["GAME_ID"].astype(str).unique().tolist()
    records = []

    # iterate and collect advanced box-score for each game
    for gid in game_ids:
        adv = get_boxscore_advanced(gid)["player_stats"]
        rec = adv[adv["personid"] == pid]
        if not rec.empty:
            records.append(rec)

    if not records:
        raise RuntimeError(f"No advanced stats found for {player} in {season_fmt}")

    # concatenate all per-game rows
    season_adv = pd.concat(records, ignore_index=True)
    return season_adv


if __name__ == "__main__":
    # manual smoke test
    print("Testing LeagueGameFinder + advanced box-score retrieval...")
    df = get_player_season_advanced("LeBron James", "2024-25")
    print(df.head())
    print(df.shape)
