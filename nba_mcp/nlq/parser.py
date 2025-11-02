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

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Literal, Optional

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
    seasons: Optional[List[str]] = None  # Phase 5.2 (P2): ["2020-21", "2021-22", "2022-23"]
    relative: Optional[str] = None  # "tonight", "last_10_games", "this_season"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "season": self.season,
            "seasons": self.seasons,  # Phase 5.2 (P2): Multi-season support
            "relative": self.relative,
        }


@dataclass
class ParsedQuery:
    """
    Structured representation of a natural language query.

    Phase 5.3 (NLQ Enhancement): Added validation feedback (2025-11-01)
    """

    raw_query: str
    intent: Literal[
        "leaders",
        "comparison",
        "game_context",
        "season_stats",
        "team_stats",
        "player_stats",
        "standings",
        "rankings",         # Phase 2.2: Team/player rankings
        "streaks",          # Phase 2.2: Win/loss or performance streaks
        "milestones",       # Phase 2.2: Career achievements, records
        "awards",           # Phase 2.2: MVP, DPOY, All-NBA, etc.
        "filtered_games",   # Phase 5.1: Games with statistical filters
        "all_time_leaders", # Phase 5.2 (P4): All-time/career statistical leaders
        "lineup_analysis",  # Phase 5.2 (P6): 5-man lineup statistics
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

    # Phase 5.3 (NLQ Enhancement): Validation feedback fields
    validation_issues: List[str] = field(default_factory=list)  # Issues detected
    suggestions: List[str] = field(default_factory=list)  # Suggested fixes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "intent": self.intent,
            "entities": self.entities,
            "stat_types": self.stat_types,
            "time_range": self.time_range.to_dict() if self.time_range else None,
            "modifiers": self.modifiers,
            "confidence": self.confidence,
            "validation_issues": self.validation_issues,
            "suggestions": self.suggestions,
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
    "minutes": ["MIN"],
    "fouls": ["PF"],
    "personal fouls": ["PF"],
    # Rebound splits (Phase 2.1)
    "offensive rebounds": ["OREB"],
    "defensive rebounds": ["DREB"],
    "total rebounds": ["REB"],
    "oreb": ["OREB"],
    "dreb": ["DREB"],
    # Plus/minus (Phase 2.1)
    "plus minus": ["PLUS_MINUS"],
    "+/-": ["PLUS_MINUS"],
    # Shooting - Basic
    "field goal": ["FG_PCT"],
    "three point": ["FG3_PCT"],
    "free throw": ["FT_PCT"],
    "shooting": ["FG_PCT", "FG3_PCT"],
    "three": ["FG3_PCT", "FG3M"],
    "threes": ["FG3_PCT", "FG3M"],
    # Shooting - Made/Attempted (Phase 2.1)
    "field goals made": ["FGM"],
    "field goals attempted": ["FGA"],
    "threes made": ["FG3M"],
    "threes attempted": ["FG3A"],
    "free throws made": ["FTM"],
    "free throws attempted": ["FTA"],
    # Shooting - Percentages (Phase 2.1)
    "fg%": ["FG_PCT"],
    "3p%": ["FG3_PCT"],
    "3pt%": ["FG3_PCT"],
    "ft%": ["FT_PCT"],
    "shooting percentage": ["FG_PCT"],
    "3pt percentage": ["FG3_PCT"],
    "3 point percentage": ["FG3_PCT"],
    "free throw percentage": ["FT_PCT"],
    # Shooting splits (Phase 2.1)
    "midrange": ["MID_RANGE_FG_PCT"],
    "mid range": ["MID_RANGE_FG_PCT"],
    "paint": ["PAINT_FG_PCT"],
    "in the paint": ["PAINT_FG_PCT"],
    "restricted area": ["RESTRICTED_AREA_FG_PCT"],
    "at rim": ["RESTRICTED_AREA_FG_PCT"],
    # Advanced shooting
    "true shooting": ["TS_PCT"],
    "ts%": ["TS_PCT"],
    "effective field goal": ["EFG_PCT"],
    "efg%": ["EFG_PCT"],
    # Advanced efficiency (Phase 2.1)
    "player efficiency rating": ["PER"],
    "per": ["PER"],
    "value over replacement": ["VORP"],
    "vorp": ["VORP"],
    "box plus minus": ["BPM"],
    "bpm": ["BPM"],
    "win shares": ["WIN_SHARES"],
    "ws": ["WIN_SHARES"],
    "offensive win shares": ["OFF_WIN_SHARES"],
    "defensive win shares": ["DEF_WIN_SHARES"],
    "ows": ["OFF_WIN_SHARES"],
    "dws": ["DEF_WIN_SHARES"],
    # Usage and impact
    "usage": ["USG_PCT"],
    "usage rate": ["USG_PCT"],
    "usg%": ["USG_PCT"],
    "player impact": ["PIE"],
    "pie": ["PIE"],
    # Ratings
    "offensive rating": ["OFF_RATING"],
    "defensive rating": ["DEF_RATING"],
    "net rating": ["NET_RATING"],
    "off rating": ["OFF_RATING"],
    "def rating": ["DEF_RATING"],
    "ortg": ["OFF_RATING"],
    "drtg": ["DEF_RATING"],
    "nrtg": ["NET_RATING"],
    "pace": ["PACE"],
    # Percentages (Phase 2.1)
    "assist percentage": ["AST_PCT"],
    "assist ratio": ["AST_RATIO"],
    "assist to turnover": ["AST_TO"],
    "rebound percentage": ["REB_PCT"],
    "offensive rebound percentage": ["OREB_PCT"],
    "defensive rebound percentage": ["DREB_PCT"],
    "turnover percentage": ["TOV_PCT"],
    # Team stats (Phase 2.1)
    "wins": ["W"],
    "losses": ["L"],
    "win percentage": ["WIN_PCT"],
    "win%": ["WIN_PCT"],
    "record": ["W", "L"],
    # Double-doubles (Phase 2.1)
    "double double": ["DD2"],
    "double doubles": ["DD2"],
    "triple double": ["TD3"],
    "triple doubles": ["TD3"],
    "dd2": ["DD2"],
    "td3": ["TD3"],
    # Games played (Phase 2.1)
    "games played": ["GP"],
    "games": ["GP"],
    "gp": ["GP"],
    "mpg": ["MIN"],
    # Common aliases
    "ppg": ["PTS"],
    "rpg": ["REB"],
    "apg": ["AST"],
    "bpg": ["BLK"],
    "spg": ["STL"],
    "scoring": ["PTS"],
    "playmaking": ["AST"],
    "defense": ["STL", "BLK", "DEF_RATING"],
    # Defensive stats (Phase 2.1)
    "stocks": ["STL", "BLK"],
    "stock": ["STL", "BLK"],
    "deflections": ["DEFLECTIONS"],
    "charges": ["CHARGES_DRAWN"],
    "contested shots": ["CONTESTED_SHOTS"],
    # Clutch (Phase 2.1)
    "clutch": ["CLUTCH_PTS"],
    "crunch time": ["CLUTCH_PTS"],
    "late game": ["CLUTCH_PTS"],
    "4th quarter": ["Q4_PTS"],
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
        # Phase 5.3 (NLQ Enhancement): Additional leader patterns (2025-11-01)
        r"leading (?:the league|nba) in",
        r"best (?:in|at)",
        r"number one in",
    ],
    "comparison": [
        r"\bvs\b",
        r"\bversus\b",
        r"compare",
        r"(?:better|worse) than",
        r"(\w+) or (\w+)",
        r"difference between",
        # Phase 5.2 (P6 Phase 2): Lineup-specific comparison patterns (2025-11-01)
        r"lineup.*\bvs\b.*lineup",
        r"compare.*lineup",
        r"best lineup.*vs",
        # Phase 5.3 (NLQ Enhancement): Additional comparison patterns (2025-11-01)
        r"has more (?:than|points|rebounds|assists)",
        r"exceeds",
        r"over \d+",
        r"above \d+",
        r"outperform",
        r"superior to",
    ],
    "game_context": [
        r"tonight",
        r"today'?s? game",
        r"matchup",
        r"who will win",
        r"prediction",
        r"preview",
    ],
    # Phase 5.2 (P6): Lineup analysis (2025-11-01)
    # MOVED: Higher priority to prevent routing conflicts with team_stats/player_stats
    # Phase 5.2 (P6 Stress Test Fix #1): Moved before standings for priority matching
    "lineup_analysis": [
        r"lineup",
        r"five[- ]man",
        r"5[- ]man",
        r"rotation",
        r"starting (?:five|lineup)",
        r"bench unit",
        # Phase 5.2 (P6 Phase 3): Trend analysis patterns (2025-11-01)
        r"lineup trend",
        r"lineup performance over time",
        r"lineup (?:performance|effectiveness) by (?:month|quarter)",
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
    # Phase 5.1: Filtered game queries (2025-11-01)
    "filtered_games": [
        r"games? (?:with|where|when|having)",
        r"(?:scored|had|shot|made) (?:at least|more than|over|above)",
        r"\d+\+ (?:points?|rebounds?|assists?)",
        r"triple[- ]double",
        r"double[- ]double",
    ],
    # Phase 5.2 (P4): All-time leaders (2025-11-01)
    "all_time_leaders": [
        r"all[- ]time",
        r"career (?:leader|total|stat)",
        r"(?:best|greatest) (?:of )?all[- ]time",
        r"historical leader",
        r"nba history",
    ],
    # Phase 2.2: New intent types (2025-11-01)
    # Phase 5.3 (NLQ Enhancement): Enhanced ranking patterns (2025-11-01)
    "rankings": [
        r"rank(?:ed|ing)?\b",
        r"where (?:do|does|is|are) .+? rank",
        r"how (?:good|well) is",
        r"position in",
        r"rated",
        r"tier list",
        r"power ranking",
        # Phase 5.3: Additional ranking patterns
        r"rank (?:teams|players) by",
        r"sort (?:teams|players) by",
        r"order (?:teams|players) by",
        r"list (?:teams|players) ranked by",
    ],
    "streaks": [
        r"streak",
        r"winning streak",
        r"losing streak",
        r"hot streak",
        r"cold streak",
        r"consecutive",
        r"in a row",
        r"straight (?:wins|losses|games)",
    ],
    "milestones": [
        r"milestone",
        r"career (?:high|low|record)",
        r"all[- ]time",
        r"record",
        r"close to \d+",
        r"away from",
        r"\d+(?:st|nd|rd|th) (?:in|all-time)",
        r"hall of fame",
        r"first (?:player|team) to",
    ],
    "awards": [
        r"mvp",
        r"most valuable player",
        r"dpoy",
        r"defensive player of the year",
        r"roy",
        r"rookie of the year",
        r"sixth man",
        r"most improved",
        r"mip",
        r"coach of the year",
        r"coy",
        r"all[- ]nba",
        r"all[- ]star",
        r"all[- ]defensive",
        r"all[- ]rookie",
        r"won (?:the )?award",
        r"award winner",
    ],
    # Phase 5.3 (NLQ Enhancement): Highlight intent (2025-11-01)
    "highlight": [
        r"highlight (?:players|teams|games)",
        r"show me (?:players|teams) (?:who|that|with)",
        r"find (?:players|teams) (?:who|that|with)",
        r"which (?:players|teams) (?:have|had)",
        r"who (?:has|have|had) (?:more than|over|at least)",
        r"players with \d+",
        r"teams with \d+",
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
    "rankings",         # Phase 2.2
    "streaks",          # Phase 2.2
    "milestones",       # Phase 2.2
    "awards",           # Phase 2.2
    "filtered_games",   # Phase 5.1
    "all_time_leaders", # Phase 5.2 (P4)
    "lineup_analysis",  # Phase 5.2 (P6)
    "unknown",
]:
    """
    Classify query intent using pattern matching.

    Args:
        query: Natural language query

    Returns:
        Intent classification (includes Phase 2.2 intents: rankings, streaks, milestones, awards)
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


def parse_calendar_anchor(query: str, today: date) -> Optional[TimeRange]:
    """
    Parse calendar anchor expressions (Phase 5.3 NLQ Enhancement).

    Handles:
    - "since Christmas", "after Christmas"
    - "since New Year", "after New Year"
    - "before playoffs", "after All-Star break"
    - "since Thanksgiving"

    Args:
        query: Natural language query
        today: Current date

    Returns:
        TimeRange object or None
    """
    query_lower = query.lower()
    current_year = today.year

    # NBA season year (starts in October)
    season_year = current_year if today.month >= 10 else current_year - 1

    # Calendar anchors with specific dates
    anchors = {
        "christmas": date(season_year, 12, 25),
        "new year": date(season_year + 1, 1, 1),
        "thanksgiving": date(season_year, 11, 24),  # Approximate (4th Thursday)
        "all-star": date(season_year + 1, 2, 15),  # Approximate All-Star weekend
        "all star": date(season_year + 1, 2, 15),
        "mlk day": date(season_year + 1, 1, 16),  # MLK Day (3rd Monday)
    }

    # Check for "since X" or "after X" patterns
    for anchor_name, anchor_date in anchors.items():
        if f"since {anchor_name}" in query_lower or f"after {anchor_name}" in query_lower:
            return TimeRange(
                start_date=anchor_date,
                end_date=today,
                relative=f"since_{anchor_name.replace(' ', '_')}"
            )
        if f"before {anchor_name}" in query_lower:
            # Get season start (October 1st of season year)
            season_start = date(season_year, 10, 1)
            return TimeRange(
                start_date=season_start,
                end_date=anchor_date,
                relative=f"before_{anchor_name.replace(' ', '_')}"
            )

    # Playoff anchor (April-June)
    if "playoffs" in query_lower or "postseason" in query_lower:
        playoff_start = date(season_year + 1, 4, 15)  # Approximate playoff start
        if "before" in query_lower or "pre" in query_lower:
            # Regular season before playoffs
            season_start = date(season_year, 10, 1)
            return TimeRange(
                start_date=season_start,
                end_date=playoff_start,
                relative="before_playoffs"
            )
        elif "during" in query_lower or "in" in query_lower:
            # During playoffs
            playoff_end = date(season_year + 1, 6, 30)
            return TimeRange(
                start_date=playoff_start,
                end_date=playoff_end,
                relative="during_playoffs"
            )

    return None


def parse_time_range(query: str) -> Optional[TimeRange]:
    """
    Parse time expressions from query.

    Handles:
    - "tonight", "today"
    - "this season", "current season"
    - "2023-24", "2020-21"
    - "last 10 games"
    - "last week", "last month"
    - Phase 5.3: "since Christmas", "after All-Star break", "last three weeks"

    Args:
        query: Natural language query

    Returns:
        TimeRange object or None
    """
    query_lower = query.lower()
    today = date.today()

    # Phase 5.3: Check calendar anchors first (since Christmas, after All-Star, etc.)
    calendar_result = parse_calendar_anchor(query, today)
    if calendar_result:
        return calendar_result

    # Tonight/Today (Phase 4.1: Enhanced relative time)
    if "tonight" in query_lower or "today" in query_lower:
        return TimeRange(start_date=today, end_date=today, relative="tonight")

    # Yesterday (Phase 4.1)
    if "yesterday" in query_lower:
        yesterday = today - timedelta(days=1)
        return TimeRange(start_date=yesterday, end_date=yesterday, relative="yesterday")

    # Tomorrow (Phase 4.1)
    if "tomorrow" in query_lower:
        tomorrow = today + timedelta(days=1)
        return TimeRange(start_date=tomorrow, end_date=tomorrow, relative="tomorrow")

    # Phase 5.3: Relative period parsing ("last three weeks", "past two weeks")
    weeks_match = re.search(r"(?:last|past) (\w+) weeks?", query_lower)
    if weeks_match:
        weeks_word = weeks_match.group(1)
        # Convert word to number
        word_to_num = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
        num_weeks = word_to_num.get(weeks_word, 1)
        # Also check for numeric
        if weeks_word.isdigit():
            num_weeks = int(weeks_word)
        days_back = num_weeks * 7
        return TimeRange(
            start_date=today - timedelta(days=days_back),
            end_date=today,
            relative=f"last_{num_weeks}_weeks"
        )

    # Phase 5.2 (P2): Check for multi-season ranges FIRST
    season_range = parse_season_range(query)
    if season_range and len(season_range) > 1:
        # Multi-season query detected
        return TimeRange(seasons=season_range, relative="multi_season")

    # This season / current season
    if "this season" in query_lower or "current season" in query_lower:
        year = today.year if today.month >= 10 else today.year - 1
        season = f"{year}-{str(year + 1)[-2:]}"
        return TimeRange(season=season, relative="this_season")

    # Last season / previous season (Phase 4.1)
    if "last season" in query_lower or "previous season" in query_lower:
        year = today.year if today.month >= 10 else today.year - 1
        last_year = year - 1
        season = f"{last_year}-{str(last_year + 1)[-2:]}"
        return TimeRange(season=season, relative="last_season")

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

    # Month names (Phase 4.1: "in December", "January games")
    month_names = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12
    }
    for month_name, month_num in month_names.items():
        if month_name in query_lower:
            # Determine year (use current year for current/future months, last year for past months)
            current_month = today.month
            if month_num > current_month:
                # Future month (likely last year's games)
                year = today.year - 1
            else:
                # Current or past month this year
                year = today.year

            # Calculate first and last day of month
            from calendar import monthrange
            last_day = monthrange(year, month_num)[1]
            start_date = date(year, month_num, 1)
            end_date = date(year, month_num, last_day)

            return TimeRange(
                start_date=start_date,
                end_date=end_date,
                relative=f"{month_name}_{year}"
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

    Phase 5.3 (NLQ Enhancement): Enhanced multi-token entity resolution (2025-11-01)
    - Supports 3-word names (Karl-Anthony Towns, Los Angeles Lakers)
    - Supports 2-word city names (San Antonio, Golden State)
    - Handles hyphenated names (already supported in regex)

    Uses entity resolver with fuzzy matching.

    Args:
        query: Natural language query

    Returns:
        List of resolved entities with metadata
    """
    entities = []

    # Common words to exclude from entity resolution
    # Phase 5.3: Keep stop words but allow them in multi-word entity attempts
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

    # Split query into tokens (includes hyphens and apostrophes)
    # Examples: "Karl-Anthony Towns", "De'Aaron Fox", "O'Neal"
    tokens = re.findall(r"\b[A-Za-z]+(?:['-][A-Za-z]+)*\b", query)

    # Phase 5.3: Enhanced multi-token entity resolution
    # Try to resolve tokens in descending order: 3-word → 2-word → 1-word
    i = 0
    while i < len(tokens):
        token = tokens[i].lower()

        # Skip stop words only if at end of query (allow in multi-word attempts)
        if token in STOP_WORDS and i + 1 >= len(tokens):
            i += 1
            continue

        resolved = False

        # Try three-word names first (e.g., "Karl-Anthony Towns", "Los Angeles Lakers")
        if i + 2 < len(tokens):
            three_word = f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}"
            try:
                entity_ref = resolve_entity(three_word, min_confidence=0.7)
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
                    f"Resolved 3-word entity: '{three_word}' → {entity_ref.name} (confidence: {entity_ref.confidence:.2f})"
                )
                i += 3  # Skip all three tokens
                resolved = True
                continue
            except EntityNotFoundError:
                pass

        # Try two-word names (e.g., "LeBron James", "San Antonio")
        if not resolved and i + 1 < len(tokens):
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
                    f"Resolved 2-word entity: '{two_word}' → {entity_ref.name} (confidence: {entity_ref.confidence:.2f})"
                )
                i += 2  # Skip both tokens
                resolved = True
                continue
            except EntityNotFoundError:
                pass

        # Try single word (skip if it's a stop word)
        if not resolved and token not in STOP_WORDS:
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
                    f"Resolved 1-word entity: '{tokens[i]}' → {entity_ref.name} (confidence: {entity_ref.confidence:.2f})"
                )
            except EntityNotFoundError:
                pass

        i += 1

    return entities


