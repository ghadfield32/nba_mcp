# nba_mcp/api/entity_resolver.py
"""
Entity resolution with fuzzy matching and caching.
Resolves ambiguous queries to specific NBA entities:
- Players (active and historical)
"""

import logging
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any, Dict, List, Literal, Optional

from nba_api.stats.static import players, teams

from .errors import EntityNotFoundError
from .models import EntityReference

logger = logging.getLogger(__name__)

# ENTITY CACHE

# LRU cache for resolved entities (1000 most recent lookups)
@lru_cache(maxsize=1000)
def _cached_player_lookup(query_lower: str) -> Optional[Dict[str, Any]]:
    """Cached player lookup by name (case-insensitive)."""
    all_players = players.get_players()

    # Exact match
    for player in all_players:
        full_name = f"{player['first_name']} {player['last_name']}".lower()
        if query_lower == full_name:
            return player

    # Last name exact match
    for player in all_players:
        if query_lower == player["last_name"].lower():
            return player

    # Fuzzy match (first partial match)
    for player in all_players:
        full_name = f"{player['first_name']} {player['last_name']}".lower()
        if query_lower in full_name:
            return player

    return None

@lru_cache(maxsize=1000)
def _cached_team_lookup(query_lower: str) -> Optional[Dict[str, Any]]:
    """Cached team lookup by name/abbreviation (case-insensitive)."""
    all_teams = teams.get_teams()

    # Exact full name match
    for team in all_teams:
        if query_lower == team["full_name"].lower():
            return team

    # Abbreviation match
    for team in all_teams:
        if query_lower == team["abbreviation"].lower():
            return team

    # City match
    for team in all_teams:
        if query_lower == team["city"].lower():
            return team

    # Nickname match
    for team in all_teams:
        if query_lower == team["nickname"].lower():
            return team

    # Fuzzy match on full name
    for team in all_teams:
        if query_lower in team["full_name"].lower():
            return team

    return None

# CONFIDENCE SCORING

def calculate_match_confidence(query: str, candidate: str) -> float:
    """
    Calculate confidence score for a match (0.0 to 1.0).

    Uses SequenceMatcher for similarity scoring.
    """
    return SequenceMatcher(None, query.lower(), candidate.lower()).ratio()

def rank_suggestions(
    query: str, candidates: List[Dict[str, Any]], name_key: str
) -> List[Dict[str, Any]]:
    """
    Rank entity suggestions by match confidence.

    Args:
        query: User's search query
        candidates: List of candidate entities
        name_key: Key to extract name from candidate dict

    Returns:
        Sorted list of candidates with confidence scores
    """
    scored = []
    for candidate in candidates:
        name = candidate.get(name_key, "")
        if isinstance(name, str):
            confidence = calculate_match_confidence(query, name)
            scored.append((candidate, confidence))

    # Sort by confidence descending
    scored.sort(key=lambda x: x[1], reverse=True)
    return [candidate for candidate, _ in scored]

# ENTITY RESOLVERS

def resolve_player(
    query: str, min_confidence: float = 0.6
) -> Optional[EntityReference]:
    """
    Resolve player name to EntityReference.

    Args:
        query: Player name (full, last name, or nickname)
        min_confidence: Minimum confidence threshold (0.0-1.0)

    Returns:
        EntityReference if found with sufficient confidence, else None
    """
    player = _cached_player_lookup(query.lower())

    if not player:
        return None

    full_name = f"{player['first_name']} {player['last_name']}"
    query_lower = query.lower()

    # Calculate confidence: 1.0 for exact matches, fuzzy for partial
    if query_lower == full_name.lower():
        confidence = 1.0  # Exact full name match
    elif query_lower == player["last_name"].lower():
        confidence = 0.9  # Last name match (high confidence but not perfect)
    elif query_lower == player["first_name"].lower():
        confidence = 0.7  # First name only (lower confidence due to common first names)
    else:
        # Fuzzy match for partial queries
        confidence = calculate_match_confidence(query, full_name)

    if confidence < min_confidence:
        return None

    # Build alternate names
    alternate_names = [
        player["last_name"],
        f"{player['first_name'][0]}. {player['last_name']}",  # "L. James"
    ]

    return EntityReference(
        entity_type="player",
        entity_id=player["id"],
        name=full_name,
        abbreviation=None,
        confidence=confidence,
        alternate_names=alternate_names,
        metadata={
            "is_active": player.get("is_active", True),
            "first_name": player["first_name"],
            "last_name": player["last_name"],
        },
    )

def resolve_team(query: str, min_confidence: float = 0.6) -> Optional[EntityReference]:
    """
    Resolve team name/abbreviation to EntityReference.

    Args:
        query: Team name, abbreviation, city, or nickname
        min_confidence: Minimum confidence threshold (0.0-1.0)

    Returns:
        EntityReference if found with sufficient confidence, else None
    """
    team = _cached_team_lookup(query.lower())

    if not team:
        return None

    full_name = team["full_name"]
    query_lower = query.lower()

    # Calculate confidence: 1.0 for exact matches, fuzzy for partial
    if query_lower == team["abbreviation"].lower():
        confidence = 1.0  # Exact abbreviation match
    elif query_lower == team["city"].lower():
        confidence = 1.0  # Exact city match
    elif query_lower == team["nickname"].lower():
        confidence = 1.0  # Exact nickname match
    elif query_lower == full_name.lower():
        confidence = 1.0  # Exact full name match
    else:
        # Fuzzy match for partial queries
        confidence = calculate_match_confidence(query, full_name)

    if confidence < min_confidence:
        return None

    # Build alternate names
    alternate_names = [
        team["abbreviation"],
        team["city"],
        team["nickname"],
        f"{team['city']} {team['nickname']}",
    ]

    return EntityReference(
        entity_type="team",
        entity_id=team["id"],
        name=full_name,
        abbreviation=team["abbreviation"],
        confidence=confidence,
        alternate_names=list(set(alternate_names)),  # Remove duplicates
        metadata={
            "city": team["city"],
            "nickname": team["nickname"],
            "year_founded": team.get("year_founded"),
            "abbreviation": team["abbreviation"],
        },
    )

