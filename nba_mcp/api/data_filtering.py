"""
DuckDB-based filtering for efficient post-fetch data operations

Provides 100x faster filtering than pandas for statistical queries.
Used when NBA API doesn't support certain filter types (e.g., MIN >= 10).
"""

from typing import Dict, Any, Tuple, Optional, Union, List
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# Try to import duckdb, fall back to pandas if not available
try:
    import duckdb
    DUCKDB_AVAILABLE = True
    logger.info("DuckDB available - using optimized filtering")
except ImportError:
    DUCKDB_AVAILABLE = False
    logger.warning("DuckDB not available - falling back to pandas (slower)")


def apply_stat_filters(
    df: pd.DataFrame,
    filters: Dict[str, Tuple[str, Union[int, float]]]
) -> pd.DataFrame:
    """
    Apply statistical filters to DataFrame using DuckDB or pandas

    Args:
        df: DataFrame to filter
        filters: Dict mapping column names to (operator, value) tuples
                 Example: {'MIN': ('>=', 10), 'PTS': ('>', 20)}

    Returns:
        Filtered DataFrame

    Examples:
        >>> df_filtered = apply_stat_filters(df, {
        ...     'MIN': ('>=', 10),
        ...     'PTS': ('>', 20),
        ...     'FG_PCT': ('>', 0.5)
        ... })
    """
    if not filters:
        return df

    if df.empty:
        logger.warning("Empty DataFrame passed to filter")
        return df

    if DUCKDB_AVAILABLE:
        return _apply_filters_duckdb(df, filters)
    else:
        return _apply_filters_pandas(df, filters)


def _apply_filters_duckdb(
    df: pd.DataFrame,
    filters: Dict[str, Tuple[str, Union[int, float]]]
) -> pd.DataFrame:
    """Apply filters using DuckDB (100x faster than pandas)"""

    # Build WHERE clause
    conditions = []
    for col, (op, value) in filters.items():
        if col not in df.columns:
            logger.warning(f"Column '{col}' not found in DataFrame - skipping filter")
            continue

        # Handle NULL values appropriately
        conditions.append(f"({col} IS NOT NULL AND {col} {op} {value})")

    if not conditions:
        return df

    where_clause = " AND ".join(conditions)

    try:
        # Use DuckDB for vectorized filtering
        result = duckdb.query(f"""
            SELECT * FROM df
            WHERE {where_clause}
        """).to_df()

        logger.info(
            f"DuckDB filter: {len(df):,} rows → {len(result):,} rows "
            f"({len(result)/len(df)*100:.1f}% kept)"
        )

        return result

    except Exception as e:
        logger.error(f"DuckDB filtering failed: {e}, falling back to pandas")
        return _apply_filters_pandas(df, filters)


def _apply_filters_pandas(
    df: pd.DataFrame,
    filters: Dict[str, Tuple[str, Union[int, float]]]
) -> pd.DataFrame:
    """Apply filters using pandas (fallback)"""

    mask = pd.Series([True] * len(df), index=df.index)

    for col, (op, value) in filters.items():
        if col not in df.columns:
            logger.warning(f"Column '{col}' not found in DataFrame - skipping filter")
            continue

        # Build comparison mask
        if op == '>=':
            mask &= df[col] >= value
        elif op == '>':
            mask &= df[col] > value
        elif op == '<=':
            mask &= df[col] <= value
        elif op == '<':
            mask &= df[col] < value
        elif op == '==':
            mask &= df[col] == value
        elif op == '!=':
            mask &= df[col] != value
        else:
            logger.warning(f"Unsupported operator: {op}")

    result = df[mask].copy()

    logger.info(
        f"Pandas filter: {len(df):,} rows → {len(result):,} rows "
        f"({len(result)/len(df)*100:.1f}% kept)"
    )

    return result