# ============================================================================
# STATISTICAL FILTER EXTRACTION (Phase 5.1: Audit Improvements)
# ============================================================================


def extract_stat_filters(query: str) -> Optional[Dict[str, List[Any]]]:
    """
    Extract statistical filters from queries like:
    - "games with 30+ points"
    - "shot above 50% from three"
    - "10+ rebounds and 5+ assists"

    Phase 5.1: Added to integrate fetch_player_games into NLQ pipeline

    Args:
        query: Natural language query

    Returns:
        Dict mapping stat codes to [operator, value] pairs
        Example: {"PTS": [">=", 30], "FG3_PCT": [">=", 0.5]}

    Examples:
        >>> extract_stat_filters("games with 30+ points")
        {"PTS": [">=", 30]}

        >>> extract_stat_filters("shot above 50% from three")
        {"FG3_PCT": [">=", 0.5]}

        >>> extract_stat_filters("10+ rebounds and 5+ assists")
        {"REB": [">=", 10], "AST": [">=", 5]}
    """
    query_lower = query.lower()
    filters = {}

    # Pattern 1: "X+ statname" → >= X
    # Examples: "30+ points", "10+ rebounds", "5+ assists"
    pattern1 = r"(\d+)\+\s*(?:points?|pts?|rebounds?|rebs?|assists?|asts?|steals?|stls?|blocks?|blks?|turnovers?|tovs?|minutes?|mins?)"
    matches1 = re.finditer(pattern1, query_lower)
    for match in matches1:
        value = int(match.group(1))
        stat_text = match.group(0)[len(match.group(1))+1:].strip()  # Remove number+

        # Map to stat code
        if re.search(r"points?|pts?", stat_text):
            filters["PTS"] = [">=", value]
        elif re.search(r"rebounds?|rebs?", stat_text):
            filters["REB"] = [">=", value]
        elif re.search(r"assists?|asts?", stat_text):
            filters["AST"] = [">=", value]
        elif re.search(r"steals?|stls?", stat_text):
            filters["STL"] = [">=", value]
        elif re.search(r"blocks?|blks?", stat_text):
            filters["BLK"] = [">=", value]
        elif re.search(r"turnovers?|tovs?", stat_text):
            filters["TOV"] = [">=", value]
        elif re.search(r"minutes?|mins?", stat_text):
            filters["MIN"] = [">=", value]

    # Pattern 2: "above/over/more than X%" → >= X/100
    # Examples: "shot above 50%", "above 40% from three"
    pattern2 = r"(?:above|over|more than|greater than)\s+(\d+)%"
    matches2 = re.finditer(pattern2, query_lower)
    for match in matches2:
        value = float(match.group(1)) / 100

        # Determine stat based on context
        if "three" in query_lower or "3pt" in query_lower or "3-pt" in query_lower:
            filters["FG3_PCT"] = [">=", value]
        elif "field goal" in query_lower or "fg" in query_lower:
            filters["FG_PCT"] = [">=", value]
        elif "free throw" in query_lower or "ft" in query_lower:
            filters["FT_PCT"] = [">=", value]
        else:
            # Default to FG%
            filters["FG_PCT"] = [">=", value]

    # Pattern 3: "below/under/less than X%" → <= X/100
    pattern3 = r"(?:below|under|less than)\s+(\d+)%"
    matches3 = re.finditer(pattern3, query_lower)
    for match in matches3:
        value = float(match.group(1)) / 100

        if "three" in query_lower or "3pt" in query_lower:
            filters["FG3_PCT"] = ["<=", value]
        elif "field goal" in query_lower or "fg" in query_lower:
            filters["FG_PCT"] = ["<=", value]
        elif "turnover" in query_lower:
            filters["TOV_PCT"] = ["<=", value]
        else:
            filters["FG_PCT"] = ["<=", value]

    # Pattern 4: "at least X" → >= X
    pattern4 = r"at least (\d+)\s*(?:points?|pts?|rebounds?|rebs?|assists?|asts?)"
    matches4 = re.finditer(pattern4, query_lower)
    for match in matches4:
        value = int(match.group(1))
        stat_text = match.group(0)[len("at least ")+len(match.group(1)):].strip()

        if re.search(r"points?|pts?", stat_text):
            filters["PTS"] = [">=", value]
        elif re.search(r"rebounds?|rebs?", stat_text):
            filters["REB"] = [">=", value]
        elif re.search(r"assists?|asts?", stat_text):
            filters["AST"] = [">=", value]

    # Pattern 5: "double-double" / "triple-double"
    if "triple" in query_lower and "double" in query_lower:
        # Triple-double: 10+ in 3 categories (typically PTS, REB, AST)
        filters["PTS"] = [">=", 10]
        filters["REB"] = [">=", 10]
        filters["AST"] = [">=", 10]
    elif "double" in query_lower and "double" in query_lower:
        # Double-double: 10+ in 2 categories (typically PTS/REB or PTS/AST)
        # We'll just filter for high scorers with rebounds
        filters["PTS"] = [">=", 10]
        filters["REB"] = [">=", 10]

    return filters if filters else None


