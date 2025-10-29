"""
Debug script to systematically test MCP queries and identify errors.

This script will:
1. Test each query type independently
2. Add detailed logging at each step
3. Catch and analyze errors with full tracebacks
4. Identify the exact location of failures
"""

import asyncio
import json
import logging
import sys
import traceback
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_mcp.api.client import NBAApiClient
from nba_mcp.nlq.pipeline import answer_nba_question

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('debug_mcp_queries.log', mode='w')
    ]
)

logger = logging.getLogger(__name__)


# ============================================================================
# TEST CASES - Based on user's requests
# ============================================================================

async def test_lebron_last_5_home():
    """Test: LeBron's last 5 game average at home"""
    logger.info("\n" + "="*80)
    logger.info("TEST 1: LeBron's last 5 game average at home")
    logger.info("="*80)

    try:
        client = NBAApiClient()

        # Step 1: Get player game log
        logger.info("Step 1: Fetching LeBron's game log for 2024-25...")
        game_log = await client.get_player_game_log(
            player_name="LeBron James",
            season="2024-25",
            as_dataframe=True
        )
        logger.info(f"✓ Got {len(game_log)} games")
        logger.debug(f"Columns: {game_log.columns.tolist()}")
        logger.debug(f"First 3 MATCHUP values: {game_log['MATCHUP'].head(3).tolist()}")

        # Step 2: Filter for home games
        logger.info("\nStep 2: Filtering for home games...")
        home_games = game_log[game_log["MATCHUP"].str.contains("vs\\.", na=False, regex=True)]
        logger.info(f"✓ Found {len(home_games)} home games")

        if len(home_games) == 0:
            logger.error("❌ No home games found!")
            logger.debug("Sample MATCHUP formats:")
            for matchup in game_log['MATCHUP'].head(10):
                logger.debug(f"  - {matchup}")
            return None

        # Step 3: Get last 5 home games
        logger.info("\nStep 3: Getting last 5 home games...")
        last_5_home = home_games.head(5)
        logger.info(f"✓ Got {len(last_5_home)} games")

        # Step 4: Calculate averages
        logger.info("\nStep 4: Calculating averages...")
        stats = {
            "games": len(last_5_home),
            "ppg": last_5_home["PTS"].mean(),
            "rpg": last_5_home["REB"].mean(),
            "apg": last_5_home["AST"].mean(),
            "fgpct": last_5_home["FG_PCT"].mean() * 100,
            "fg3pct": last_5_home["FG3_PCT"].mean() * 100,
        }

        logger.info("✓ Last 5 home games averages:")
        for key, value in stats.items():
            if key == "games":
                logger.info(f"  {key}: {value}")
            else:
                logger.info(f"  {key}: {value:.1f}")

        return stats

    except Exception as e:
        logger.error(f"❌ Error in test_lebron_last_5_home: {type(e).__name__}: {str(e)}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        return None


async def test_curry_shot_chart():
    """Test: Steph Curry's shot chart from last 3 games"""
    logger.info("\n" + "="*80)
    logger.info("TEST 2: Steph Curry's shot chart from last 3 games")
    logger.info("="*80)

    try:
        client = NBAApiClient()

        # Step 1: Get recent games to find date range
        logger.info("Step 1: Finding Steph's recent games...")
        game_log = await client.get_player_game_log(
            player_name="Stephen Curry",
            season="2024-25",
            as_dataframe=True
        )
        logger.info(f"✓ Got {len(game_log)} games this season")

        if len(game_log) == 0:
            logger.warning("⚠ No games found for Steph Curry in 2024-25")
            logger.info("Trying 2023-24 season instead...")
            game_log = await client.get_player_game_log(
                player_name="Stephen Curry",
                season="2023-24",
                as_dataframe=True
            )
            logger.info(f"✓ Got {len(game_log)} games in 2023-24")
            season = "2023-24"
        else:
            season = "2024-25"

        # Get last 3 games dates
        last_3 = game_log.head(3)
        logger.info(f"\nLast 3 games:")
        for idx, row in last_3.iterrows():
            logger.info(f"  {row['GAME_DATE']}: {row['MATCHUP']} - {row['PTS']} pts")

        date_from = last_3.iloc[-1]['GAME_DATE']  # Oldest of last 3
        date_to = last_3.iloc[0]['GAME_DATE']     # Most recent
        logger.info(f"\nDate range: {date_from} to {date_to}")

        # Step 2: Get shot chart
        logger.info("\nStep 2: Fetching shot chart...")
        from nba_stats_api.stats_api import get_player_shotchart

        # Resolve player ID
        player_info = await client.resolve_player_name("Stephen Curry")
        player_id = player_info["id"]
        logger.info(f"✓ Player ID: {player_id}")

        shot_data = await get_player_shotchart(
            player_id=player_id,
            season=season,
            season_type="Regular Season"
        )

        logger.info(f"✓ Got shot chart data")
        logger.info(f"  Total shots: {len(shot_data)}")

        # Filter to date range if possible
        if 'GAME_DATE' in shot_data.columns:
            shot_data_filtered = shot_data[
                (shot_data['GAME_DATE'] >= date_from) &
                (shot_data['GAME_DATE'] <= date_to)
            ]
            logger.info(f"  Shots in last 3 games: {len(shot_data_filtered)}")

        return {"total_shots": len(shot_data), "season": season}

    except Exception as e:
        logger.error(f"❌ Error in test_curry_shot_chart: {type(e).__name__}: {str(e)}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        return None


async def test_durant_monthly_progression():
    """Test: Kevin Durant's month over month progression last season"""
    logger.info("\n" + "="*80)
    logger.info("TEST 3: Kevin Durant's month over month progression last season")
    logger.info("="*80)

    try:
        client = NBAApiClient()

        # Step 1: Get full season game log
        logger.info("Step 1: Fetching KD's 2023-24 game log...")
        game_log = await client.get_player_game_log(
            player_name="Kevin Durant",
            season="2023-24",
            as_dataframe=True
        )
        logger.info(f"✓ Got {len(game_log)} games")

        # Step 2: Parse dates and group by month
        logger.info("\nStep 2: Grouping by month...")
        import pandas as pd

        game_log['GAME_DATE'] = pd.to_datetime(game_log['GAME_DATE'])
        game_log['MONTH'] = game_log['GAME_DATE'].dt.to_period('M')

        # Step 3: Calculate monthly averages
        logger.info("\nStep 3: Calculating monthly averages...")
        monthly_stats = game_log.groupby('MONTH').agg({
            'PTS': 'mean',
            'REB': 'mean',
            'AST': 'mean',
            'FG_PCT': 'mean',
            'GAME_ID': 'count'  # Number of games
        }).rename(columns={'GAME_ID': 'GAMES'})

        logger.info("✓ Monthly progression:")
        logger.info(f"\n{monthly_stats}")

        return monthly_stats.to_dict()

    except Exception as e:
        logger.error(f"❌ Error in test_durant_monthly_progression: {type(e).__name__}: {str(e)}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        return None


async def test_warriors_home_performance():
    """Test: Warriors home performance last season"""
    logger.info("\n" + "="*80)
    logger.info("TEST 4: Warriors home performance last season")
    logger.info("="*80)

    try:
        client = NBAApiClient()

        # Step 1: Get team game log
        logger.info("Step 1: Fetching Warriors 2023-24 game log...")
        game_log = await client.get_team_game_log(
            team_name="Warriors",
            season="2023-24",
            as_dataframe=True
        )
        logger.info(f"✓ Got {len(game_log)} games")

        # Step 2: Filter for home games
        logger.info("\nStep 2: Filtering for home games...")
        home_games = game_log[game_log["MATCHUP"].str.contains("vs\\.", na=False, regex=True)]
        logger.info(f"✓ Found {len(home_games)} home games")

        # Step 3: Calculate home record
        logger.info("\nStep 3: Calculating home record...")
        wins = (home_games["WL"] == "W").sum()
        losses = (home_games["WL"] == "L").sum()
        win_pct = wins / len(home_games) if len(home_games) > 0 else 0

        stats = {
            "games": len(home_games),
            "wins": int(wins),
            "losses": int(losses),
            "win_pct": win_pct,
            "avg_pts": home_games["PTS"].mean(),
            "avg_pts_allowed": home_games["PTS"].mean() - home_games["PLUS_MINUS"].mean()
        }

        logger.info("✓ Home performance:")
        logger.info(f"  Record: {stats['wins']}-{stats['losses']} ({stats['win_pct']:.1%})")
        logger.info(f"  Avg Points: {stats['avg_pts']:.1f}")
        logger.info(f"  Avg Points Allowed: {stats['avg_pts_allowed']:.1f}")

        return stats

    except Exception as e:
        logger.error(f"❌ Error in test_warriors_home_performance: {type(e).__name__}: {str(e)}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        return None


async def test_all_players_first_3_months():
    """Test: All players in first 3 months of last season"""
    logger.info("\n" + "="*80)
    logger.info("TEST 5: All players in first 3 months of last season per game")
    logger.info("="*80)

    try:
        from nba_stats_api.stats_api import get_league_leaders

        # Step 1: Get league leaders (this returns all qualifying players)
        logger.info("Step 1: Fetching league leaders data...")
        leaders = await get_league_leaders(
            stat_category="PTS",
            season="2023-24",
            per_mode="PerGame"
        )
        logger.info(f"✓ Got {len(leaders)} players")

        # Step 2: Get date range for first 3 months
        logger.info("\nStep 2: Filtering for first 3 months (Oct-Dec 2023)...")
        # 2023-24 season started around Oct 2023
        date_from = "2023-10-01"
        date_to = "2023-12-31"

        logger.info(f"  Date range: {date_from} to {date_to}")
        logger.info(f"  Total players: {len(leaders)}")

        # Note: Getting game-by-game data for ALL players would be too expensive
        # Instead, show sample of top 10 players
        logger.info("\nStep 3: Showing top 10 scorers...")
        top_10 = leaders.head(10)[['PLAYER', 'TEAM', 'GP', 'PTS', 'REB', 'AST']]
        logger.info(f"\n{top_10}")

        return {
            "total_players": len(leaders),
            "date_from": date_from,
            "date_to": date_to,
            "top_10": top_10.to_dict('records')
        }

    except Exception as e:
        logger.error(f"❌ Error in test_all_players_first_3_months: {type(e).__name__}: {str(e)}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        return None


async def test_nlq_queries():
    """Test the NLQ pipeline with the problematic queries"""
    logger.info("\n" + "="*80)
    logger.info("TEST 6: NLQ Pipeline Queries (Debug)")
    logger.info("="*80)

    queries = [
        "Show me LeBron James last 5 game averages at home for the 2024-25 season",
        "Show me Kevin Durant's month by month progression for the 2023-24 season"
    ]

    for i, query in enumerate(queries, 1):
        logger.info(f"\n--- Query {i}: {query} ---")
        try:
            result = await answer_nba_question(query, return_metadata=True)
            logger.info(f"✓ Result type: {type(result)}")

            if isinstance(result, dict):
                logger.info(f"✓ Keys: {result.keys()}")
                logger.info(f"✓ Answer length: {len(result.get('answer', ''))}")
            elif isinstance(result, str):
                logger.info(f"✓ String result length: {len(result)}")
                if "error" in result.lower() or "unexpected" in result.lower():
                    logger.error(f"❌ Error in result: {result}")
            else:
                logger.warning(f"⚠ Unexpected result type: {type(result)}")

        except Exception as e:
            logger.error(f"❌ Error in NLQ query: {type(e).__name__}: {str(e)}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")


# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Run all debug tests"""
    logger.info("="*80)
    logger.info("NBA MCP QUERY DEBUG SUITE")
    logger.info("="*80)
    logger.info(f"Log file: debug_mcp_queries.log")
    logger.info("")

    results = {}

    # Run each test
    results['lebron_home'] = await test_lebron_last_5_home()
    results['curry_shots'] = await test_curry_shot_chart()
    results['durant_monthly'] = await test_durant_monthly_progression()
    results['warriors_home'] = await test_warriors_home_performance()
    results['all_players'] = await test_all_players_first_3_months()

    # Test NLQ pipeline
    await test_nlq_queries()

    # Summary
    logger.info("\n" + "="*80)
    logger.info("SUMMARY")
    logger.info("="*80)
    for test_name, result in results.items():
        status = "✓ PASS" if result is not None else "❌ FAIL"
        logger.info(f"{test_name}: {status}")

    logger.info("\nFull debug log saved to: debug_mcp_queries.log")


if __name__ == "__main__":
    asyncio.run(main())
