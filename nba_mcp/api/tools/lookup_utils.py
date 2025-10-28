from nba_api.stats.static import players

def get_player_id(player_name: str):
    """Lookup a player's unique NBA ID by their full name (to avoid circular imports between server and client)."""
    # Normalize the input name for case-insensitive comparison
    target_name = player_name.strip().lower()
    try:
        player_list = players.get_players()
    except Exception:
        # If static data retrieval fails, return None
        return None
    for player in player_list:
        if player.get("full_name", "").strip().lower() == target_name:
            return player.get("id")
    return None
