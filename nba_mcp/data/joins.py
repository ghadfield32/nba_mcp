"""
DuckDB-powered SQL joins for NBA MCP datasets.

Provides safe, validated join operations on PyArrow tables using DuckDB.
"""

from typing import List, Union, Dict, Any, Literal, Optional
import pyarrow as pa
import duckdb
from datetime import datetime


class JoinError(Exception):
    """Raised when join operation fails."""

    pass


def validate_join_columns(
    tables: List[pa.Table], on: Union[str, List[str], Dict[str, str]]
) -> bool:
    """
    Validate that join columns exist in all tables.

    Args:
        tables: List of PyArrow tables to join
        on: Column name(s) or mapping for join

    Returns:
        True if valid

    Raises:
        JoinError: If columns don't exist or are invalid
    """
    if len(tables) < 2:
        raise JoinError("At least 2 tables required for join")

    # Convert on to consistent format
    if isinstance(on, str):
        # Single column name - must exist in all tables
        for i, table in enumerate(tables):
            if on not in table.column_names:
                raise JoinError(
                    f"Join column '{on}' not found in table {i}. "
                    f"Available columns: {', '.join(table.column_names)}"
                )

    elif isinstance(on, list):
        # List of column names - must exist in all tables
        for col in on:
            for i, table in enumerate(tables):
                if col not in table.column_names:
                    raise JoinError(
                        f"Join column '{col}' not found in table {i}. "
                        f"Available columns: {', '.join(table.column_names)}"
                    )

    elif isinstance(on, dict):
        # Dictionary mapping {left_col: right_col}
        if len(tables) != 2:
            raise JoinError(
                "Dictionary join keys only supported for exactly 2 tables. "
                f"Got {len(tables)} tables."
            )

        left_table, right_table = tables[0], tables[1]

        for left_col, right_col in on.items():
            if left_col not in left_table.column_names:
                raise JoinError(
                    f"Left join column '{left_col}' not found in first table. "
                    f"Available columns: {', '.join(left_table.column_names)}"
                )
            if right_col not in right_table.column_names:
                raise JoinError(
                    f"Right join column '{right_col}' not found in second table. "
                    f"Available columns: {', '.join(right_table.column_names)}"
                )

    else:
        raise JoinError(
            f"Invalid 'on' parameter type: {type(on)}. "
            f"Must be str, list, or dict."
        )

    return True


def join_tables(
    tables: List[pa.Table],
    on: Union[str, List[str], Dict[str, str]],
    how: Literal["inner", "left", "right", "outer", "cross"] = "left",
    suffixes: tuple[str, str] = ("_left", "_right"),
) -> pa.Table:
    """
    Join multiple PyArrow tables using DuckDB.

    Args:
        tables: List of PyArrow tables to join (2 or more)
        on: Join column(s):
            - str: Single column name present in all tables
            - List[str]: Multiple columns present in all tables
            - Dict[str, str]: Mapping {left_col: right_col} for 2 tables
        how: Join type (inner, left, right, outer, cross)
        suffixes: Suffixes for duplicate column names (left, right)

    Returns:
        Joined PyArrow table

    Raises:
        JoinError: If join fails or validation fails

    Examples:
        # Simple join on single column
        result = join_tables([table1, table2], on="PLAYER_ID", how="inner")

        # Join on multiple columns
        result = join_tables(
            [table1, table2],
            on=["PLAYER_ID", "SEASON"],
            how="left"
        )

        # Join with column mapping
        result = join_tables(
            [player_table, team_table],
            on={"TEAM_ID": "ID"},
            how="left"
        )
    """
    # Validate inputs
    if len(tables) < 2:
        raise JoinError("At least 2 tables required for join")

    if how not in ["inner", "left", "right", "outer", "cross"]:
        raise JoinError(
            f"Invalid join type: {how}. Must be one of: inner, left, right, outer, cross"
        )

    # Validate columns
    validate_join_columns(tables, on)

    try:
        # Create DuckDB connection (in-memory)
        conn = duckdb.connect(":memory:")

        # Register tables with DuckDB
        for i, table in enumerate(tables):
            conn.register(f"table_{i}", table)

        # Build SQL query
        if isinstance(on, dict) and len(tables) == 2:
            # Dictionary join with column mapping
            join_conditions = " AND ".join(
                [f"table_0.{left} = table_1.{right}" for left, right in on.items()]
            )
            sql = f"""
                SELECT * FROM table_0
                {how.upper()} JOIN table_1
                ON {join_conditions}
            """

        elif isinstance(on, str):
            # Simple single column join
            sql = f"SELECT * FROM table_0"
            for i in range(1, len(tables)):
                sql += f" {how.upper()} JOIN table_{i} USING ({on})"

        elif isinstance(on, list):
            # Multiple column join
            using_clause = ", ".join(on)
            sql = f"SELECT * FROM table_0"
            for i in range(1, len(tables)):
                sql += f" {how.upper()} JOIN table_{i} USING ({using_clause})"

        else:
            raise JoinError(f"Unsupported 'on' type: {type(on)}")

        # Execute join
        result = conn.execute(sql).fetch_arrow_table()

        # Close connection
        conn.close()

        # Add metadata
        metadata = {
            "join_type": how,
            "join_columns": str(on),
            "input_tables": str(len(tables)),
            "joined_at": datetime.utcnow().isoformat(),
        }
        result = result.replace_schema_metadata(metadata)

        return result

    except duckdb.Error as e:
        raise JoinError(f"DuckDB join failed: {str(e)}") from e
    except Exception as e:
        raise JoinError(f"Join operation failed: {str(e)}") from e


