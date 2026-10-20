# MatchDay

Conversational AI agent for global football, deployed at
https://matchday-901040990547.us-central1.run.app

Originally built as a World Cup 2026 assistant for the Google Cloud Rapid Agent
Hackathon (MongoDB partner track). Now a general football companion: it answers
questions about any league, club, national team, player, or transfer, using
structured tools where they exist and web search for everything else. The
World Cup 2026 is a completed tournament (June 11 to July 19, 2026). Live
fixtures for UEFA Champions League 2026-27 and Premier League 2026-27 are
planned.

The live app is a public portfolio demo, so first-time visitors must get
useful answers without setup.

## Architecture

Single FastAPI service on Cloud Run wrapping a custom Python tool-calling loop
against Gemini via Vertex AI. Tools split into four categories:

- **ESPN API** — live match data (schedules, results, standings)
- **Static snapshot** — World Cup 2026 results (`data/world_cup_2026.json`),
  read by `get_world_cup_results` in `tools/world_cup.py`
- **MongoDB MCP** — user state (follows, reminders, predictions) via the
  MongoDB MCP server (Node.js subprocess spawned at app startup)
- **Discovery Engine** — RAG-based venue knowledge (Google Cloud AI Applications)
- **Google Search** — head-to-head queries via Gemini's native grounding

A background asyncio task checks MongoDB every 30 seconds for due reminders
and sends emails via Brevo SMTP. See "Deploy configuration" for why it
currently doesn't fire reliably.

## Directory layout

matchday/
├── main.py # FastAPI app, lifespan, routes
├── agent.py # Gemini tool-calling loop, tool declarations
├── prompts/ # System instruction template (Markdown)
├── tools/ # Tool implementations
├── data/ # Static snapshots read at runtime (World Cup 2026 results)
├── static/ # Chat UI + bracket page
├── venue_docs/ # Source docs for Discovery Engine
├── tests/ # Structured tests (unit, integration, agent, eval)
├── scripts/ # Diagnostic and utility scripts
├── docs/ # Architecture and evaluation writeups
├── Dockerfile
├── requirements.txt
├── LICENSE
├── README.md
└── CLAUDE.md


## Tech stack

- Python 3.11 in production (Cloud Run); local dev may be 3.10
- FastAPI + uvicorn
- google-genai SDK (NOT the older vertexai SDK)
- Gemini model set via `GEMINI_MODEL` env var, defaulting to
  `gemini-3.1-pro-preview`
- pymongo + MongoDB MCP server 1.11.0 (pinned, Node.js 22+)
- Google Cloud Discovery Engine client
- Brevo SMTP via smtplib

## GCP resources

- Project ID: `matchday-agent-511216`
- Cloud Run service: `matchday` (region `us-central1`)
- Venue docs bucket: `gs://matchday-venue-docs-511216`
- Discovery Engine data store: `matchday-venues_1791751375788`
- Discovery Engine search app: `matchday-search_1791751586714`
- All config and credentials live in Secret Manager

## Code style

- Type hints on function signatures where meaningful, not obsessive about them
- Async where the tool touches network I/O or MCP; sync for pure functions
- Print statements with a two-space `→` prefix for tool call logging
- Tools catch exceptions and return string error messages rather than raising,
  so a single tool failure never crashes the agent loop
- Prefer clarity over cleverness

## Key patterns

### Adding a new tool

Follow the `agent-tools` skill in `.claude/skills/agent-tools/SKILL.md`.

### MongoDB MCP calls

- Parse array responses with `extract_mcp_data()` from `tools/mongodb_mcp.py`.
  MCP responses are wrapped in security tags; never parse raw text directly.
- Check every `call_tool` result with `mcp_error()` before trusting it.
  - Writes: on error, return a message saying what failed, e.g.
    `f"Failed to follow {team_name}: {err}"`. Never return a success
    message without checking.
  - Reads: on error, return the same response shape as the success path plus
    an `error` field, e.g. `{"followed_teams": [], "error": err}`. This lets
    the agent tell "nothing found" apart from "the call failed".

### Gemini calls

- All model calls in the agent loop go through `generate_with_retry()` in
  `agent.py`, never `client.aio.models.generate_content()` directly. It
  retries 429/500/503 with exponential backoff and jitter.
- `run_agent` records the history length at the start of each turn and rolls
  back on failure. Do not remove this: a half-finished turn left in history
  (e.g. a function call with no function response) makes Gemini reject every
  later message from that user.

### System instruction

- Lives in `prompts/system_instruction.md`, not in `agent.py`. It's loaded
  once at import and filled per request by `build_system_instruction()`,
  which replaces `{{user_id}}` and `{{today}}` (UTC date, e.g.
  `2026-10-18 (Sunday)`). Import fails if the file or a placeholder is
  missing, so a broken prompt can't ship silently.
- The model gets today's date from `{{today}}`, never from its training data.
  Don't hardcode facts that tools or web search should provide (e.g. the
  World Cup winner).
