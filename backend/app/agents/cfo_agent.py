"""
AI CFO Agent — LangGraph StateGraph Implementation.

This is a REAL agentic pipeline, not the old if/elif routing.

Graph: financial_analysis → memory_retrieval → graph_reasoning → ai_synthesis

Each node:
1. Gathers structured context from its domain
2. Adds it to the shared state
3. The final AI Synthesis node sends ALL context to the LLM for a genuine,
   contextual response, not a template string.
"""
import logging
from typing import TypedDict, Optional
from sqlalchemy.orm import Session
from langgraph.graph import StateGraph, END

from .. import models
from ..services import financial_twin, memory_engine, llm_client
from ..services.wealth_graph import get_graph_context

logger = logging.getLogger("finmate.cfo_agent")

# ─── System Prompt ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are FinMate AI CFO — an intelligent, empathetic financial advisor powered by a Financial Digital Twin.

You have access to the user's REAL financial data:
- Their complete financial snapshot (income, expenses, savings, net worth)
- Their financial memories (past behaviors, preferences, spending patterns)
- Their goals and progress toward each goal
- Graph-based insights about what's delaying or blocking their goals

RULES:
1. Always cite specific numbers from their financial data (e.g., "Your ₹18,000/month rent takes up 21% of income")
2. Be honest but encouraging — don't sugarcoat problems, but show actionable paths forward
3. Keep responses concise (3-6 sentences) unless the question demands detail
4. Use Indian Rupee (₹) formatting with commas (e.g., ₹1,50,000)
5. When suggesting changes, quantify the impact (e.g., "Cutting food delivery by ₹2,000/month gets you to your emergency fund 3 months faster")
6. Reference their specific goals by name when relevant
7. If you detect concerning patterns from their behavioral memories, proactively mention them
8. Think like a real CFO — connect spending decisions to long-term wealth outcomes"""


# ─── State Definition ────────────────────────────────────────────────────────

class CFOState(TypedDict):
    user_id: int
    query: str
    snapshot: Optional[dict]
    memories: Optional[list]
    goals: Optional[list]
    graph_context: Optional[dict]
    trace: list
    reply: Optional[str]


# ─── Graph Nodes ─────────────────────────────────────────────────────────────

def node_financial_analysis(state: CFOState) -> dict:
    """Node 1: Compute the Financial Digital Twin snapshot."""
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        snapshot = financial_twin.get_snapshot(db, state["user_id"])
        trace_entry = {
            "node": "Financial Analysis",
            "detail": f"Savings rate {snapshot['savings_rate']}%, cash flow ₹{snapshot['cash_flow']:,.0f}, "
                      f"health score {snapshot['financial_health_score']}/100, "
                      f"net worth ₹{snapshot['net_worth']:,.0f}.",
        }
        return {
            "snapshot": snapshot,
            "trace": state["trace"] + [trace_entry],
        }
    finally:
        db.close()


def node_memory_retrieval(state: CFOState) -> dict:
    """Node 2: Retrieve semantically relevant memories from Qdrant/keyword index."""
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        memories = memory_engine.retrieve_relevant(db, state["user_id"], state["query"])
        memory_summary = []
        for m in memories:
            memory_summary.append(f"[{m.memory_type}] {m.content}")
        
        trace_entry = {
            "node": "Memory Retrieval",
            "detail": f"Found {len(memories)} relevant memories "
                      f"({', '.join(sorted(set(m.memory_type for m in memories))) or 'none'}). "
                      f"{'Using Qdrant vector search.' if memory_engine.get_qdrant() else 'Using keyword fallback.'}",
        }
        return {
            "memories": memories,
            "trace": state["trace"] + [trace_entry],
        }
    finally:
        db.close()


def node_graph_reasoning(state: CFOState) -> dict:
    """Node 3: Query Neo4j wealth graph for relationship-based insights."""
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        goals = db.query(models.Goal).filter(
            models.Goal.user_id == state["user_id"]
        ).order_by(models.Goal.priority).all()
        
        graph_ctx = get_graph_context(state["user_id"])
        
        goal_details = []
        for g in goals:
            progress = (g.current_amount / g.target_amount * 100) if g.target_amount else 0
            goal_details.append(
                f"'{g.name}' (P{g.priority}): ₹{g.current_amount:,.0f}/₹{g.target_amount:,.0f} ({progress:.0f}%)"
            )
        
        trace_detail = f"Top priority goal: {goal_details[0] if goal_details else 'none set'}."
        if graph_ctx.get("available"):
            delays = graph_ctx.get("goal_delays", [])
            if delays:
                trace_detail += f" Graph found {len(delays)} spending categories delaying goals."
        else:
            trace_detail += " Neo4j graph not available — using relational context."
        
        trace_entry = {
            "node": "Goal & Graph Context",
            "detail": trace_detail,
        }
        return {
            "goals": goals,
            "graph_context": graph_ctx,
            "trace": state["trace"] + [trace_entry],
        }
    finally:
        db.close()


def node_ai_synthesis(state: CFOState) -> dict:
    """
    Node 4: AI Synthesis — Send ALL gathered context to the LLM.
    
    This is where the REAL intelligence happens. The LLM receives:
    - The user's question
    - Complete financial snapshot
    - Relevant memories
    - Goal progress
    - Graph-based relationship insights
    
    And generates a genuinely contextual, personalized response.
    """
    snapshot = state["snapshot"] or {}
    goals = state["goals"] or []
    memories = state["memories"] or []
    graph_ctx = state["graph_context"] or {}
    query = state["query"]
    
    # Build rich context for the LLM
    memory_text = "\n".join(f"  - [{m.memory_type}] {m.content}" for m in memories) or "  No relevant memories."
    
    goal_text = "\n".join(
        f"  - {g.name} (P{g.priority}): ₹{g.current_amount:,.0f} / ₹{g.target_amount:,.0f} "
        f"({(g.current_amount/g.target_amount*100) if g.target_amount else 0:.0f}% funded, "
        f"₹{g.monthly_contribution:,.0f}/mo contribution)"
        for g in goals
    ) or "  No goals set."
    
    graph_text = ""
    if graph_ctx.get("available"):
        delays = graph_ctx.get("goal_delays", [])
        blocks = graph_ctx.get("goal_blocks", [])
        if delays:
            graph_text += "\n  Goal Delays (from spending):\n"
            for d in delays:
                graph_text += f"    - '{d['category']}' delays '{d['goal']}' by ₹{d['impact']:,.0f}/mo\n"
        if blocks:
            graph_text += "  Goal Blocks (from debt):\n"
            for b in blocks:
                graph_text += f"    - '{b['liability']}' drains ₹{b['drain']:,.0f}/mo from '{b['goal']}'\n"
    else:
        graph_text = "  Graph insights not available."
    
    expense_text = "\n".join(
        f"  - {c['category']}: ₹{c['amount']:,.0f}"
        for c in snapshot.get("top_expense_categories", [])
    ) or "  No expense data."
    
    prompt = f"""User's question: "{query}"

