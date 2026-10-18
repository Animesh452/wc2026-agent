"""RAG retrieval eval runner.

Run from the repo root:
    python -m tests.eval.rag_eval [--limit N]

Calls retrieve_venue_docs (the same function search_venue_info uses) for each
query in the dataset and writes one self-contained line per query to
tests/eval/results/<YYYYMMDD-HHMMSS>_rag/raw.jsonl. Queries whose retrieval
raised are recorded with an error and excluded from all averages.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from tests.eval.metrics import aggregate
from tools.venues import retrieve_venue_docs

DATASET_PATH = Path("tests/eval/eval_datasets/rag_queries.jsonl")
RESULTS_DIR = Path("tests/eval/results")
RETRIEVAL_K = 5
KS = [1, 2, 3, 5]
REQUIRED_FIELDS = ("id", "query", "relevant")


def load_dataset(path: Path) -> list[dict]:
    cases = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            case = json.loads(line)
            missing = [field for field in REQUIRED_FIELDS if field not in case]
            if missing:
                raise ValueError(f"{path}:{line_no} is missing fields: {missing}")
            case.setdefault("tags", [])
            cases.append(case)
    return cases


def run_case(case: dict) -> dict:
    record = {
        "id": case["id"],
        "query": case["query"],
        "relevant": case["relevant"],
        "tags": case["tags"],
        "retrieval_k": RETRIEVAL_K,
        "retrieved": [],
        "links": [],
        "error": None,
    }
    try:
        docs = retrieve_venue_docs(case["query"], k=RETRIEVAL_K)
        record["retrieved"] = [doc["stem"] for doc in docs]
        record["links"] = [doc["link"] for doc in docs]
    except Exception as e:
        record["error"] = f"{type(e).__name__}: {e}"
    return record


def compute_groups(records: list[dict]) -> dict[str, dict]:
    """Aggregate overall and per tag, excluding errored records."""
    scored = [r for r in records if r["error"] is None]
    errored = [r for r in records if r["error"] is not None]

    groups = {"overall": (scored, errored)}
    tags = sorted({tag for r in records for tag in r["tags"]})
    for tag in tags:
        groups[tag] = (
            [r for r in scored if tag in r["tags"]],
            [r for r in errored if tag in r["tags"]],
        )

    results = {}
    for name, (group_scored, group_errored) in groups.items():
        metrics = aggregate(group_scored, KS)
        metrics["n_errored"] = len(group_errored)
        results[name] = metrics
    return results


def print_table(results: dict[str, dict]) -> None:
    metric_rows = [f"{m}@{k}" for m in ("hit_rate", "recall", "precision") for k in KS] + ["mrr"]
    count_rows = [("n_evaluated", "evaluated"), ("n_skipped", "out-of-scope"), ("n_errored", "errored")]

    columns = list(results)
    label_width = max(len(r) for r in metric_rows + [label for _, label in count_rows])
    col_width = max(10, max(len(c) for c in columns) + 2)

    print(" " * label_width + "".join(c.rjust(col_width) for c in columns))
    for row in metric_rows:
        cells = []
        for c in columns:
            value = results[c][row]
            cells.append(("n/a" if value is None else f"{value:.3f}").rjust(col_width))
        print(row.ljust(label_width) + "".join(cells))
    print("-" * (label_width + col_width * len(columns)))
    for key, label in count_rows:
        print(label.ljust(label_width) + "".join(str(results[c][key]).rjust(col_width) for c in columns))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the RAG retrieval eval.")
    parser.add_argument("--limit", type=int, default=None, help="only run the first N queries")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    cases = load_dataset(DATASET_PATH)
    if args.limit is not None:
        cases = cases[: args.limit]

    run_dir = RESULTS_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_rag"
    run_dir.mkdir(parents=True, exist_ok=False)
    raw_path = run_dir / "raw.jsonl"

    print(f"Running {len(cases)} queries from {DATASET_PATH} (retrieval k={RETRIEVAL_K})")
    records = []
    with raw_path.open("w", encoding="utf-8") as raw_file:
        for i, case in enumerate(cases, start=1):
            record = run_case(case)
            records.append(record)
            raw_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            raw_file.flush()

            prefix = f"[{i}/{len(cases)}] {record['id']}"
            if record["error"]:
                print(f"{prefix} ERROR  {record['error']}")
            else:
                top = record["retrieved"][0] if record["retrieved"] else "(no results)"
                print(f"{prefix} ok  top: {top}")

    print()
    print_table(compute_groups(records))
    print()
    print("precision@k always divides by k, even when fewer than k docs were retrieved.")
    print("Errored queries are excluded from all averages, never scored as misses.")

    errored = [r for r in records if r["error"]]
    if errored:
        print(f"\nErrored queries ({len(errored)}):")
        for r in errored:
            print(f"  {r['id']}: {r['error']}")

    print(f"\nRaw results: {raw_path}")


if __name__ == "__main__":
    main()