def join_with_stats(
    tables: List[pa.Table],
    on: Union[str, List[str], Dict[str, str]],
    how: Literal["inner", "left", "right", "outer", "cross"] = "left",
) -> Dict[str, Any]:
    """
    Join tables and return both result and statistics.

    Args:
        tables: List of tables to join
        on: Join columns
        how: Join type

    Returns:
        Dictionary with:
            - result: Joined PyArrow table
            - stats: Join statistics
    """
    import time

    start_time = time.time()

    # Get input stats
    input_rows = [t.num_rows for t in tables]
    input_cols = [t.num_columns for t in tables]

    # Perform join
    result = join_tables(tables, on, how)

    # Calculate statistics
    execution_time_ms = (time.time() - start_time) * 1000

    return {
        "result": result,
        "stats": {
            "input_table_count": len(tables),
            "input_row_counts": input_rows,
            "input_column_counts": input_cols,
            "output_row_count": result.num_rows,
            "output_column_count": result.num_columns,
            "join_type": how,
            "join_columns": str(on),
            "execution_time_ms": round(execution_time_ms, 2),
            "row_reduction": sum(input_rows) - result.num_rows,
            "column_union": result.num_columns - input_cols[0],
        },
    }


def cross_join_tables(left: pa.Table, right: pa.Table) -> pa.Table:
    """
    Perform a cross join (Cartesian product) of two tables.

    Args:
        left: Left table
        right: Right table

    Returns:
        Cross-joined table

    Note:
        Cross joins can produce very large results.
        Result size = left_rows × right_rows
    """
    return join_tables([left, right], on=[], how="cross")


def anti_join(left: pa.Table, right: pa.Table, on: Union[str, List[str]]) -> pa.Table:
    """
    Perform an anti join (return rows from left that don't match right).

    Args:
        left: Left table
        right: Right table
        on: Join column(s)

    Returns:
        Table with rows from left that have no match in right
    """
    conn = duckdb.connect(":memory:")
    conn.register("left_table", left)
    conn.register("right_table", right)

    if isinstance(on, str):
        on_clause = f"left_table.{on} = right_table.{on}"
    elif isinstance(on, list):
        on_clause = " AND ".join([f"left_table.{col} = right_table.{col}" for col in on])
    else:
        raise JoinError("Anti join requires str or list for 'on' parameter")

    sql = f"""
        SELECT left_table.*
        FROM left_table
        LEFT JOIN right_table ON {on_clause}
        WHERE right_table.{on if isinstance(on, str) else on[0]} IS NULL
    """

    result = conn.execute(sql).fetch_arrow_table()
    conn.close()

    return result


def semi_join(left: pa.Table, right: pa.Table, on: Union[str, List[str]]) -> pa.Table:
    """
    Perform a semi join (return rows from left that have a match in right).

    Args:
        left: Left table
        right: Right table
        on: Join column(s)

    Returns:
        Table with rows from left that have a match in right
    """
    conn = duckdb.connect(":memory:")
    conn.register("left_table", left)
    conn.register("right_table", right)

    if isinstance(on, str):
        on_clause = f"left_table.{on} = right_table.{on}"
    elif isinstance(on, list):
        on_clause = " AND ".join([f"left_table.{col} = right_table.{col}" for col in on])
    else:
        raise JoinError("Semi join requires str or list for 'on' parameter")

    sql = f"""
        SELECT DISTINCT left_table.*
        FROM left_table
        INNER JOIN right_table ON {on_clause}
    """

    result = conn.execute(sql).fetch_arrow_table()
    conn.close()

    return result


