# Relic.ai

Autonomous deploy risk and incident intelligence for GitHub repositories. Relic.ai watches every pull request and incident, reasons over a vector database of past outages, and surfaces the knowledge your team has earned the hard way — automatically, within seconds.

---

## What it does

### Event 1 — Pull Request Opened
When a PR is opened, Relic.ai:
1. Fetches the full diff.
2. Searches a Pinecone vector database of historical incidents for semantically similar past outages.
3. Sends the diff and retrieved incidents to Claude for risk analysis.
4. Posts a structured risk comment on the PR with: a 0-100 risk score, full reasoning, high-risk files, suggested actions, and links to similar past incidents.
5. Persists the result to SQLite for dashboard display.

### Event 2 — Incident Opened (labeled "incident")
When an issue labeled `incident` is opened, Relic.ai:
1. Embeds the issue title and description.
2. Retrieves similar past incidents from Pinecone.
3. Generates an instant triage brief: likely root cause, confidence score, estimated resolution time, resolution steps derived from past incidents.
4. Posts the triage brief as the first comment on the issue within seconds of it being opened.

### Event 3 — Incident Closed
When an incident issue is closed, Relic.ai:
1. Scrapes the full issue thread.
2. Extracts structured lessons: confirmed root cause, exact resolution steps, time to resolution, affected files, follow-up actions.
3. Stores the lessons as a new embedding in Pinecone — permanently improving future risk scores and triage briefs.
4. Updates SQLite and posts a confirmation comment.

---

## Architecture

```
relic-ai/
├── webhook/server.py        Flask app — verifies HMAC sigs, dispatches events
├── engine/
│   ├── risk_scorer.py       PR opened pipeline
│   ├── incident_triage.py   Incident opened pipeline
│   └── memory_updater.py    Incident closed pipeline
├── clients/
│   ├── github_client.py     GitHub REST API (mock/live)
│   ├── anthropic_client.py  Claude API (mock/live)
│   └── pinecone_client.py   Pinecone vector DB (mock/live)
├── db/
│   ├── schema.sql           SQLite schema
│   └── database.py          Read/write wrapper
├── dashboard/
│   ├── api.py               JSON API blueprint
│   ├── templates/           Jinja2 HTML pages
│   └── static/              CSS + JS
└── utils/logger.py          Structured logger
```

### Mock / Live switch

The single environment variable `USE_MOCK_RESPONSES` controls the entire system:

- `true` — all external calls return realistic mock responses. No API keys needed. Safe for development, demos, and testing.
- `false` — all calls go to real services. Requires all API keys to be set.

---

## Running locally

### With Docker (recommended)

```bash
git clone <repo>
cd relic-ai
cp .env.example .env
# Edit .env if you want live mode; mock mode works without any changes
docker-compose up --build
```

The dashboard is available at http://localhost:5050.

### Without Docker

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m webhook.server
```

---

## Registering the GitHub webhook

1. Go to your repository → Settings → Webhooks → Add webhook.
2. Set **Payload URL** to `https://your-domain.com/webhook` (must be publicly reachable — use ngrok for local development: `ngrok http 5050`).
3. Set **Content type** to `application/json`.
4. Set **Secret** to the value of `GITHUB_WEBHOOK_SECRET` in your `.env`.
5. Under **Which events?** select **Let me select individual events** and enable:
   - Pull requests
   - Issues
6. Click **Add webhook**.

---

## Switching from mock to live

1. Fill in all values in `.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   PINECONE_API_KEY=...
   PINECONE_ENVIRONMENT=us-east-1-aws
   PINECONE_INDEX_NAME=relic-ai-incidents
   GITHUB_TOKEN=ghp_...
   GITHUB_REPO_OWNER=your-org
   GITHUB_REPO_NAME=your-repo
   GITHUB_WEBHOOK_SECRET=your-secret
   ```
2. Create a Pinecone index named `relic-ai-incidents` with:
   - Dimension: **1536** (matches text-embedding-3-large)
   - Metric: **cosine**
3. Set `USE_MOCK_RESPONSES=false` in `.env`.
4. Restart: `docker-compose restart` or `python -m webhook.server`.
5. The system will begin storing real incident memories as PRs and issues flow through.

---

## Dashboard pages

| Page | URL | Description |
|------|-----|-------------|
| Overview | `/` | Stats, activity feed, risk trend chart, system health |
| Risk Analysis | `/risk` | Filterable PR risk table with detail panel |
| Incidents | `/incidents` | Active/resolved incidents with triage briefs |
| Memory Archive | `/memory` | Stored incident memories with stratigraphy timeline |
| Settings | `/settings` | Env vars, system status, go-live instructions |

---

## API endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhook` | POST | GitHub webhook receiver |
| `/health` | GET | System health JSON |
| `/api/scores` | GET | Recent risk scores JSON |
| `/api/incidents` | GET | All incidents JSON |
| `/api/memory` | GET | Memory store count + preview |
| `/api/clear` | POST | Wipe all data (requires `{"confirm": true}`) |
