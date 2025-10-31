from types import SimpleNamespace

from nba_mcp.api.tools import live_nba_endpoints as live_tools


def _fake_game_summary(game_id: str, home_abbr: str, away_abbr: str) -> dict:
    return {
        "gameId": game_id,
        "gameStatusText": "Final",
        "period": 4,
        "gameClock": "0:00",
        "homeTeam": {"teamTricode": home_abbr, "teamName": "Home Team", "score": 100},
        "awayTeam": {"teamTricode": away_abbr, "teamName": "Away Team", "score": 98},
    }


def _fake_espn_payload(home_abbr: str, away_abbr: str) -> dict:
    return {
        "events": [
            {
                "id": "401234567",
                "competitions": [
                    {
                        "competitors": [
                            {
                                "homeAway": "home",
                                "team": {"abbreviation": home_abbr},
                                "moneyline": "-145",
                            },
                            {
                                "homeAway": "away",
                                "team": {"abbreviation": away_abbr},
                                "moneyline": "+125",
                            },
                        ],
                        "odds": [
                            {
                                "provider": {"name": "ESPN BET"},
                                "details": f"{home_abbr} -3.5",
                                "spread": -3.5,
                                "overUnder": 226.5,
                                "lastUpdated": "2025-01-01T12:00Z",
                            }
                        ],
                    }
                ],
            }
        ]
    }


def test_fetch_live_scores_injects_espn_odds(monkeypatch):
    sample_games = [_fake_game_summary("001", "BOS", "LAL")]

    class FakeScoreBoard:
        def __init__(self, *args, **kwargs):
            self.games = SimpleNamespace(get_dict=lambda: sample_games)
            self.score_board_date = "2025-01-01"

    def fake_fetch_game_live_data(*args, **kwargs):
        return {
            "gameId": kwargs.get("game_id"),
            "boxScore": {},
            "playByPlay": [],
            "odds": {},
        }

    monkeypatch.setattr(live_tools, "ScoreBoard", FakeScoreBoard)
    monkeypatch.setattr(live_tools, "fetch_game_live_data", fake_fetch_game_live_data)
    monkeypatch.setattr(
        live_tools, "_fetch_espn_scoreboard", lambda *a, **k: _fake_espn_payload("BOS", "LAL")
    )

    payload = live_tools.fetch_live_boxsc_odds_playbyplaydelayed_livescores()

    assert payload["date"] == "2025-01-01"
    assert len(payload["games"]) == 1
    game = payload["games"][0]
    assert game["odds"]["provider"] == "ESPN BET"
    assert game["odds"]["spread"] == -3.5
    assert game["scoreBoardSummary"]["homeTeam"]["teamTricode"] == "BOS"


def test_fetch_live_scores_handles_missing_odds(monkeypatch):
    sample_games = [_fake_game_summary("002", "NYK", "MIA")]

    class FakeScoreBoard:
        def __init__(self, *args, **kwargs):
            self.games = SimpleNamespace(get_dict=lambda: sample_games)
            self.score_board_date = "2025-02-02"

    def fake_fetch_game_live_data(*args, **kwargs):
        return {
            "gameId": kwargs.get("game_id"),
            "boxScore": {},
            "playByPlay": [],
            "odds": {},
        }

    monkeypatch.setattr(live_tools, "ScoreBoard", FakeScoreBoard)
    monkeypatch.setattr(live_tools, "fetch_game_live_data", fake_fetch_game_live_data)
    monkeypatch.setattr(live_tools, "_fetch_espn_scoreboard", lambda *a, **k: {"events": []})

    payload = live_tools.fetch_live_boxsc_odds_playbyplaydelayed_livescores()

    assert payload["date"] == "2025-02-02"
    assert len(payload["games"]) == 1
    assert payload["games"][0]["odds"] == {}
