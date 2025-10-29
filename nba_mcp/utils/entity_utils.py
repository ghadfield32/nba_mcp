"""
Entity Utilities for Flexible Input Handling

Provides helper functions to accept both entity IDs (int) and names (str)
for players and teams, with automatic resolution to IDs.
"""

from typing import Optional, Union
import logging

logger = logging.getLogger(__name__)


def resolve_flexible_input(
    value: Optional[Union[int, str]],
    entity_type: str,
    param_name: str = "entity"
) -> Optional[int]:
    """
    Resolve flexible player/team input to entity ID.

    Accepts both numeric IDs and natural language names, automatically
    resolving names to IDs when needed. Provides pass-through for IDs
    for backward compatibility.

    Args:
        value: Entity identifier - can be:
            - None: No filtering (returns None)
            - int: Entity ID (pass-through, e.g., 2544 for LeBron)
            - str: Entity name (resolved to ID, e.g., "LeBron James")
        entity_type: Type of entity ("player" or "team")
        param_name: Parameter name for error messages

    Returns:
        Entity ID (int) if value provided, None otherwise

    Raises:
        ValueError: If entity name cannot be resolved
        TypeError: If value is neither int nor str

    Examples:
        >>> # Pass-through for IDs (backward compatible)
        >>> resolve_flexible_input(2544, "player", "player")
        2544

        >>> # Auto-resolve names to IDs
        >>> resolve_flexible_input("LeBron James", "player", "player")
        2544

        >>> # Team abbreviations work
        >>> resolve_flexible_input("LAL", "team", "team")
        1610612747

        >>> # None means no filtering
        >>> resolve_flexible_input(None, "player", "player")
        None
    """
    # No filtering if None
    if value is None:
        return None

    # Pass-through if already an ID
    if isinstance(value, int):
        logger.debug(f"{param_name}: Using ID directly: {value}")
        return value

    # Resolve name to ID
    if isinstance(value, str):
        logger.info(f"{param_name}: Resolving '{value}' to ID")

        # Import here to avoid circular dependency
        from nba_mcp.api.entity_resolver import resolve_player, resolve_team

        # Resolve based on entity type
        if entity_type == "player":
            entity_ref = resolve_player(value, min_confidence=0.6)
        elif entity_type == "team":
            entity_ref = resolve_team(value, min_confidence=0.6)
        else:
            raise ValueError(f"Invalid entity_type: {entity_type}. Must be 'player' or 'team'.")

        if entity_ref is None:
            raise ValueError(
                f"Could not resolve {entity_type} '{value}'. "
                f"Please check spelling or try using {entity_type} ID instead."
            )

        resolved_id = entity_ref.entity_id
        logger.info(
            f"{param_name}: Resolved '{value}' → {entity_ref.name} (ID: {resolved_id}, "
            f"confidence: {entity_ref.confidence:.2f})"
        )
        return resolved_id

    # Invalid type
    raise TypeError(
        f"{param_name} must be int (ID) or str (name), got {type(value).__name__}"
    )


def resolve_player_input(value: Optional[Union[int, str]]) -> Optional[int]:
    """
    Convenience function to resolve player input to ID.

    Args:
        value: Player ID (int) or player name (str)

    Returns:
        Player ID (int) or None

    Examples:
        >>> resolve_player_input("LeBron James")
        2544
        >>> resolve_player_input(2544)
        2544
        >>> resolve_player_input(None)
        None
    """
    return resolve_flexible_input(value, "player", "player")


def resolve_team_input(value: Optional[Union[int, str]]) -> Optional[int]:
    """
    Convenience function to resolve team input to ID.

    Args:
        value: Team ID (int), team name (str), or team abbreviation (str)

    Returns:
        Team ID (int) or None

    Examples:
        >>> resolve_team_input("Los Angeles Lakers")
        1610612747
        >>> resolve_team_input("LAL")
        1610612747
        >>> resolve_team_input(1610612747)
        1610612747
        >>> resolve_team_input(None)
        None
    """
    return resolve_flexible_input(value, "team", "team")
