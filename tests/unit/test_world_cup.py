import copy
import json
from collections import Counter
from pathlib import Path

import pytest

from scripts.snapshot_world_cup import parse_event
from tools.espn import normalize_team
from tools.world_cup import (
    filter_matches,
    format_match,
    get_world_cup_results,
    load_matches,
    resolve_team,
    team_summary,
)

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "espn_scoreboard_sample.json"
EVENTS = {e["name"]: e for e in json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["events"]}
MATCHES = [parse_event(e) for e in EVENTS.values()]


def parsed(name: str) -> dict:
    return parse_event(EVENTS[name])


# --- Parsing ESPN events ---

def test_parse_group_draw():
    m = parsed("Cape Verde at Spain")
    assert m["stage"] == "group"
    assert m["group"] == "H"
    assert m["home"] == {"team": "Spain", "score": 0}
    assert m["away"] == {"team": "Cape Verde", "score": 0}
    assert m["decided"] == "regulation"
    assert m["winner"] is None
    assert m["venue"] == "Mercedes-Benz Stadium"
    assert m["city"] == "Atlanta, Georgia"
    assert m["date"] == "2026-06-15"


def test_parse_late_kickoff_uses_eastern_date():
    m = parsed("New Zealand at Iran")
    assert m["kickoff_utc"] == "2026-06-16T01:00Z"
    assert m["date"] == "2026-06-15"


def test_parse_knockout_regulation_win():
    m = parsed("Norway at Ivory Coast")
    assert m["stage"] == "round_of_32"
    assert m["group"] is None
    assert m["home"] == {"team": "Ivory Coast", "score": 1}
    assert m["away"] == {"team": "Norway", "score": 2}
    assert m["decided"] == "regulation"
    assert m["winner"] == "Norway"


def test_parse_penalty_shootout_winner():
    m = parsed("Paraguay at Germany")
    assert m["home"] == {"team": "Germany", "score": 1, "penalties": 3}
    assert m["away"] == {"team": "Paraguay", "score": 1, "penalties": 4}
    assert m["decided"] == "penalties"
    assert m["winner"] == "Paraguay"


def test_parse_final_after_extra_time():
    m = parsed("Argentina at Spain")
    assert m["stage"] == "final"
    assert m["decided"] == "extra_time"
    assert m["winner"] == "Spain"
    assert m["venue"] == "MetLife Stadium"


def test_parse_unknown_stage_raises():
    event = copy.deepcopy(EVENTS["Argentina at Spain"])
    event["season"]["slug"] = "playoff"
    with pytest.raises(ValueError, match="unknown stage"):
        parse_event(event)


def test_parse_incomplete_match_raises():
    event = copy.deepcopy(EVENTS["Argentina at Spain"])
    event["competitions"][0]["status"]["type"]["completed"] = False
    with pytest.raises(ValueError, match="not completed"):
        parse_event(event)


def test_parse_winner_disagreeing_with_espn_raises():
    event = copy.deepcopy(EVENTS["Paraguay at Germany"])
    for competitor in event["competitions"][0]["competitors"]:
        competitor["winner"] = not competitor["winner"]
    with pytest.raises(ValueError, match="disagrees"):
        parse_event(event)


def test_parse_knockout_draw_without_shootout_raises():
    event = copy.deepcopy(EVENTS["Norway at Ivory Coast"])
    for competitor in event["competitions"][0]["competitors"]:
        competitor["score"] = "2"
        competitor["winner"] = False
    with pytest.raises(ValueError, match="without a winner"):
        parse_event(event)


# --- Formatting ---

def test_format_match_lines():
    assert format_match(parsed("Cape Verde at Spain")) == (
        "2026-06-15 | Group H | Spain 0-0 Cape Verde (draw) | Mercedes-Benz Stadium, Atlanta, Georgia"
    )
    assert format_match(parsed("Norway at Ivory Coast")) == (
        "2026-06-30 | Round of 32 | Ivory Coast 1-2 Norway | AT&T Stadium, Arlington, Texas"
    )
    assert format_match(parsed("Paraguay at Germany")) == (
        "2026-06-29 | Round of 32 | Germany 1-1 Paraguay (Paraguay won 4-3 on penalties)"
        " | Gillette Stadium, Foxborough, Massachusetts"
    )
    assert format_match(parsed("Argentina at Spain")) == (
        "2026-07-19 | Final | Spain 1-0 Argentina (after extra time) | MetLife Stadium, East Rutherford, New Jersey"
    )


# --- Team resolution and filtering ---

