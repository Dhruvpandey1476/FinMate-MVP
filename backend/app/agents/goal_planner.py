"""
Goal Planner Agent — AI-enhanced goal planning with actionable milestones.

Keeps the solid deterministic milestone math.
NEW: LLM generates personalized recommendation text.
"""
import math
from datetime import datetime
from sqlalchemy.orm import Session
from .. import models
from ..services import financial_twin, llm_client

GOAL_TEMPLATES = {
    "emergency_fund": {"label": "Emergency Fund", "default_months_of_expenses": 6},
    "vehicle": {"label": "Vehicle"},
    "home": {"label": "Home Down Payment"},
    "education": {"label": "Education"},
    "startup": {"label": "Startup Fund"},
    "custom": {"label": "Custom Goal"},
}


def plan_for_goal(db: Session, user_id: int, goal_id: int) -> dict:
    goal = db.query(models.Goal).filter(models.Goal.id == goal_id, models.Goal.user_id == user_id).first()
    if not goal:
        return {"error": "Goal not found"}

    snapshot = financial_twin.get_snapshot(db, user_id)
    remaining = max(goal.target_amount - goal.current_amount, 0)

    available_for_goal = goal.monthly_contribution if goal.monthly_contribution > 0 else max(snapshot["cash_flow"] * 0.3, 0)

    months_needed = math.ceil(remaining / available_for_goal) if available_for_goal > 0 else None

    milestones = []
    running = goal.current_amount
    if available_for_goal > 0 and months_needed:
        checkpoint_every = max(1, months_needed // 4)
        for m in range(1, months_needed + 1):
            running += available_for_goal
            if m % checkpoint_every == 0 or m == months_needed:
                milestones.append({
                    "month": m,
                    "cumulative_amount": round(min(running, goal.target_amount), 2),
                    "percent_complete": round(min(running, goal.target_amount) / goal.target_amount * 100, 1),
                })

    # AI-generated recommendation
    recommendation = _ai_recommendation(goal, remaining, available_for_goal, months_needed, snapshot)

    return {
        "goal": {
            "id": goal.id,
            "name": goal.name,
            "goal_type": goal.goal_type,
            "target_amount": goal.target_amount,
            "current_amount": goal.current_amount,
        },
        "remaining_amount": round(remaining, 2),
        "recommended_monthly_contribution": round(available_for_goal, 2),
        "months_to_complete": months_needed,
        "milestones": milestones,
        "recommendation": recommendation,
    }


def _ai_recommendation(goal, remaining, available_for_goal, months_needed, snapshot) -> str:
    """Generate AI-powered recommendation for goal planning."""
    prompt = f"""You are a financial advisor. Generate a 2-3 sentence actionable recommendation for this goal.

Goal: {goal.name} ({goal.goal_type})
Target: ₹{goal.target_amount:,.0f}
Current progress: ₹{goal.current_amount:,.0f} ({(goal.current_amount/goal.target_amount*100) if goal.target_amount else 0:.0f}%)
Remaining: ₹{remaining:,.0f}
Monthly contribution: ₹{available_for_goal:,.0f}
Estimated months to complete: {months_needed or 'Unknown'}
User's monthly cash flow: ₹{snapshot['cash_flow']:,.0f}
User's savings rate: {snapshot['savings_rate']:.1f}%
User's risk profile: based on their financial health score of {snapshot['financial_health_score']}/100

Give specific, actionable advice. If the goal seems achievable, encourage them. If it's a stretch, suggest practical ways to accelerate. Use ₹ with Indian formatting."""

    fallback = _deterministic_recommendation(goal, remaining, available_for_goal, months_needed, snapshot)
    
    return llm_client.generate(
        prompt=prompt,
        fallback=fallback,
        system_prompt="You are FinMate, an AI financial advisor. Be concise and encouraging.",
        temperature=0.6,
    )


def _deterministic_recommendation(goal, remaining, available_for_goal, months_needed, snapshot) -> str:
    """Fallback recommendation when LLM is unavailable."""
    if available_for_goal <= 0:
        return (
            f"Your current cash flow doesn't leave room for '{goal.name}'. Free up budget first — "
            f"check the Insights page for spending leaks."
        )
    if months_needed and months_needed <= 12:
        return (
            f"At ₹{available_for_goal:,.0f}/month, '{goal.name}' is fully funded in {months_needed} months — "
            f"achievable with your current {snapshot['savings_rate']}% savings rate."
        )
    if months_needed:
        accelerated = math.ceil(remaining / (available_for_goal * 1.3)) if available_for_goal else None
        return (
            f"At current pace, '{goal.name}' takes {months_needed} months. Increasing by 30% "
            f"(to ₹{available_for_goal*1.3:,.0f}/month) cuts that to {accelerated} months."
        )
    return f"Set a monthly contribution for '{goal.name}' to generate a timeline."