# ============================================================================
# SEASON RANGE PARSING (Phase 5.2 P2: Multi-Season Support)
# ============================================================================


def parse_season_range(query: str) -> Optional[List[str]]:
    """
    Parse season ranges from queries for multi-season support.

    Phase 5.2 (P2): Multi-Season Support (2025-11-01)

    Detects patterns like:
    - "2020-21 to 2023-24" → ["2020-21", "2021-22", "2022-23", "2023-24"]
    - "from 2021-22 through 2023-24" → ["2021-22", "2022-23", "2023-24"]
    - "last 3 seasons" → ["2022-23", "2023-24", "2024-25"]

    Args:
        query: Natural language query

    Returns:
        List of season strings in YYYY-YY format, or None if no range found

    Examples:
        >>> parse_season_range("LeBron stats from 2020-21 to 2023-24")
        ["2020-21", "2021-22", "2022-23", "2023-24"]

        >>> parse_season_range("Compare Curry's last 3 seasons")
        ["2022-23", "2023-24", "2024-25"]
    """
    query_lower = query.lower()
    seasons = []

    # Pattern 1: Explicit season range "YYYY-YY to/through YYYY-YY"
    pattern1 = r"(\d{4})-(\d{2})\s+(?:to|through|thru|-)\s+(\d{4})-(\d{2})"
    match1 = re.search(pattern1, query)
    if match1:
        start_year = int(match1.group(1))
        start_suffix = match1.group(2)
        end_year = int(match1.group(3))
        end_suffix = match1.group(4)

        # Generate all seasons in range
        current_year = start_year
        while current_year <= end_year:
            next_year_suffix = str(current_year + 1)[-2:]
            season = f"{current_year}-{next_year_suffix}"
            seasons.append(season)
            current_year += 1

        return seasons

    # Pattern 2: Relative season ranges "last N seasons"
    pattern2 = r"last (\d+) seasons?"
    match2 = re.search(pattern2, query_lower)
    if match2:
        n_seasons = int(match2.group(1))

        # Get current season year
        from datetime import datetime
        current_date = datetime.now()
        current_month = current_date.month

        # NBA season starts in October, so if we're before October,
        # the current season is (year-1)-(year)
        if current_month < 10:
            current_season_start = current_date.year - 1
        else:
            current_season_start = current_date.year

        # Generate last N seasons
        for i in range(n_seasons - 1, -1, -1):
            year = current_season_start - i
            next_year_suffix = str(year + 1)[-2:]
            season = f"{year}-{next_year_suffix}"
            seasons.append(season)

        return seasons

    # Pattern 3: "previous N seasons"
    pattern3 = r"(?:previous|past) (\d+) seasons?"
    match3 = re.search(pattern3, query_lower)
    if match3:
        n_seasons = int(match3.group(1))

        from datetime import datetime
        current_date = datetime.now()
        current_month = current_date.month

        if current_month < 10:
            current_season_start = current_date.year - 1
        else:
            current_season_start = current_date.year

        # Previous N seasons (not including current)
        for i in range(n_seasons, 0, -1):
            year = current_season_start - i
            next_year_suffix = str(year + 1)[-2:]
            season = f"{year}-{next_year_suffix}"
            seasons.append(season)

        return seasons

    return None


