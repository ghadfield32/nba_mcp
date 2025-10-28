"""
Golden tests for NBA MCP.

This module provides snapshot testing for the top 20 NBA queries to ensure
schema stability and correctness across updates.
"""

from tests.golden.queries import (
    GoldenQuery,
    GOLDEN_QUERIES,
    get_query_by_id,
    get_queries_by_category,
    get_queries_by_intent,
    get_all_categories,
    get_all_intents,
    get_query_statistics,
)

__all__ = [
    "GoldenQuery",
    "GOLDEN_QUERIES",
    "get_query_by_id",
    "get_queries_by_category",
    "get_queries_by_intent",
    "get_all_categories",
    "get_all_intents",
    "get_query_statistics",
]
