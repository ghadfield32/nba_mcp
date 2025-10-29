"""
Data management package for NBA MCP.

This package provides dataset management, joins, and data catalog functionality.

Modules:
    - catalog: Endpoint metadata and data dictionary
    - dataset_manager: Dataset lifecycle management
    - fetch: Raw data retrieval from NBA API
    - joins: DuckDB-powered SQL joins
    - introspection: Endpoint capability discovery
    - pagination: Large dataset chunking and fetching
    - limits: Dataset size limit configuration
"""

from nba_mcp.data.catalog import DataCatalog, EndpointMetadata, JoinRelationship
from nba_mcp.data.dataset_manager import (
    DatasetManager,
    DatasetHandle,
    ProvenanceInfo,
    get_manager,
    get_dataset_manager,
)
from nba_mcp.data.fetch import fetch_endpoint
from nba_mcp.data.joins import join_tables, validate_join_columns
from nba_mcp.data.introspection import (
    EndpointIntrospector,
    EndpointCapabilities,
    get_introspector,
)
from nba_mcp.data.pagination import DatasetPaginator, ChunkInfo, get_paginator
from nba_mcp.data.limits import FetchLimits, SizeCheckResult, get_limits, reset_limits

__all__ = [
    # Catalog
    "DataCatalog",
    "EndpointMetadata",
    "JoinRelationship",
    # Dataset Management
    "DatasetManager",
    "DatasetHandle",
    "ProvenanceInfo",
    "get_manager",
    "get_dataset_manager",
    # Operations
    "fetch_endpoint",
    "join_tables",
    "validate_join_columns",
    # Introspection
    "EndpointIntrospector",
    "EndpointCapabilities",
    "get_introspector",
    # Pagination
    "DatasetPaginator",
    "ChunkInfo",
    "get_paginator",
    # Limits
    "FetchLimits",
    "SizeCheckResult",
    "get_limits",
    "reset_limits",
]