=== FINANCIAL DIGITAL TWIN ===
Net Worth: ₹{snapshot.get('net_worth', 0):,.0f}
Monthly Income: ₹{snapshot.get('total_income_month', 0):,.0f}
Monthly Expenses: ₹{snapshot.get('total_expense_month', 0):,.0f}
Cash Flow: ₹{snapshot.get('cash_flow', 0):,.0f}
Savings Rate: {snapshot.get('savings_rate', 0):.1f}%
Financial Health Score: {snapshot.get('financial_health_score', 0)}/100
Total Assets: ₹{snapshot.get('total_assets', 0):,.0f}
Total Liabilities: ₹{snapshot.get('total_liabilities', 0):,.0f}

Top Expense Categories:
{expense_text}

=== USER MEMORIES ===
{memory_text}

=== GOALS ===
{goal_text}

=== WEALTH GRAPH INSIGHTS ===
{graph_text}

Answer the user's question using ALL the context above. Be specific, cite their real numbers, and give actionable advice."""

    # Generate the deterministic fallback (kept as safety net)
    fallback = _rule_based_fallback(query, snapshot, goals, memories)
    
    # LLM is the PRIMARY path now
    reply = llm_client.generate(
        prompt=prompt,
        fallback=fallback,
        system_prompt=SYSTEM_PROMPT,
        temperature=0.7,
    )
    
    provider = llm_client.get_last_provider()
    trace_entry = {
        "node": "AI Synthesis",
        "detail": f"Generated response via {provider}. "
                  f"Context: {len(memories)} memories, {len(goals)} goals, "
                  f"{'graph-enhanced' if graph_ctx.get('available') else 'relational'}.",
    }
    return {
        "reply": reply,
        "trace": state["trace"] + [trace_entry],
    }


