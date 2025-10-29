"""
Comprehensive Name Variations for NBA Teams and Players

Provides exhaustive mappings of common variations, nicknames, abbreviations,
and alternate spellings for all NBA teams and players.

This file serves as the single source of truth for name resolution,
enabling users to query entities in the most natural way possible.
"""

from typing import Dict, Set

# ============================================================================
# TEAM NAME VARIATIONS
# ============================================================================
# Maps variation → official abbreviation
# All keys are lowercase for case-insensitive matching

TEAM_VARIATIONS: Dict[str, str] = {
    # Atlanta Hawks
    "hawks": "ATL",
    "atl": "ATL",
    "atlanta": "ATL",
    "atlanta hawks": "ATL",
    "the hawks": "ATL",

    # Boston Celtics
    "celtics": "BOS",
    "bos": "BOS",
    "boston": "BOS",
    "boston celtics": "BOS",
    "the celtics": "BOS",
    "c's": "BOS",
    "celts": "BOS",

    # Brooklyn Nets
    "nets": "BKN",
    "bkn": "BKN",
    "brooklyn": "BKN",
    "brooklyn nets": "BKN",
    "the nets": "BKN",
    "brk": "BKN",  # Alternate abbreviation

    # Charlotte Hornets
    "hornets": "CHA",
    "cha": "CHA",
    "charlotte": "CHA",
    "charlotte hornets": "CHA",
    "the hornets": "CHA",
    "cho": "CHA",  # Alternate abbreviation

    # Chicago Bulls
    "bulls": "CHI",
    "chi": "CHI",
    "chicago": "CHI",
    "chicago bulls": "CHI",
    "the bulls": "CHI",

    # Cleveland Cavaliers
    "cavaliers": "CLE",
    "cavs": "CLE",
    "cle": "CLE",
    "cleveland": "CLE",
    "cleveland cavaliers": "CLE",
    "the cavs": "CLE",
    "the cavaliers": "CLE",

    # Dallas Mavericks
    "mavericks": "DAL",
    "mavs": "DAL",
    "dal": "DAL",
    "dallas": "DAL",
    "dallas mavericks": "DAL",
    "the mavs": "DAL",
    "the mavericks": "DAL",

    # Denver Nuggets
    "nuggets": "DEN",
    "nugs": "DEN",
    "den": "DEN",
    "denver": "DEN",
    "denver nuggets": "DEN",
    "the nuggets": "DEN",

    # Detroit Pistons
    "pistons": "DET",
    "det": "DET",
    "detroit": "DET",
    "detroit pistons": "DET",
    "the pistons": "DET",

    # Golden State Warriors
    "warriors": "GSW",
    "dubs": "GSW",  # Very common nickname
    "gsw": "GSW",
    "gs": "GSW",
    "golden state": "GSW",
    "golden state warriors": "GSW",
    "the warriors": "GSW",
    "the dubs": "GSW",
    "w's": "GSW",
    "dubz": "GSW",  # Alternate spelling

    # Houston Rockets
    "rockets": "HOU",
    "hou": "HOU",
    "houston": "HOU",
    "houston rockets": "HOU",
    "the rockets": "HOU",

    # Indiana Pacers
    "pacers": "IND",
    "ind": "IND",
    "indiana": "IND",
    "indiana pacers": "IND",
    "the pacers": "IND",

    # LA Clippers
    "clippers": "LAC",
    "clips": "LAC",  # Very common
    "lac": "LAC",
    "la clippers": "LAC",
    "los angeles clippers": "LAC",
    "the clippers": "LAC",
    "the clips": "LAC",

    # Los Angeles Lakers
    "lakers": "LAL",
    "lal": "LAL",
    "la": "LAL",  # Often refers to Lakers
    "los angeles": "LAL",  # Often refers to Lakers
    "la lakers": "LAL",
    "los angeles lakers": "LAL",
    "the lakers": "LAL",
    "lake show": "LAL",  # Popular nickname
    "lakeshow": "LAL",

    # Memphis Grizzlies
    "grizzlies": "MEM",
    "grizz": "MEM",
    "mem": "MEM",
    "memphis": "MEM",
    "memphis grizzlies": "MEM",
    "the grizzlies": "MEM",
    "the grizz": "MEM",

    # Miami Heat
    "heat": "MIA",
    "mia": "MIA",
    "miami": "MIA",
    "miami heat": "MIA",
    "the heat": "MIA",

    # Milwaukee Bucks
    "bucks": "MIL",
    "mil": "MIL",
    "milwaukee": "MIL",
    "milwaukee bucks": "MIL",
    "the bucks": "MIL",

    # Minnesota Timberwolves
    "timberwolves": "MIN",
    "wolves": "MIN",
    "twolves": "MIN",
    "min": "MIN",
    "minnesota": "MIN",
    "minnesota timberwolves": "MIN",
    "the wolves": "MIN",
    "the timberwolves": "MIN",

    # New Orleans Pelicans
    "pelicans": "NOP",
    "pels": "NOP",
    "nop": "NOP",
    "no": "NOP",
    "new orleans": "NOP",
    "new orleans pelicans": "NOP",
    "the pelicans": "NOP",
    "the pels": "NOP",

    # New York Knicks
    "knicks": "NYK",
    "nyk": "NYK",
    "ny": "NYK",
    "new york": "NYK",
    "new york knicks": "NYK",
    "the knicks": "NYK",
    "knickerbockers": "NYK",
    "bockers": "NYK",

    # Oklahoma City Thunder
    "thunder": "OKC",
    "okc": "OKC",
    "oklahoma city": "OKC",
    "oklahoma city thunder": "OKC",
    "the thunder": "OKC",

    # Orlando Magic
    "magic": "ORL",
    "orl": "ORL",
    "orlando": "ORL",
    "orlando magic": "ORL",
    "the magic": "ORL",

    # Philadelphia 76ers
    "76ers": "PHI",
    "sixers": "PHI",  # Very common
    "phi": "PHI",
    "philadelphia": "PHI",
    "philadelphia 76ers": "PHI",
    "the sixers": "PHI",
    "the 76ers": "PHI",
    "philly": "PHI",
    "76'ers": "PHI",  # Alternate spelling

    # Phoenix Suns
    "suns": "PHX",
    "phx": "PHX",
    "phoenix": "PHX",
    "phoenix suns": "PHX",
    "the suns": "PHX",

    # Portland Trail Blazers
    "trail blazers": "POR",
    "blazers": "POR",
    "por": "POR",
    "portland": "POR",
    "portland trail blazers": "POR",
    "the blazers": "POR",
    "the trail blazers": "POR",
    "rip city": "POR",  # Popular nickname
    "ripcity": "POR",

    # Sacramento Kings
    "kings": "SAC",
    "sac": "SAC",
    "sacramento": "SAC",
    "sacramento kings": "SAC",
    "the kings": "SAC",

    # San Antonio Spurs
    "spurs": "SAS",
    "sas": "SAS",
    "sa": "SAS",
    "san antonio": "SAS",
    "san antonio spurs": "SAS",
    "the spurs": "SAS",

    # Toronto Raptors
    "raptors": "TOR",
    "raps": "TOR",
    "tor": "TOR",
    "toronto": "TOR",
    "toronto raptors": "TOR",
    "the raptors": "TOR",
    "the raps": "TOR",

    # Utah Jazz
    "jazz": "UTA",
    "uta": "UTA",
    "utah": "UTA",
    "utah jazz": "UTA",
    "the jazz": "UTA",

    # Washington Wizards
    "wizards": "WAS",
    "wiz": "WAS",
    "was": "WAS",
    "washington": "WAS",
    "washington wizards": "WAS",
    "the wizards": "WAS",
    "the wiz": "WAS",

    # ========================================================================
    # HISTORICAL TEAMS (relocated/renamed)
    # ========================================================================

    # Seattle SuperSonics (now Oklahoma City Thunder)
    "supersonics": "OKC",
    "sonics": "OKC",
    "seattle": "OKC",
    "seattle supersonics": "OKC",
    "the sonics": "OKC",

    # New Jersey Nets (now Brooklyn Nets)
    "new jersey": "BKN",
    "new jersey nets": "BKN",
    "nj": "BKN",
    "njn": "BKN",

    # Charlotte Bobcats (now Charlotte Hornets)
    "bobcats": "CHA",
    "charlotte bobcats": "CHA",
    "the bobcats": "CHA",

    # New Orleans Hornets (now New Orleans Pelicans)
    "new orleans hornets": "NOP",
    "noh": "NOP",

    # Vancouver Grizzlies (now Memphis Grizzlies)
    "vancouver": "MEM",
    "vancouver grizzlies": "MEM",

    # Washington Bullets (now Washington Wizards)
    "bullets": "WAS",
    "washington bullets": "WAS",
    "the bullets": "WAS",
}