# ============================================================================
# MODIFIER EXTRACTION
# ============================================================================


def extract_modifiers(query: str) -> Dict[str, Any]:
    """
    Extract query modifiers (top N, normalization mode, conference, etc.).

    Args:
        query: Natural language query

    Returns:
        Dictionary of modifiers

    Phase 2.4 Enhancements:
        - Conference/division filters
        - Expanded season type handling
        - Opponent filters
    """
    modifiers = {}
    query_lower = query.lower()

    # Top N
    top_n_match = re.search(r"top (\d+)", query_lower)
    if top_n_match:
        modifiers["top_n"] = int(top_n_match.group(1))

    # Per-game vs per-possession
    if "per game" in query_lower or "ppg" in query_lower:
        modifiers["normalization"] = "per_game"
    elif "per 75" in query_lower or "per possession" in query_lower:
        modifiers["normalization"] = "per_75"
    elif "per 100" in query_lower:
        modifiers["normalization"] = "per_100"
    elif "per 36" in query_lower:
        modifiers["normalization"] = "per_36"
    elif "per 48" in query_lower:
        modifiers["normalization"] = "per_48"

    # Home/away
    if "home" in query_lower:
        modifiers["location"] = "home"
    elif "away" in query_lower or "road" in query_lower:
        modifiers["location"] = "away"

    # Playoffs vs regular season (Phase 2.4: Enhanced)
    if "playoff" in query_lower or "postseason" in query_lower:
        modifiers["season_type"] = "playoffs"
    elif "regular season" in query_lower:
        modifiers["season_type"] = "regular"
    elif "preseason" in query_lower or "pre-season" in query_lower:
        modifiers["season_type"] = "preseason"

    # Conference filter (Phase 2.4)
    if re.search(r"\beastern\b|\beast\b", query_lower):
        modifiers["conference"] = "East"
    elif re.search(r"\bwestern\b|\bwest\b", query_lower):
        modifiers["conference"] = "West"

    # Division filter (Phase 2.4)
    divisions = {
        "atlantic": "Atlantic",
        "central": "Central",
        "southeast": "Southeast",
        "pacific": "Pacific",
        "northwest": "Northwest",
        "southwest": "Southwest",
    }
    for div_key, div_name in divisions.items():
        if div_key in query_lower:
            modifiers["division"] = div_name
            break

    # Opponent filter (Phase 2.4)
    # Pattern: "vs Lakers", "against Celtics", "versus Warriors"
    opponent_match = re.search(r"(?:vs|versus|against)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)", query_lower)
    if opponent_match:
        modifiers["opponent"] = opponent_match.group(1).strip()

    # Win/Loss outcome (Phase 2.4)
    if re.search(r"\bwins?\b|\bwon\b", query_lower) and not re.search(r"who will win", query_lower):
        modifiers["outcome"] = "W"
    elif re.search(r"\bloss(?:es)?\b|\blost\b", query_lower):
        modifiers["outcome"] = "L"

    # First/Second half (Phase 2.4)
    if "first half" in query_lower:
        modifiers["game_segment"] = "First Half"
    elif "second half" in query_lower:
        modifiers["game_segment"] = "Second Half"
    elif "overtime" in query_lower or "ot" in query_lower:
        modifiers["game_segment"] = "Overtime"

    # Starter/bench (Phase 2.4)
    if "starter" in query_lower or "starting" in query_lower:
        modifiers["starter_bench"] = "Starters"
    elif "bench" in query_lower or "reserve" in query_lower:
        modifiers["starter_bench"] = "Bench"

    # Phase 5.2 (P6 Phase 2): Lineup modifiers
    # lineup_type (starting/bench)
    if "starting lineup" in query_lower or "starting five" in query_lower or "starting unit" in query_lower:
        modifiers["lineup_type"] = "starting"
    elif "bench lineup" in query_lower or "bench unit" in query_lower or "second unit" in query_lower:
        modifiers["lineup_type"] = "bench"

    # with_player (lineups including player)
    with_player_match = re.search(r"(?:with|including)\s+([A-Za-z\s]+?)(?:\s+lineup|\s+and|\s+,|$)", query_lower)
    if with_player_match:
        player_name = with_player_match.group(1).strip()
        # Clean up common words
        player_name = re.sub(r"\s+(lineup|stats|statistics|analysis)$", "", player_name)
        if player_name and len(player_name) > 2:  # Avoid single letters
            modifiers["with_player"] = player_name

    # without_player (lineups excluding player)
    without_player_match = re.search(r"(?:without|excluding|except)\s+([A-Za-z\s]+?)(?:\s+lineup|\s+and|\s+,|$)", query_lower)
    if without_player_match:
        player_name = without_player_match.group(1).strip()
        # Clean up common words
        player_name = re.sub(r"\s+(lineup|stats|statistics|analysis)$", "", player_name)
        if player_name and len(player_name) > 2:  # Avoid single letters
            modifiers["without_player"] = player_name

    # Phase 5.3 (NLQ Enhancement): Additional modifiers for enhanced query support

    # Minimum games filter (Phase 5.3)
    # Examples: "min 10 games", "at least 20 games", "minimum 15 games"
    min_games_match = re.search(r"(?:min(?:imum)?|at least)\s+(\d+)\s+games?", query_lower)
    if min_games_match:
        modifiers["min_games"] = int(min_games_match.group(1))

    # Last N games (Phase 5.3)
    # Examples: "last 10 games", "past 5 games", "recent 20 games"
    last_n_match = re.search(r"(?:last|past|recent)\s+(\d+)\s+games?", query_lower)
    if last_n_match:
        modifiers["last_n_games"] = int(last_n_match.group(1))

    # Clutch time filter (Phase 5.3)
    # Examples: "clutch stats", "final 5 minutes", "crunch time", "close games"
    if re.search(r"\bclutch\b|\bcrunch time\b|final \d+ minutes?|close games?", query_lower):
        modifiers["clutch"] = True

    # Month filter (Phase 5.3)
    # Examples: "in January", "during December", "November games"
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12
    }
    for month_name, month_num in months.items():
        if re.search(rf"\b(?:in|during)\s+{month_name}\b", query_lower) or re.search(rf"\b{month_name}\s+games?\b", query_lower):
            modifiers["month"] = month_num
            break

    # Best/Worst N (Phase 5.3)
    # Examples: "worst 5 performances", "bottom 10 teams"
    worst_match = re.search(r"(?:worst|bottom)\s+(\d+)", query_lower)
    if worst_match:
        modifiers["worst_n"] = int(worst_match.group(1))
        modifiers["sort_order"] = "ascending"  # For worst/bottom queries

    # Statistical filters (Phase 5.1: Audit Improvements)
    # Detect queries like "games with 30+ points" or "shot above 50%"
    stat_filters = extract_stat_filters(query)
    if stat_filters:
        modifiers["stat_filters"] = stat_filters

    return modifiers


