# MatchDay

Conversational AI agent for global football, currently deployed at
https://wc2026-agent-623255749732.us-central1.run.app

Originally built as a World Cup 2026 assistant for the Google Cloud Rapid Agent
Hackathon (MongoDB partner track). Being expanded to support multiple
tournaments: World Cup 2026 (recap mode), UEFA Champions League 2026-27,
Premier League 2026-27.

## Architecture

Single FastAPI service on Cloud Run wrapping a custom Python tool-calling loop
against Gemini 3.1 Pro via Vertex AI. Tools split into four categories:

- **ESPN API** — live match data (schedules, results, standings)
- **MongoDB MCP** — user state (follows, reminders, predictions) via the
  MongoDB MCP server (Node.js subprocess spawned at app startup)
- **Discovery Engine** — RAG-based venue knowledge (Google Cloud AI Applications)
- **Google Search** — head-to-head queries via Gemini's native grounding

Background asyncio task runs every 30 seconds, checks MongoDB for due
reminders, sends emails via Brevo SMTP relay. Runs alongside the FastAPI app
in the same Cloud Run container (requires `--no-cpu-throttling` on deploy).

## Directory layout

matchday/
├── main.py # FastAPI app, lifespan, routes
├── agent.py # Gemini tool-calling loop, tool declarations
├── tools/ # Tool implementations
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

- Python 3.11+ (Cloud Run runs 3.11, local dev may be 3.10)
- FastAPI + uvicorn
- google-genai SDK (NOT the older vertexai SDK — see "Gotchas" below)
- pymongo + MongoDB MCP server (Node.js 22+)
- Google Cloud Discovery Engine client
- Brevo SMTP via smtplib

## Code style

- Type hints on function signatures where meaningful, not obsessive about them
- Async where the tool touches network I/O or MCP; sync for pure functions
- Print statements with a two-space `→` prefix for tool call logging (see agent.py)
- Error handling: tools catch exceptions and return string error messages
  rather than raising — this keeps the agent loop from crashing on tool failures
- Prefer clarity over cleverness; this is a demo project, not a performance-tuned one

## Key patterns

### Adding a new tool

Every agent tool follows the same pattern:

1. Write the implementation in `tools/<name>.py` — sync or async depending on what it does
2. Import it in `agent.py`
3. Add a `types.FunctionDeclaration` to `TOOL_DECLARATIONS`
4. Add the function to `SYNC_TOOLS` or `ASYNC_TOOLS` dict
5. If the tool needs new behavior expectations from the model, update the
   system instruction in `run_agent`

### MongoDB MCP tools

MCP responses come wrapped in security tags. Use `extract_mcp_data()` from
`tools/mongodb_mcp.py` to parse array responses. Never parse the raw text
directly.

### Tool call logging

Every tool call prints a line like `  → calling tool_name({args})` inside the
agent loop. Keep this format — it's useful for grep-based log analysis.

## Gotchas

- **google-genai vs vertexai SDK.** Use `from google import genai`, NOT the
  older `import vertexai`. The old SDK is deprecated. Model calls use
  `client.aio.models.generate_content(...)` for async.

- **MongoDB MCP connection string.** The URI must include the database name
  (`.../wc2026?params`, not `.../?params`). Missing DB name causes cryptic
  "invalid connection string" errors. Passed as `MDB_MCP_CONNECTION_STRING`
  env var to the MCP subprocess.

- **Atlas IP whitelist.** Must allow `0.0.0.0/0` for Cloud Run to connect —
  Cloud Run egress IPs are dynamic.

- **Cloud Run background workers.** Require `--no-cpu-throttling` on deploy,
  otherwise CPU is frozen between requests and background asyncio tasks
  silently stop ticking.

- **Windows-only pip packages.** `pywin32`, `colorama`, `watchfiles` show up
  in `pip freeze` on Windows dev machines but break the Linux Docker build.
  Strip them before deploying.

- **Team name normalization.** ESPN uses full names ("United States",
  "Türkiye", "Czechia") but users type shortcuts ("USA", "Turkey"). See
  `TEAM_ALIASES` in `tools/espn.py`.

- **ESPN scoreboard endpoint.** Returns only the current/most recent matchday
  by default. For date ranges, loop through days and hit the scoreboard with
  `?dates=YYYYMMDD` param per day.

## Deploy

Cloud Run deploy is a single gcloud command with secrets from Secret Manager.
Full command is in the README. Do NOT commit `.env` files or hardcode secrets.

For local dev: `uvicorn main:app` from repo root with a `.env` file present.

## Testing philosophy

- **Unit tests** — pure functions (parsers, alias lookups, metric computations)
- **Integration tests** — MongoDB, Discovery Engine, ESPN (may be flaky, skip on CI)
- **Agent tests** — tool selection accuracy for known prompts
- **Eval tests** — RAG retrieval quality, response quality (LLM-as-judge)

Evals live in `tests/eval/` with datasets in `tests/eval/eval_datasets/` as
JSONL. Metric computation is pure functions.

## Things NOT to do

- Do NOT switch to LangChain, LlamaIndex, or other agent frameworks — the
  custom loop is intentional
- Do NOT add new dependencies without discussion — dependency creep is a real
  cost in deployment size and complexity
- Do NOT modify the MCP response parser without adding test coverage first —
  it's fragile and has caused past bugs
- Do NOT commit changes that touch deployment (Dockerfile, deploy scripts,
  secrets) without explicit human review
- Do NOT invent metrics or benchmarks that weren't actually measured