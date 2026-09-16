"""
Next Best Action - orchestration over existing modules.

The design constraint that matters here, and the one an investor is most likely
to probe: **the decision is made in code, not by a model.**

  1. Candidates are gathered from modules that already exist (goal planner,
     opportunity discovery, safe-to-spend, early warning, the twin).
  2. A deterministic scoring function ranks them. Same inputs, same winner,
     every time - it can be unit-tested, and it can be explained on a slide.
  3. Only then is an LLM asked to phrase the chosen action in plain language.
     It never sees the other candidates and cannot change the pick.

Keeping the ranking separate also keeps it honest later: when a recommendation
could lead to a paid partner action, the scoring function is the thing that has
to stay free of commercial weighting, and it is isolated enough to audit.
"""
import logging

from sqlalchemy.orm import Session

from .. import models
from ..services import financial_twin, llm_client, safe_to_spend, prompt_safety, entitlements
from ..agents import goal_planner, opportunity_discovery, early_warning

logger = logging.getLogger("finmate.next_best_action")

# --- Scoring weights -------------------------------------------------------
# Effort is a coarse proxy (1 = one-tap, 5 = sustained behaviour change) because
# nothing in the data model measures real effort. It is declared per candidate
# source rather than guessed per instance, so the ranking stays reproducible.
EFFORT = {
    "cash_flow": 1,        # move money / delay a purchase - immediate
    "subscription": 1,     # cancel once, saves monthly
    "goal_contribution": 3,
    "spending_leak": 4,    # requires changing habits
    "emergency_fund": 3,
}

URGENCY = {
    "cash_flow": 1.0,
    "subscription": 0.45,
    "emergency_fund": 0.6,
    "goal_contribution": 0.4,
    "spending_leak": 0.35,
}

# Rupees of monthly impact treated as "full marks", so impact and urgency are
# on comparable scales instead of impact dominating by magnitude alone.
IMPACT_NORMALISER = 5_000.0

# Commitments a person cannot simply cancel. Recurring-charge detection finds
# rent, EMIs and utilities exactly as reliably as it finds Netflix, and without
# this the top recommendation becomes "eliminate your Rs 18,000 rent" - advice
# that is both useless and discrediting. These are excluded from cancel-style
# candidates; they still appear in the forecast as committed bills.
ESSENTIAL_CATEGORIES = {
    "rent", "utilities", "emi/loan", "emi", "loan", "insurance", "health",
    "education", "childcare", "mortgage", "tax", "salary",
}
ESSENTIAL_KEYWORDS = (
    "rent", "landlord", "electricity", "water", "gas", "emi", "loan",
    "insurance", "premium", "school", "tuition", "mortgage", "utilit",
    "childcare", "medical", "hospital", "pharmacy",
)


def _is_essential(text: str) -> bool:
    """True when a recurring charge is a commitment rather than a choice."""
    lowered = (text or "").strip().lower()
    if lowered in ESSENTIAL_CATEGORIES:
        return True
    return any(word in lowered for word in ESSENTIAL_KEYWORDS)


def _score(candidate: dict) -> float:
    """
    impact-per-unit-effort, lifted by urgency. Pure arithmetic, no model.
    """
    kind = candidate["kind"]
    impact = min(candidate.get("estimated_impact_rupees", 0) / IMPACT_NORMALISER, 2.0)
    effort = EFFORT.get(kind, 3)
    urgency = URGENCY.get(kind, 0.5)
    return round((impact / effort) + (urgency * 1.5), 4)


# --- Candidate collection --------------------------------------------------

def _from_cash_flow(db: Session, user_id: int) -> list:
    out = []
    try:
        warnings = early_warning.check(db, user_id)
        crunch = next((w for w in warnings if w["kind"] == "cash_crunch"), None)
        if crunch:
            out.append({
                "kind": "cash_flow",
                "source": "safe_to_spend",
                "action_text": f"Cover Rs {crunch['amount']:,.0f} of bills due this week",
                "estimated_impact_rupees": crunch["amount"],
                "estimated_impact_months": 0,
                "context": crunch["message"],
            })
    except Exception as e:
        logger.warning("Cash-flow candidates failed: %s", e)
    return out


