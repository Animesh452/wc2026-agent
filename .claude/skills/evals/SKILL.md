---
name: evals
description: Conventions for building and running evaluations in MatchDay, including RAG retrieval evals against Discovery Engine (recall@k, precision@k, MRR, hit rate) and agent evals (tool-selection accuracy, LLM-as-judge). Use when creating eval datasets, eval runners, metric functions, or eval reports, or when the user mentions evals, benchmarks, retrieval quality, or measuring agent behavior.
---

# Evals

## Principles

- **Evaluate the production code path.** Retrieval evals must call the same
  retrieval function the agent uses, never a reimplementation. If production
  code doesn't expose what an eval needs (e.g. ranked document IDs), refactor
  production code to expose it and have the agent tool use that same function.
- **The developer writes golden datasets.** Do not generate or expand eval
  queries or expected answers unless explicitly asked. If useful, propose
  candidate queries in chat for review instead of writing them to the dataset.
  Never edit expected answers to make a run pass.
- **Never fabricate or estimate results.** Every number in a report must come
  from an actual run, with raw outputs saved.
- **Metrics are pure functions** with unit tests.
- **Evals cost money** (Gemini and Discovery Engine calls). Don't rerun full
  suites casually. Runners must support `--limit N` for quick smoke runs.

## Layout

tests/
├── eval/
│ ├── eval_datasets/
│ │ ├── rag_queries.jsonl
│ │ └── agent_prompts.jsonl
│ ├── metrics.py # pure metric functions
│ ├── rag_eval.py # RAG runner
│ ├── agent_eval.py # agent runner
│ └── results/
│ └── <YYYYMMDD-HHMMSS>_<eval_name>/
│ ├── raw.jsonl
│ ├── report.json
│ └── report.md
└── unit/
└── test_metrics.py


`tests/eval/results/` is committed only for runs referenced in
`docs/EVALUATION.md`. Other runs stay local.

## Dataset formats

### RAG (`rag_queries.jsonl`), one JSON object per line

```json
{"id": "rag-001", "query": "where is the fan zone in miami", "relevant": ["hard_rock_stadium"], "tags": ["single-venue"], "notes": ""}
```

- `relevant` holds document IDs, defined as the filename stem of the source
  doc in `venue_docs/` (`hard_rock_stadium.txt` becomes `hard_rock_stadium`).
  Discovery Engine's own document IDs are opaque hashes; map results to stems
  via `derived_struct_data["link"]`.
- `relevant` may contain multiple documents. Relevance is binary and order
  doesn't matter.
- `relevant: []` marks an out-of-scope query. Exclude these from recall and
  MRR averages and report them separately.
- `tags` enable sliced reporting (e.g. `single-venue`, `ambiguous`,
  `multi-venue`, `out-of-scope`).

### Agent (`agent_prompts.jsonl`)

```json
{"id": "agent-001", "prompt": "plan my world cup trip", "expected_tools": ["get_followed_teams", "get_team_schedule", "search_venue_info"], "forbidden_tools": [], "setup": {"follow": ["Brazil"]}, "tags": ["multi-step"], "notes": ""}
```

- Each case runs with a fresh, eval-specific user ID
  (`eval_<run_id>_<case_id>`) so state never leaks between cases.
- `setup` describes state to create before the prompt runs.
- Eval users and their data are deleted after the run.

## Metrics (`metrics.py`)

Retrieval, computed per query, then averaged:

- `hit_rate@k`: 1 if any relevant doc is in the top k, else 0
- `recall@k`: |relevant ∩ top k| / |relevant|
- `precision@k`: |relevant ∩ top k| / k. The denominator stays k even if fewer
  than k docs were retrieved; state this in the report.
- `reciprocal_rank`: 1 / rank of the first relevant doc, 0 if none retrieved
- `MRR`: mean of reciprocal ranks

Default k values: 1, 3, 5.

Agent:

- Tool-set precision and recall against `expected_tools`
- Exact set match rate
- Forbidden-tool violation rate

## Reports

`report.json` must record: timestamp, git commit hash, dataset path and
case count, Discovery Engine data store and engine IDs, `GEMINI_MODEL`, k
values, per-case results, and aggregates overall and per tag.

`report.md` contains:

1. Summary table of aggregate metrics
2. Per-tag table
3. Failure list: query, expected docs, retrieved top-k. This is the most
   useful section; never truncate it.

## Interpreting failures

Classify each failure as one of: dataset error, ranking failure (right doc
exists but ranked low), coverage gap (no relevant doc exists), or genuine
ambiguity. Findings go in `docs/EVALUATION.md`, which the developer reviews
and edits before committing.