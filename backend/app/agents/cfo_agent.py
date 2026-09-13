"""
AI CFO Agent - LangGraph StateGraph implementation.

Graph: financial_analysis -> memory_retrieval -> graph_reasoning -> ai_synthesis

Each node gathers structured context from its domain and adds it to shared
state; the final AI Synthesis node sends all of it to the LLM.

Two things this version fixes:

  * Sessions. Every node used to open its own SessionLocal(), so one chat
    message consumed four connections and no node could see another's
    uncommitted work. The request's session is now threaded through state.

  * Trust boundary. Merchant names and notes come from user-uploaded PDFs. They
    are scrubbed and fenced (services/prompt_safety.py) before entering the
    prompt, and the system prompt tells the model that fenced content is data.
"""
import logging
from typing import TypedDict, Optional, Any, Iterator

from sqlalchemy.orm import Session
from langgraph.graph import StateGraph, END

from .. import models
from ..services import financial_twin, memory_engine, llm_client, prompt_safety
from ..services.wealth_graph import get_graph_context

logger = logging.getLogger("finmate.cfo_agent")

# --- System Prompt ---------------------------------------------------------

SYSTEM_PROMPT = """You are FinMate AI CFO - an intelligent, empathetic financial advisor powered by a Financial Digital Twin.

You have access to the user's REAL financial data:
- Their complete financial snapshot (income, expenses, savings, net worth)
- Their financial memories (past behaviors, preferences, spending patterns)
- Their goals and progress toward each goal
- Graph-based insights about what's delaying or blocking their goals

RULES:
1. Always cite specific numbers from their financial data (e.g., "Your Rs 18,000/month rent takes up 21% of income")
2. Be honest but encouraging - don't sugarcoat problems, but show actionable paths forward
3. Keep responses concise (3-6 sentences) unless the question demands detail
4. Use Indian Rupee formatting with commas and the Rs symbol
5. When suggesting changes, quantify the impact
6. Reference their specific goals by name when relevant
7. If you detect concerning patterns from their behavioral memories, proactively mention them
8. Think like a real CFO - connect spending decisions to long-term wealth outcomes
9. You are not a SEBI-registered investment adviser. Discuss categories and
   planning, never specific securities to buy or sell.""" + prompt_safety.UNTRUSTED_DATA_NOTICE


# --- State -----------------------------------------------------------------

class CFOState(TypedDict):
    user_id: int
    query: str
    db: Any                    # the request-scoped Session, shared by all nodes
    snapshot: Optional[dict]
    memories: Optional[list]
    goals: Optional[list]
    graph_context: Optional[dict]
    trace: list
    prompt: Optional[str]
    reply: Optional[str]
    llm_result: Optional[Any]


# --- Nodes -----------------------------------------------------------------

def node_financial_analysis(state: CFOState) -> dict:
    """Node 1: compute the Financial Digital Twin snapshot."""
    db: Session = state["db"]
    snapshot = financial_twin.get_snapshot(db, state["user_id"])
    trace_entry = {
        "node": "Financial Analysis",
        "detail": (
            f"Savings rate {snapshot['savings_rate']}%, cash flow Rs {snapshot['cash_flow']:,.0f}, "
            f"health score {snapshot['financial_health_score']}/100, "
            f"net worth Rs {snapshot['net_worth']:,.0f}."
        ),
    }
    return {"snapshot": snapshot, "trace": state["trace"] + [trace_entry]}


def node_memory_retrieval(state: CFOState) -> dict:
    """Node 2: retrieve relevant memories (Qdrant vectors, keyword fallback)."""
    db: Session = state["db"]
    memories = memory_engine.retrieve_relevant(db, state["user_id"], state["query"])
    kinds = ", ".join(sorted({m.memory_type for m in memories})) or "none"
    trace_entry = {
        "node": "Memory Retrieval",
        "detail": (
            f"Found {len(memories)} relevant memories ({kinds}). "
            f"{'Using Qdrant vector search.' if memory_engine.get_qdrant() else 'Using keyword fallback.'}"
        ),
    }
    return {"memories": memories, "trace": state["trace"] + [trace_entry]}


def node_graph_reasoning(state: CFOState) -> dict:
    """Node 3: goal context plus Neo4j wealth-graph relationships."""
    db: Session = state["db"]
    goals = (
        db.query(models.Goal)
        .filter(models.Goal.user_id == state["user_id"])
        .order_by(models.Goal.priority)
        .all()
    )
    graph_ctx = get_graph_context(state["user_id"])

    goal_details = []
    for g in goals:
        progress = (g.current_amount / g.target_amount * 100) if g.target_amount else 0
        goal_details.append(
            f"'{prompt_safety.scrub(g.name, 60)}' (P{g.priority}): "
            f"Rs {g.current_amount:,.0f}/Rs {g.target_amount:,.0f} ({progress:.0f}%)"
        )

    trace_detail = f"Top priority goal: {goal_details[0] if goal_details else 'none set'}."
    if graph_ctx.get("available"):
        delays = graph_ctx.get("goal_delays", [])
        if delays:
            trace_detail += f" Graph found {len(delays)} spending categories delaying goals."
    else:
        trace_detail += " Neo4j graph not available - using relational context."

    return {
        "goals": goals,
        "graph_context": graph_ctx,
        "trace": state["trace"] + [{"node": "Goal & Graph Context", "detail": trace_detail}],
    }


