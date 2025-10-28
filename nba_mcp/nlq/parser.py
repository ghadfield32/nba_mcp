# nba_mcp/nlq/parser.py
"""
Natural Language Query Parser for NBA queries.

Extracts structured components from natural language:
- Entities (players, teams) using entity resolver
- Stat categories (points, assists, advanced metrics)
- Time ranges (season, date, "tonight", "last 10 games")
- Query intent (comparison, leaders, game context, etc.)

Uses pattern matching + optional LLM fallback for ambiguous queries.
"""

from typing import Optional, List, Dict, Any, Literal
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
import re
import logging

from ..api.entity_resolver import resolve_entity, suggest_players, suggest_teams
from ..api.errors import EntityNotFoundError

logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class TimeRange:
    """Parsed time range for query."""

    start_date: Optional[date] = None
    end_date: Optional[date] = None
    season: Optional[str] = None  # "2023-24"
    relative: Optional[str] = None  # "tonight", "last_10_games", "this_season"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "season": self.season,
            "relative": self.relative,
        }


@dataclass
class ParsedQuery:
    """Structured representation of a natural language query."""

    raw_query: str
    intent: Literal[
        "leaders",
        "comparison",
        "game_context",
        "season_stats",
        "team_stats",
        "player_stats",
        "standings",
        "unknown",
    ]
    entities: List[Dict[str, Any]] = field(
        default_factory=list
    )  # Resolved players/teams
    stat_types: List[str] = field(default_factory=list)  # ["PTS", "AST", "TS_PCT"]
    time_range: Optional[TimeRange] = None
    modifiers: Dict[str, Any] = field(
        default_factory=dict
    )  # top_n, normalization, etc.
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "intent": self.intent,
            "entities": self.entities,
            "stat_types": self.stat_types,
            "time_range": self.time_range.to_dict() if self.time_range else None,
            "modifiers": self.modifiers,
            "confidence": self.confidence,
        }


# ============================================================================
# STAT CATEGORY MAPPING
# ============================================================================

STAT_PATTERNS = {
    # Basic stats
    "points": ["PTS"],
    "rebounds": ["REB"],
    "assists": ["AST"],
    "steals": ["STL"],
    "blocks": ["BLK"],
    "turnovers": ["TOV"],
    # Shooting
    "field goal": ["FG_PCT"],
    "three point": ["FG3_PCT"],
    "free throw": ["FT_PCT"],
    "shooting": ["FG_PCT", "FG3_PCT"],
    # Advanced
    "true shooting": ["TS_PCT"],
    "effective field goal": ["EFG_PCT"],
    "usage": ["USG_PCT"],
    "player impact": ["PIE"],
    "offensive rating": ["OFF_RATING"],
    "defensive rating": ["DEF_RATING"],
    "net rating": ["NET_RATING"],
    "pace": ["PACE"],
    # Aliases
    "ppg": ["PTS"],
    "rpg": ["REB"],
    "apg": ["AST"],
    "scoring": ["PTS"],
    "playmaking": ["AST"],
    "defense": ["STL", "BLK", "DEF_RATING"],
}


def extract_stat_types(query: str) -> List[str]:
    """
    Extract stat categories from query using pattern matching.

    Args:
        query: Natural language query

    Returns:
        List of stat category codes (e.g., ["PTS", "AST"])
    """
    query_lower = query.lower()
    stats = set()

    for pattern, codes in STAT_PATTERNS.items():
        if pattern in query_lower:
            stats.update(codes)

    # If no specific stats mentioned, return empty (planner will decide)
    return sorted(list(stats))


# ============================================================================
# INTENT CLASSIFICATION
# ============================================================================

INTENT_PATTERNS = {
    "leaders": [
        r"who leads?\b",
        r"top \d+",
        r"best (?:player|scorer|rebounder)",
        r"leader(?:s)? in",
        r"highest",
        r"most",
    ],
    "comparison": [
        r"\bvs\b",
        r"\bversus\b",
        r"compare",
        r"(?:better|worse) than",
        r"(\w+) or (\w+)",
        r"difference between",
    ],
    "game_context": [
        r"tonight",
        r"today'?s? game",
        r"matchup",
        r"who will win",
        r"prediction",
        r"preview",
    ],
    "standings": [
        r"standings?",
        r"playoff race",
        r"conference rank",
        r"division rank",
        r"seed",
    ],
    "team_stats": [
        r"team (?:stats?|performance)",
        r"(?:offense|defense|pace) (?:of|for)",
        r"(?:lakers|warriors|celtics|bulls)",  # Team name patterns
    ],
    "player_stats": [
        r"(?:lebron|curry|durant|giannis)",  # Player name patterns
        r"player stats?",
        r"career (?:stats?|average)",
        r"season average",
    ],
    "season_stats": [
        r"this season",
        r"current season",
        r"\d{4}-\d{2}",  # Season format
        r"compared? to (?:last|previous) (?:season|year)",
    ],
}


