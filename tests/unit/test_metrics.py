import pytest

from tests.eval.metrics import (
    abstention,
    aggregate,
    hit_rate_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

AT_K_FUNCS = [hit_rate_at_k, recall_at_k, precision_at_k]


# --- Basic ranking: retrieved [x, a, y, b, z], relevant [a, b, c] ---

BASIC_RETRIEVED = ["x", "a", "y", "b", "z"]
BASIC_RELEVANT = ["a", "b", "c"]


@pytest.mark.parametrize("k, expected", [(1, 0.0), (3, 1.0), (5, 1.0)])
def test_basic_hit_rate(k, expected):
    assert hit_rate_at_k(BASIC_RETRIEVED, BASIC_RELEVANT, k) == expected


@pytest.mark.parametrize("k, expected", [(1, 0.0), (3, 1 / 3), (5, 2 / 3)])
def test_basic_recall(k, expected):
    assert recall_at_k(BASIC_RETRIEVED, BASIC_RELEVANT, k) == pytest.approx(expected)


@pytest.mark.parametrize("k, expected", [(1, 0.0), (3, 1 / 3), (5, 2 / 5)])
def test_basic_precision(k, expected):
    assert precision_at_k(BASIC_RETRIEVED, BASIC_RELEVANT, k) == pytest.approx(expected)


def test_basic_reciprocal_rank():
    assert reciprocal_rank(BASIC_RETRIEVED, BASIC_RELEVANT) == pytest.approx(1 / 2)


def test_perfect_top_1():
    retrieved, relevant = ["a", "x"], ["a"]
    assert hit_rate_at_k(retrieved, relevant, 1) == 1.0
    assert recall_at_k(retrieved, relevant, 1) == 1.0
    assert precision_at_k(retrieved, relevant, 1) == 1.0
    assert reciprocal_rank(retrieved, relevant) == 1.0


# --- None placeholders ---

def test_none_never_matches():
    retrieved, relevant = [None, "a"], ["a"]
    assert hit_rate_at_k(retrieved, relevant, 1) == 0.0
    assert precision_at_k(retrieved, relevant, 2) == pytest.approx(1 / 2)
    assert reciprocal_rank(retrieved, relevant) == pytest.approx(1 / 2)


def test_all_none():
    retrieved, relevant = [None, None], ["a"]
    assert hit_rate_at_k(retrieved, relevant, 2) == 0.0
    assert recall_at_k(retrieved, relevant, 2) == 0.0
    assert precision_at_k(retrieved, relevant, 2) == 0.0
    assert reciprocal_rank(retrieved, relevant) == 0.0


# --- Duplicates count once ---

def test_duplicates_count_once():
    retrieved, relevant = ["a", "a", "a"], ["a", "b"]
    assert recall_at_k(retrieved, relevant, 3) == pytest.approx(1 / 2)
    assert precision_at_k(retrieved, relevant, 3) == pytest.approx(1 / 3)
    assert hit_rate_at_k(retrieved, relevant, 3) == 1.0


# --- Precision denominator is always k ---

def test_precision_denominator_is_k_when_fewer_retrieved():
    retrieved, relevant = ["a"], ["a"]
    assert precision_at_k(retrieved, relevant, 5) == pytest.approx(1 / 5)
    assert recall_at_k(retrieved, relevant, 5) == 1.0


def test_empty_retrieved():
    retrieved, relevant = [], ["a"]
    assert hit_rate_at_k(retrieved, relevant, 3) == 0.0
    assert recall_at_k(retrieved, relevant, 3) == 0.0
    assert precision_at_k(retrieved, relevant, 3) == 0.0
    assert reciprocal_rank(retrieved, relevant) == 0.0


# --- Reciprocal rank uses the full list ---

def test_reciprocal_rank_uses_full_list():
    retrieved = ["x", "y", "z", "w", "v", "a"]
    assert reciprocal_rank(retrieved, ["a"]) == pytest.approx(1 / 6)


# --- Validation ---

@pytest.mark.parametrize("func", AT_K_FUNCS)
@pytest.mark.parametrize("k", [0, -1])
def test_invalid_k_raises(func, k):
    with pytest.raises(ValueError):
        func(["a"], ["a"], k)


@pytest.mark.parametrize("func", AT_K_FUNCS)
def test_empty_relevant_raises_at_k(func):
    with pytest.raises(ValueError):
        func(["a"], [], 1)


def test_empty_relevant_raises_reciprocal_rank():
    with pytest.raises(ValueError):
        reciprocal_rank(["a"], [])


# --- Aggregation ---

def test_aggregate():
    cases = [
        {"retrieved": ["a", "x"], "relevant": ["a"]},
        {"retrieved": ["x", "b"], "relevant": ["b", "c"]},
        {"retrieved": ["a"], "relevant": []},
    ]
    result = aggregate(cases, [1, 2])
    assert result == {
        "hit_rate@1": pytest.approx(0.5),
        "recall@1": pytest.approx(0.5),
        "precision@1": pytest.approx(0.5),
        "hit_rate@2": pytest.approx(1.0),
        "recall@2": pytest.approx(0.75),
        "precision@2": pytest.approx(0.5),
        "mrr": pytest.approx(0.75),
        "abstention_rate": 0.0,
        "n_evaluated": 2,
        "n_skipped": 1,
    }


def test_aggregate_all_skipped():
    cases = [
        {"retrieved": ["a"], "relevant": []},
        {"retrieved": [], "relevant": []},
    ]
    result = aggregate(cases, [1, 3])
    assert result == {
        "hit_rate@1": None,
        "recall@1": None,
        "precision@1": None,
        "hit_rate@3": None,
        "recall@3": None,
        "precision@3": None,
        "mrr": None,
        "abstention_rate": pytest.approx(0.5),
        "n_evaluated": 0,
        "n_skipped": 2,
    }


def test_aggregate_invalid_k_raises_even_if_all_skipped():
    with pytest.raises(ValueError):
        aggregate([{"retrieved": ["a"], "relevant": []}], [0])


# --- Abstention (out-of-scope queries) ---

@pytest.mark.parametrize(
    "retrieved, expected",
    [
        ([], 1.0),
        ([None, None], 1.0),
        (["a"], 0.0),
        ([None, "a"], 0.0),
    ],
)
def test_abstention(retrieved, expected):
    assert abstention(retrieved, []) == expected


def test_abstention_raises_for_in_scope_query():
    with pytest.raises(ValueError):
        abstention(["a"], ["a"])


def test_aggregate_abstention_rate_none_without_out_of_scope():
    cases = [{"retrieved": ["a"], "relevant": ["a"]}]
    assert aggregate(cases, [1])["abstention_rate"] is None


def test_aggregate_abstention_rate():
    cases = [
        {"retrieved": ["a"], "relevant": ["a"]},
        {"retrieved": ["x"], "relevant": []},
        {"retrieved": [None], "relevant": []},
    ]
    result = aggregate(cases, [1])
    assert result["abstention_rate"] == pytest.approx(0.5)
    assert result["n_skipped"] == 2