def build_prompt(state: CFOState) -> str:
    """
    Assemble the synthesis prompt.

    Computed figures sit outside the fence; anything the user supplied (merchant
    names, notes, memory text, goal names) is scrubbed and fenced.
    """
    snapshot = state["snapshot"] or {}
    goals = state["goals"] or []
    memories = state["memories"] or []
    graph_ctx = state["graph_context"] or {}
    query = state["query"]

    memory_text = prompt_safety.scrub_lines(
        memories,
        lambda m: f"  - [{prompt_safety.scrub(m.memory_type, 20)}] {prompt_safety.scrub(m.content, 300)}",
    ) or "  No relevant memories."

    goal_text = prompt_safety.scrub_lines(
        goals,
        lambda g: (
            f"  - {prompt_safety.scrub(g.name, 60)} (P{g.priority}): "
            f"Rs {g.current_amount:,.0f} / Rs {g.target_amount:,.0f} "
            f"({(g.current_amount / g.target_amount * 100) if g.target_amount else 0:.0f}% funded, "
            f"Rs {g.monthly_contribution:,.0f}/mo contribution)"
        ),
    ) or "  No goals set."

    graph_lines = []
    if graph_ctx.get("available"):
        for d in graph_ctx.get("goal_delays", []):
            graph_lines.append(
                f"    - '{prompt_safety.scrub(d.get('category'), 40)}' delays "
                f"'{prompt_safety.scrub(d.get('goal'), 40)}' by Rs {d.get('impact', 0):,.0f}/mo"
            )
        for b in graph_ctx.get("goal_blocks", []):
            graph_lines.append(
                f"    - '{prompt_safety.scrub(b.get('liability'), 40)}' drains "
                f"Rs {b.get('drain', 0):,.0f}/mo from '{prompt_safety.scrub(b.get('goal'), 40)}'"
            )
    graph_text = "\n".join(graph_lines) or "  Graph insights not available."

    expense_text = prompt_safety.scrub_lines(
        snapshot.get("top_expense_categories", []),
        lambda c: f"  - {prompt_safety.scrub(c.get('category'), 40)}: Rs {c.get('amount', 0):,.0f}",
    ) or "  No expense data."

    untrusted = prompt_safety.fence(
        "user financial records",
        f"""Top Expense Categories:
{expense_text}

=== USER MEMORIES ===
{memory_text}

=== GOALS ===
{goal_text}

=== WEALTH GRAPH INSIGHTS ===
{graph_text}""",
    )

    return f"""User's question: "{prompt_safety.scrub(query, 1000)}"

=== FINANCIAL DIGITAL TWIN (computed, trusted) ===
Net Worth: Rs {snapshot.get('net_worth', 0):,.0f}
Monthly Income: Rs {snapshot.get('total_income_month', 0):,.0f}
Monthly Expenses: Rs {snapshot.get('total_expense_month', 0):,.0f}
Cash Flow: Rs {snapshot.get('cash_flow', 0):,.0f}
Savings Rate: {snapshot.get('savings_rate', 0):.1f}%
Financial Health Score: {snapshot.get('financial_health_score', 0)}/100
Total Assets: Rs {snapshot.get('total_assets', 0):,.0f}
Total Liabilities: Rs {snapshot.get('total_liabilities', 0):,.0f}

{untrusted}

Answer the user's question using the context above. Be specific, cite their real
numbers, and give actionable advice."""


def node_ai_synthesis(state: CFOState) -> dict:
    """Node 4: send the assembled context to the LLM."""
    prompt = build_prompt(state)
    fallback = rule_based_fallback(
        state["query"], state["snapshot"] or {}, state["goals"] or [], state["memories"] or []
    )

    result = llm_client.generate_detailed(
        prompt=prompt,
        fallback=fallback,
        system_prompt=SYSTEM_PROMPT,
        temperature=0.7,
    )

    trace_entry = {
        "node": "AI Synthesis",
        "detail": (
            f"Generated response via {result.provider}. "
            f"Context: {len(state['memories'] or [])} memories, {len(state['goals'] or [])} goals, "
            f"{'graph-enhanced' if (state['graph_context'] or {}).get('available') else 'relational'}."
        ),
    }
    return {
        "reply": result.text,
        "prompt": prompt,
        "llm_result": result,
        "trace": state["trace"] + [trace_entry],
    }


# --- Graph -----------------------------------------------------------------

def _build_graph():
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


_agent = _build_graph()


def _initial_state(db: Session, user_id: int, query: str) -> CFOState:
    return {
        "user_id": user_id,
        "query": query,
        "db": db,
        "snapshot": None,
        "memories": None,
        "goals": None,
        "graph_context": None,
        "trace": [],
        "prompt": None,
        "reply": None,
        "llm_result": None,
    }


