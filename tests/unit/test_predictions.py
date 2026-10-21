import asyncio
import copy
import threading
from types import SimpleNamespace

import pytest

import tools.predictions as predictions

# Two pending predictions with scores already set in the DB, so scoring uses
# the DB fallback: Brazil 2-1 Japan is exact (3 points), Spain 1-0 Argentina
# against an actual 2-0 is the right winner (1 point).
PENDING = [
    {
        "match_id": "m1", "home_team": "Brazil", "away_team": "Japan",
        "predicted_home_score": 2, "predicted_away_score": 1,
        "actual_home_score": 2, "actual_away_score": 1,
    },
    {
        "match_id": "m2", "home_team": "Spain", "away_team": "Argentina",
        "predicted_home_score": 1, "predicted_away_score": 0,
        "actual_home_score": 2, "actual_away_score": 0,
    },
]


def ok():
    return SimpleNamespace(isError=False, content=[])


def failure(message: str):
    return SimpleNamespace(isError=True, content=[SimpleNamespace(text=message)])


class FakeSession:
    """Stands in for the MCP session: find succeeds, update-many returns queued results."""

    def __init__(self, update_results):
        self.update_results = list(update_results)
        self.calls = []

    async def call_tool(self, name, args):
        self.calls.append(name)
        if name == "find":
            return ok()
        if name == "update-many":
            return self.update_results.pop(0)
        raise AssertionError(f"unexpected MCP call {name}")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(predictions, "extract_mcp_data", lambda result: copy.deepcopy(PENDING))
    monkeypatch.setattr(predictions, "fetch_match_result", lambda match_id: None)


def test_failed_write_is_not_counted():
    session = FakeSession([failure("write conflict"), ok()])
    result = asyncio.run(predictions.score_predictions(session, "u1"))

    assert session.calls == ["find", "update-many", "update-many"]
    assert result["updated"] == 1
    assert result["total_points_earned"] == 1
    assert [b["match"] for b in result["breakdown"]] == ["Spain vs Argentina"]
    assert result["failed"] == ["Brazil vs Japan: write conflict"]


def test_all_writes_succeed():
    result = asyncio.run(predictions.score_predictions(FakeSession([ok(), ok()]), "u1"))

    assert result["updated"] == 2
    assert result["total_points_earned"] == 4
    assert [(b["match"], b["points"]) for b in result["breakdown"]] == [
        ("Brazil vs Japan", 3),
        ("Spain vs Argentina", 1),
    ]
    assert "failed" not in result


def test_fetch_match_result_runs_off_the_event_loop_thread(monkeypatch):
    threads = []

    def fake_fetch(match_id):
        threads.append(threading.current_thread())
        return None

    monkeypatch.setattr(predictions, "fetch_match_result", fake_fetch)
    asyncio.run(predictions.score_predictions(FakeSession([ok(), ok()]), "u1"))

    assert len(threads) == 2
    assert all(t is not threading.current_thread() for t in threads)
