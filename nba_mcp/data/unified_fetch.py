"""
Unified dataset fetching system for NBA MCP.

This module provides a single, efficient entry point for all data fetching operations,
replacing the fragmented if/elif routing with a clean, extensible interface.

Features:
- Single unified fetch function for all endpoints
- Batch fetching with parallel execution
- Automatic parameter processing and validation
- Entity resolution (player/team names → IDs)
- Generic filter support (post-fetch filtering)
- Provenance tracking
- Comprehensive error handling
- Easy to use for frontend APIs or MCP tools

Usage:
    # Simple single fetch
    data, prov = await unified_fetch(
        "player_career_stats",
        {"player_name": "LeBron James", "season": "2023-24"}
    )

    # Fetch with filters
    data, prov = await unified_fetch(
        "team_game_log",
        {"team": "Lakers", "season": "2023-24"},
        filters={"WL": ["==", "W"], "PTS": [">=", 110]}
    )

    # Batch fetch (parallel)
    results = await batch_fetch([
        {"endpoint": "player_career_stats", "params": {"player_name": "LeBron"}},
        {"endpoint": "team_standings", "params": {"season": "2023-24"}},
    ])
"""

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime
import logging

import pandas as pd
import pyarrow as pa
import duckdb

from nba_mcp.data.endpoint_registry import get_registry
from nba_mcp.data.parameter_processor import get_processor, ParameterValidationError
from nba_mcp.data.dataset_manager import ProvenanceInfo
from nba_mcp.data.catalog import get_catalog
from nba_mcp.data.cache_integration import get_cache_manager
from nba_mcp.data.filter_pushdown import get_pushdown_mapper
from nba_mcp.api.errors import NBAApiError, EntityNotFoundError

logger = logging.getLogger(__name__)


class FetchError(Exception):
    """Raised when data fetching fails."""
    pass


class UnifiedFetchResult:
    """
    Container for fetch results with comprehensive metadata.

    Attributes:
        data: PyArrow Table with fetched data
        provenance: Provenance tracking information
        warnings: Non-fatal warnings from processing
        transformations: Record of applied transformations
        execution_time_ms: Total execution time
        from_cache: Whether result was from cache
    """

    def __init__(
        self,
        data: pa.Table,
        provenance: ProvenanceInfo,
        warnings: Optional[List[str]] = None,
        transformations: Optional[List[str]] = None,
        execution_time_ms: float = 0.0,
        from_cache: bool = False
    ):
        self.data = data
        self.provenance = provenance
        self.warnings = warnings or []
        self.transformations = transformations or []
        self.execution_time_ms = execution_time_ms
        self.from_cache = from_cache

    def to_tuple(self) -> Tuple[pa.Table, ProvenanceInfo]:
        """Convert to simple (data, provenance) tuple for backward compatibility."""
        return (self.data, self.provenance)

    def __repr__(self) -> str:
        return (
            f"UnifiedFetchResult(rows={self.data.num_rows}, "
            f"cols={self.data.num_columns}, "
            f"time={self.execution_time_ms:.2f}ms, "
            f"cached={self.from_cache})"
        )


