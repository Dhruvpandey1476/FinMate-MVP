# FinMate — Pitch Notes

## The 30-second pitch

Budgeting apps show you the past. FinMate builds a **financial digital twin**
that remembers your history, simulates your future, and acts as an AI CFO that
tells you what to actually do about it — not just what you spent.

## The problem with every other personal finance app

- They categorize transactions. They don't reason about them.
- They have no memory — every session starts from zero context.
- They answer "what happened" but never "what should I do" or "what if."

## What makes FinMate different (say this explicitly to judges)

1. **A real memory architecture, not a chat log.** Three distinct memory types —
   episodic (events), semantic (preferences), behavioral (patterns) — feed into
   every AI CFO answer. Show the Memory Timeline page.
2. **Visible agent reasoning.** Every AI CFO response shows its 4-node reasoning
   trace (Financial Analysis → Memory Retrieval → Goal Context → Recommendation).
   This is the difference between "an LLM wrapper" and "an agentic system" —
   open it live during the demo.
3. **It doesn't just analyze, it simulates.** The Scenario Simulator runs actual
   forward projections — "what if I buy this," "what if my salary changes,"
   not generic advice.
4. **Goal-aware by design.** Every recommendation — in chat, in insights, in
   simulations — is contextualized against the user's actual goals and priority
   order, not generic financial tips.

## Demo script (5 minutes)

1. **Dashboard** (30s) — "This is Aarav's financial twin, updated in real time."
   Point at the Health Score gauge and net worth.
2. **AI CFO Chat** (90s) — Ask "Can I afford a ₹50,000 laptop?" then "Why am I
   overspending?" Open the reasoning trace on one answer. This is the centerpiece.
3. **Insights** (60s) — Show the auto-detected subscription/spending-leak
   opportunities with their monthly ₹ impact.
4. **Simulations** (60s) — Run an investment scenario, show the projected vs.
   baseline net worth chart.
5. **Goals + Memory Timeline** (60s) — Show a goal's AI-generated milestone plan,
   then the Memory Timeline to reinforce "this system remembers you."

## Anticipated judge questions

**"Is this just calling an LLM and formatting the output?"**
No — by default it runs on a deterministic rule engine (visible in the reasoning
trace), and optionally upgrades to Gemini/OpenAI for richer natural-language
explanations. The financial logic, memory retrieval, and goal math are all
separate from any LLM call.

**"How does this scale / what's the real production architecture?"**
SQLite + keyword retrieval today (for a zero-dependency demo); the data models
map 1:1 onto PostgreSQL + Neo4j (Wealth Graph) + Qdrant (vector memory) for
production — see `DEPLOYMENT.md`. The agent pipeline is structured so each node
maps directly onto a LangGraph `StateGraph` node.

**"What's the business model?"**
Freemium: free Financial Twin + basic AI CFO; paid tier unlocks deeper scenario
simulation, multi-account aggregation, and proactive opportunity alerts. B2B2C
angle: white-label the AI CFO for neobanks and fintech apps that want an
"intelligence layer" without building one.

**"What do you build next with funding?"**
Real bank/UPI data ingestion (Account Aggregator framework in India), the Neo4j
Wealth Graph for multi-hop reasoning ("how does paying off this loan affect my
car goal AND my emergency fund simultaneously"), and a mobile app.

## What NOT to claim in front of judges

Don't say "we have a live Neo4j knowledge graph in production" — be upfront that
the wealth-graph relationships exist in the relational data model today and the
graph database is the documented next step. Judges respect honesty about scope
far more than they respect overclaiming, and it's an easy thing to get caught on.
