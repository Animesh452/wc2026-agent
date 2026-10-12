# MatchDay — World Cup 2026 AI Assistant

> A conversational AI agent that helps fans track teams, plan trips, predict matches, and explore host city venues during the FIFA World Cup 2026.

**Live demo:** [wc2026-agent-901040990547.us-central1.run.app](https://matchday-901040990547.us-central1.run.app/)

Built for the **Google Cloud Rapid Agent Hackathon** — MongoDB partner track.

---

## What it does

MatchDay is a multi-tool AI agent that handles the full fan experience for the World Cup 2026:

- **Live match data** — schedules, results, standings, and team info pulled from ESPN's live API
- **Team following** — persistent user state stored in MongoDB Atlas via the MongoDB MCP server
- **Match reminders** — set personalized reminders with custom timing, delivered via email (Brevo SMTP) by a background scheduler
- **Trip planning** — multi-step itineraries that chain match schedules with venue knowledge from a Google Cloud Discovery Engine data store
- **Fantasy predictions** — predict match scores, get scored when results come in (3 points for exact, 1 for correct winner), compete on a multi-user leaderboard
- **Head-to-head queries** — historical matchup data via Gemini's grounded Google Search
- **Conversation memory** — the agent remembers context across turns within a session

---

## Architecture

The agent runs on **Gemini 3.1 Pro Preview** via Vertex AI, orchestrated by a custom Python tool-calling loop. FastAPI serves the chat API and HTML frontend, deployed as a container on Cloud Run.

**Tool layer:**

| Tool | Purpose | Backend |
|------|---------|---------|
| ESPN API | Live match data, schedules, results | Public ESPN endpoint |
| MongoDB MCP | User state, reminders, predictions | MongoDB Atlas + MCP server |
| Discovery Engine | Venue knowledge base (RAG) | GCP AI Applications / Vertex AI Search |
| Google Search | News, head-to-head queries | Gemini native grounding |

**Persistent state in MongoDB:**

- `users` — followed teams per user
- `reminders` — scheduled email reminders
- `predictions` — match score predictions with scoring history
- `match_cache` — optional caching

**Background worker:**

A separate asyncio task runs every 30 seconds, queries MongoDB for due reminders, and dispatches emails via Brevo SMTP.

---

## Technology stack

- **AI model:** Gemini 3.1 Pro Preview (Vertex AI)
- **Agent framework:** Custom Python tool-calling loop using `google-genai` SDK
- **Backend:** FastAPI on Cloud Run (Python 3.11)
- **Frontend:** Single-page HTML/JS chat interface
- **Database:** MongoDB Atlas via MongoDB MCP server (partner track)
- **Knowledge base:** Google Cloud Discovery Engine (AI Applications)
- **Secrets:** GCP Secret Manager
- **Email:** Brevo SMTP relay
- **Source control:** GitHub
- **Deployment:** Cloud Run with auto-scaling, min 1 instance for background worker

---

## Partner integration — MongoDB MCP

This project is submitted to the **MongoDB track**. The MongoDB MCP server is integrated as a Node.js subprocess managed by the FastAPI lifespan. The MCP client connection persists across the application lifetime, with tools dispatched for:

- Reading followed teams (`find`)
- Reading reminders and predictions (`find`)
- Saving user preferences (`update-many` with `$addToSet` and upsert)
- Saving reminders and predictions (`insert-many`)
- Deleting reminders, predictions, and follows (`delete-many`, `update-many` with `$pull`)
- Aggregating leaderboard stats (`aggregate` with `$group` and `$sort`)

The MCP integration is meaningful and non-trivial — every user state operation in the agent goes through MCP, with a custom parser to extract document arrays from the server's structured security-wrapped responses.

---

## Repository structure
```text
wc2026-agent/
├── main.py                    # FastAPI app, lifespan, routes
├── agent.py                   # Gemini tool-calling loop, tool declarations
├── tools/
│   ├── espn.py                # Match data, schedules, results
│   ├── mongodb_mcp.py         # MCP CRUD operations
│   ├── predictions.py         # Prediction save/score/leaderboard logic
│   ├── venues.py              # Discovery Engine RAG queries
│   ├── email_sender.py        # Brevo SMTP integration
│   ├── reminder_worker.py     # Background asyncio scheduler
│   └── web_search.py          # Gemini grounded search
├── static/
│   ├── index.html             # Chat UI
│   └── bracket.html           # Tournament bracket page
├── venue_docs/                # Source documents for Discovery Engine
├── Dockerfile
├── requirements.txt
├── LICENSE
└── README.md
```

---

## Setup & deployment

### Prerequisites

- Google Cloud project with billing enabled
- MongoDB Atlas cluster (M0 free tier works)
- Brevo SMTP account (for email reminders)
- Python 3.11+, Node.js 22+

### Required GCP APIs

- Vertex AI API
- Cloud Run Admin API
- Secret Manager API
- Discovery Engine API
- Cloud Build API

### Secrets

Create the following in GCP Secret Manager:
MONGODB_URI
GCP_PROJECT_ID
DISCOVERY_ENGINE_LOCATION
DISCOVERY_STORE_ID
DISCOVERY_ENGINE_ID
BREVO_SMTP_LOGIN
BREVO_SMTP_KEY
BREVO_SENDER_EMAIL

### Discovery Engine setup

1. Upload venue documents from `venue_docs/` to a Cloud Storage bucket
2. Create a Discovery Engine data store pointing to that bucket
3. Create a Search app on top of the data store
4. Record the data store ID and engine ID for the secrets above

### Deploy

```bash
gcloud run deploy wc2026-agent \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-secrets="MONGODB_URI=MONGODB_URI:latest,GCP_PROJECT_ID=GCP_PROJECT_ID:latest,DISCOVERY_ENGINE_LOCATION=DISCOVERY_ENGINE_LOCATION:latest,DISCOVERY_STORE_ID=DISCOVERY_STORE_ID:latest,DISCOVERY_ENGINE_ID=DISCOVERY_ENGINE_ID:latest,BREVO_SMTP_LOGIN=BREVO_SMTP_LOGIN:latest,BREVO_SMTP_KEY=BREVO_SMTP_KEY:latest,BREVO_SENDER_EMAIL=BREVO_SENDER_EMAIL:latest" \
  --min-instances 1 \
  --no-cpu-throttling \
  --timeout 300 \
  --memory 1Gi
```

The `--no-cpu-throttling` flag keeps the background reminder worker active.

---

## Local development

```bash
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
npm install -g mongodb-mcp-server
```

Create a `.env` with the same keys as the GCP secrets, then:

```bash
uvicorn main:app
```

---

## Author

**Animesh Kumar**

Built solo for the Google Cloud Rapid Agent Hackathon, May 2026.

---

## License

MIT — see [LICENSE](./LICENSE) for details.