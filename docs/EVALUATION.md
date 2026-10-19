# Evaluation

This document covers the retrieval evaluation for MatchDay's venue knowledge base: how it's set up, what it found, and the decisions made from it.

## Scope

The evaluation measures **retrieval quality**: given a user query, does Discovery Engine return the venue documents that answer it? It calls `retrieve_venue_docs()` in `tools/venues.py`, the same function the agent's `search_venue_info` tool uses, so the eval measures the production code path rather than a reimplementation.

Answer quality (whether Gemini produces a correct response from the retrieved docs) is not measured yet. See [Next steps](#next-steps).

## Setup

### Corpus

9 plain-text documents in Discovery Engine: 8 World Cup 2026 venues plus a tournament overview (`world_cup_2026_overview`).

### Dataset

`tests/eval/eval_datasets/rag_queries.jsonl`: 28 hand-written queries, labeled before any run.

| Tag | Queries | What it tests |
|---|---|---|
| `city-only` | 6 | City named, stadium not named |
| `direct` | 5 | Stadium named |
| `attribute` | 5 | Neither named; identified by a feature (altitude, roof, weather, prices) |
| `multi-venue` | 3 | Answer spread across 2-3 documents |
| `tournament` | 2 | Answered by the overview |
| `ambiguous` | 3 | User's wording differs from the doc's (e.g. "Dallas" for Arlington, "Estadio Banorte" for Estadio Azteca) |
| `out-of-scope` | 4 | No document can answer |

**Labeling rule:** a document is relevant if it contains information needed to answer the query. Relevance is binary. Out-of-scope queries have `relevant: []`.

Queries were written in natural user phrasing, deliberately avoiding the documents' own wording, so that retrieval is tested on meaning rather than keyword overlap.

### Metrics

Computed per query, then averaged. Implemented as pure functions in `tests/eval/metrics.py`, with unit tests in `tests/unit/test_metrics.py`.

| Metric | Definition |
|---|---|
| Hit rate@k | 1 if any relevant doc is in the top k, else 0 |
| Recall@k | Fraction of relevant docs found in the top k |
| Precision@k | Fraction of the top k that is relevant (denominator is always k) |
| MRR | Mean of 1 / rank of the first relevant doc (0 if none retrieved) |
| Abstention rate | Out-of-scope queries only: fraction that correctly returned zero results |

Reported at k = 1, 2, 3, 5. **`search_venue_info` passes the top 2 documents to the agent, so @2 is the production-relevant cutoff.**

Out-of-scope queries are excluded from hit rate, recall, precision, and MRR, and measured by abstention rate instead. Queries where the retrieval call errors are excluded from all averages and never scored as misses.

### Running it

```bash
python -m tests.eval.rag_eval                      # API default threshold
python -m tests.eval.rag_eval --threshold LOWEST   # specific threshold
python -m tests.eval.rag_eval --limit 3            # quick smoke run
```

Each run writes `raw.jsonl` to `tests/eval/results/<timestamp>_rag_<threshold>/`, one self-contained line per query, so metrics can be recomputed without calling the API again.

## Finding 1: Historical content outranks current content

Observed while building `retrieve_venue_docs`, before the formal eval.

**Query:** "Which stadium hosts the World Cup final?"

| Rank | Document |
|---|---|
| 1 | `world_cup_2026_overview` |
| 2 | `estadio_azteca` |
| 3 | `metlife_stadium` |
| 4 | `sofi_stadium` |
| 5 | `bc_place` |

The Azteca document discusses hosting the 1970 and 1986 World Cup Finals, so it overlaps heavily with "World Cup final" even though that content is historical, not about 2026. MetLife's document, the actual 2026 final venue, mentions its role only once.

This is a classic RAG failure mode: a document that shares vocabulary with the query outranks the one that answers it. In this case the agent still receives a correct answer, because the overview ranked first and states the final is at MetLife Stadium.

## Finding 2: Most failures were zero-result queries

### Baseline

The first full run, at the API's default relevance threshold:

| hit@1 | hit@2 | recall@2 | MRR |
|---|---|---|---|
| 0.583 | 0.583 | 0.569 | 0.583 |

Two patterns stood out:

1. **hit@1 equaled hit@5 in every tag, and MRR equaled hit@1.** Whenever the search returned anything, a relevant doc was at rank 1. Retrieving deeper never rescued a query, so ranking was not the problem.
2. **10 of 28 queries returned no documents at all.** One was out-of-scope, where empty is correct. The other 9 accounted for 9 of the 10 in-scope misses. The `attribute` tag scored 0 across every metric.

### Diagnosis

**Hypothesis 1: strict keyword matching.** Zero-result queries like "how to reach metlife" contained words absent from the documents ("reach"), suggesting every query term had to match.

**Falsified** by probing (`scripts/probe_retrieval.py`): single words that do appear in the documents also failed. "arlington" returned nothing, though the AT&T Stadium document contains "Arlington, Texas." "metlife" returned only the overview, not the MetLife document.

**Hypothesis 2: a relevance threshold discards low-confidence results.** Discovery Engine filters results below a confidence threshold. Short or loosely worded queries score low and get dropped entirely, which also explains why surviving results ranked well.

**Confirmed** by probing with the threshold lowered (`scripts/probe_search_settings.py`):

| Query | Default threshold | `LOWEST` threshold, top result |
|---|---|---|
| metlife | `world_cup_2026_overview` only | `metlife_stadium` |
| metlife transit | none | `metlife_stadium` |
| how to reach metlife | none | `metlife_stadium` |
| arlington | none | `att_stadium` |
| arlington texas | `att_stadium` | `att_stadium` |
| how to reach arlington | none | `att_stadium` |

At `LOWEST`, the correct document ranked first for every probe. The threshold had been deleting correct answers, not reordering them. Adding a second matching term ("arlington texas") was enough to clear the default threshold, where "arlington" alone was not.

Query expansion (`QueryExpansionSpec`, condition `AUTO`) was also tested and had no effect: results were identical to the default.

## Finding 3: Relevance threshold sweep

The full dataset was run at each threshold level.

| Threshold | hit@1 | hit@2 | recall@2 | precision@2 | MRR | Abstention |
|---|---|---|---|---|---|---|
| `MEDIUM` | 0.417 | 0.417 | 0.389 | 0.208 | 0.417 | 1.00 |
| default | 0.583 | 0.583 | 0.569 | 0.333 | 0.583 | 0.25 |
| `LOW` | 0.583 | 0.583 | 0.569 | 0.333 | 0.583 | 0.25 |
| `LOWEST` | 0.833 | 0.917 | 0.903 | 0.521 | 0.894 | 0.00 |

hit@2 by tag, default vs `LOWEST`:

| Tag (n) | Default | `LOWEST` |
|---|---|---|
| `ambiguous` (3) | 0.667 | 1.000 |
| `attribute` (5) | 0.000 | 0.800 |
| `city-only` (6) | 0.667 | 1.000 |
| `direct` (5) | 0.800 | 1.000 |
| `multi-venue` (3) | 0.667 | 0.667 |
| `tournament` (2) | 1.000 | 1.000 |

Observations:

- **The tradeoff is monotonic.** Each stricter level loses recall and gains abstention. `MEDIUM` abstains on every out-of-scope query but misses over half the answerable ones.
- **The default behaved identically to `LOW`** on all 28 queries, result for result. This is an observation on this dataset, not a general claim about the API.
- **The default threshold bought little safety.** It abstained on only 1 of 4 out-of-scope queries, while discarding 9 answerable ones.
- **The largest gain was on `attribute` queries**, the paraphrased ones, from 0.0 to 0.8 hit@2.

## Decision: use `LOWEST` in production

**Status:** applied in `search_venue_info` and deployed.

`LOWEST` raises production-relevant hit@2 from 0.583 to 0.917, at the cost of abstention dropping from 0.25 to 0.

The reasoning goes beyond the numbers. In this architecture the retriever is not the last line of defense: Gemini reads the retrieved documents, and the system instruction tells it to refuse out-of-scope questions rather than fabricate. Abstention is therefore delegated to the model, and the retriever is optimized for recall.

**Accepted risk:** for out-of-scope questions, Gemini now always receives two documents, which may be irrelevant. For example, a question about transit to Toronto's stadium could receive the MetLife document, and the model could misapply its transit details. This needs answer-level verification (see [Next steps](#next-steps)).

**Post-deployment spot check.** Three out-of-scope questions were asked on the live agent (transit to the Toronto and Kansas City stadiums, and semifinal venues). In none did the agent present another venue's details as an answer. Logs show that for Toronto and Kansas City it queried the knowledge base first, judged the results irrelevant, and fell back to `web_search`; for the semifinals it went to `web_search` directly. This supports delegating abstention to the model, though it's three queries, not a measurement. Toronto took four reworded knowledge base queries before falling back, adding latency.

## Remaining misses at `LOWEST`

Queries where no relevant document appeared in the top 2. Each illustrates a different known failure mode.

### rag-016: vocabulary mismatch

**Query:** "which stadium won't rip me off on food and drinks"
**Relevant:** `mercedes_benz_stadium`, retrieved at rank 4. Top 2: `levis_stadium`, `metlife_stadium`.

The query says "food and drinks" and uses an idiom ("rip me off"); the document says "affordable stadium concessions." No shared words, and the relevant fact is a single short line. Retrieval detected some signal, ranking the document 4th of 9, but not enough.

Rewording the document to match this query would be teaching to the test. A document change is only justified if it reflects how users actually phrase the topic generally.

### rag-018: negation

**Query:** "what places i shouldn't take a car to"
**Relevant:** `sofi_stadium`, `estadio_azteca`, `metlife_stadium`. Only `metlife_stadium` was retrieved, at rank 5. Top 2: `bc_place`, `world_cup_2026_overview`.

Embedding-based retrieval handles negation poorly: "places I shouldn't take a car to" sits close to "places with cars" in vector space. The `bc_place` result is not random: its document emphasizes walkability and SkyTrain access, which is semantically "no car needed." Retrieval captured the topic but not the negation. The answer is also spread across three documents.

### rag-019: numeric comparison (partial)

**Query:** "venues with 80k+ capacities"
**Relevant:** `att_stadium`, `estadio_azteca`, `metlife_stadium`. `att_stadium` and `metlife_stadium` ranked 1 and 2; `estadio_azteca` was not retrieved. Recall@2 = 2/3.

Semantic retrieval matches meaning; it cannot compare numbers. This was expected when the query was written. The right fix is structural, not a retrieval tweak: a `capacity` metadata field on each document, filtered numerically.

## Limitations

- **Small dataset.** 28 queries, so each is worth about 4 percentage points overall. Per-tag results rest on 2 to 6 queries each and are noisy.
- **Small corpus.** With 9 documents, `LOWEST` returns 5 of 9 for every query. Results may differ substantially with a larger corpus containing near-duplicate venues.
- **Raw user phrasing.** In production, Gemini writes the query passed to `search_venue_info`, often shorter and more keyword-like than the user's message. This eval measures retrieval on raw phrasing, so production performance is likely somewhat better.
- **Retrieval only.** Whether the agent answers correctly from what it retrieves is not measured.

## Next steps

1. **Apply `LOWEST` in `search_venue_info`**, deploy, and spot-check out-of-scope questions on the live agent to see whether it admits it doesn't know or misuses an irrelevant document.
2. **Expand the corpus** to cover Premier League and Champions League venues (~60 documents), and rerun this same dataset to measure how retrieval holds up against near-duplicates. Query IDs are kept stable so runs remain comparable.
3. **Add structured metadata** (competition, city, capacity) using Discovery Engine's metadata import, enabling filtered retrieval and addressing numeric queries like rag-019.
4. **Answer-level evaluation:** score the agent's final responses, including out-of-scope refusals, using an LLM-as-judge rubric.
5. **Rewritten-query evaluation:** measure retrieval on the queries Gemini actually generates, alongside raw user phrasing.