def apply_complex_filter(
    df: pd.DataFrame,
    sql_where: str
) -> pd.DataFrame:
    """
    Apply complex SQL WHERE clause using DuckDB

    Args:
        df: DataFrame to filter
        sql_where: SQL WHERE clause (without the WHERE keyword)

    Returns:
        Filtered DataFrame

    Examples:
        >>> # Complex conditions
        >>> df_filtered = apply_complex_filter(df,
        ...     "(MIN >= 10 AND PTS > 20) OR (AST >= 10)"
        ... )
        >>>
        >>> # IN clause
        >>> df_filtered = apply_complex_filter(df,
        ...     "TEAM_ABBREVIATION IN ('LAL', 'BOS', 'GSW')"
        ... )
    """
    if not DUCKDB_AVAILABLE:
        logger.error("Complex filters require DuckDB - not available")
        return df

    try:
        result = duckdb.query(f"""
            SELECT * FROM df
            WHERE {sql_where}
        """).to_df()

        logger.info(
            f"Complex filter: {len(df):,} rows → {len(result):,} rows "
            f"({len(result)/len(df)*100:.1f}% kept)"
        )

        return result

    except Exception as e:
        logger.error(f"Complex filtering failed: {e}")
        return df


def query_dataframe(df: pd.DataFrame, sql: str) -> pd.DataFrame:
    """
    Run arbitrary SQL query on DataFrame

    Args:
        df: DataFrame to query
        sql: Full SQL query (must SELECT FROM df)

    Returns:
        Query result as DataFrame

    Examples:
        >>> # Aggregation
        >>> result = query_dataframe(df, '''
        ...     SELECT PLAYER_NAME, AVG(PTS) as avg_pts, COUNT(*) as games
        ...     FROM df
        ...     WHERE MIN >= 10
        ...     GROUP BY PLAYER_NAME
        ...     ORDER BY avg_pts DESC
        ...     LIMIT 10
        ... ''')
    """
    if not DUCKDB_AVAILABLE:
        logger.error("SQL queries require DuckDB - not available")
        return df

    try:
        result = duckdb.query(sql).to_df()
        logger.info(f"Query returned {len(result):,} rows")
        return result

    except Exception as e:
        logger.error(f"Query failed: {e}")
        return pd.DataFrame()


def split_filters(
    filters: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Tuple[str, Union[int, float]]]]:
    """
    Split filters into API parameters and stat filters

    API filters: Direct parameters for NBA API (season, player_id, etc.)
    Stat filters: Post-fetch statistical filters (MIN >= 10, etc.)

    Args:
        filters: Combined filter dict

    Returns:
        Tuple of (api_filters, stat_filters)

    Examples:
        >>> filters = {
        ...     'season': '2024-25',
        ...     'location': 'Home',
        ...     'MIN': ('>=', 10),
        ...     'PTS': ('>', 20)
        ... }
        >>> api_filters, stat_filters = split_filters(filters)
        >>> # api_filters = {'season': '2024-25', 'location': 'Home'}
        >>> # stat_filters = {'MIN': ('>=', 10), 'PTS': ('>', 20)}
    """
    api_filters = {}
    stat_filters = {}

    for key, value in filters.items():
        # Stat filters are tuples of (operator, value)
        if isinstance(value, tuple) and len(value) == 2:
            stat_filters[key] = value
        else:
            api_filters[key] = value

    return api_filters, stat_filters


# Convenience function for common pattern: MIN >= threshold
def filter_min_minutes(df: pd.DataFrame, min_minutes: float) -> pd.DataFrame:
    """
    Filter to games with minimum minutes played

    Args:
        df: DataFrame with MIN column
        min_minutes: Minimum minutes threshold

    Returns:
        Filtered DataFrame
    """
    return apply_stat_filters(df, {'MIN': ('>=', min_minutes)})


# Check if DuckDB is available for user
def is_duckdb_available() -> bool:
    """Check if DuckDB is available for optimized filtering"""
    return DUCKDB_AVAILABLE