# ============================================================================
# VALIDATION FEEDBACK GENERATION (Phase 5.3: NLQ Enhancement)
# ============================================================================


def generate_validation_feedback(parsed: ParsedQuery) -> None:
    """
    Generate validation feedback for a parsed query (Phase 5.3).

    Analyzes the ParsedQuery and populates validation_issues and suggestions
    to help users understand parsing results and improve their queries.

    Args:
        parsed: ParsedQuery to analyze (modified in-place)

    Examples:
        - Unknown intent → suggests similar query patterns
        - Low confidence → identifies ambiguous parts
        - Missing entities → suggests adding player/team names
    """
    issues = []
    suggestions = []

    # Issue 1: Unknown intent
    if parsed.intent == "unknown":
        issues.append("Could not determine query intent")
        suggestions.append("Try queries like: 'Who leads in points?', 'Lakers vs Celtics', 'LeBron stats this season'")

    # Issue 2: Low confidence (< 0.7)
    if parsed.confidence < 0.7:
        issues.append(f"Low parsing confidence ({parsed.confidence:.0%})")
        if not parsed.entities and parsed.intent in ["comparison", "player_stats", "team_stats"]:
            suggestions.append("Try including specific player or team names (e.g., 'LeBron James', 'Lakers')")

    # Issue 3: Comparison intent but wrong entity count
    if parsed.intent == "comparison":
        if len(parsed.entities) < 2:
            issues.append("Comparison query requires 2 entities")
            suggestions.append("Try: 'Compare LeBron James and Kevin Durant' or 'Lakers vs Celtics'")
        elif len(parsed.entities) > 2:
            issues.append(f"Too many entities for comparison ({len(parsed.entities)} found, expected 2)")
            suggestions.append("Specify exactly 2 players or teams to compare")

    # Issue 4: Leaders query without stat type
    if parsed.intent == "leaders" and not parsed.stat_types:
        issues.append("Leaders query should specify a statistic")
        suggestions.append("Try: 'Who leads in points?', 'Top 10 assists', 'Best rebounders'")

    # Issue 5: Entity-based query without entities
    if parsed.intent in ["player_stats", "team_stats", "game_context"] and not parsed.entities:
        entity_type = "player" if parsed.intent == "player_stats" else "team"
        issues.append(f"No {entity_type} recognized in query")
        suggestions.append(f"Try adding a {entity_type} name (e.g., 'LeBron James', 'Lakers', 'Warriors')")

    # Issue 6: Low entity confidence
    if parsed.entities:
        low_conf_entities = [e for e in parsed.entities if e.get("confidence", 1.0) < 0.8]
        if low_conf_entities:
            names = [e.get("name", "unknown") for e in low_conf_entities]
            issues.append(f"Uncertain entity recognition: {', '.join(names)}")
            suggestions.append("Try using full names or common abbreviations (e.g., 'LAL' for Lakers)")

    # Issue 7: Ambiguous stat types (multiple possible interpretations)
    if len(parsed.stat_types) > 5:
        issues.append(f"Query matched many stat types ({len(parsed.stat_types)}), results may be unfocused")
        suggestions.append("Try being more specific (e.g., 'points' instead of 'scoring stats')")

    # Populate ParsedQuery fields
    parsed.validation_issues = issues
    parsed.suggestions = suggestions

    # Log feedback if issues found
    if issues:
        logger.debug(f"Validation issues: {issues}")
        logger.debug(f"Suggestions: {suggestions}")


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

    # Phase 3.5: LLM fallback for low-confidence parses
    # If confidence < 0.5, attempt to refine parse using LLM
    if confidence < 0.5:
        from .llm_fallback import refine_parse

        logger.info(
            f"Low confidence ({confidence:.2f}), attempting LLM refinement..."
        )
        initial_parse = ParsedQuery(
            raw_query=query,
            intent=intent,
            entities=entities,
            stat_types=stat_types,
            time_range=time_range,
            modifiers=modifiers,
            confidence=confidence,
        )
        refined_parse = await refine_parse(initial_parse)

        # If refinement successful (confidence improved), use refined parse
        if refined_parse.confidence > confidence:
            logger.info(
                f"LLM refinement successful: {confidence:.2f} → {refined_parse.confidence:.2f}"
            )
            # Phase 5.3: Generate validation feedback before returning
            generate_validation_feedback(refined_parse)
            return refined_parse
        else:
            logger.debug("LLM refinement did not improve confidence, using original parse")

    # Create final parsed query
    result = ParsedQuery(
        raw_query=query,
        intent=intent,
        entities=entities,
        stat_types=stat_types,
        time_range=time_range,
        modifiers=modifiers,
        confidence=confidence,
    )

    # Phase 5.3 (NLQ Enhancement): Generate validation feedback
    generate_validation_feedback(result)

    return result