# ─── Build the LangGraph ─────────────────────────────────────────────────────

def _build_graph() -> StateGraph:
    """Construct the AI CFO agent graph."""
    graph = StateGraph(CFOState)
    
    graph.add_node("financial_analysis", node_financial_analysis)
    graph.add_node("memory_retrieval", node_memory_retrieval)
    graph.add_node("graph_reasoning", node_graph_reasoning)
    graph.add_node("ai_synthesis", node_ai_synthesis)
    
    graph.set_entry_point("financial_analysis")
    graph.add_edge("financial_analysis", "memory_retrieval")
    graph.add_edge("memory_retrieval", "graph_reasoning")
    graph.add_edge("graph_reasoning", "ai_synthesis")
    graph.add_edge("ai_synthesis", END)
    
    return graph.compile()


# Compile once at module load
_agent = _build_graph()


def run(db: Session, user_id: int, query: str) -> dict:
    """Execute the AI CFO agent pipeline."""
    initial_state: CFOState = {
        "user_id": user_id,
        "query": query,
        "snapshot": None,
        "memories": None,
        "goals": None,
        "graph_context": None,
        "trace": [],
        "reply": None,
    }
    
    try:
        result = _agent.invoke(initial_state)
        return {"reply": result["reply"], "trace": result["trace"]}
    except Exception as e:
        logger.error("CFO agent pipeline failed: %s", e, exc_info=True)
        # Emergency fallback
        snapshot = financial_twin.get_snapshot(db, user_id)
        fallback = _rule_based_fallback(query, snapshot, [], [])
        return {
            "reply": fallback,
            "trace": [{"node": "Error Recovery", "detail": f"Agent pipeline failed: {str(e)[:100]}. Used rule-based fallback."}],
        }


# ─── Rule-based Fallback (last resort only) ──────────────────────────────────

def _rule_based_fallback(query: str, snapshot: dict, goals: list, memories: list) -> str:
    """Deterministic fallback — only used when ALL LLM providers fail."""
    q = query.lower()
    
    if "afford" in q:
        import re
        nums = re.findall(r"[\d,]+", q.replace("₹", "").replace("rs", "").replace("inr", ""))
        amount = float(nums[0].replace(",", "")) if nums else None
        cash_flow = snapshot.get("cash_flow", 0)
        
        if amount and amount <= cash_flow * 0.5:
            return f"Yes — ₹{amount:,.0f} is within reach. You have ₹{cash_flow:,.0f} in free cash flow this month."
        elif amount and amount <= cash_flow:
            return f"It's affordable but tight. ₹{amount:,.0f} uses {(amount/cash_flow*100):.0f}% of your monthly cash flow."
        elif amount:
            return f"Not comfortably this month — you'd need ~{max(1, round(amount/max(cash_flow,1)))} months of savings."
        return f"Your current free cash flow is ₹{cash_flow:,.0f}/month."
    
    if "overspend" in q or "spending more" in q:
        cats = snapshot.get("top_expense_categories", [])
        if cats:
            return f"Your biggest category is '{cats[0]['category']}' at ₹{cats[0]['amount']:,.0f}. Savings rate: {snapshot.get('savings_rate', 0)}%."
        return "I need more transaction data to identify overspending patterns."
    
    if "save" in q and "how" in q:
        return (
            f"Currently saving at {snapshot.get('savings_rate', 0)}% of income. "
            f"Target 25-30% for healthy growth."
        )
    
    return (
        f"Your Financial Health Score is {snapshot.get('financial_health_score', 0)}/100 "
        f"with ₹{snapshot.get('cash_flow', 0):,.0f} monthly cash flow and "
        f"{snapshot.get('savings_rate', 0)}% savings rate."
    )
