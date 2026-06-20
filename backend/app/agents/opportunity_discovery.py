"""
Opportunity Discovery Agent — AI-enhanced proactive insights.

Keeps the solid rule-based detection logic.
NEW: LLM enriches insight descriptions with personalized advice.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .. import models
from ..services import llm_client


def discover(db: Session, user_id: int) -> list:
    txns = db.query(models.Transaction).filter(models.Transaction.user_id == user_id).all()
    goals = db.query(models.Goal).filter(models.Goal.user_id == user_id).order_by(models.Goal.priority).all()
    insights = []

    insights += _detect_subscriptions(txns, goals)
    insights += _detect_spending_leaks(txns, goals)
    insights += _detect_unusual_spending(txns)

    # Rank by potential monthly impact, descending
    insights.sort(key=lambda x: -x.get("monthly_impact", 0))
    
    # AI-enhance top insights
    if insights:
        insights = _ai_enhance_insights(insights, goals)
    
    return insights


def _ai_enhance_insights(insights: list, goals: list) -> list:
    """Use LLM to make insight descriptions more actionable and personalized."""
    top_goal = goals[0] if goals else None
    goal_name = top_goal.name if top_goal else "your financial goals"
    
    insight_summaries = []
    for ins in insights[:5]:  # Enhance top 5 only
        insight_summaries.append(f"- {ins['title']}: {ins['description']}")
    
    prompt = f"""You are a financial advisor. I have these spending insights for a user. 
Rewrite EACH insight's description to be more actionable and personalized. Their top goal is '{goal_name}'.

Insights:
{chr(10).join(insight_summaries)}

For each insight, respond with a JSON array of objects with "index" (0-based) and "enhanced_description" keys.
Keep descriptions concise (1-2 sentences each). Use ₹ with Indian formatting."""

    try:
        result = llm_client.generate_json(
            prompt=prompt,
            fallback=[],
        )
        
        if isinstance(result, list):
            for item in result:
                idx = item.get("index", -1)
                desc = item.get("enhanced_description", "")
                if 0 <= idx < len(insights) and desc:
                    insights[idx]["description"] = desc
    except Exception:
        pass  # Keep original descriptions if AI enhancement fails
    
    return insights


def _months_to_goal_acceleration(goal, extra_monthly):
    if not goal or goal.monthly_contribution <= 0 or extra_monthly <= 0:
        return None
    remaining = max(goal.target_amount - goal.current_amount, 0)
    current_months = remaining / goal.monthly_contribution if goal.monthly_contribution else None
    new_months = remaining / (goal.monthly_contribution + extra_monthly)
    if current_months is None:
        return None
    return round(current_months - new_months, 1)


def _detect_subscriptions(txns, goals):
    """Recurring small-amount transactions in the same category = likely subscriptions."""
    recurring = defaultdict(list)
    for t in txns:
        if t.is_recurring and t.amount < 0:
            recurring[(t.category, t.merchant)].append(t)

    insights = []
    top_goal = goals[0] if goals else None
    for (category, merchant), items in recurring.items():
        if len(items) >= 2:
            monthly_amount = abs(items[0].amount)
            accel = _months_to_goal_acceleration(top_goal, monthly_amount)
            text = f"'{merchant or category}' is a recurring ₹{monthly_amount:,.0f}/month charge."
            if accel:
                text += f" Cancelling it could reach '{top_goal.name}' about {accel} months earlier."
            insights.append({
                "type": "subscription",
                "title": f"Recurring charge: {merchant or category}",
                "description": text,
                "monthly_impact": monthly_amount,
            })
    return insights


def _detect_spending_leaks(txns, goals):
    cat_totals = defaultdict(float)
    cat_counts = defaultdict(int)
    for t in txns:
        if t.amount < 0:
            cat_totals[t.category] += -t.amount
            cat_counts[t.category] += 1

    if not cat_totals:
        return []

    total_spend = sum(cat_totals.values())
    insights = []
    top_goal = goals[0] if goals else None

    for category, total in cat_totals.items():
        share = total / total_spend if total_spend else 0
        if share > 0.12 and cat_counts[category] >= 3:
            reducible = total * 0.2
            accel = _months_to_goal_acceleration(top_goal, reducible)
            text = f"'{category}' makes up {share*100:.0f}% of your spending (₹{total:,.0f})."
            if accel:
                text += f" Reducing by 20% (₹{reducible:,.0f}/month) gets you to '{top_goal.name}' {accel} months sooner."
            else:
                text += f" A 20% cut would free up ₹{reducible:,.0f}/month."
            insights.append({
                "type": "spending_leak",
                "title": f"Spending leak: {category}",
                "description": text,
                "monthly_impact": reducible,
            })
    return insights


def _detect_unusual_spending(txns):
    """Flags transactions significantly larger than typical spend in that category."""
    cat_amounts = defaultdict(list)
    for t in txns:
        if t.amount < 0:
            cat_amounts[t.category].append(-t.amount)

    insights = []
    for category, amounts in cat_amounts.items():
        if len(amounts) < 3:
            continue
        avg = sum(amounts) / len(amounts)
        for amt in amounts:
            if amt > avg * 2.5 and amt > 1000:
                insights.append({
                    "type": "unusual_spending",
                    "title": f"Unusual spike in {category}",
                    "description": (
                        f"A ₹{amt:,.0f} transaction in '{category}' is over 2.5x your typical ₹{avg:,.0f} spend."
                    ),
                    "monthly_impact": 0,
                })
                break
    return insights