# ============================================================================
# VALIDATION (Phase 2.5: Enhanced with actionable hints)
# ============================================================================


@dataclass
class ValidationResult:
    """Result of query validation with actionable hints."""

    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    hints: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "hints": self.hints,
        }


def validate_parsed_query(parsed: ParsedQuery) -> ValidationResult:
    """
    Validate that parsed query has sufficient information.

    Phase 2.5: Enhanced with actionable error messages and hints.

    Args:
        parsed: Parsed query

    Returns:
        ValidationResult with specific errors, warnings, and hints
    """
    result = ValidationResult(valid=True)

    # Check confidence threshold
    if parsed.confidence < 0.3:
        result.valid = False
        result.errors.append(f"Query confidence too low: {parsed.confidence:.2f}")
        result.hints.append("Try being more specific about players, teams, or stats.")
        result.hints.append("Example: 'LeBron James points this season' instead of 'show stats'")

    # Check intent-specific requirements
    if parsed.intent == "comparison":
        if len(parsed.entities) < 2:
            result.valid = False
            result.errors.append("Comparison queries require at least 2 players or teams")
            result.hints.append("Example: 'Compare LeBron James and Kevin Durant'")
            result.hints.append("Example: 'Lakers vs Celtics'")
        elif len(parsed.entities) > 2:
            result.warnings.append(f"Found {len(parsed.entities)} entities, using first 2 for comparison")

    if parsed.intent in ["player_stats", "team_stats"]:
        if len(parsed.entities) < 1:
            result.valid = False
            result.errors.append(f"'{parsed.intent}' queries require at least 1 player or team name")
            if parsed.intent == "player_stats":
                result.hints.append("Example: 'LeBron James stats this season'")
                result.hints.append("Example: 'Show me Stephen Curry averages'")
            else:
                result.hints.append("Example: 'Lakers team stats'")
                result.hints.append("Example: 'Warriors offensive rating'")

    if parsed.intent == "leaders":
        if not parsed.stat_types:
            result.warnings.append("No specific stat mentioned, will use default (points)")
            result.hints.append("Try: 'Who leads the NBA in assists?'")
            result.hints.append("Or: 'Top 10 scorers this season'")

    if parsed.intent == "game_context":
        if len(parsed.entities) < 2:
            result.warnings.append("Game context works best with 2 teams")
            result.hints.append("Example: 'Lakers vs Celtics tonight'")
            result.hints.append("Example: 'Warriors Suns matchup'")

    # Phase 2.2: Validate new intent types
    if parsed.intent == "awards":
        if not any(kw in parsed.raw_query.lower() for kw in ["mvp", "dpoy", "roy", "all-nba", "all-star"]):
            result.warnings.append("Award type not clearly specified")
            result.hints.append("Example: 'Who won MVP in 2023?'")
            result.hints.append("Example: 'LeBron James awards'")

    if parsed.intent == "streaks":
        if not parsed.entities:
            result.warnings.append("Streak queries work best with a specific team or player")
            result.hints.append("Example: 'Lakers winning streak'")
            result.hints.append("Example: 'LeBron consecutive 30-point games'")

    if parsed.intent == "milestones":
        if not parsed.entities:
            result.warnings.append("Milestone queries usually need a player or team name")
            result.hints.append("Example: 'LeBron James career high'")
            result.hints.append("Example: 'Players close to 10,000 points'")

    # Check time range consistency (Phase 2.5)
    if parsed.time_range:
        if parsed.time_range.start_date and parsed.time_range.end_date:
            if parsed.time_range.start_date > parsed.time_range.end_date:
                result.valid = False
                result.errors.append("Start date is after end date")
                result.hints.append("Check your date range")

    # Check unknown intent
    if parsed.intent == "unknown":
        result.valid = False
        result.errors.append("Could not determine query intent")
        result.hints.append("Try one of these patterns:")
        result.hints.append("  - Leaders: 'Who leads the NBA in assists?'")
        result.hints.append("  - Comparison: 'Compare LeBron James and Kevin Durant'")
        result.hints.append("  - Stats: 'LeBron James stats this season'")
        result.hints.append("  - Game: 'Lakers vs Celtics tonight'")
        result.hints.append("  - Standings: 'Eastern Conference standings'")

    # Log results
    if not result.valid:
        logger.warning(f"Validation failed: {result.errors}")
    elif result.warnings:
        logger.info(f"Validation warnings: {result.warnings}")

    return result