def _from_insights(db: Session, user_id: int, user) -> list:
    out = []
    try:
        for insight in opportunity_discovery.discover(db, user_id, user=user)[:8]:
            impact = insight.get("monthly_impact", 0)
            if impact <= 0:
                continue
            # Never suggest cancelling something the user is committed to.
            if _is_essential(insight.get("title", "")) or _is_essential(insight.get("category", "")):
                continue
            kind = "subscription" if insight["type"] == "subscription" else "spending_leak"
            out.append({
                "kind": kind,
                "source": "opportunity_discovery",
                "action_text": insight["title"],
                "estimated_impact_rupees": impact,
                "estimated_impact_months": 0,
                "context": insight["description"],
            })
    except Exception as e:
        logger.warning("Insight candidates failed: %s", e)
    return out


def _from_goals(db: Session, user_id: int) -> list:
    out = []
    try:
        goals = (
            db.query(models.Goal)
            .filter(models.Goal.user_id == user_id)
            .order_by(models.Goal.priority)
            .limit(3)
            .all()
        )
        for goal in goals:
            remaining = max(goal.target_amount - goal.current_amount, 0)
            if remaining <= 0 or goal.monthly_contribution <= 0:
                continue
            # What a 20% bump buys, in months saved. Same arithmetic the goal
            # planner already uses - not a second model of goal progress.
            current_months = remaining / goal.monthly_contribution
            bumped = goal.monthly_contribution * 1.2
            new_months = remaining / bumped
            saved = round(current_months - new_months, 1)
            if saved < 0.5:
                continue
            out.append({
                "kind": "goal_contribution",
                "source": "goal_planner",
                "action_text": (
                    f"Add Rs {bumped - goal.monthly_contribution:,.0f}/month to "
                    f"'{goal.name}' to finish {saved:g} months sooner"
                ),
                "estimated_impact_rupees": round(bumped - goal.monthly_contribution, 2),
                "estimated_impact_months": saved,
                "context": (
                    f"'{goal.name}' is Rs {remaining:,.0f} from target at "
                    f"Rs {goal.monthly_contribution:,.0f}/month."
                ),
            })
    except Exception as e:
        logger.warning("Goal candidates failed: %s", e)
    return out


def _from_emergency_fund(db: Session, user_id: int) -> list:
    """Under three months of expense coverage is the classic first priority."""
    out = []
    try:
        snapshot = financial_twin.get_snapshot(db, user_id)
        # Run rate, not the partial current month: on the 2nd of the month the
        # snapshot's expense is near zero and this candidate would never fire.
        run_rate = financial_twin.monthly_run_rate(db, user_id)
        monthly_expense = run_rate["expense"] or snapshot.get("total_expense_month", 0)
        if monthly_expense <= 0:
            return out

        liquid = safe_to_spend.running_balance(db, user_id)["balance"]
        months_covered = liquid / monthly_expense
        if months_covered >= 3:
            return out

        target = monthly_expense * 3
        gap = max(target - liquid, 0)
        cash_flow = max(run_rate["income"] - run_rate["expense"], 0)
        monthly = round(min(max(cash_flow * 0.3, 1000), gap), 2) if cash_flow else 0

        if monthly <= 0:
            return out

        out.append({
            "kind": "emergency_fund",
            "source": "financial_twin",
            "action_text": f"Start an emergency fund with Rs {monthly:,.0f}/month",
            "estimated_impact_rupees": monthly,
            "estimated_impact_months": round(gap / monthly, 1) if monthly else 0,
            "context": (
                f"You have about {months_covered:.1f} months of expenses covered. "
                f"Three months would be Rs {target:,.0f}."
            ),
        })
    except Exception as e:
        logger.warning("Emergency-fund candidate failed: %s", e)
    return out


def collect_candidates(db: Session, user_id: int, user=None) -> list:
    """Every candidate action, scored and ranked. Exposed for testing."""
    candidates = (
        _from_cash_flow(db, user_id)
        + _from_emergency_fund(db, user_id)
        + _from_insights(db, user_id, user)
        + _from_goals(db, user_id)
    )
    for c in candidates:
        c["urgency_score"] = URGENCY.get(c["kind"], 0.5)
        c["effort"] = EFFORT.get(c["kind"], 3)
        c["score"] = _score(c)

    candidates.sort(key=lambda c: -c["score"])
    return candidates


# --- Phrasing (the only place a model is involved) -------------------------

