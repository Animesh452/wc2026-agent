import copy

import pytest

from results import KNOCKOUT_ROUNDS, bracket_order, build_results_view
from tools.world_cup import load_matches


@pytest.fixture(scope="module")
def view():
    return build_results_view(load_matches())


def teams(m: dict) -> set[str]:
    return {m["home"]["team"], m["away"]["team"]}


def test_round_sizes(view):
    assert [r["stage"] for r in view["rounds"]] == KNOCKOUT_ROUNDS
    assert [len(r["matches"]) for r in view["rounds"]] == [16, 8, 4, 2, 1]


def test_adjacent_winners_meet_in_next_round(view):
    rounds = view["rounds"]
    for earlier, later in zip(rounds, rounds[1:]):
        for i, m in enumerate(later["matches"]):
            feeders = earlier["matches"][2 * i: 2 * i + 2]
            assert {f["winner"] for f in feeders} == teams(m), (earlier["stage"], m["id"])
            # Home team's feeder comes first.
            assert feeders[0]["winner"] == m["home"]["team"]


def test_champion_and_runner_up(view):
    final = view["rounds"][-1]["matches"][0]
    assert view["champion"] == final["winner"] == "Spain"
    assert view["runner_up"] == "Argentina"


def test_third_place_is_separate(view):
    assert view["third_place"]["stage"] == "third_place"
    assert all(m["stage"] != "third_place" for r in view["rounds"] for m in r["matches"])


def test_groups(view):
    assert [g["group"] for g in view["groups"]] == list("ABCDEFGHIJKL")
    for g in view["groups"]:
        assert len(g["matches"]) == 6
        assert all(m["group"] == g["group"] for m in g["matches"])
        kickoffs = [m["kickoff_utc"] for m in g["matches"]]
        assert kickoffs == sorted(kickoffs)


def test_inconsistent_bracket_raises():
    matches = copy.deepcopy(load_matches())
    final = next(m for m in matches if m["stage"] == "final")
    final["home"]["team"] = "Wakanda"
    with pytest.raises(ValueError, match="Wakanda has no semifinal win"):
        bracket_order(matches)


def test_missing_final_raises():
    matches = [m for m in load_matches() if m["stage"] != "final"]
    with pytest.raises(ValueError, match="expected 1 final"):
        bracket_order(matches)


def test_unused_match_raises():
    matches = copy.deepcopy(load_matches())
    extra = copy.deepcopy(next(m for m in matches if m["stage"] == "round_of_16"))
    extra["id"] = "extra"
    extra["winner"] = "Somewhere FC"
    matches.append(extra)
    with pytest.raises(ValueError, match="not leading to the quarterfinal"):
        bracket_order(matches)