async def unified_fetch(
    endpoint: str,
    params: Dict[str, Any],
    filters: Optional[Dict[str, List[Any]]] = None,
    as_arrow: bool = True,
    apply_defaults: bool = True,
    resolve_entities: bool = True,
    use_cache: bool = True,
    force_refresh: bool = False
) -> Union[UnifiedFetchResult, Tuple[pa.Table, ProvenanceInfo]]:
    """
    Unified entry point for fetching NBA data from any endpoint.

    This function replaces the if/elif chain in fetch.py with a clean,
    extensible interface that automatically handles:
    - Parameter validation and normalization
    - Entity resolution (player/team names → IDs)
    - Handler routing via registry
    - Post-fetch filtering
    - Provenance tracking
    - Error handling

    Args:
        endpoint: Endpoint name (e.g., "player_career_stats")
        params: Raw parameters (will be processed automatically)
        filters: Optional post-fetch filters (DuckDB syntax)
                 Format: {"column": ["operator", value], ...}
                 Example: {"PTS": [">=", 20], "WL": ["==", "W"]}
        as_arrow: If True, return PyArrow Table; if False, return pandas DataFrame
        apply_defaults: Whether to apply smart defaults from catalog
        resolve_entities: Whether to resolve player/team names to IDs
        use_cache: Whether to use Redis/memory cache (default: True)
        force_refresh: Force cache refresh even if data exists (default: False)

    Returns:
        UnifiedFetchResult with data, provenance, and metadata
        Or tuple (data, provenance) for backward compatibility

    Raises:
        FetchError: If fetch fails
        ParameterValidationError: If parameters are invalid

    Examples:
        # Simple fetch
        result = await unified_fetch(
            "player_career_stats",
            {"player_name": "LeBron James"}
        )

        # Fetch with filters
        result = await unified_fetch(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"},
            filters={"WL": ["==", "W"], "PTS": [">=", 110]}
        )

        # Get just the data
        data, prov = result.to_tuple()
    """
    start_time = time.time()

    # Step 1: Get handler from registry
    registry = get_registry()
    handler = registry.get_handler(endpoint)

    if handler is None:
        available = registry.list_endpoints()
        raise FetchError(
            f"Endpoint '{endpoint}' not registered. "
            f"Available endpoints: {', '.join(available)}"
        )

    # Step 2: Process parameters
    try:
        processor = get_processor()
        processed = await processor.process(
            endpoint=endpoint,
            params=params,
            apply_defaults=apply_defaults,
            resolve_entities=resolve_entities
        )
    except ParameterValidationError as e:
        raise FetchError(f"Parameter validation failed: {str(e)}") from e

    # Step 3: Filter pushdown - split filters into API params and post-fetch filters
    # This MUST happen BEFORE provenance creation so pushed params are captured
    post_fetch_filters = filters
    pushed_param_count = 0

    if filters:
        pushdown_mapper = get_pushdown_mapper()
        api_filter_params, post_fetch_filters = pushdown_mapper.split_filters(
            endpoint=endpoint,
            filters=filters,
            params=processed.params
        )

        # Merge pushed-down filters into parameters
        if api_filter_params:
            processed.params.update(api_filter_params)
            pushed_param_count = len(api_filter_params)
            processed.transformations.append(
                f"Pushed {pushed_param_count} filter(s) to API: {list(api_filter_params.keys())}"
            )
            logger.info(f"Filter pushdown: {api_filter_params}")

    # Step 4: Set up provenance tracking (AFTER filter pushdown)
    # Build operations list
    operations = ["unified_fetch"]

    # Add transformation operations
    if processed.transformations:
        operations.extend([f"transform:{t}" for t in processed.transformations])

    # Add filter pushdown operation if filters were pushed
    if pushed_param_count > 0:
        operations.append(f"filter_pushdown:{pushed_param_count} params")

    # Create provenance with finalized parameters (including pushed filters)
    provenance = ProvenanceInfo(
        source_endpoints=[endpoint],
        operations=operations,
        parameters=processed.params,  # Now includes pushed parameters!
    )

    # Step 5: Get data from cache or fetch
    cache_mgr = get_cache_manager(enable_cache=use_cache)
    from_cache = False

    async def fetch_func():
        """Wrapper function for cache integration."""
        data = await handler(processed.params, provenance)
        # Convert to Arrow table for consistent caching
        if isinstance(data, pd.DataFrame):
            return pa.Table.from_pandas(data)
        elif isinstance(data, pa.Table):
            return data
        else:
            # Handle dict or list of dicts
            return pa.Table.from_pandas(pd.DataFrame(data))

    try:
        if use_cache:
            data, from_cache = await cache_mgr.get_or_fetch(
                endpoint,
                processed.params,
                fetch_func,
                force_refresh=force_refresh
            )

            if from_cache:
                provenance.operations.append("cache:hit")
                provenance.cache_hits = getattr(provenance, 'cache_hits', 0) + 1
            else:
                provenance.operations.append("cache:miss")
                provenance.cache_misses = getattr(provenance, 'cache_misses', 0) + 1
        else:
            # Cache disabled, fetch directly
            data = await fetch_func()
            from_cache = False

    except (EntityNotFoundError, NBAApiError, ValueError) as e:
        execution_time_ms = (time.time() - start_time) * 1000
        provenance.execution_time_ms = execution_time_ms
        logger.error(f"Failed to fetch from '{endpoint}': {e}")
        raise FetchError(f"Failed to fetch from '{endpoint}': {str(e)}") from e
    except Exception as e:
        execution_time_ms = (time.time() - start_time) * 1000
        provenance.execution_time_ms = execution_time_ms
        logger.exception(f"Unexpected error fetching from '{endpoint}'")
        raise FetchError(
            f"Unexpected error fetching from '{endpoint}': {str(e)}"
        ) from e

    # Step 5: Convert to PyArrow Table if needed
    if as_arrow:
        if isinstance(data, pd.DataFrame):
            table = pa.Table.from_pandas(data)
        elif isinstance(data, pa.Table):
            table = data
        else:
            # Handle dict or list of dicts
            table = pa.Table.from_pandas(pd.DataFrame(data))

        # Add metadata
        metadata = {
            "endpoint": endpoint,
            "fetched_at": datetime.utcnow().isoformat(),
            "row_count": str(table.num_rows),
            "column_count": str(table.num_columns),
        }
        table = table.replace_schema_metadata(metadata)
    else:
        # Return as DataFrame or original format
        if isinstance(data, pa.Table):
            table = data.to_pandas()
        else:
            table = data

    # Step 6: Apply post-fetch filters if specified (skip if table is empty)
    # Optimization: Skip filtering if table is empty (0 rows) to prevent unnecessary DuckDB queries
    # This can occur when API-level filters (e.g., date_from) return no matching data
    if post_fetch_filters and isinstance(table, pa.Table):
        if table.num_rows == 0:
            logger.debug(f"Skipping post-fetch filters: table is empty (0 rows)")
            provenance.operations.append("post_filter:skipped (empty table)")
        else:
            try:
                table = apply_filters(table, post_fetch_filters)
                provenance.operations.append(f"post_filter:{len(post_fetch_filters)} conditions")
                logger.debug(f"Applied {len(post_fetch_filters)} post-fetch filter(s)")
            except Exception as e:
                logger.warning(f"Failed to apply post-fetch filters: {e}")
                processed.warnings.append(f"Post-fetch filter application failed: {str(e)}")

    # Step 7: Calculate execution time
    execution_time_ms = (time.time() - start_time) * 1000
    provenance.execution_time_ms = execution_time_ms

    # Return unified result
    return UnifiedFetchResult(
        data=table,
        provenance=provenance,
        warnings=processed.warnings,
        transformations=processed.transformations,
        execution_time_ms=execution_time_ms,
        from_cache=from_cache
    )