def classify_intent(
    query: str,
) -> Literal[
    "leaders",
    "comparison",
    "game_context",
    "season_stats",
    "team_stats",
    "player_stats",
    "standings",
    "unknown",
]:
    """
    Classify query intent using pattern matching.

    Args:
        query: Natural language query

    Returns:
        Intent classification
    """
    query_lower = query.lower()

    # Check patterns in priority order
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, query_lower):
                logger.debug(f"Matched intent '{intent}' with pattern: {pattern}")
                return intent

    # If comparison keywords found in entity count, default to comparison
    # This will be refined after entity extraction

    return "unknown"


# ============================================================================
# TIME RANGE PARSING
# ============================================================================


def parse_time_range(query: str) -> Optional[TimeRange]:
    """
    Parse time expressions from query.

    Handles:
    - "tonight", "today"
    - "this season", "current season"
    - "2023-24", "2020-21"
    - "last 10 games"
    - "last week", "last month"

    Args:
        query: Natural language query

    Returns:
        TimeRange object or None
    """
    query_lower = query.lower()
    today = date.today()

    # Tonight/Today
    if "tonight" in query_lower or "today" in query_lower:
        return TimeRange(start_date=today, end_date=today, relative="tonight")

    # This season / current season
    if "this season" in query_lower or "current season" in query_lower:
        year = today.year if today.month >= 10 else today.year - 1
        season = f"{year}-{str(year + 1)[-2:]}"
        return TimeRange(season=season, relative="this_season")

    # Specific season (YYYY-YY format)
    season_match = re.search(r"(\d{4})-(\d{2})", query)
    if season_match:
        season = season_match.group(0)
        return TimeRange(season=season)

    # Last N games
    last_games_match = re.search(r"last (\d+) games?", query_lower)
    if last_games_match:
        n_games = int(last_games_match.group(1))
        return TimeRange(relative=f"last_{n_games}_games")

    # Last week/month
    if "last week" in query_lower:
        return TimeRange(
            start_date=today - timedelta(days=7), end_date=today, relative="last_week"
        )

    if "last month" in query_lower:
        return TimeRange(
            start_date=today - timedelta(days=30), end_date=today, relative="last_month"
        )

    # Career/all-time
    if "career" in query_lower or "all-time" in query_lower or "history" in query_lower:
        return TimeRange(relative="career")

    # Default: current season
    year = today.year if today.month >= 10 else today.year - 1
    season = f"{year}-{str(year + 1)[-2:]}"
    return TimeRange(season=season, relative="default")


# ============================================================================
# ENTITY EXTRACTION
# ============================================================================


async def extract_entities(query: str) -> List[Dict[str, Any]]:
    """
    Extract and resolve entities (players, teams) from query.

    Uses entity resolver with fuzzy matching.

    Args:
        query: Natural language query

    Returns:
        List of resolved entities with metadata
    """
    entities = []

    # Common words to exclude from entity resolution
    STOP_WORDS = {
        "the",
        "who",
        "what",
        "when",
        "where",
        "how",
        "is",
        "are",
        "was",
        "were",
        "compare",
        "vs",
        "versus",
        "against",
        "leads",
        "leads",
        "leader",
        "tonight",
        "today",
        "game",
        "stats",
        "statistics",
        "season",
        "career",
        "best",
        "top",
        "show",
        "tell",
        "me",
        "about",
        "in",
        "of",
        "for",
        "to",
        "from",
        "with",
        "will",
        "win",
        "lose",
        "score",
        "points",
        "assists",
        "rebounds",
    }

    # Split query into tokens
    tokens = re.findall(r"\b[A-Za-z]+\b", query)

    # Try to resolve each token or token pair as entity
    i = 0
    while i < len(tokens):
        token = tokens[i].lower()

        # Skip stop words
        if token in STOP_WORDS:
            i += 1
            continue

        # Try two-word names first (e.g., "LeBron James")
        if i + 1 < len(tokens):
            two_word = f"{tokens[i]} {tokens[i+1]}"
            try:
                entity_ref = resolve_entity(two_word, min_confidence=0.7)
                entities.append(
                    {
                        "entity_type": entity_ref.entity_type,
                        "entity_id": entity_ref.entity_id,
                        "name": entity_ref.name,
                        "abbreviation": entity_ref.abbreviation,
                        "confidence": entity_ref.confidence,
                    }
                )
                logger.info(
                    f"Resolved entity: '{two_word}' → {entity_ref.name} (confidence: {entity_ref.confidence:.2f})"
                )
                i += 2  # Skip both tokens
                continue
            except EntityNotFoundError:
                pass

        # Try single word
        try:
            entity_ref = resolve_entity(tokens[i], min_confidence=0.7)
            entities.append(
                {
                    "entity_type": entity_ref.entity_type,
                    "entity_id": entity_ref.entity_id,
                    "name": entity_ref.name,
                    "abbreviation": entity_ref.abbreviation,
                    "confidence": entity_ref.confidence,
                }
            )
            logger.info(
                f"Resolved entity: '{tokens[i]}' → {entity_ref.name} (confidence: {entity_ref.confidence:.2f})"
            )
        except EntityNotFoundError:
            pass

        i += 1

    return entities