# ============================================================================
# PLAYER NICKNAME PATTERNS
# ============================================================================
# Maps nickname → search pattern (lowercase)
# These are famous nicknames that should resolve to specific players

PLAYER_NICKNAMES: Dict[str, str] = {
    # Active Stars
    "king james": "lebron james",
    "the king": "lebron james",
    "bron": "lebron james",
    "greek freak": "giannis antetokounmpo",
    "the greek freak": "giannis antetokounmpo",
    "giannis": "giannis antetokounmpo",
    "the beard": "james harden",
    "the brodie": "russell westbrook",
    "russ": "russell westbrook",
    "westbrook": "russell westbrook",
    "the process": "joel embiid",
    "jojo": "joel embiid",
    "the klaw": "kawhi leonard",
    "the claw": "kawhi leonard",
    "kawhi": "kawhi leonard",
    "the joker": "nikola jokic",
    "joker": "nikola jokic",
    "dame": "damian lillard",
    "dame time": "damian lillard",
    "dame dolla": "damian lillard",
    "chef curry": "stephen curry",
    "steph": "stephen curry",
    "chef": "stephen curry",
    "the baby faced assassin": "stephen curry",
    "kd": "kevin durant",
    "the slim reaper": "kevin durant",
    "durantula": "kevin durant",
    "ad": "anthony davis",
    "the brow": "anthony davis",
    "pg13": "paul george",
    "pg-13": "paul george",
    "playoff p": "paul george",
    "cp3": "chris paul",
    "the point god": "chris paul",
    "luka": "luka doncic",
    "luka magic": "luka doncic",
    "the unicorn": "kristaps porzingis",
    "zingis": "kristaps porzingis",
    "ja": "ja morant",
    "the flash": "dwyane wade",
    "dwade": "dwyane wade",
    "d wade": "dwyane wade",
    "flash": "dwyane wade",
    "boogie": "demarcus cousins",
    "boogie cousins": "demarcus cousins",
    "spida": "donovan mitchell",
    "the spida": "donovan mitchell",
    "dame lillard": "damian lillard",
    "kyrie": "kyrie irving",
    "uncle drew": "kyrie irving",
    "the truth": "paul pierce",
    "the answer": "allen iverson",
    "ai": "allen iverson",
    "the black mamba": "kobe bryant",
    "mamba": "kobe bryant",
    "kb24": "kobe bryant",
    "bean": "kobe bryant",
    "the diesel": "shaquille o'neal",
    "shaq": "shaquille o'neal",
    "superman": "dwight howard",
    "air jordan": "michael jordan",
    "mj": "michael jordan",
    "his airness": "michael jordan",
    "the dream": "hakeem olajuwon",
    "the admiral": "david robinson",
    "the big fundamental": "tim duncan",
    "timmy": "tim duncan",
    "the mailman": "karl malone",
    "the glove": "gary payton",
    "magic": "magic johnson",
    "big o": "oscar robertson",
    "dr j": "julius erving",
    "the doctor": "julius erving",
    "pistol pete": "pete maravich",
    "penny": "anfernee hardaway",

    # Common first name variations
    "lebron": "lebron james",
    "kawhi": "kawhi leonard",
    "giannis": "giannis antetokounmpo",
    "luka": "luka doncic",
    "nikola": "nikola jokic",  # May match multiple, fuzzy will disambiguate
    "damian": "damian lillard",
    "stephen": "stephen curry",
    "kevin": "kevin durant",
    "joel": "joel embiid",
    "james": "james harden",  # May match multiple
    "russell": "russell westbrook",
    "anthony": "anthony davis",
    "paul": "paul george",  # May match multiple
}

