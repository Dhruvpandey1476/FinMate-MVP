"""
Stateless Next Best Action, for the B2B API.

Same principle as the consumer version: a deterministic scoring function picks
the action, and no model is involved in the decision. It cannot reuse
agents/next_best_action directly because that one reads a user's goals, memory
and detected bills from the database, and a partner call has no account behind
it - only the batch they posted.

Kept deliberately small. If it grew to duplicate the consumer ranking, the two
would drift and a partner would get different advice from the same data.
"""

# Same effort/urgency shape as the consumer scorer, so the two stay comparable.
EFFORT = {"cash_flow": 1, "subscription": 1, "spending_leak": 4, "emergency_fund": 3}
URGENCY = {"cash_flow": 1.0, "subscription": 0.45, "emergency_fund": 0.6,
           "spending_leak": 0.35}
IMPACT_NORMALISER = 5_000.0

ESSENTIAL = ("rent", "utilities", "emi", "loan", "insurance", "health",
             "education", "mortgage", "tax", "salary")


def _score(kind: str, impact: float) -> float:
    return round(
        (min(impact / IMPACT_NORMALISER, 2.0) / EFFORT.get(kind, 3))
        + URGENCY.get(kind, 0.5) * 1.5,
        4,
    )


def recommend(monthly_income: float, monthly_expense: float, categories: dict,
              obligations: float = 0, goal_target: float = None,
              goal_saved: float = None) -> dict:
    """Return the single highest-scoring action, with how it was chosen."""
    candidates = []
    cash_flow = monthly_income - monthly_expense

    if cash_flow < 0:
        candidates.append({
            "kind": "cash_flow",
            "action": f"Close a monthly shortfall of Rs {abs(cash_flow):,.0f}",
            "impact_rupees": round(abs(cash_flow), 2),
            "rationale": "Spending exceeds income every month, which compounds faster "
                         "than anything else on this list.",
        })

    if monthly_expense > 0 and cash_flow >= 0:
        # Three months of expenses is the standard first buffer.
        target = monthly_expense * 3
        candidates.append({
            "kind": "emergency_fund",
            "action": f"Build an emergency fund of Rs {target:,.0f}",
            "impact_rupees": round(min(cash_flow * 0.3, target), 2),
            "rationale": f"Three months of expenses at the current run rate of "
                         f"Rs {monthly_expense:,.0f}/month.",
        })

    total_spend = sum(categories.values()) or 1
    for category, amount in sorted(categories.items(), key=lambda kv: -kv[1])[:5]:
        # Never suggest cutting a commitment - same rule as the consumer scorer.
        if any(word in category.lower() for word in ESSENTIAL):
            continue
        share = amount / total_spend
        if share < 0.12:
            continue
        candidates.append({
            "kind": "spending_leak",
            "action": f"Reduce {category} spending by 20%",
            "impact_rupees": round(amount * 0.2, 2),
            "rationale": f"{category} is {share * 100:.0f}% of total spending.",
        })

    if not candidates:
        return {
            "action": "No single action stands out",
            "rationale": "Spending is balanced across categories with positive cash flow.",
            "impact_rupees": 0,
            "decided_by": "deterministic_scoring",
            "considered": 0,
        }

    for c in candidates:
        c["score"] = _score(c["kind"], c["impact_rupees"])
    candidates.sort(key=lambda c: -c["score"])

    best = candidates[0]
    return {
        "action": best["action"],
        "rationale": best["rationale"],
        "impact_rupees": best["impact_rupees"],
        "kind": best["kind"],
        "score": best["score"],
        "considered": len(candidates),
        "decided_by": "deterministic_scoring",
    }