# ============================================================================
# MODIFIER EXTRACTION
# ============================================================================


def extract_modifiers(query: str) -> Dict[str, Any]:
    """
    Extract query modifiers (top N, normalization mode, etc.).

    Args:
        query: Natural language query

    Returns:
        Dictionary of modifiers
    """
    modifiers = {}

    # Top N
    top_n_match = re.search(r"top (\d+)", query.lower())
    if top_n_match:
        modifiers["top_n"] = int(top_n_match.group(1))

    # Per-game vs per-possession
    if "per game" in query.lower() or "ppg" in query.lower():
        modifiers["normalization"] = "per_game"
    elif "per 75" in query.lower() or "per possession" in query.lower():
        modifiers["normalization"] = "per_75"
    elif "per 100" in query.lower():
        modifiers["normalization"] = "per_100"

    # Home/away
    if "home" in query.lower():
        modifiers["location"] = "home"
    elif "away" in query.lower() or "road" in query.lower():
        modifiers["location"] = "away"

    # Playoffs vs regular season
    if "playoff" in query.lower() or "postseason" in query.lower():
        modifiers["season_type"] = "playoffs"
    elif "regular season" in query.lower():
        modifiers["season_type"] = "regular"

    return modifiers


# ============================================================================
# MAIN PARSER
# ============================================================================


async def parse_query(query: str) -> ParsedQuery:
    """
    Parse natural language NBA query into structured components.

    Pipeline:
    1. Classify intent
    2. Extract entities
    3. Extract stat types
    4. Parse time range
    5. Extract modifiers
    6. Calculate confidence

    Args:
        query: Natural language query

    Returns:
        ParsedQuery with all structured components

    Examples:
        >>> await parse_query("Who leads the NBA in assists?")
        ParsedQuery(intent="leaders", stat_types=["AST"], time_range=TimeRange(season="2024-25"))

        >>> await parse_query("Compare LeBron James and Kevin Durant")
        ParsedQuery(intent="comparison", entities=[LeBron, Durant], time_range=TimeRange(season="2024-25"))

        >>> await parse_query("Lakers vs Celtics tonight")
        ParsedQuery(intent="game_context", entities=[LAL, BOS], time_range=TimeRange(relative="tonight"))
    """
    logger.info(f"Parsing query: '{query}'")

    # Step 1: Classify intent
    intent = classify_intent(query)
    logger.debug(f"Classified intent: {intent}")

    # Step 2: Extract entities
    entities = await extract_entities(query)
    logger.debug(f"Extracted {len(entities)} entities: {[e['name'] for e in entities]}")

    # Refine intent based on entity count
    if intent == "unknown" and len(entities) == 2:
        intent = "comparison"
        logger.debug("Refined intent to 'comparison' based on 2 entities")
    elif intent == "unknown" and len(entities) == 1:
        entity_type = entities[0].get("entity_type")
        if entity_type == "player":
            intent = "player_stats"
        elif entity_type == "team":
            intent = "team_stats"
        logger.debug(f"Refined intent to '{intent}' based on entity type")

    # Step 3: Extract stat types
    stat_types = extract_stat_types(query)
    logger.debug(f"Extracted stat types: {stat_types}")

    # Step 4: Parse time range
    time_range = parse_time_range(query)
    logger.debug(f"Parsed time range: {time_range}")

    # Step 5: Extract modifiers
    modifiers = extract_modifiers(query)
    logger.debug(f"Extracted modifiers: {modifiers}")

    # Step 6: Calculate confidence
    confidence = 1.0
    if intent == "unknown":
        confidence *= 0.5
    if not entities and intent in ["comparison", "player_stats", "team_stats"]:
        confidence *= 0.3

    # Calculate average entity confidence
    if entities:
        avg_entity_confidence = sum(e["confidence"] for e in entities) / len(entities)
        confidence *= avg_entity_confidence

    logger.info(f"Parse complete: intent={intent}, confidence={confidence:.2f}")

    return ParsedQuery(
        raw_query=query,
        intent=intent,
        entities=entities,
        stat_types=stat_types,
        time_range=time_range,
        modifiers=modifiers,
        confidence=confidence,
    )


# ============================================================================
# VALIDATION
# ============================================================================


def validate_parsed_query(parsed: ParsedQuery) -> bool:
    """
    Validate that parsed query has sufficient information.

    Args:
        parsed: Parsed query

    Returns:
        True if valid, False otherwise
    """
    # Check confidence threshold
    if parsed.confidence < 0.3:
        logger.warning(f"Query confidence too low: {parsed.confidence:.2f}")
        return False

    # Check intent-specific requirements
    if parsed.intent == "comparison":
        if len(parsed.entities) < 2:
            logger.warning("Comparison intent requires at least 2 entities")
            return False

    if parsed.intent in ["player_stats", "team_stats"]:
        if len(parsed.entities) < 1:
            logger.warning(f"{parsed.intent} requires at least 1 entity")
            return False

    if parsed.intent == "leaders":
        if not parsed.stat_types:
            logger.warning("Leaders intent should have stat types (will use default)")

    return True
