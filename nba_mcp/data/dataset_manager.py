"""
Dataset lifecycle management for NBA MCP.

Handles dataset creation, storage, retrieval, and cleanup.
Datasets are stored in-memory with TTL and can be exported to various formats.
"""

import uuid
import time
import asyncio
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional, Literal
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.feather as feather
import pyarrow.csv as csv_arrow
from pydantic import BaseModel, Field
import json
import pandas as pd
import duckdb


def get_default_save_path(
    endpoint: str = "dataset",
    format: str = "parquet",
    base_dir: str = "mcp_data"
) -> Path:
    """
    Generate a default organized path in the mcp_data/ folder.

    Creates structure: mcp_data/YYYY-MM-DD/endpoint_HHMMSS.format

    Args:
        endpoint: Endpoint name or dataset identifier
        format: File format extension (parquet, csv, feather, json)
        base_dir: Base directory name (default: "mcp_data")

    Returns:
        Path object with organized structure

    Example:
        >>> get_default_save_path("player_stats", "parquet")
        Path("mcp_data/2025-10-29/player_stats_143052.parquet")
    """
    base = Path(base_dir)
    date_folder = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%H%M%S")

    # Clean endpoint name (remove invalid path characters)
    safe_endpoint = "".join(c for c in endpoint if c.isalnum() or c in "_-")

    filename = f"{safe_endpoint}_{timestamp}.{format}"
    return base / date_folder / filename


def generate_descriptive_filename(data: Dict[str, Any]) -> str:
    """
    Generate descriptive filename from NBA data content.

    Analyzes the data structure to create meaningful filenames that
    include entity names, dates, and data types.

    Args:
        data: NBA data dictionary (shot charts, game context, stats, etc.)

    Returns:
        Descriptive filename string (without extension or timestamp)

    Examples:
        Shot chart (team): "warriors_shot_chart_2025-10-28"
        Shot chart (player): "stephen_curry_shot_chart_2023-24"
        Game context: "lakers_vs_warriors_context"
        Player stats: "lebron_james_advanced_stats_2023-24"
    """
    parts = []

    # Check if this is a ResponseEnvelope with nested data
    actual_data = data.get("data", data)

    # Detect data type and extract relevant information

    # 1. Shot Chart Data
    if "entity" in actual_data and "zone_summary" in actual_data:
        entity = actual_data["entity"]
        entity_name = entity.get("name", "unknown")
        entity_type = entity.get("type", "")

        # Sanitize entity name
        clean_name = entity_name.lower().replace(" ", "_")
        clean_name = "".join(c for c in clean_name if c.isalnum() or c == "_")
        parts.append(clean_name)
        parts.append("shot_chart")

        # Add date context
        if "date_from" in actual_data:
            parts.append(actual_data["date_from"])
        elif "season" in actual_data:
            parts.append(actual_data["season"].replace("-", "_"))

    # 2. Game Context Data
    elif "matchup" in actual_data and "narrative" in actual_data:
        matchup = actual_data["matchup"]
        team1 = matchup.get("team1_name", "team1")
        team2 = matchup.get("team2_name", "team2")

        # Sanitize team names
        clean_team1 = team1.lower().replace(" ", "_")
        clean_team1 = "".join(c for c in clean_team1 if c.isalnum() or c == "_")
        clean_team2 = team2.lower().replace(" ", "_")
        clean_team2 = "".join(c for c in clean_team2 if c.isalnum() or c == "_")

        parts.append(clean_team1)
        parts.append("vs")
        parts.append(clean_team2)
        parts.append("context")

    # 3. Player Advanced Stats
    elif "player_name" in actual_data or "player" in actual_data:
        player_name = actual_data.get("player_name") or actual_data.get("player", {}).get("name", "unknown")
        clean_name = player_name.lower().replace(" ", "_")
        clean_name = "".join(c for c in clean_name if c.isalnum() or c == "_")
        parts.append(clean_name)

        # Detect stats type
        if "ts_pct" in actual_data or "usage_pct" in actual_data:
            parts.append("advanced_stats")
        else:
            parts.append("stats")

        # Add season if available
        if "season" in actual_data:
            parts.append(actual_data["season"].replace("-", "_"))

    # 4. Team Stats
    elif "team_name" in actual_data or "team" in actual_data:
        team_name = actual_data.get("team_name") or actual_data.get("team", {}).get("name", "unknown")
        clean_name = team_name.lower().replace(" ", "_")
        clean_name = "".join(c for c in clean_name if c.isalnum() or c == "_")
        parts.append(clean_name)

        # Detect stats type
        if "off_rating" in actual_data or "def_rating" in actual_data:
            parts.append("advanced_stats")
        else:
            parts.append("stats")

        # Add season if available
        if "season" in actual_data:
            parts.append(actual_data["season"].replace("-", "_"))

    # 5. Standings Data
    elif "standings" in actual_data or isinstance(actual_data, list):
        parts.append("standings")
        if isinstance(data, dict) and "season" in data:
            parts.append(data["season"].replace("-", "_"))

    # 6. Default fallback
    if not parts:
        parts.append("nba_data")

    return "_".join(parts)


