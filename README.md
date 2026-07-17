# FinMate — Agentic Financial Operating System

FinMate builds a **Financial Digital Twin** for every user, remembers their financial
history through a three-tier Memory Engine, and runs four specialized agents
(AI CFO, Scenario Simulator, Goal Planner, Opportunity Discovery) on top of it.

This repo is a **multi-user, auth-protected product**: real backend, real frontend,
per-account data isolation, and a live memory engine that learns from each user's
chats and uploads. Runs locally in minutes.

> **⚠️ Security first:** API keys were previously committed to `backend/.env` and
> **must be rotated** (Groq, Gemini, OpenAI, Qdrant, Neo4j) before any deployment.
> `.env` is now git-ignored. See `backend/.env.example`.

## Accounts

- **Sign up** creates a fresh, empty account — upload a statement or click
  *Load sample data* to explore.
- **Demo login:** `demo@finmate.ai` / `demo1234` (pre-loaded with 6 months of data).
- Every request is authenticated with a JWT bearer token; all data is scoped per user.

## Quick Start

### 1. Backend (FastAPI)

```bash
cd backend
python3 -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

On startup the app creates the demo account (`demo@finmate.ai` / `demo1234`) with
6 months of realistic data. Set `JWT_SECRET` in `.env` (generate with
`python -c "import secrets; print(secrets.token_hex(32))"`). API docs at
`http://localhost:8000/docs`.

### 2. Frontend (Next.js)

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Open `http://localhost:3000`.

Set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` to point at your backend
(defaults to `http://localhost:8000`).

## Deploy (near-zero cost)

- **Backend:** push to GitHub → Render *New → Blueprint* (uses `render.yaml`;
  provisions a free Postgres + web service, auto-generates `JWT_SECRET`).
  Set `GROQ_API_KEY` and `EXTRA_ORIGINS` (your Vercel URL) in the dashboard.
  Railway/Fly work too via `backend/Dockerfile`.
- **Frontend:** import `frontend/` into Vercel, set `NEXT_PUBLIC_API_URL` to the
  Render URL. Free tier is enough to validate with early users.

## What's in the MVP

| Module | Status | Notes |
|---|---|---|
| Financial Digital Twin | ✅ Real | Computes net worth, savings rate, cash flow, health score from transactions |
| Memory Engine (episodic/semantic/behavioral) | ✅ Real | Stored in SQLite, retrieved via keyword-ranked search |
| AI CFO Agent | ✅ Real | 4-node pipeline (Financial Analysis → Memory Retrieval → Goal Context → Recommendation) with visible reasoning trace |
| Scenario Simulator | ✅ Real | Purchase / salary change / investment / savings projections |
| Goal Planning Agent | ✅ Real | Timelines, milestones, monthly contribution recommendations |
| Opportunity Discovery | ✅ Real | Detects recurring subscriptions, spending leaks, unusual transactions |
| 8 frontend pages | ✅ Real | Dashboard, Financial Twin, AI CFO Chat, Goals, Simulations, Insights, Memory Timeline, Settings |
| LLM-backed reasoning | ⚙️ Optional | Off by default (deterministic rule engine). Flip on with a Gemini/OpenAI key — see Settings page |
| PostgreSQL / Neo4j / Qdrant | ⚙️ Upgrade path | Demo uses SQLite + in-process retrieval so it runs anywhere with no infra. `docker-compose.yml` spins up the production stack when you're ready — see `DEPLOYMENT.md` |

**Why SQLite instead of Postgres/Neo4j/Qdrant for the demo:** those three require
running servers, which makes "unzip and run" impossible and is exactly the kind
of friction that costs you points live in front of judges. The data models
(Wealth Graph entities, three memory types) are designed 1:1 to map onto Postgres
and Neo4j when you're ready — see `DEPLOYMENT.md` for the swap.

## Architecture

```
finmate/
├── backend/                  FastAPI app
│   └── app/
│       ├── models.py         User, Transaction, Goal, Asset, Liability, Memory (Wealth Graph entities)
│       ├── services/
│       │   ├── financial_twin.py    Real-time snapshot computation
│       │   ├── memory_engine.py     Episodic/semantic/behavioral storage + retrieval
│       │   └── llm_client.py        Optional Gemini/OpenAI hook
│       ├── agents/
│       │   ├── cfo_agent.py             4-node reasoning pipeline
│       │   ├── scenario_simulator.py    What-if projections
│       │   ├── goal_planner.py          Timeline generation
│       │   └── opportunity_discovery.py Spending leak detection
│       └── routers/          REST endpoints per module
├── frontend/                 Next.js 15 + TypeScript + Tailwind
│   └── app/                  8 pages, glassmorphism UI
├── docker-compose.yml         Postgres + Neo4j + Qdrant (production upgrade)
├── PITCH.md                   Hackathon pitch talking points
└── DEPLOYMENT.md              Vercel + Railway deployment + infra upgrade guide
```

## The AI CFO's reasoning is real, not decorative

Every chat response shows its reasoning trace — which node looked at what, and why
it answered the way it did. Click "View agent reasoning" under any AI CFO message
in the Chat page. This is the single most important thing to show judges: it proves
the system isn't just an LLM wrapper, it's a pipeline with real financial state,
real memory, and real goal context feeding into the final answer.

## Upgrading the AI CFO to a real LLM

Set in `backend/.env`:
```
LLM_PROVIDER=gemini       # or openai
GEMINI_API_KEY=your_key_here
```
No frontend changes needed. The agent pipeline routes through the configured
provider automatically, falling back to the rule-based engine if the call fails —
so a flaky API never breaks your live demo.