async def batch_fetch(
    requests: List[Dict[str, Any]],
    as_arrow: bool = True,
    max_concurrent: int = 5
) -> List[UnifiedFetchResult]:
    """
    Fetch multiple datasets in parallel for efficiency.

    This function executes multiple fetch operations concurrently using
    asyncio.gather(), which is much faster than sequential fetching.

    Args:
        requests: List of request dictionaries, each containing:
                  - endpoint: Endpoint name
                  - params: Parameters dict
                  - filters: Optional filters dict
        as_arrow: Whether to return PyArrow Tables
        max_concurrent: Maximum concurrent requests (to avoid overwhelming API)

    Returns:
        List of UnifiedFetchResult objects (one per request)

    Raises:
        FetchError: If any fetch fails

    Example:
        results = await batch_fetch([
            {
                "endpoint": "player_career_stats",
                "params": {"player_name": "LeBron James"}
            },
            {
                "endpoint": "team_standings",
                "params": {"season": "2023-24"}
            },
            {
                "endpoint": "league_leaders",
                "params": {"stat_category": "PTS"},
                "filters": {"PTS": [">=", 25]}
            }
        ])

        # Access results
        for result in results:
            print(f"Fetched {result.data.num_rows} rows in {result.execution_time_ms:.2f}ms")
    """
    if not requests:
        return []

    # Create semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_with_semaphore(request: Dict[str, Any]) -> UnifiedFetchResult:
        """Wrapper to apply semaphore."""
        async with semaphore:
            return await unified_fetch(
                endpoint=request["endpoint"],
                params=request.get("params", {}),
                filters=request.get("filters"),
                as_arrow=as_arrow
            )

    # Execute all requests in parallel
    try:
        results = await asyncio.gather(
            *[fetch_with_semaphore(req) for req in requests],
            return_exceptions=False  # Raise first exception
        )
        return results
    except Exception as e:
        raise FetchError(f"Batch fetch failed: {str(e)}") from e