def union_tables(
    tables: List[pa.Table], all: bool = True, check_schema: bool = True
) -> pa.Table:
    """
    Union multiple tables (stack rows).

    Args:
        tables: List of tables to union
        all: If True, keep duplicates (UNION ALL); if False, remove duplicates (UNION)
        check_schema: If True, validate that all tables have the same schema

    Returns:
        Unioned table

    Raises:
        JoinError: If schemas don't match (when check_schema=True)
    """
    if len(tables) < 2:
        raise JoinError("At least 2 tables required for union")

    if check_schema:
        # Check that all tables have the same schema
        first_schema = tables[0].schema
        for i, table in enumerate(tables[1:], start=1):
            if not table.schema.equals(first_schema):
                raise JoinError(
                    f"Table {i} schema doesn't match first table schema. "
                    f"Use check_schema=False to skip validation."
                )

    try:
        conn = duckdb.connect(":memory:")

        # Register all tables
        for i, table in enumerate(tables):
            conn.register(f"table_{i}", table)

        # Build UNION query
        union_type = "UNION ALL" if all else "UNION"
        sql = " ".join(
            [f"SELECT * FROM table_{i}" for i in range(len(tables))],
        )
        sql = f" {union_type} ".join(
            [f"SELECT * FROM table_{i}" for i in range(len(tables))]
        )

        result = conn.execute(sql).fetch_arrow_table()
        conn.close()

        return result

    except duckdb.Error as e:
        raise JoinError(f"DuckDB union failed: {str(e)}") from e


def aggregate_table(
    table: pa.Table,
    group_by: List[str],
    aggregations: Dict[str, str],
) -> pa.Table:
    """
    Aggregate a table using GROUP BY.

    Args:
        table: Input table
        group_by: Columns to group by
        aggregations: Dictionary of {column: agg_function}
            agg_function can be: sum, avg, count, min, max, etc.

    Returns:
        Aggregated table

    Example:
        aggregate_table(
            table,
            group_by=["TEAM_ID"],
            aggregations={"PTS": "avg", "REB": "sum", "PLAYER_ID": "count"}
        )
    """
    conn = duckdb.connect(":memory:")
    conn.register("input_table", table)

    # Build aggregation clause
    agg_clauses = [
        f"{func}({col}) as {col}_{func}" for col, func in aggregations.items()
    ]
    group_clause = ", ".join(group_by)
    select_clause = ", ".join([group_clause] + agg_clauses)

    sql = f"""
        SELECT {select_clause}
        FROM input_table
        GROUP BY {group_clause}
    """

    result = conn.execute(sql).fetch_arrow_table()
    conn.close()

    return result


def filter_table(
    table: pa.Table, conditions: List[Dict[str, Any]]
) -> pa.Table:
    """
    Filter a table using SQL WHERE conditions.

    Args:
        table: Input table
        conditions: List of condition dicts:
            {"column": "PTS", "op": ">", "value": 20}
            op can be: =, !=, <, >, <=, >=, IN, NOT IN, LIKE

    Returns:
        Filtered table

    Example:
        filter_table(
            table,
            [
                {"column": "PTS", "op": ">", "value": 20},
                {"column": "TEAM_ID", "op": "=", "value": "1610612747"}
            ]
        )
    """
    conn = duckdb.connect(":memory:")
    conn.register("input_table", table)

    # Build WHERE clause
    where_clauses = []
    for cond in conditions:
        column = cond["column"]
        op = cond["op"]
        value = cond["value"]

        if isinstance(value, str):
            value = f"'{value}'"
        elif isinstance(value, list):
            value = f"({', '.join([f"'{v}'" if isinstance(v, str) else str(v) for v in value])})"

        where_clauses.append(f"{column} {op} {value}")

    where_clause = " AND ".join(where_clauses)

    sql = f"""
        SELECT * FROM input_table
        WHERE {where_clause}
    """

    result = conn.execute(sql).fetch_arrow_table()
    conn.close()

    return result