# ============================================================================
# Parquet Migration - New Helper Functions
# ============================================================================


def is_tabular_data(data: Any) -> bool:
    """
    Check if data has tabular structure (can be converted to DataFrame).

    Checks for:
    - ResponseEnvelope with 'data' key containing list of dicts
    - Direct list of dicts
    - Dict with 'events' key (lineup data)
    - Dict with 'raw_shots' key (shot chart data)
    - Aggregated stats (single dict with many columns)

    Args:
        data: Any data structure to check

    Returns:
        True if data can be converted to DataFrame, False otherwise

    Examples:
        >>> # Game log data (list of dicts)
        >>> data = {"data": [{"GAME_ID": "123", "PTS": 25}, ...]}
        >>> is_tabular_data(data)
        True

        >>> # Markdown play-by-play
        >>> data = {"format": "markdown", "data": "Q1 12:00..."}
        >>> is_tabular_data(data)
        False

        >>> # Lineup events
        >>> data = {"events": [{"gameid": "123", ...}, ...]}
        >>> is_tabular_data(data)
        True
    """
    # Check for markdown format (NOT tabular)
    if isinstance(data, dict) and data.get('format') == 'markdown':
        return False

    # Check for ResponseEnvelope format
    if isinstance(data, dict):
        # Has 'data' key with list?
        if 'data' in data:
            inner_data = data['data']
            if isinstance(inner_data, list) and len(inner_data) > 0:
                # Check if list items are dicts
                return isinstance(inner_data[0], dict)
            # Check if inner_data has tabular sub-keys (raw_shots, events)
            if isinstance(inner_data, dict):
                # Shot chart data has 'raw_shots'
                if 'raw_shots' in inner_data:
                    shots = inner_data['raw_shots']
                    if isinstance(shots, list) and len(shots) > 0:
                        return isinstance(shots[0], dict)
                # Lineup data has 'events'
                if 'events' in inner_data:
                    events = inner_data['events']
                    if isinstance(events, list) and len(events) > 0:
                        return isinstance(events[0], dict)
                # Single dict with multiple keys (aggregated stats)
                if len(inner_data) > 5:
                    return True

        # Has 'events' key (lineup data)?
        if 'events' in data:
            events = data['events']
            if isinstance(events, list) and len(events) > 0:
                return isinstance(events[0], dict)

        # Has 'raw_shots' key (shot chart data)?
        if 'raw_shots' in data:
            shots = data['raw_shots']
            if isinstance(shots, list) and len(shots) > 0:
                return isinstance(shots[0], dict)

    # Direct list of dicts?
    if isinstance(data, list) and len(data) > 0:
        return isinstance(data[0], dict)

    return False