def apply_filters(
    table: pa.Table,
    filters: Dict[str, List[Any]]
) -> pa.Table:
    """
    Apply post-fetch filters to a PyArrow table using DuckDB.

    This provides generic filtering that works on any tabular data,
    regardless of the endpoint.

    Filter format:
        {
            "column_name": ["operator", value],
            ...
        }

    Supported operators:
        - "==", "!=": Equality
        - ">", ">=", "<", "<=": Comparison
        - "IN": Value in list
        - "BETWEEN": Value between two values
        - "LIKE": String pattern matching

    Args:
        table: PyArrow Table to filter
        filters: Dictionary of filter conditions

    Returns:
        Filtered PyArrow Table

    Raises:
        ValueError: If filter syntax is invalid

    Examples:
        # Simple equality
        filtered = apply_filters(table, {"WL": ["==", "W"]})

        # Comparison
        filtered = apply_filters(table, {"PTS": [">=", 20]})

        # Multiple filters (AND)
        filtered = apply_filters(table, {
            "WL": ["==", "W"],
            "PTS": [">=", 110],
            "FG_PCT": [">", 0.5]
        })

        # IN operator
        filtered = apply_filters(table, {
            "TEAM_ABBREVIATION": ["IN", ["LAL", "GSW", "BOS"]]
        })
    """
    if not filters:
        return table

    # Build SQL WHERE clause
    conditions = []
    for column, filter_spec in filters.items():
        if not isinstance(filter_spec, list) or len(filter_spec) < 2:
            raise ValueError(
                f"Invalid filter for '{column}': must be [operator, value]"
            )

        operator = filter_spec[0].upper()
        value = filter_spec[1]

        # Validate column exists
        if column not in table.column_names:
            raise ValueError(
                f"Column '{column}' not found in table. "
                f"Available: {', '.join(table.column_names)}"
            )

        # Build condition based on operator
        if operator in ("==", "="):
            if isinstance(value, str):
                conditions.append(f'"{column}" = \'{value}\'')
            else:
                conditions.append(f'"{column}" = {value}')

        elif operator == "!=":
            if isinstance(value, str):
                conditions.append(f'"{column}" != \'{value}\'')
            else:
                conditions.append(f'"{column}" != {value}')

        elif operator in (">", ">=", "<", "<="):
            conditions.append(f'"{column}" {operator} {value}')

        elif operator == "IN":
            if not isinstance(value, (list, tuple)):
                raise ValueError(f"IN operator requires a list, got {type(value)}")
            # Format list values
            if value and isinstance(value[0], str):
                values_str = ", ".join(f"'{v}'" for v in value)
            else:
                values_str = ", ".join(str(v) for v in value)
            conditions.append(f'"{column}" IN ({values_str})')

        elif operator == "BETWEEN":
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise ValueError("BETWEEN operator requires [min, max]")
            conditions.append(f'"{column}" BETWEEN {value[0]} AND {value[1]}')

        elif operator == "LIKE":
            if not isinstance(value, str):
                raise ValueError("LIKE operator requires a string pattern")
            conditions.append(f'"{column}" LIKE \'{value}\'')

        else:
            raise ValueError(
                f"Unsupported operator: {operator}. "
                f"Supported: ==, !=, >, >=, <, <=, IN, BETWEEN, LIKE"
            )

    # Combine conditions with AND
    where_clause = " AND ".join(conditions)

    # Execute filter using DuckDB with registered table
    # FIX: DuckDB requires explicit table registration - 'table' is a keyword, not a reference
    # We register the Arrow table temporarily, query it, then close the connection
    try:
        con = duckdb.connect(':memory:')
        con.register('arrow_table', table)
        filtered = con.execute(
            f'SELECT * FROM arrow_table WHERE {where_clause}'
        ).fetch_arrow_table()
        con.close()
        return filtered
    except Exception as e:
        raise ValueError(f"Filter execution failed: {str(e)}") from e


# Backward compatibility alias
fetch_endpoint = unified_fetch
