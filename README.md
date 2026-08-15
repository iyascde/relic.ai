# Relic.ai

**Autonomous deploy risk and incident intelligence for engineering teams.**

Relic.ai turns a team's past production incidents into active engineering context.

It watches GitHub pull requests and incidents, retrieves semantically similar failures from a vector database, and uses Claude to reason over that history in real time. Instead of letting incident knowledge disappear into old tickets and postmortems, Relic.ai continuously feeds those lessons back into the development cycle.

A risky PR can be connected to a failure from months ago. A newly opened incident can immediately surface likely causes and recovery steps. When that incident is resolved, Relic.ai learns from it and adds the resolution back into its memory.

**The result is a closed feedback loop:**

```text
Past Incidents
      ↓
Institutional Memory
      ↓
Pull Request Risk Analysis
      ↓
Production
      ↓
Incident Detection & Triage
      ↓
Resolution
      ↓
New Institutional Memory
      ↺
```

---

## Why Relic.ai?

Engineering teams accumulate valuable operational knowledge every time something breaks:

* which files tend to cause outages
* which deployment patterns are dangerous
* what symptoms point to a particular failure
* which fixes actually worked
* how long similar incidents took to resolve

But most of that knowledge lives in old GitHub issues, incident threads, and postmortems that engineers have to manually search.

Relic.ai makes that history **queryable and proactive**.

Instead of asking:

> "Has something like this happened before?"

Relic.ai automatically asks that question on every relevant pull request and incident.

---

## Core Workflows

### 1. Pull Request Risk Analysis

When a pull request is opened, Relic.ai:

1. Fetches the complete GitHub diff.
2. Searches Pinecone for semantically similar historical incidents.
3. Sends the code changes and retrieved incident context to Claude.
4. Generates a structured risk assessment containing:

   * **0–100 risk score**
   * reasoning behind the score
   * high-risk files
   * recommended actions
   * related historical incidents
5. Posts the analysis directly to the pull request.
6. Persists the result to SQLite for visualization in the dashboard.

```text
GitHub PR
   ↓
Fetch Diff
   ↓
Retrieve Similar Incidents
   ↓
Claude Risk Analysis
   ↓
Risk Score + Recommendations
   ↓
PR Comment + Dashboard
```

The goal is not simply to inspect what changed, but to evaluate the change against **what has historically gone wrong**.

---

### 2. Autonomous Incident Triage

When a GitHub issue labeled `incident` is opened, Relic.ai immediately begins triage.

It:

1. Reads the incident title and description.
2. Retrieves semantically similar historical incidents.
3. Uses Claude to generate a triage brief containing:

   * likely root cause
   * confidence score
   * estimated resolution time
   * ordered remediation steps
   * links to relevant previous incidents
4. Posts the triage brief directly to the incident thread.

```text
New Incident
     ↓
Retrieve Similar Failures
     ↓
Claude Triage
     ↓
Likely Cause
Resolution Steps
Estimated Resolution Time
     ↓
GitHub Issue Comment
```

This gives an on-call engineer historical context immediately, without requiring them to manually search previous outages while responding to an active incident.

---

### 3. Continuous Incident Memory

Relic.ai does not stop once an incident has been resolved.

When an incident issue closes, it:

1. Reads the full issue discussion.
2. Extracts structured operational knowledge:

   * confirmed root cause
   * resolution steps
   * time to resolution
   * affected files or services
   * follow-up actions
3. Stores the resulting incident memory in Pinecone.
4. Updates the local incident record in SQLite.
5. Makes the new incident available to future PR analysis and triage workflows.

That creates the central feedback loop behind Relic.ai:

```text
Predict → Observe → Resolve → Learn → Predict Better
```

Every resolved incident makes the system's institutional memory richer.

---

## Architecture

Relic.ai is implemented as an event-driven Python service centered around GitHub webhooks.

```text
                           ┌─────────────────────┐
                           │       GitHub        │
                           │  PRs + Incidents    │
                           └──────────┬──────────┘
                                      │
                                   Webhook
                                      │
                                      ▼
                           ┌─────────────────────┐
                           │   Flask Webhook     │
                           │      Server         │
                           └──────────┬──────────┘
                                      │
                ┌─────────────────────┼─────────────────────┐
                │                     │                     │
                ▼                     ▼                     ▼
        ┌──────────────┐     ┌────────────────┐    ┌────────────────┐
        │ Risk Scorer  │     │Incident Triage │    │ Memory Updater │
        └──────┬───────┘     └───────┬────────┘    └───────┬────────┘
               │                     │                      │
               └──────────────┬──────┴──────────────┬───────┘
                              │                     │
                         ┌────▼─────┐         ┌─────▼──────┐
                         │  Claude  │         │  Pinecone  │
                         │   API    │         │Vector Store│
                         └──────────┘         └────────────┘
                              │
                              ▼
                         ┌─────────┐
                         │ SQLite  │
                         └────┬────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │ Relic Dashboard   │
                    └───────────────────┘
```

### Project Structure

