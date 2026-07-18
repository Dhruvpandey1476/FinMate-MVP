# FinMate — Deployment Guide

This covers taking FinMate from "runs on my laptop" to a live URL you can put
in a hackathon submission or send to investors, plus the path from demo infra
to production infra.

## Part 1: Deploy the demo as-is (fastest path)

### Backend → Railway

1. Push this repo to GitHub.
2. On [railway.app](https://railway.app), "New Project" → "Deploy from GitHub repo" → select `backend/` as the root.
3. Railway auto-detects Python. Set the start command:
   ```
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
4. Add environment variables from `backend/.env.example` (at minimum, leave
   `DATABASE_URL` as the SQLite default unless you've provisioned Postgres —
   see Part 2).
5. Set `FRONTEND_ORIGIN` to your Vercel URL once you have it (step below).
6. Deploy. Note the public URL (e.g. `https://finmate-backend.up.railway.app`).

> SQLite on Railway: the filesystem is ephemeral on redeploy, which is fine for
> a hackathon demo (data reseeds automatically on startup) but not for real
> users — move to Postgres (Part 2) before any real launch.

### Frontend → Vercel

1. On [vercel.com](https://vercel.com), import the same GitHub repo, set the
   root directory to `frontend/`.
2. Add environment variable:
   ```
   NEXT_PUBLIC_API_URL=https://finmate-backend.up.railway.app
   ```
3. Deploy. Vercel gives you a `https://finmate-yourname.vercel.app` URL —
   that's what goes in your submission.

## Part 2: Production infra upgrade

When you're past the demo stage and want real users, swap each piece below.
None of these changes touch the frontend.

### PostgreSQL (replaces SQLite)

1. Provision Postgres on Railway (one click, "Add Database") or any managed
   provider (Supabase, Neon, RDS).
2. Update `backend/.env`:
   ```
   DATABASE_URL=postgresql://user:password@host:5432/finmate
   ```
3. Install the driver: `pip install psycopg2-binary`
4. No code changes needed — SQLAlchemy models in `app/models.py` are
   database-agnostic.

### Qdrant (replaces keyword-based memory retrieval)

The current `memory_engine.retrieve_relevant()` in
`backend/app/services/memory_engine.py` uses keyword overlap as a stand-in for
vector similarity. To upgrade:

1. Run Qdrant via `docker-compose.yml` (included) or Qdrant Cloud.
2. Add an embedding model call (OpenAI `text-embedding-3-small` or a local
   sentence-transformers model) when writing memories in `add_memory()`.
3. Replace the body of `retrieve_relevant()` with a Qdrant similarity search
   using the query's embedding.
4. The function signature stays the same — nothing else in the codebase needs
   to change.

### Neo4j (Wealth Graph)

The relational tables (`User`, `Goal`, `Asset`, `Liability`, `Transaction`)
already encode the Wealth Graph entities and relationships described in the
product spec. To move to actual graph queries:

1. Run Neo4j via `docker-compose.yml` or Neo4j Aura (managed).
2. Write a sync job (or dual-write in the relevant router) that mirrors new
   Transactions/Goals/Assets as nodes and edges (`User -[:HAS_GOAL]-> Goal`,
   `Transaction -[:IN_CATEGORY]-> ExpenseCategory`, etc).
3. Use Cypher queries for multi-hop questions the AI CFO agent can call into —
   e.g. "which goals are affected if I increase spending in category X."

### LangGraph (replaces the explicit pipeline)

`backend/app/agents/cfo_agent.py` is already structured as discrete node
functions (`node_financial_analysis`, `node_memory_retrieval`,
`node_goal_context`, `node_recommendation`) with a state dict passed between
them — this maps directly onto a LangGraph `StateGraph`:

```python
from langgraph.graph import StateGraph

graph = StateGraph(dict)
graph.add_node("financial_analysis", node_financial_analysis)
graph.add_node("memory_retrieval", node_memory_retrieval)
graph.add_node("goal_context", node_goal_context)
graph.add_node("recommendation", node_recommendation)
graph.add_edge("financial_analysis", "memory_retrieval")
graph.add_edge("memory_retrieval", "goal_context")
graph.add_edge("goal_context", "recommendation")
graph.set_entry_point("financial_analysis")
compiled = graph.compile()
```

No business logic changes — only the orchestration layer.

## Part 3: Authentication (Clerk / Auth.js)

The demo runs as a single hardcoded user (`DEMO_USER_ID = 1` in each router)
so the whole MVP works with zero auth setup. To add real multi-user support:

1. Add Clerk (recommended for speed) to the Next.js frontend.
2. Pass the Clerk user ID as a header or JWT to the backend.
3. Replace `DEMO_USER_ID = 1` in each router file with the authenticated
   user's ID, resolved via a FastAPI dependency.

This is intentionally the last step — get the product demo ready first, add
auth once you're confident in the core experience.
