"""
Plugin-based endpoint registry for NBA MCP data fetching.

This module replaces the if/elif routing chain with a decorator-based
registration system that makes it easy to add new endpoints and maintain
existing ones.

Features:
- Decorator-based registration
- Automatic handler discovery
- Metadata storage (required params, validators)
- Type-safe handler signatures
- Validation on startup
- Easy extensibility

Usage:
    from nba_mcp.data.endpoint_registry import register_endpoint, get_registry

    @register_endpoint(
        "player_career_stats",
        required_params=["player_name"],
        optional_params=["season"]
    )
    async def fetch_player_career_stats(params, provenance):
        # Implementation
        return dataframe

    # Later, get the handler
    handler = get_registry().get_handler("player_career_stats")
    data = await handler(params, provenance)
"""

import asyncio
import inspect
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field
import logging

import pandas as pd
import pyarrow as pa

from nba_mcp.data.dataset_manager import ProvenanceInfo

logger = logging.getLogger(__name__)


# Type alias for endpoint handlers
EndpointHandler = Callable[[Dict[str, Any], ProvenanceInfo], Any]


@dataclass
class EndpointRegistration:
    """
    Metadata for a registered endpoint handler.

    Attributes:
        name: Endpoint name (e.g., "player_career_stats")
        handler: Async function that fetches the data
        required_params: List of required parameter names
        optional_params: List of optional parameter names
        description: Human-readable description
        tags: Tags for categorization (e.g., ["player", "stats"])
        supports_batch: Whether endpoint supports batch operations
        cache_ttl_seconds: How long to cache results (0 = no cache)
    """
    name: str
    handler: EndpointHandler
    required_params: List[str] = field(default_factory=list)
    optional_params: List[str] = field(default_factory=list)
    description: str = ""
    tags: Set[str] = field(default_factory=set)
    supports_batch: bool = False
    cache_ttl_seconds: int = 0

    def __post_init__(self):
        """Validate the registration on creation."""
        if not asyncio.iscoroutinefunction(self.handler):
            raise ValueError(
                f"Handler for '{self.name}' must be an async function"
            )

        # Validate handler signature
        sig = inspect.signature(self.handler)
        params = list(sig.parameters.keys())

        if len(params) < 2:
            raise ValueError(
                f"Handler for '{self.name}' must accept at least 2 parameters: "
                f"(params: Dict[str, Any], provenance: ProvenanceInfo)"
            )

    def validate_params(self, params: Dict[str, Any]) -> List[str]:
        """
        Validate that all required parameters are present.

        Args:
            params: Parameter dictionary to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        for required in self.required_params:
            if required not in params:
                errors.append(
                    f"Required parameter '{required}' missing for endpoint '{self.name}'"
                )

        return errors


class EndpointRegistry:
    """
    Central registry for all NBA API endpoint handlers.

    This registry replaces the if/elif chain in fetch.py with a flexible,
    extensible plugin system. Endpoints are registered using decorators,
    making it easy to add new endpoints or modify existing ones.

    Features:
    - Automatic handler discovery via decorators
    - Metadata storage and validation
    - Thread-safe registration
    - Query by name, tag, or capabilities
    - Validation on startup

    Example:
        registry = get_registry()

        # Register an endpoint
        @register_endpoint("my_endpoint", required_params=["param1"])
        async def my_handler(params, provenance):
            return pd.DataFrame(...)

        # Get and call a handler
        handler = registry.get_handler("my_endpoint")
        data = await handler(params, provenance)
    """

    def __init__(self):
        """Initialize the endpoint registry."""
        self._endpoints: Dict[str, EndpointRegistration] = {}
        self._tags: Dict[str, Set[str]] = {}  # tag -> set of endpoint names

    def register(
        self,
        name: str,
        handler: EndpointHandler,
        required_params: Optional[List[str]] = None,
        optional_params: Optional[List[str]] = None,
        description: str = "",
        tags: Optional[Set[str]] = None,
        supports_batch: bool = False,
        cache_ttl_seconds: int = 0,
    ) -> EndpointRegistration:
        """
        Register an endpoint handler.

        Args:
            name: Unique endpoint name
            handler: Async function that fetches data
            required_params: List of required parameter names
            optional_params: List of optional parameter names
            description: Human-readable description
            tags: Tags for categorization
            supports_batch: Whether endpoint supports batch operations
            cache_ttl_seconds: Cache TTL (0 = no cache)

        Returns:
            EndpointRegistration object

        Raises:
            ValueError: If endpoint already registered or invalid
        """
        if name in self._endpoints:
            logger.warning(
                f"Endpoint '{name}' is already registered. Overwriting..."
            )

        registration = EndpointRegistration(
            name=name,
            handler=handler,
            required_params=required_params or [],
            optional_params=optional_params or [],
            description=description,
            tags=tags or set(),
            supports_batch=supports_batch,
            cache_ttl_seconds=cache_ttl_seconds,
        )

        # Store registration
        self._endpoints[name] = registration

        # Update tag index
        for tag in registration.tags:
            if tag not in self._tags:
                self._tags[tag] = set()
            self._tags[tag].add(name)

        logger.debug(f"Registered endpoint: {name}")

        return registration

    def get_handler(self, name: str) -> Optional[EndpointHandler]:
        """
        Get the handler function for an endpoint.

        Args:
            name: Endpoint name

        Returns:
            Handler function or None if not found
        """
        registration = self._endpoints.get(name)
        return registration.handler if registration else None

    def get_registration(self, name: str) -> Optional[EndpointRegistration]:
        """
        Get the full registration metadata for an endpoint.

        Args:
            name: Endpoint name

        Returns:
            EndpointRegistration or None if not found
        """
        return self._endpoints.get(name)

    def list_endpoints(
        self,
        tag: Optional[str] = None,
        supports_batch: Optional[bool] = None
    ) -> List[str]:
        """
        List all registered endpoint names, optionally filtered.

        Args:
            tag: Filter by tag
            supports_batch: Filter by batch support

        Returns:
            List of endpoint names
        """
        endpoints = list(self._endpoints.keys())

        # Filter by tag
        if tag is not None:
            endpoints = [
                name for name in endpoints
                if tag in self._endpoints[name].tags
            ]

        # Filter by batch support
        if supports_batch is not None:
            endpoints = [
                name for name in endpoints
                if self._endpoints[name].supports_batch == supports_batch
            ]

        return sorted(endpoints)

    def list_registrations(self) -> List[EndpointRegistration]:
        """
        Get all endpoint registrations.

        Returns:
            List of EndpointRegistration objects
        """
        return list(self._endpoints.values())

    def has_endpoint(self, name: str) -> bool:
        """Check if an endpoint is registered."""
        return name in self._endpoints

    def get_by_tag(self, tag: str) -> List[str]:
        """
        Get all endpoint names with a specific tag.

        Args:
            tag: Tag to search for

        Returns:
            List of endpoint names
        """
        return sorted(self._tags.get(tag, set()))

    def validate_all(self) -> Dict[str, List[str]]:
        """
        Validate all registered endpoints.

        Returns:
            Dictionary mapping endpoint names to validation errors
        """
        errors = {}

        for name, registration in self._endpoints.items():
            # Check if handler is callable
            if not callable(registration.handler):
                errors[name] = ["Handler is not callable"]
                continue

            # Check if handler is async
            if not asyncio.iscoroutinefunction(registration.handler):
                errors[name] = ["Handler must be an async function"]

        return {k: v for k, v in errors.items() if v}  # Only return endpoints with errors

    def get_stats(self) -> Dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "total_endpoints": len(self._endpoints),
            "total_tags": len(self._tags),
            "batch_supported": sum(
                1 for r in self._endpoints.values() if r.supports_batch
            ),
            "cached_endpoints": sum(
                1 for r in self._endpoints.values() if r.cache_ttl_seconds > 0
            ),
            "tags": {
                tag: len(names) for tag, names in self._tags.items()
            }
        }


# Global registry instance (singleton)
_registry = None


def get_registry() -> EndpointRegistry:
    """
    Get the global endpoint registry instance.

    Returns:
        EndpointRegistry singleton
    """
    global _registry
    if _registry is None:
        _registry = EndpointRegistry()
    return _registry


def register_endpoint(
    name: str,
    required_params: Optional[List[str]] = None,
    optional_params: Optional[List[str]] = None,
    description: str = "",
    tags: Optional[Set[str]] = None,
    supports_batch: bool = False,
    cache_ttl_seconds: int = 0,
):
    """
    Decorator for registering endpoint handlers.

    Args:
        name: Unique endpoint name
        required_params: List of required parameter names
        optional_params: List of optional parameter names
        description: Human-readable description
        tags: Tags for categorization
        supports_batch: Whether endpoint supports batch operations
        cache_ttl_seconds: Cache TTL (0 = no cache)

    Returns:
        Decorator function

    Example:
        @register_endpoint(
            "player_career_stats",
            required_params=["player_name"],
            optional_params=["season"],
            description="Get player career statistics",
            tags={"player", "stats", "career"}
        )
        async def fetch_player_career_stats(params, provenance):
            # Implementation
            return dataframe
    """
    def decorator(func: EndpointHandler) -> EndpointHandler:
        """Actual decorator that registers the function."""
        registry = get_registry()

        registry.register(
            name=name,
            handler=func,
            required_params=required_params,
            optional_params=optional_params,
            description=description,
            tags=tags,
            supports_batch=supports_batch,
            cache_ttl_seconds=cache_ttl_seconds,
        )

        return func

    return decorator


def unregister_endpoint(name: str) -> bool:
    """
    Unregister an endpoint (useful for testing).

    Args:
        name: Endpoint name to unregister

    Returns:
        True if unregistered, False if not found
    """
    registry = get_registry()
    if name in registry._endpoints:
        # Remove from endpoints
        registration = registry._endpoints.pop(name)

        # Remove from tag index
        for tag in registration.tags:
            if tag in registry._tags:
                registry._tags[tag].discard(name)
                # Clean up empty tag sets
                if not registry._tags[tag]:
                    del registry._tags[tag]

        logger.debug(f"Unregistered endpoint: {name}")
        return True

    return False


def clear_registry():
    """
    Clear all registered endpoints (useful for testing).
    """
    registry = get_registry()
    registry._endpoints.clear()
    registry._tags.clear()
    logger.debug("Cleared endpoint registry")