def extract_dataframe(data: Any) -> pd.DataFrame:
    """
    Extract DataFrame from various data structures.

    Handles:
    - ResponseEnvelope with 'data' key
    - Lineup data with 'events' key
    - Shot chart data with 'raw_shots' key
    - Direct list of dicts
    - Aggregated stats (single dict)

    Args:
        data: Data structure to convert

    Returns:
        pandas DataFrame

    Raises:
        ValueError: If data cannot be converted to DataFrame

    Examples:
        >>> # Extract from ResponseEnvelope
        >>> data = {"data": [{"PTS": 25}, {"PTS": 30}]}
        >>> df = extract_dataframe(data)
        >>> df.shape
        (2, 1)

        >>> # Extract from lineup events
        >>> data = {"events": [{"gameid": "123"}, {"gameid": "124"}]}
        >>> df = extract_dataframe(data)
        >>> df.shape
        (2, 1)
    """
    # ResponseEnvelope with 'data' key
    if isinstance(data, dict) and 'data' in data:
        inner_data = data['data']

        # List of dicts (game logs, etc.)
        if isinstance(inner_data, list):
            return pd.DataFrame(inner_data)

        # Single dict - check for nested tabular data
        if isinstance(inner_data, dict):
            # Shot chart data nested in ResponseEnvelope
            if 'raw_shots' in inner_data:
                return pd.DataFrame(inner_data['raw_shots'])
            # Lineup data nested in ResponseEnvelope
            if 'events' in inner_data:
                return pd.DataFrame(inner_data['events'])
            # Aggregated season stats (convert to single-row DataFrame)
            return pd.DataFrame([inner_data])

    # Lineup data with 'events' key
    if isinstance(data, dict) and 'events' in data:
        return pd.DataFrame(data['events'])

    # Shot chart data with 'raw_shots' key
    if isinstance(data, dict) and 'raw_shots' in data:
        return pd.DataFrame(data['raw_shots'])

    # Direct list of dicts
    if isinstance(data, list):
        return pd.DataFrame(data)

    # Fallback: try to convert as-is
    try:
        return pd.DataFrame(data)
    except Exception as e:
        raise ValueError(f"Cannot convert data to DataFrame: {e}")