# ============================================================================
# ALTERNATE SPELLINGS (International Names)
# ============================================================================
# Maps common misspellings/ASCII versions → correct Unicode name

ALTERNATE_SPELLINGS: Dict[str, str] = {
    # Players with diacritical marks
    "luka doncic": "luka dončić",
    "doncic": "dončić",
    "nikola jokic": "nikola jokić",
    "jokic": "jokić",
    "bogdan bogdanovic": "bogdan bogdanović",
    "bogdanovic": "bogdanović",
    "bojan bogdanovic": "bojan bogdanović",
    "nikola vucevic": "nikola vučević",
    "vucevic": "vučević",
    "jusuf nurkic": "jusuf nurkić",
    "nurkic": "nurkić",
    "nikola mirotic": "nikola mirotić",
    "mirotic": "mirotić",
    "dario saric": "dario šarić",
    "saric": "šarić",
    "boban marjanovic": "boban marjanović",
    "marjanovic": "marjanović",
    "ivica zubac": "ivica zubac",
    "zubac": "zubac",

    # Common misspellings
    "giannis": "giannis antetokounmpo",
    "antentokounmpo": "antetokounmpo",
    "antentokoumpo": "antetokounmpo",
}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def get_team_abbreviation(query: str) -> str:
    """
    Get official team abbreviation from any variation.

    Args:
        query: Any team name variation (case-insensitive)

    Returns:
        Official abbreviation (e.g., "GSW") or None if not found

    Examples:
        >>> get_team_abbreviation("Dubs")
        'GSW'
        >>> get_team_abbreviation("Lake Show")
        'LAL'
        >>> get_team_abbreviation("Sixers")
        'PHI'
    """
    return TEAM_VARIATIONS.get(query.lower())