@pytest.mark.parametrize(
    "query, expected",
    [
        ("Spain", "Spain"),
        ("  spain ", "Spain"),
        ("IRAN", "Iran"),
        ("ivory coast", "Ivory Coast"),
        ("Côte d'Ivoire", "Ivory Coast"),
        ("cote d'ivoire", "Ivory Coast"),
        ("Italy", None),
    ],
)
def test_resolve_team(query, expected):
    assert resolve_team(MATCHES, query) == expected


def test_resolve_team_ignores_accents():
    matches = [{"home": {"team": "Türkiye"}, "away": {"team": "Curaçao"}}]
    assert resolve_team(matches, "turkiye") == "Türkiye"
    assert resolve_team(matches, "Turkey") == "Türkiye"
    assert resolve_team(matches, "curacao") == "Curaçao"


def ids(matches: list[dict]) -> list[str]:
    return sorted(f"{m['home']['team']} v {m['away']['team']}" for m in matches)


def test_filter_by_team():
    assert ids(filter_matches(MATCHES, team="Spain")) == ["Spain v Argentina", "Spain v Cape Verde"]


def test_filter_by_stage():
    assert ids(filter_matches(MATCHES, stage="group")) == ["Iran v New Zealand", "Spain v Cape Verde"]
    assert ids(filter_matches(MATCHES, stage="final")) == ["Spain v Argentina"]
    assert ids(filter_matches(MATCHES, stage="round_of_16")) == []


def test_filter_knockout():
    assert ids(filter_matches(MATCHES, stage="knockout")) == [
        "Germany v Paraguay", "Ivory Coast v Norway", "Spain v Argentina",
    ]


def test_filter_team_and_stage():
    assert ids(filter_matches(MATCHES, team="Spain", stage="knockout")) == ["Spain v Argentina"]


def test_filter_no_filters_returns_everything():
    assert len(filter_matches(MATCHES)) == len(MATCHES)


def test_invalid_stage_returns_error_string():
    result = get_world_cup_results(stage="semis")
    assert isinstance(result, str)
    assert result.startswith("Invalid stage 'semis'")


# --- Team summary ---

@pytest.mark.parametrize(
    "team, expected",
    [
        ("Spain", "Spain: champion, beat Argentina in the final"),
        ("Argentina", "Argentina: runner-up, lost to Spain in the final"),
        ("Ivory Coast", "Ivory Coast: eliminated in the round of 32 by Norway"),
        ("Cape Verde", "Cape Verde: eliminated in the group stage"),
        # The fixture stops after Norway's round-of-32 win, so there's no outcome to report.
        ("Norway", None),
    ],
)
def test_team_summary(team, expected):
    assert team_summary(MATCHES, team) == expected


def make_match(stage, home, away, winner, kickoff):
    return {
        "stage": stage,
        "home": {"team": home},
        "away": {"team": away},
        "winner": winner,
        "kickoff_utc": kickoff,
    }


def test_team_summary_third_place_match():
    matches = [
        make_match("semifinal", "A", "B", "B", "2026-07-14T19:00Z"),
        make_match("third_place", "A", "C", "A", "2026-07-18T21:00Z"),
    ]
    assert team_summary(matches, "A") == "A: third place, beat C in the third-place match"
    assert team_summary(matches, "C") == "C: fourth place, lost to A in the third-place match"


# --- Committed snapshot (reads data/world_cup_2026.json, no network) ---

def test_snapshot_has_every_match():
    matches = load_matches()
    assert len(matches) == 104
    assert Counter(m["stage"] for m in matches) == {
        "group": 72,
        "round_of_32": 16,
        "round_of_16": 8,
        "quarterfinal": 4,
        "semifinal": 2,
        "third_place": 1,
        "final": 1,
    }


def test_snapshot_knockout_matches_have_winners():
    for m in load_matches():
        if m["stage"] != "group":
            assert m["winner"] in (m["home"]["team"], m["away"]["team"]), m["id"]


def test_snapshot_team_names_normalize_to_themselves():
    teams = {m[side]["team"] for m in load_matches() for side in ("home", "away")}
    assert len(teams) == 48
    for team in teams:
        assert normalize_team(team) == team


@pytest.mark.parametrize(
    "alias",
    [
        "usa", "turkey", "czech republic", "korea", "korea republic", "ivory coast",
        "côte d'ivoire", "cote d'ivoire", "dr congo", "congo dr",
        "democratic republic of the congo", "bosnia", "bosnia and herzegovina",
        "cabo verde", "holland", "ir iran",
    ],
)
def test_aliases_resolve_to_snapshot_teams(alias):
    assert resolve_team(load_matches(), alias) is not None


def test_unknown_team_lists_tournament_teams():
    result = get_world_cup_results(team="Wakanda")
    assert result["count"] == 0
    assert result["matches"] == []
    assert result["note"].startswith("Wakanda did not play at World Cup 2026")
    assert "Spain" in result["note"]