SYSTEM_PROMPT = (
    "You are FinMate's AI CFO. You are given ONE action that has already been "
    "chosen for the user by a deterministic scoring function. Your only job is "
    "to phrase it, and the reason for it, in warm plain English. "
    "Do not suggest a different action. Do not invent numbers. "
    "You are not a SEBI-registered investment adviser: never name a specific "
    "security, fund or product."
    + prompt_safety.UNTRUSTED_DATA_NOTICE
)


def _phrase(db: Session, user_id: int, chosen: dict, snapshot: dict) -> dict:
    """Ask the LLM to word the decision. Falls back to the computed text."""
    fallback_action = chosen["action_text"]
    fallback_why = chosen.get("context", "")

    if not llm_client.llm_configured():
        return {"action_text": fallback_action, "why_text": fallback_why}

    prompt = f"""The chosen action for this user is:

{prompt_safety.fence("chosen action", (
    f"Action: {prompt_safety.scrub(chosen['action_text'], 200)}\\n"
    f"Why it was chosen: {prompt_safety.scrub(chosen.get('context', ''), 400)}\\n"
    f"Estimated impact: Rs {chosen.get('estimated_impact_rupees', 0):,.0f}"
    + (f" and {chosen['estimated_impact_months']} months sooner"
       if chosen.get("estimated_impact_months") else "")
))}

Their situation: monthly cash flow Rs {snapshot.get('cash_flow', 0):,.0f},
savings rate {snapshot.get('savings_rate', 0):.0f}%, health score
{snapshot.get('financial_health_score', 0)}/100.

Respond with JSON only:
{{"action_text": "<one imperative sentence, under 90 characters>",
  "why_text": "<two sentences explaining why this one matters most right now, citing the numbers above>"}}"""

    try:
        result = llm_client.generate_detailed(
            prompt=prompt, fallback="", system_prompt=SYSTEM_PROMPT, temperature=0.4,
        )
        entitlements.record_usage(
            db, user_id, "next_best_action", result.provider, result.model,
            result.prompt_tokens, result.completion_tokens, result.latency_ms, result.ok,
        )
        parsed = llm_client._parse_json(result.text, {})
        if isinstance(parsed, dict) and parsed.get("action_text"):
            return {
                "action_text": str(parsed["action_text"])[:160],
                "why_text": str(parsed.get("why_text") or fallback_why)[:600],
            }
    except Exception as e:
        logger.warning("NBA phrasing failed, using computed text: %s", e)

    return {"action_text": fallback_action, "why_text": fallback_why}


def run(db: Session, user_id: int, user=None, phrase: bool = True) -> dict:
    """
    The single action to put in front of the user right now.

    `phrase=False` returns the deterministic pick without the LLM wording pass.
    The dashboard aggregate uses it on a cold cache: the ranking is instant, but
    the phrasing call is a network round trip that can take tens of seconds on a
    cold host, and blocking the whole dashboard on it risks a gateway timeout
    that leaves the user with no Core Loop at all.
    """
    candidates = collect_candidates(db, user_id, user)

    if not candidates:
        return {
            "action_text": "Add a few transactions so FinMate can find your next move",
            "why_text": "There isn't enough activity yet to rank anything meaningfully.",
            "estimated_impact": 0,
            "source_module": None,
            "considered": 0,
            "decided_by": "deterministic_scoring",
        }

    chosen = candidates[0]
    if phrase:
        snapshot = financial_twin.get_snapshot(db, user_id)
        phrased = _phrase(db, user_id, chosen, snapshot)
    else:
        phrased = {"action_text": chosen["action_text"],
                   "why_text": chosen.get("context", "")}

    return {
        "action_text": phrased["action_text"],
        "why_text": phrased["why_text"],
        "estimated_impact": chosen.get("estimated_impact_rupees", 0),
        "estimated_impact_months": chosen.get("estimated_impact_months", 0),
        "source_module": chosen["source"],
        "kind": chosen["kind"],
        "score": chosen["score"],
        "considered": len(candidates),
        # Surfaced so the UI (and an investor) can see the ranking was not an
        # LLM judgement call.
        "decided_by": "deterministic_scoring",
        "phrased": phrase,
        "runners_up": [
            {"action_text": c["action_text"], "score": c["score"], "source": c["source"]}
            for c in candidates[1:4]
        ],
    }