def run(db: Session, user_id: int, query: str) -> dict:
    """Execute the full pipeline and return {reply, trace, llm_result}."""
    try:
        result = _agent.invoke(_initial_state(db, user_id, query))
        return {
            "reply": result["reply"],
            "trace": result["trace"],
            "llm_result": result.get("llm_result"),
        }
    except Exception as e:
        logger.error("CFO agent pipeline failed: %s", e, exc_info=True)
        try:
            snapshot = financial_twin.get_snapshot(db, user_id)
        except Exception:
            snapshot = {}
        return {
            "reply": rule_based_fallback(query, snapshot, [], []),
            "trace": [{
                "node": "Error Recovery",
                "detail": f"Agent pipeline failed: {str(e)[:100]}. Used rule-based fallback.",
            }],
            "llm_result": None,
        }


def run_streaming(db: Session, user_id: int, query: str) -> Iterator[dict]:
    """
    Run the context nodes, then stream the synthesis token by token.

    Yields {"type": "trace", "step": {...}} as each node completes, then
    {"type": "token", "text": ...}, then a final {"type": "done", ...}. Showing
    the reasoning trace fill in while the answer streams is the whole point of
    the visible pipeline - it should not arrive as one 30-second block.
    """
    state = _initial_state(db, user_id, query)

    try:
        for node in (node_financial_analysis, node_memory_retrieval, node_graph_reasoning):
            update = node(state)
            state.update(update)
            yield {"type": "trace", "step": state["trace"][-1]}
    except Exception as e:
        logger.error("CFO streaming context phase failed: %s", e, exc_info=True)
        step = {"node": "Error Recovery", "detail": f"Context gathering failed: {str(e)[:100]}."}
        state["trace"] = state["trace"] + [step]
        yield {"type": "trace", "step": step}

    prompt = build_prompt(state)
    fallback = rule_based_fallback(
        query, state.get("snapshot") or {}, state.get("goals") or [], state.get("memories") or []
    )

    final = None
    text_parts = []
    for chunk in llm_client.stream(
        prompt=prompt, fallback=fallback, system_prompt=SYSTEM_PROMPT, temperature=0.7
    ):
        if chunk["type"] == "token":
            text_parts.append(chunk["text"])
            yield {"type": "token", "text": chunk["text"]}
        elif chunk["type"] == "done":
            final = chunk["result"]

    reply = "".join(text_parts).strip() or (final.text if final else fallback)
    synthesis_step = {
        "node": "AI Synthesis",
        "detail": (
            f"Streamed response via {final.provider if final else 'rule_based'}. "
            f"Context: {len(state.get('memories') or [])} memories, "
            f"{len(state.get('goals') or [])} goals."
        ),
    }
    state["trace"] = state["trace"] + [synthesis_step]
    yield {"type": "trace", "step": synthesis_step}
    yield {"type": "done", "reply": reply, "trace": state["trace"], "llm_result": final}


# --- Rule-based fallback (last resort only) --------------------------------

def rule_based_fallback(query: str, snapshot: dict, goals: list, memories: list) -> str:
    """Deterministic fallback - used only when every LLM provider fails."""
    q = (query or "").lower()

    if "afford" in q:
        import re
        nums = re.findall(r"[\d,]+", q.replace("₹", "").replace("rs", "").replace("inr", ""))
        amount = None
        for n in nums:
            cleaned = n.replace(",", "")
            if cleaned.isdigit() and int(cleaned) > 0:
                amount = float(cleaned)
                break
        cash_flow = snapshot.get("cash_flow", 0)

        if amount and cash_flow > 0 and amount <= cash_flow * 0.5:
            return f"Yes - Rs {amount:,.0f} is within reach. You have Rs {cash_flow:,.0f} in free cash flow this month."
        if amount and cash_flow > 0 and amount <= cash_flow:
            return f"It's affordable but tight. Rs {amount:,.0f} uses {(amount / cash_flow * 100):.0f}% of your monthly cash flow."
        if amount:
            return f"Not comfortably this month - you'd need about {max(1, round(amount / max(cash_flow, 1)))} months of savings."
        return f"Your current free cash flow is Rs {cash_flow:,.0f}/month."

    if "overspend" in q or "spending more" in q:
        cats = snapshot.get("top_expense_categories", [])
        if cats:
            return (
                f"Your biggest category is '{cats[0]['category']}' at Rs {cats[0]['amount']:,.0f}. "
                f"Savings rate: {snapshot.get('savings_rate', 0)}%."
            )
        return "I need more transaction data to identify overspending patterns."

    if "save" in q and "how" in q:
        return (
            f"Currently saving at {snapshot.get('savings_rate', 0)}% of income. "
            f"Target 25-30% for healthy growth."
        )

    return (
        f"Your Financial Health Score is {snapshot.get('financial_health_score', 0)}/100 "
        f"with Rs {snapshot.get('cash_flow', 0):,.0f} monthly cash flow and "
        f"{snapshot.get('savings_rate', 0)}% savings rate."
    )


# Backwards-compatible alias for the old private name.
_rule_based_fallback = rule_based_fallback