def save_parquet(
    df: pd.DataFrame,
    filename_base: str,
    base_dir: str = "mcp_data"
) -> Path:
    """
    Save DataFrame as Parquet file using DuckDB with snappy compression.

    Uses:
    - Snappy compression for optimal size/speed tradeoff
    - Date-based folder structure (mcp_data/YYYY-MM-DD/)
    - Timestamp in filename for uniqueness
    - DuckDB for efficient conversion

    Args:
        df: pandas DataFrame to save
        filename_base: Base filename (without extension or timestamp)
        base_dir: Base directory name (default: "mcp_data")

    Returns:
        Path object where file was saved

    Examples:
        >>> df = pd.DataFrame({"PTS": [25, 30], "REB": [10, 12]})
        >>> path = save_parquet(df, "player_game")
        >>> print(path)
        mcp_data/2025-10-30/player_game_143052.parquet
    """
    # Create folder structure
    today = date.today().strftime("%Y-%m-%d")
    folder = Path(base_dir) / today
    folder.mkdir(parents=True, exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"{filename_base}_{timestamp}.parquet"
    file_path = folder / filename

    # Save using DuckDB for better compression
    # DuckDB automatically handles PyArrow tables efficiently
    duckdb.sql(f"""
        COPY (SELECT * FROM df)
        TO '{file_path}'
        (FORMAT PARQUET, COMPRESSION SNAPPY)
    """)

    return file_path


def save_text(
    text: str,
    filename_base: str,
    base_dir: str = "mcp_data"
) -> Path:
    """
    Save text data to .txt file.

    Used for markdown play-by-play data and other text formats.

    Args:
        text: Text content to save
        filename_base: Base filename (without extension or timestamp)
        base_dir: Base directory name (default: "mcp_data")

    Returns:
        Path object where file was saved

    Examples:
        >>> text = "Q1 12:00 | Start of game\\nQ1 11:45 | Jump ball"
        >>> path = save_text(text, "play_by_play")
        >>> print(path)
        mcp_data/2025-10-30/play_by_play_143052.txt
    """
    # Create folder structure
    today = date.today().strftime("%Y-%m-%d")
    folder = Path(base_dir) / today
    folder.mkdir(parents=True, exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"{filename_base}_{timestamp}.txt"
    file_path = folder / filename

    # Save text with UTF-8 encoding
    file_path.write_text(text, encoding='utf-8')

    return file_path


# ============================================================================
# End of Parquet Migration Helper Functions
# ============================================================================


def save_json_data(
    data: Dict[str, Any],
    endpoint: str = "data",
    base_dir: str = "mcp_data",
    custom_filename: Optional[str] = None
) -> Path:
    """
    Save JSON data to organized mcp_data/ folder structure with smart naming.

    Creates structure: mcp_data/YYYY-MM-DD/descriptive_name_HHMMSS.json

    Args:
        data: JSON-serializable data (dict, list, etc.)
        endpoint: Fallback endpoint name if descriptive generation fails
        base_dir: Base directory name (default: "mcp_data")
        custom_filename: Optional custom filename (without extension)

    Returns:
        Path object where data was saved

    Examples:
        >>> # Auto-generate descriptive name from data
        >>> data = {"entity": {"name": "Warriors"}, "zone_summary": {...}}
        >>> path = save_json_data(data)
        >>> print(path)
        mcp_data/2025-10-29/warriors_shot_chart_2025-10-28_143052.json

        >>> # Use custom filename
        >>> path = save_json_data(data, custom_filename="my_analysis")
        >>> print(path)
        mcp_data/2025-10-29/my_analysis_143052.json
    """
    # Determine filename base
    if custom_filename:
        # Use custom filename (sanitize it)
        filename_base = "".join(c for c in custom_filename if c.isalnum() or c in "_-")
    else:
        # Try to generate descriptive filename from data content
        try:
            filename_base = generate_descriptive_filename(data)
        except Exception:
            # Fallback to endpoint if generation fails
            filename_base = endpoint

    # Create full path with timestamp
    base = Path(base_dir)
    date_folder = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"{filename_base}_{timestamp}.json"
    file_path = base / date_folder / filename

    # Create directories if they don't exist
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Save to JSON with pretty formatting
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return file_path


class ProvenanceInfo(BaseModel):
    """Tracks the lineage and history of a dataset."""

    source_endpoints: List[str] = Field(default_factory=list)
    operations: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    nba_api_calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    execution_time_ms: float = 0.0
    parameters: Dict[str, Any] = Field(default_factory=dict)


class DatasetHandle(BaseModel):
    """
    Handle for a stored dataset.

    Provides a unique identifier and metadata for accessing datasets.
    """

    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    expires_at: str = Field(
        default_factory=lambda: (
            datetime.utcnow() + timedelta(hours=1)
        ).isoformat()
    )
    row_count: int = 0
    column_count: int = 0
    column_names: List[str] = Field(default_factory=list)
    size_bytes: int = 0
    provenance: ProvenanceInfo = Field(default_factory=ProvenanceInfo)

    def is_expired(self) -> bool:
        """Check if the dataset handle has expired."""
        expiry = datetime.fromisoformat(self.expires_at)
        return datetime.utcnow() > expiry

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "uuid": self.uuid,
            "name": self.name,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "column_names": self.column_names,
            "size_bytes": self.size_bytes,
            "size_mb": round(self.size_bytes / 1024 / 1024, 2),
            "provenance": self.provenance.model_dump(),
            "is_expired": self.is_expired(),
        }


class DatasetManager:
    """
    Manages the lifecycle of datasets.

    Features:
    - In-memory storage with TTL
    - Automatic cleanup of expired datasets
    - Format conversion (Arrow → Parquet/CSV/Feather/JSON)
    - Size tracking and memory management
    """

    def __init__(self, max_size_mb: int = 500, cleanup_interval_seconds: int = 300):
        """
        Initialize the dataset manager.

        Args:
            max_size_mb: Maximum total size of datasets in memory (MB)
            cleanup_interval_seconds: How often to run cleanup (seconds)
        """
        self._datasets: Dict[str, pa.Table] = {}
        self._handles: Dict[str, DatasetHandle] = {}
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._cleanup_interval = cleanup_interval_seconds
        self._total_size_bytes = 0
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start(self):
        """Start the background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        """Stop the background cleanup task."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _cleanup_loop(self):
        """Periodically cleanup expired datasets."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self.cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in cleanup loop: {e}")

    async def store(
        self,
        table: pa.Table,
        name: Optional[str] = None,
        provenance: Optional[ProvenanceInfo] = None,
    ) -> DatasetHandle:
        """
        Store a dataset in memory and return a handle.

        Args:
            table: PyArrow Table to store
            name: Optional human-readable name
            provenance: Optional provenance information

        Returns:
            DatasetHandle for accessing the dataset

        Raises:
            MemoryError: If dataset exceeds size limits
        """
        async with self._lock:
            # Calculate size
            size_bytes = table.nbytes

            # Check if we need to make space
            if self._total_size_bytes + size_bytes > self._max_size_bytes:
                # Try cleanup first
                await self._cleanup_expired_sync()

                # Check again
                if self._total_size_bytes + size_bytes > self._max_size_bytes:
                    raise MemoryError(
                        f"Dataset size ({size_bytes / 1024 / 1024:.2f} MB) would exceed "
                        f"maximum allowed ({self._max_size_bytes / 1024 / 1024:.2f} MB). "
                        f"Current usage: {self._total_size_bytes / 1024 / 1024:.2f} MB"
                    )

            # Create handle
            handle = DatasetHandle(
                name=name,
                row_count=table.num_rows,
                column_count=table.num_columns,
                column_names=table.column_names,
                size_bytes=size_bytes,
                provenance=provenance or ProvenanceInfo(),
            )

            # Store
            self._datasets[handle.uuid] = table
            self._handles[handle.uuid] = handle
            self._total_size_bytes += size_bytes

            return handle

    async def retrieve(self, handle_or_uuid: str | DatasetHandle) -> pa.Table:
        """
        Retrieve a dataset by handle or UUID.

        Args:
            handle_or_uuid: DatasetHandle object or UUID string

        Returns:
            PyArrow Table

        Raises:
            KeyError: If dataset not found
            ValueError: If dataset has expired
        """
        uuid_str = (
            handle_or_uuid.uuid
            if isinstance(handle_or_uuid, DatasetHandle)
            else handle_or_uuid
        )

        if uuid_str not in self._datasets:
            raise KeyError(f"Dataset {uuid_str} not found")

        handle = self._handles[uuid_str]
        if handle.is_expired():
            # Auto-cleanup expired dataset
            await self.delete(uuid_str)
            raise ValueError(f"Dataset {uuid_str} has expired")

        return self._datasets[uuid_str]

    async def delete(self, handle_or_uuid: str | DatasetHandle):
        """
        Delete a dataset from memory.

        Args:
            handle_or_uuid: DatasetHandle object or UUID string
        """
        uuid_str = (
            handle_or_uuid.uuid
            if isinstance(handle_or_uuid, DatasetHandle)
            else handle_or_uuid
        )

        async with self._lock:
            if uuid_str in self._datasets:
                size = self._handles[uuid_str].size_bytes
                del self._datasets[uuid_str]
                del self._handles[uuid_str]
                self._total_size_bytes -= size

    async def get_handle(self, uuid_str: str) -> DatasetHandle:
        """
        Get the handle for a dataset without retrieving the data.

        Args:
            uuid_str: Dataset UUID

        Returns:
            DatasetHandle

        Raises:
            KeyError: If dataset not found
        """
        if uuid_str not in self._handles:
            raise KeyError(f"Dataset {uuid_str} not found")
        return self._handles[uuid_str]

    async def list_handles(
        self, include_expired: bool = False
    ) -> List[DatasetHandle]:
        """
        List all dataset handles.

        Args:
            include_expired: Whether to include expired handles

        Returns:
            List of DatasetHandles
        """
        handles = list(self._handles.values())
        if not include_expired:
            handles = [h for h in handles if not h.is_expired()]
        return handles

    async def cleanup_expired(self) -> int:
        """
        Remove all expired datasets.

        Returns:
            Number of datasets removed
        """
        return await self._cleanup_expired_sync()

    async def _cleanup_expired_sync(self) -> int:
        """Internal synchronous cleanup (assumes lock is held or not needed)."""
        expired_uuids = [
            uuid_str
            for uuid_str, handle in self._handles.items()
            if handle.is_expired()
        ]

        for uuid_str in expired_uuids:
            size = self._handles[uuid_str].size_bytes
            del self._datasets[uuid_str]
            del self._handles[uuid_str]
            self._total_size_bytes -= size

        return len(expired_uuids)

    async def save_to_file(
        self,
        handle_or_uuid: str | DatasetHandle,
        path: str | Path,
        format: Literal["parquet", "csv", "feather", "json"] = "parquet",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Save a dataset to disk in the specified format.

        Args:
            handle_or_uuid: Dataset handle or UUID
            path: Output file path
            format: Output format (parquet, csv, feather, json)
            **kwargs: Additional format-specific options

        Returns:
            Dictionary with save information

        Raises:
            KeyError: If dataset not found
            ValueError: If format not supported or dataset expired
        """
        # Retrieve the dataset
        table = await self.retrieve(handle_or_uuid)

        # Get handle for metadata
        uuid_str = (
            handle_or_uuid.uuid
            if isinstance(handle_or_uuid, DatasetHandle)
            else handle_or_uuid
        )
        handle = self._handles[uuid_str]

        # Convert path
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Save based on format
        start_time = time.time()

        if format == "parquet":
            compression = kwargs.get("compression", "snappy")
            pq.write_table(table, output_path, compression=compression)

        elif format == "csv":
            csv_arrow.write_csv(table, output_path)

        elif format == "feather":
            compression = kwargs.get("compression", "lz4")
            feather.write_feather(table, output_path, compression=compression)

        elif format == "json":
            # Convert to pandas then JSON for better formatting
            df = table.to_pandas()
            orient = kwargs.get("orient", "records")
            df.to_json(output_path, orient=orient, indent=2)

        else:
            raise ValueError(
                f"Unsupported format: {format}. "
                f"Supported formats: parquet, csv, feather, json"
            )

        execution_time_ms = (time.time() - start_time) * 1000
        file_size_bytes = output_path.stat().st_size

        return {
            "success": True,
            "path": str(output_path.absolute()),
            "format": format,
            "rows": table.num_rows,
            "columns": table.num_columns,
            "file_size_bytes": file_size_bytes,
            "file_size_mb": round(file_size_bytes / 1024 / 1024, 2),
            "execution_time_ms": round(execution_time_ms, 2),
            "dataset_uuid": uuid_str,
            "dataset_name": handle.name,
        }

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get manager statistics.

        Returns:
            Dictionary with statistics
        """
        total_datasets = len(self._datasets)
        expired_count = sum(1 for h in self._handles.values() if h.is_expired())

        return {
            "total_datasets": total_datasets,
            "expired_datasets": expired_count,
            "active_datasets": total_datasets - expired_count,
            "total_size_bytes": self._total_size_bytes,
            "total_size_mb": round(self._total_size_bytes / 1024 / 1024, 2),
            "max_size_mb": round(self._max_size_bytes / 1024 / 1024, 2),
            "usage_percent": round(
                (self._total_size_bytes / self._max_size_bytes) * 100, 2
            ),
        }


# Global manager instance
_manager = None


def get_manager() -> DatasetManager:
    """
    Get the global dataset manager instance (singleton pattern).

    Returns:
        DatasetManager instance
    """
    global _manager
    if _manager is None:
        _manager = DatasetManager()
    return _manager


# Convenience alias
get_dataset_manager = get_manager


async def initialize_manager():
    """Initialize and start the global dataset manager."""
    manager = get_manager()
    await manager.start()


async def shutdown_manager():
    """Shutdown the global dataset manager."""
    manager = get_manager()
    await manager.stop()
