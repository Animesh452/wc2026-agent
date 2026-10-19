"""Pure retrieval metric functions for the RAG eval.

retrieved is a ranked list of document stems, best-first, which may contain
None placeholders for results that couldn't be mapped to a stem. relevant is
the list of stems judged relevant for the query.

- None never counts as a match.
- A stem appearing more than once in retrieved counts once.
- "Top k" is positional (retrieved[:k]), so placeholders and duplicates still
  occupy rank slots.
- precision@k always divides by k, even if fewer than k docs were retrieved.
"""


def _validate_k(k: int) -> None:
    if k < 1:
        raise ValueError(f"k must be at least 1, got {k}")


def _validate_relevant(relevant: list[str]) -> None:
    if not relevant:
        raise ValueError("relevant must not be empty")


def _matches_at_k(retrieved: list[str | None], relevant: list[str], k: int) -> int:
    _validate_k(k)
    _validate_relevant(relevant)
    top_k = set(retrieved[:k]) - {None}
    return len(top_k & set(relevant))


def hit_rate_at_k(retrieved: list[str | None], relevant: list[str], k: int) -> float:
    return 1.0 if _matches_at_k(retrieved, relevant, k) > 0 else 0.0


def recall_at_k(retrieved: list[str | None], relevant: list[str], k: int) -> float:
    return _matches_at_k(retrieved, relevant, k) / len(set(relevant))


def precision_at_k(retrieved: list[str | None], relevant: list[str], k: int) -> float:
    return _matches_at_k(retrieved, relevant, k) / k


def reciprocal_rank(retrieved: list[str | None], relevant: list[str]) -> float:
    _validate_relevant(relevant)
    relevant_set = set(relevant)
    for rank, stem in enumerate(retrieved, start=1):
        if stem is not None and stem in relevant_set:
            return 1.0 / rank
    return 0.0


def abstention(retrieved: list[str | None], relevant: list[str]) -> float:
    """1.0 if an out-of-scope query retrieved no non-None results, else 0.0."""
    if relevant:
        raise ValueError("abstention only applies to out-of-scope queries (empty relevant)")
    return 0.0 if any(stem is not None for stem in retrieved) else 1.0


def aggregate(cases: list[dict], ks: list[int]) -> dict:
    """Average per-query metrics over cases.

    Each case is {"retrieved": [...], "relevant": [...]}. Cases with empty
    relevant (out-of-scope queries) are skipped from the retrieval metrics and
    counted in n_skipped; abstention_rate is averaged over those cases only.
    If no cases are evaluated, every retrieval metric is None; if there are no
    out-of-scope cases, abstention_rate is None.
    """
    for k in ks:
        _validate_k(k)

    evaluated = [c for c in cases if c["relevant"]]
    out_of_scope = [c for c in cases if not c["relevant"]]
    n_evaluated = len(evaluated)
    n_skipped = len(out_of_scope)

    def mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    result = {}
    for k in ks:
        result[f"hit_rate@{k}"] = mean([hit_rate_at_k(c["retrieved"], c["relevant"], k) for c in evaluated])
        result[f"recall@{k}"] = mean([recall_at_k(c["retrieved"], c["relevant"], k) for c in evaluated])
        result[f"precision@{k}"] = mean([precision_at_k(c["retrieved"], c["relevant"], k) for c in evaluated])
    result["mrr"] = mean([reciprocal_rank(c["retrieved"], c["relevant"]) for c in evaluated])
    result["abstention_rate"] = mean([abstention(c["retrieved"], c["relevant"]) for c in out_of_scope])
    result["n_evaluated"] = n_evaluated
    result["n_skipped"] = n_skipped
    return result
