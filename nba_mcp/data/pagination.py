"""
Pagination and chunking utilities for large NBA datasets.

Handles large dataset fetching by:
- Splitting requests into manageable chunks
- Yielding results incrementally
- Providing progress tracking
- Supporting multiple chunking strategies (date, season, game)

This enables fetching datasets of any size without memory issues.
"""

import asyncio
import logging
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple
from datetime import date, datetime, timedelta
from dataclasses import dataclass
import pyarrow as pa

from nba_mcp.data.fetch import fetch_endpoint, FetchError
from nba_mcp.data.introspection import get_introspector, EndpointCapabilities

logger = logging.getLogger(__name__)


@dataclass
class ChunkInfo:
    """Information about a data chunk."""

    chunk_number: int
    total_chunks: int
    params: Dict[str, Any]
    row_count: int
    date_range: Optional[Tuple[date, date]] = None
    season: Optional[str] = None
    game_id: Optional[str] = None


class DatasetPaginator:
    """
    Handle large dataset fetching with chunking strategies.

    Supports three chunking strategies:
    1. Date-based: Split by date ranges (for time-series data)
    2. Season-based: Fetch one season at a time (for historical data)
    3. Game-based: Process one game at a time (for detailed play-by-play)
    """

    def __init__(self):
        """Initialize the paginator."""
        self._introspector = get_introspector()

    async def fetch_chunked(
        self,
        endpoint: str,
        params: Dict[str, Any],
        chunk_strategy: Optional[str] = None,
        max_chunk_size: int = 5000,
        check_size_limit: bool = True,
    ) -> AsyncIterator[Tuple[pa.Table, ChunkInfo]]:
        """
        Fetch dataset in chunks, yielding tables incrementally.

        Chunking automatically bypasses size limits since data is fetched
        incrementally. Size check will show informational message if dataset
        is large, but won't block the fetch.

        Args:
            endpoint: Endpoint name from catalog
            params: Base parameters for the endpoint
            chunk_strategy: Strategy to use ("date", "season", "game", "none", or None for auto)
            max_chunk_size: Maximum rows per chunk (used for auto-chunking decisions)
            check_size_limit: Show size info message if large dataset (default: True)

        Yields:
            Tuple of (Arrow table, ChunkInfo) for each chunk

        Example:
            async for table, info in paginator.fetch_chunked("shot_chart", {...}, "date"):
                print(f"Chunk {info.chunk_number}/{info.total_chunks}: {info.row_count} rows")
                # Process table...
        """
        logger.info(f"Starting chunked fetch for {endpoint} with strategy={chunk_strategy}")

        # Check size limits (informational only - chunking bypasses limits)
        if check_size_limit:
            size_check = await self._introspector.check_size_limit(endpoint, params)
            if not size_check.allowed:
                logger.info(
                    f"Large dataset detected ({size_check.estimated_mb:.2f} MB > "
                    f"{size_check.limit_mb:.0f} MB limit) - using chunked fetch for efficiency"
                )

        # Inspect endpoint to determine capabilities
        caps = await self._introspector.inspect_endpoint(endpoint, params)

        # Auto-select chunking strategy if not provided
        if chunk_strategy is None:
            chunk_strategy = caps.chunk_strategy
            logger.info(f"Auto-selected chunking strategy: {chunk_strategy}")

        # Validate chunking strategy
        if chunk_strategy not in ["date", "season", "game", "none"]:
            raise ValueError(
                f"Invalid chunk_strategy: {chunk_strategy}. "
                f"Must be 'date', 'season', 'game', 'none', or None (auto)"
            )

        # Execute chunking based on strategy
        if chunk_strategy == "date":
            async for chunk in self._fetch_by_date(endpoint, params, caps):
                yield chunk
        elif chunk_strategy == "season":
            async for chunk in self._fetch_by_season(endpoint, params, caps):
                yield chunk
        elif chunk_strategy == "game":
            async for chunk in self._fetch_by_game(endpoint, params, caps):
                yield chunk
        else:  # "none"
            # Fetch all at once (no chunking)
            table, provenance = await fetch_endpoint(endpoint, params)
            chunk_info = ChunkInfo(
                chunk_number=1,
                total_chunks=1,
                params=params,
                row_count=table.num_rows,
            )
            yield table, chunk_info

    async def fetch_with_progress(
        self,
        endpoint: str,
        params: Dict[str, Any],
        chunk_strategy: Optional[str] = None,
        progress_callback: Optional[Callable[[ChunkInfo], None]] = None,
        check_size_limit: bool = True,
        force: bool = False,
    ) -> pa.Table:
        """
        Fetch dataset with progress tracking, returning complete table.

        Args:
            endpoint: Endpoint name from catalog
            params: Base parameters for the endpoint
            chunk_strategy: Strategy to use (or None for auto)
            progress_callback: Optional callback called for each chunk
            check_size_limit: Check size limits before fetching (default: True)
            force: Force fetch even if size exceeds limit (default: False)

        Returns:
            Complete Arrow table with all chunks concatenated

        Raises:
            ValueError: If dataset exceeds size limit and force=False

        Example:
            def on_progress(info: ChunkInfo):
                print(f"Progress: {info.chunk_number}/{info.total_chunks}")

            table = await paginator.fetch_with_progress(
                "shot_chart",
                {"entity_name": "Stephen Curry"},
                progress_callback=on_progress
            )
        """
        logger.info(f"Fetching {endpoint} with progress tracking")

        # Check size limits if requested
        if check_size_limit and not force:
            size_check = await self._introspector.check_size_limit(endpoint, params)
            if not size_check.allowed:
                error_msg = (
                    f"Dataset size {size_check.estimated_mb:.2f} MB exceeds limit "
                    f"({size_check.limit_mb:.0f} MB). Use force=True to override or "
                    f"fetch_chunked() for better performance."
                )
                logger.warning(error_msg)
                raise ValueError(error_msg)

        chunks: List[pa.Table] = []
        total_rows = 0

        async for table, chunk_info in self.fetch_chunked(
            endpoint, params, chunk_strategy, check_size_limit=False  # Already checked above
        ):
            chunks.append(table)
            total_rows += chunk_info.row_count

            # Call progress callback if provided
            if progress_callback:
                try:
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback(chunk_info)
                    else:
                        progress_callback(chunk_info)
                except Exception as e:
                    logger.error(f"Progress callback error: {e}")

            logger.debug(
                f"Chunk {chunk_info.chunk_number}/{chunk_info.total_chunks}: "
                f"{chunk_info.row_count} rows (total: {total_rows})"
            )

        # Concatenate all chunks
        if len(chunks) == 0:
            raise FetchError(f"No data returned from {endpoint}")

        if len(chunks) == 1:
            result = chunks[0]
        else:
            result = pa.concat_tables(chunks)

        logger.info(f"Completed fetch: {result.num_rows} rows, {result.num_columns} columns")
        return result

    async def _fetch_by_date(
        self,
        endpoint: str,
        params: Dict[str, Any],
        caps: EndpointCapabilities,
    ) -> AsyncIterator[Tuple[pa.Table, ChunkInfo]]:
        """
        Chunk by date ranges (monthly or custom intervals).

        Args:
            endpoint: Endpoint name
            params: Base parameters
            caps: Endpoint capabilities

        Yields:
            Tuple of (table, chunk_info) for each date range
        """
        if not caps.supports_date_range:
            raise ValueError(f"Endpoint {endpoint} does not support date ranges")

        # Extract date range from params or use defaults
        date_from = params.get("date_from")
        date_to = params.get("date_to")

        if date_from:
            if isinstance(date_from, str):
                date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        else:
            date_from = caps.min_date

        if date_to:
            if isinstance(date_to, str):
                date_to = datetime.strptime(date_to, "%Y-%m-%d").date()
        else:
            date_to = caps.max_date

        if not date_from or not date_to:
            raise ValueError("Could not determine date range for chunking")

        # Generate monthly chunks
        chunks = self._generate_date_chunks(date_from, date_to)
        total_chunks = len(chunks)

        logger.info(f"Date-based chunking: {total_chunks} chunks from {date_from} to {date_to}")

        for chunk_num, (chunk_start, chunk_end) in enumerate(chunks, start=1):
            # Update params with date range
            chunk_params = params.copy()
            chunk_params["date_from"] = chunk_start.strftime("%Y-%m-%d")
            chunk_params["date_to"] = chunk_end.strftime("%Y-%m-%d")

            logger.debug(f"Fetching chunk {chunk_num}/{total_chunks}: {chunk_start} to {chunk_end}")

            try:
                table, provenance = await fetch_endpoint(endpoint, chunk_params)

                chunk_info = ChunkInfo(
                    chunk_number=chunk_num,
                    total_chunks=total_chunks,
                    params=chunk_params,
                    row_count=table.num_rows,
                    date_range=(chunk_start, chunk_end),
                )

                yield table, chunk_info

            except FetchError as e:
                logger.warning(f"Chunk {chunk_num} failed: {e}")
                # Continue with next chunk
                continue

    async def _fetch_by_season(
        self,
        endpoint: str,
        params: Dict[str, Any],
        caps: EndpointCapabilities,
    ) -> AsyncIterator[Tuple[pa.Table, ChunkInfo]]:
        """
        Chunk by NBA seasons.

        Args:
            endpoint: Endpoint name
            params: Base parameters
            caps: Endpoint capabilities

        Yields:
            Tuple of (table, chunk_info) for each season
        """
        if not caps.supports_season_filter:
            raise ValueError(f"Endpoint {endpoint} does not support season filtering")

        # Get seasons to fetch
        seasons = params.get("seasons")
        if seasons:
            # User provided specific seasons
            if isinstance(seasons, str):
                seasons = [seasons]
        else:
            # Use all available seasons
            seasons = caps.available_seasons

        if not seasons:
            raise ValueError("No seasons available for chunking")

        total_chunks = len(seasons)
        logger.info(f"Season-based chunking: {total_chunks} seasons")

        for chunk_num, season in enumerate(seasons, start=1):
            # Update params with season
            chunk_params = params.copy()
            chunk_params["season"] = season

            logger.debug(f"Fetching chunk {chunk_num}/{total_chunks}: season {season}")

            try:
                table, provenance = await fetch_endpoint(endpoint, chunk_params)

                chunk_info = ChunkInfo(
                    chunk_number=chunk_num,
                    total_chunks=total_chunks,
                    params=chunk_params,
                    row_count=table.num_rows,
                    season=season,
                )

                yield table, chunk_info

            except FetchError as e:
                logger.warning(f"Season {season} failed: {e}")
                # Continue with next season
                continue

    async def _fetch_by_game(
        self,
        endpoint: str,
        params: Dict[str, Any],
        caps: EndpointCapabilities,
    ) -> AsyncIterator[Tuple[pa.Table, ChunkInfo]]:
        """
        Chunk by individual games.

        Args:
            endpoint: Endpoint name
            params: Base parameters
            caps: Endpoint capabilities

        Yields:
            Tuple of (table, chunk_info) for each game

        Note:
            This requires first fetching a game list, then fetching each game's details.
        """
        # Game-based chunking requires game IDs
        game_ids = params.get("game_ids")

        if not game_ids:
            raise ValueError(
                "Game-based chunking requires 'game_ids' parameter. "
                "First fetch game logs to get game IDs, then use this strategy."
            )

        if isinstance(game_ids, str):
            game_ids = [game_ids]

        total_chunks = len(game_ids)
        logger.info(f"Game-based chunking: {total_chunks} games")

        for chunk_num, game_id in enumerate(game_ids, start=1):
            # Update params with game ID
            chunk_params = params.copy()
            chunk_params["game_id"] = game_id

            logger.debug(f"Fetching chunk {chunk_num}/{total_chunks}: game {game_id}")

            try:
                table, provenance = await fetch_endpoint(endpoint, chunk_params)

                chunk_info = ChunkInfo(
                    chunk_number=chunk_num,
                    total_chunks=total_chunks,
                    params=chunk_params,
                    row_count=table.num_rows,
                    game_id=game_id,
                )

                yield table, chunk_info

            except FetchError as e:
                logger.warning(f"Game {game_id} failed: {e}")
                # Continue with next game
                continue

    def _generate_date_chunks(
        self, start_date: date, end_date: date, chunk_size_days: int = 30
    ) -> List[Tuple[date, date]]:
        """
        Generate date range chunks.

        Args:
            start_date: Start date
            end_date: End date
            chunk_size_days: Days per chunk (default: 30 for monthly)

        Returns:
            List of (chunk_start, chunk_end) tuples
        """
        chunks = []
        current_start = start_date

        while current_start < end_date:
            current_end = min(
                current_start + timedelta(days=chunk_size_days - 1), end_date
            )
            chunks.append((current_start, current_end))
            current_start = current_end + timedelta(days=1)

        return chunks

    async def estimate_fetch_time(
        self, endpoint: str, params: Dict[str, Any], chunk_strategy: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Estimate time and resources needed for a fetch operation.

        Args:
            endpoint: Endpoint name
            params: Parameters
            chunk_strategy: Chunking strategy (or None for auto)

        Returns:
            Dictionary with estimates:
            {
                "estimated_rows": int,
                "estimated_chunks": int,
                "estimated_time_seconds": float,
                "recommended_strategy": str,
                "memory_estimate_mb": float
            }
        """
        caps = await self._introspector.inspect_endpoint(endpoint, params)

        if chunk_strategy is None:
            chunk_strategy = caps.chunk_strategy

        # Estimate chunks
        if chunk_strategy == "date" and caps.min_date and caps.max_date:
            date_from = params.get("date_from", caps.min_date)
            date_to = params.get("date_to", caps.max_date)
            if isinstance(date_from, str):
                date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
            if isinstance(date_to, str):
                date_to = datetime.strptime(date_to, "%Y-%m-%d").date()
            chunks = self._generate_date_chunks(date_from, date_to)
            estimated_chunks = len(chunks)
        elif chunk_strategy == "season":
            seasons = params.get("seasons", caps.available_seasons)
            if isinstance(seasons, str):
                seasons = [seasons]
            estimated_chunks = len(seasons)
        elif chunk_strategy == "game":
            game_ids = params.get("game_ids", [])
            if isinstance(game_ids, str):
                game_ids = [game_ids]
            estimated_chunks = len(game_ids)
        else:
            estimated_chunks = 1

        estimated_rows = caps.estimated_row_count or 1000

        # Rough time estimates (based on NBA API latency)
        time_per_chunk = 2.0  # seconds per API call
        estimated_time = estimated_chunks * time_per_chunk

        # Memory estimate (rough: 1KB per row in Arrow format)
        memory_mb = (estimated_rows * 1024) / (1024 * 1024)

        return {
            "estimated_rows": estimated_rows,
            "estimated_chunks": estimated_chunks,
            "estimated_time_seconds": estimated_time,
            "recommended_strategy": chunk_strategy,
            "memory_estimate_mb": round(memory_mb, 2),
        }


# Global paginator instance
_paginator = None


def get_paginator() -> DatasetPaginator:
    """
    Get the global dataset paginator instance (singleton pattern).

    Returns:
        DatasetPaginator instance
    """
    global _paginator
    if _paginator is None:
        _paginator = DatasetPaginator()
    return _paginator