def suggest_players(query: str, top_n: int = 5) -> List[EntityReference]:
    """
    Get ranked player suggestions for ambiguous query.

    Args:
        query: Partial or ambiguous player name
        top_n: Number of suggestions to return

    Returns:
        List of EntityReference sorted by confidence
    """
    all_players = players.get_players()
    query_lower = query.lower()

    # Filter to candidates containing query
    candidates = [
        p
        for p in all_players
        if query_lower in f"{p['first_name']} {p['last_name']}".lower()
    ]

    # Rank by confidence
    ranked = rank_suggestions(
        query, candidates, name_key="full_name"  # Will be constructed
    )

    # Convert to EntityReference
    suggestions = []
    for player_data in ranked[:top_n]:
        full_name = f"{player_data['first_name']} {player_data['last_name']}"
        confidence = calculate_match_confidence(query, full_name)

        suggestions.append(
            EntityReference(
                entity_type="player",
                entity_id=player_data["id"],
                name=full_name,
                abbreviation=None,
                confidence=confidence,
                alternate_names=[player_data["last_name"]],
                metadata={
                    "is_active": player_data.get("is_active", True),
                    "first_name": player_data["first_name"],
                    "last_name": player_data["last_name"],
                },
            )
        )

    return suggestions

def suggest_teams(query: str, top_n: int = 5) -> List[EntityReference]:
    """
    Get ranked team suggestions for ambiguous query.

    Args:
        query: Partial or ambiguous team name
        top_n: Number of suggestions to return

    Returns:
        List of EntityReference sorted by confidence
    """
    all_teams = teams.get_teams()
    query_lower = query.lower()

    # Filter to candidates
    candidates = [
        t
        for t in all_teams
        if query_lower in t["full_name"].lower()
        or query_lower in t["city"].lower()
        or query_lower in t["nickname"].lower()
        or query_lower in t["abbreviation"].lower()
    ]

    # Rank by confidence
    ranked = rank_suggestions(query, candidates, name_key="full_name")

    # Convert to EntityReference
    suggestions = []
    for team_data in ranked[:top_n]:
        confidence = calculate_match_confidence(query, team_data["full_name"])

        suggestions.append(
            EntityReference(
                entity_type="team",
                entity_id=team_data["id"],
                name=team_data["full_name"],
                abbreviation=team_data["abbreviation"],
                confidence=confidence,
                alternate_names=[
                    team_data["abbreviation"],
                    team_data["city"],
                    team_data["nickname"],
                ],
                metadata={
                    "city": team_data["city"],
                    "nickname": team_data["nickname"],
                    "abbreviation": team_data["abbreviation"],
                },
            )
        )

    return suggestions

# UNIFIED ENTITY RESOLVER

def resolve_entity(
    query: str,
    entity_type: Optional[Literal["player", "team"]] = None,
    min_confidence: float = 0.6,
    return_suggestions: bool = True,
    max_suggestions: int = 5,
) -> EntityReference:
    """
    Universal entity resolver with fuzzy matching.

    Args:
        query: Entity name/abbreviation to resolve
        entity_type: If specified, only search this type
        min_confidence: Minimum confidence threshold (0.0-1.0)
        return_suggestions: If True and no match, include suggestions
        max_suggestions: Max suggestions to return

    Returns:
        EntityReference for best match

    Raises:
        EntityNotFoundError: If no match found above confidence threshold
    """
    suggestions_list = []

    # Try player resolution
    if entity_type is None or entity_type == "player":
        player_ref = resolve_player(query, min_confidence)
        if player_ref:
            return player_ref

        if return_suggestions:
            suggestions_list.extend(suggest_players(query, max_suggestions))

    # Try team resolution
    if entity_type is None or entity_type == "team":
        team_ref = resolve_team(query, min_confidence)
        if team_ref:
            return team_ref

        if return_suggestions:
            suggestions_list.extend(suggest_teams(query, max_suggestions))

    # No match found
    suggestion_names = [s.name for s in suggestions_list[:max_suggestions]]

    raise EntityNotFoundError(
        entity_type=entity_type or "player/team",
        query=query,
        suggestions=suggestion_names,
    )

# CACHE MANAGEMENT

def clear_entity_cache():
    """Clear LRU cache for entity lookups."""
    _cached_player_lookup.cache_clear()
    _cached_team_lookup.cache_clear()
    logger.info("Entity cache cleared")

def get_cache_info() -> Dict[str, Any]:
    """Get cache statistics."""
    return {
        "player_cache": _cached_player_lookup.cache_info()._asdict(),
        "team_cache": _cached_team_lookup.cache_info()._asdict(),
    }