```text
relic-ai/
├── webhook/
│   └── server.py              # GitHub webhook receiver and event dispatcher
│
├── engine/
│   ├── risk_scorer.py         # Pull request risk-analysis pipeline
│   ├── incident_triage.py     # New-incident triage pipeline
│   └── memory_updater.py      # Closed-incident learning pipeline
│
├── clients/
│   ├── github_client.py       # GitHub REST API integration
│   ├── anthropic_client.py    # Claude reasoning layer
│   └── pinecone_client.py     # Vector-memory retrieval and storage
│
├── db/
│   ├── schema.sql             # SQLite schema
│   └── database.py            # Persistence layer
│
├── dashboard/
│   ├── api.py                 # Dashboard API
│   ├── templates/             # Jinja2 views
│   └── static/                # JavaScript, CSS, and assets
│
├── utils/
│   └── logger.py              # Structured application logging
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## Tech Stack

**Backend**

* Python
* Flask
* SQLite

**AI / Retrieval**

* Anthropic Claude
* Pinecone vector database
* semantic incident retrieval

**Integrations**

* GitHub REST API
* GitHub Webhooks
* HMAC webhook verification

**Frontend**

* Jinja2
* JavaScript
* HTML/CSS

**Infrastructure**

* Docker
* Docker Compose

---

## Dashboard

Relic.ai includes a dashboard for inspecting both current system state and accumulated operational memory.

| Page               | Route        | Purpose                                                 |
| ------------------ | ------------ | ------------------------------------------------------- |
| **Overview**       | `/`          | System statistics, activity, risk trends, and health    |
| **Risk Analysis**  | `/risk`      | Browse PR risk assessments and high-risk changes        |
| **Incidents**      | `/incidents` | View open and resolved incidents and triage results     |
| **Memory Archive** | `/memory`    | Explore accumulated incident knowledge                  |
| **Settings**       | `/settings`  | Configuration, system state, and live-mode instructions |

---

## API

| Endpoint         | Method | Description                                    |
| ---------------- | ------ | ---------------------------------------------- |
| `/webhook`       | `POST` | Receives GitHub webhook events                 |
| `/health`        | `GET`  | Returns service health                         |
| `/api/scores`    | `GET`  | Returns recent PR risk analyses                |
| `/api/incidents` | `GET`  | Returns incident records                       |
| `/api/memory`    | `GET`  | Returns incident-memory statistics and preview |
| `/api/clear`     | `POST` | Clears stored data when explicitly confirmed   |

---

## Mock Mode

Relic.ai can run end-to-end without external API credentials.

```env
USE_MOCK_RESPONSES=true
```

In mock mode, GitHub, Claude, and Pinecone interactions return realistic development responses. This makes it possible to run and explore the complete application locally without configuring external services.

To use live integrations:

```env
USE_MOCK_RESPONSES=false
```

and provide the required credentials in `.env`.

---

## Running Locally

### Docker

```bash
git clone https://github.com/iyascde/relic.ai.git
cd relic.ai

cp .env.example .env

docker-compose up --build
```

Then open:

```text
http://localhost:5050
```

### Without Docker

```bash
git clone https://github.com/iyascde/relic.ai.git
cd relic.ai

python -m venv venv
```

On macOS/Linux:

```bash
source venv/bin/activate
```

On Windows:

```powershell
venv\Scripts\activate
```

Then:

```bash
pip install -r requirements.txt
cp .env.example .env
python -m webhook.server
```

The dashboard will be available at:

```text
http://localhost:5050
```

---

## Configuration

Copy the provided configuration template:

```bash
cp .env.example .env
```

Relevant variables include:

```env
# Anthropic
ANTHROPIC_API_KEY=

# Pinecone
PINECONE_API_KEY=
PINECONE_ENVIRONMENT=us-east-1-aws
PINECONE_INDEX_NAME=relic-ai-incidents

# GitHub
GITHUB_TOKEN=
GITHUB_REPO_OWNER=
GITHUB_REPO_NAME=
GITHUB_WEBHOOK_SECRET=

# Application
FLASK_PORT=5050
FLASK_DEBUG=false
USE_MOCK_RESPONSES=true

# Persistence
DATABASE_PATH=./db/relic.db
LOG_LEVEL=INFO
```

> `.env` is intentionally excluded from Git and should never contain credentials committed to the repository.

---

## GitHub Webhook Setup

To connect Relic.ai to a repository:

1. Open the target GitHub repository.
2. Go to **Settings → Webhooks → Add webhook**.
3. Set the payload URL to:

```text
https://your-domain.com/webhook
```

4. Set the content type to:

```text
application/json
```

5. Configure the webhook secret to match `GITHUB_WEBHOOK_SECRET`.
6. Subscribe to:

   * Pull requests
   * Issues
7. Save the webhook.

For local development, expose port `5050` using a tunneling service and point GitHub to the resulting public `/webhook` URL.

---

## Design Principles

### Historical context over isolated analysis

A code diff by itself only tells part of the story. Relic.ai combines the current change with historical failures so risk analysis can incorporate the operational history of the codebase.

### AI as a reasoning layer

Claude is used to reason over structured engineering context rather than as a standalone chatbot. The system assembles the PR, incident, and historical context before requesting a structured analysis.

### Closed-loop learning

Resolved incidents are fed back into the memory system instead of becoming static records. Future analyses can therefore benefit from lessons learned during previous failures.

### Developer-native workflows

Relic.ai surfaces intelligence where engineers are already working: directly inside pull requests and incident issues.

---

## The Idea

Most engineering organizations already possess the knowledge required to prevent many repeat failures.

The problem is that the knowledge is fragmented across months or years of incidents and difficult to access at the exact moment an engineer needs it.

Relic.ai explores a simple question:

**What if a codebase could remember how it had failed before?**

By connecting deployment analysis, incident response, and long-term operational memory, Relic.ai turns historical failures from passive documentation into an active part of the software-development process.