- `user_id` is inserted into the prompt, so `ChatRequest` in `main.py`
  restricts it to `[A-Za-z0-9_-]{1,40}` (422 otherwise). Keep that validation
  if the request model changes.

### Tool call logging

Every tool call prints `  → calling tool_name({args})` inside the agent loop.
Keep this format; it's used for grep-based log analysis.

## Gotchas

- **google-genai vs vertexai SDK.** Use `from google import genai`, not the
  deprecated `import vertexai`.

- **mongodb-mcp-server is pinned to 1.11.0 on purpose.** Version 3.x requires a
  `connectionId` argument on every tool call that this codebase doesn't send.
  An unpinned install silently pulled 3.x and broke all MongoDB operations.
  Upgrading is a deliberate task (inspect the new tool schemas via
  `session.list_tools()` first), not a casual version bump.

- **Pin dependencies in the Dockerfile.** Unpinned installs make builds
  non-reproducible. Any new global install must specify a version.

- **MongoDB connection string.** The URI must include the database name
  (`.../wc2026?params`, not `.../?params`).

- **Atlas IP access list.** Must allow `0.0.0.0/0`; Cloud Run egress IPs are
  dynamic.

- **Gemini 429s.** Preview models share capacity across all customers and
  return 429 `RESOURCE_EXHAUSTED` intermittently, independent of our own
  usage. Handled by `generate_with_retry()`.

- **Windows-only pip packages.** `pywin32`, `colorama`, and `watchfiles` show
  up in `pip freeze` on Windows dev machines but break the Linux Docker build.
  Strip them from `requirements.txt` before deploying.

- **Windows line endings in .env.** Strip `\r` when reading `.env` values in
  shell scripts, or invisible carriage returns end up inside secrets.

- **Team name normalization.** ESPN uses full names ("United States",
  "Türkiye", "Czechia") but users type shortcuts ("USA", "Turkey"). See
  `TEAM_ALIASES` in `tools/espn.py`.

- **ESPN scoreboard endpoint.** Returns only the current or most recent
  matchday by default. For date ranges, loop through days with
  `?dates=YYYYMMDD`. ESPN also doesn't populate future fixtures until close to
  matchday, so empty results for dates weeks ahead are expected.

- **ESPN tools are World Cup-only.** `tools/espn.py` uses the `fifa.world`
  league and looks at windows relative to today (`get_recent_results` looks
  back 14 days). Since the tournament is over, the match, results, schedule
  and standings tools return nothing. World Cup results come from the static
  snapshot via `get_world_cup_results`; scorers, stats and group standings
  come from `web_search`. Don't recompute group standings from results (FIFA
  tiebreakers are out of scope).

- **World Cup snapshot.** `data/world_cup_2026.json` is built by
  `python -m scripts.snapshot_world_cup`, which only writes the file if it
  parses exactly 104 matches and every winner matches ESPN's `winner` flag.
  The tool reads it at runtime, so `data/` must stay out of `.dockerignore`.
  The frontend results page should reuse this file. Match `date` is the US
  Eastern date (how ESPN groups matchdays); `kickoff_utc` is exact.

- **Venue retrieval uses `relevance_threshold="LOWEST"` on purpose.** The
  default threshold discarded correct results for 9 of 24 answerable eval
  queries. Abstention for out-of-scope questions is left to Gemini, not the
  retriever. See `docs/EVALUATION.md` before changing it.

## Deploy configuration

Deployed in low-cost mode: `--min-instances 0` with default CPU throttling.
Consequences:

- First request after idle has a cold start (container boot plus MCP
  subprocess spawn).
- The background reminder worker freezes between requests, so email reminders
  are saved but not reliably sent. The planned fix is Cloud Scheduler calling
  an endpoint periodically.

The full deploy command is in the README.

For local dev: `uvicorn main:app` from the repo root with a `.env` file present.

## Testing philosophy

- **Unit tests** — pure functions (parsers, alias lookups, metric computations)
- **Integration tests** — MongoDB, Discovery Engine, ESPN (may be flaky, skip on CI)
- **Agent tests** — tool selection accuracy for known prompts
- **Eval tests** — RAG retrieval quality, response quality (LLM-as-judge)

Evals live in `tests/eval/` with datasets in `tests/eval/eval_datasets/` as
JSONL. Metric computation is pure functions.

## Things NOT to do

- Do NOT run `gcloud` commands. All deployment and GCP changes are done
  manually by the developer.
- Do NOT switch to LangChain, LlamaIndex, or other agent frameworks; the
  custom loop is intentional.
- Do NOT add new dependencies without discussion.
- Do NOT modify the MCP response parser or `mcp_error()` without adding test
  coverage first.
- Do NOT call Gemini without going through `generate_with_retry()`.
- Do NOT unpin or bump `mongodb-mcp-server` without explicit discussion.
- Do NOT commit changes that touch deployment (Dockerfile, deploy commands,
  secrets) without explicit human review.
- Do NOT invent metrics or benchmarks that weren't actually measured.