def get_player_nickname_search(query: str) -> str:
    """
    Get searchable player name from nickname.

    Args:
        query: Player nickname (case-insensitive)

    Returns:
        Full name to search for, or original query if not a known nickname

    Examples:
        >>> get_player_nickname_search("King James")
        'lebron james'
        >>> get_player_nickname_search("Greek Freak")
        'giannis antetokounmpo'
    """
    return PLAYER_NICKNAMES.get(query.lower(), query.lower())


def get_alternate_spelling(query: str) -> str:
    """
    Get correct spelling for common misspellings/ASCII versions.

    Args:
        query: Possibly misspelled name

    Returns:
        Correct spelling with diacritical marks, or original if not found

    Examples:
        >>> get_alternate_spelling("Luka Doncic")
        'luka dončić'
        >>> get_alternate_spelling("Nikola Jokic")
        'nikola jokić'
    """
    return ALTERNATE_SPELLINGS.get(query.lower(), query.lower())


def get_all_team_variations() -> Set[str]:
    """Get set of all known team name variations."""
    return set(TEAM_VARIATIONS.keys())


def get_all_player_nicknames() -> Set[str]:
    """Get set of all known player nicknames."""
    return set(PLAYER_NICKNAMES.keys())


# ============================================================================
# STATISTICS
# ============================================================================

def get_variations_stats() -> Dict[str, int]:
    """Get statistics about variations coverage."""
    return {
        "total_team_variations": len(TEAM_VARIATIONS),
        "unique_teams_covered": len(set(TEAM_VARIATIONS.values())),
        "total_player_nicknames": len(PLAYER_NICKNAMES),
        "total_alternate_spellings": len(ALTERNATE_SPELLINGS),
    }
