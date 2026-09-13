"""
Opportunity Discovery Agent - proactive insights.

Deterministic detection (subscriptions, spending leaks, unusual spikes) with an
optional LLM pass that rewrites the copy to be personal and actionable.

The LLM pass is cached against a fingerprint of the user's transactions. It used
to run on every /api/insights call - which the dashboard fires on mount - so a
user refreshing three times paid for three identical enrichments.
"""
import logging
from collections import defaultdict

from sqlalchemy.orm import Session

from .. import models
from ..services import llm_client, cache, financial_twin, prompt_safety, entitlements

logger = logging.getLogger("finmate.insights")

CACHE_KIND = "insights"


def discover(db: Session, user_id: int, use_cache: bool = True, user=None) -> list:
    """
    Return ranked insights. Cheap deterministic detection always runs; the LLM
    enrichment is served from cache when the underlying data is unchanged.
    """
    fingerprint = financial_twin.transactions_fingerprint(db, user_id)

    if use_cache:
        cached = cache.get(db, user_id, CACHE_KIND, fingerprint)
        if cached is not None:
            logger.debug("Insights cache hit for user=%s", user_id)
            return cached

    txns = db.query(models.Transaction).filter(models.Transaction.user_id == user_id).all()
    goals = (
        db.query(models.Goal)
        .filter(models.Goal.user_id == user_id)
        .order_by(models.Goal.priority)
        .all()
    )

    insights = []
    insights += _detect_subscriptions(txns, goals)
    insights += _detect_spending_leaks(txns, goals)
    insights += _detect_unusual_spending(txns)

    # Rank by potential monthly impact, descending
    insights.sort(key=lambda x: -x.get("monthly_impact", 0))

    ai_allowed = user is None or entitlements.feature_enabled(user, "ai_insights")
    if insights and ai_allowed and llm_client.llm_configured():
        insights = _ai_enhance_insights(insights, goals, db, user_id)

    if use_cache:
        cache.put(db, user_id, CACHE_KIND, fingerprint, insights)

    return insights


def _ai_enhance_insights(insights: list, goals: list, db: Session, user_id: int) -> list:
    """Rewrite the top insights' descriptions to be actionable and personal."""
    top_goal = goals[0] if goals else None
    goal_name = prompt_safety.scrub(top_goal.name, 60) if top_goal else "their financial goals"

    summaries = prompt_safety.scrub_lines(
        list(enumerate(insights[:5])),
        lambda pair: (
            f"{pair[0]}. {prompt_safety.scrub(pair[1]['title'], 80)}: "
            f"{prompt_safety.scrub(pair[1]['description'], 300)}"
        ),
    )

    prompt = f"""Rewrite each spending insight's description so it is more actionable and personal.
The user's top goal is '{goal_name}'.

{prompt_safety.fence("detected insights", summaries)}

Respond with a JSON array of objects with "index" (the number shown above) and
"enhanced_description". Keep each description to 1-2 sentences. Use Rs with
Indian digit grouping. Do not invent numbers that are not present above."""

    try:
        result = llm_client.generate_detailed(
            prompt=prompt + "\n\nRespond with valid JSON only. No markdown, no code fences.",
            fallback="[]",
            system_prompt=(
                "You are FinMate, an AI financial advisor. Be concise and data-driven."
                + prompt_safety.UNTRUSTED_DATA_NOTICE
            ),
            temperature=0.3,
        )
        entitlements.record_usage(
            db, user_id, "insights", result.provider, result.model,
            result.prompt_tokens, result.completion_tokens, result.latency_ms, result.ok,
        )

        parsed = llm_client._parse_json(result.text, [])
        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                try:
                    idx = int(item.get("index", -1))
                except (TypeError, ValueError):
                    continue
                desc = (item.get("enhanced_description") or "").strip()
                if 0 <= idx < len(insights) and desc:
                    insights[idx]["description"] = desc
                    insights[idx]["ai_enhanced"] = True
    except Exception as e:
        logger.warning("Insight enhancement failed: %s - keeping deterministic copy.", e)

    return insights


def _months_to_goal_acceleration(goal, extra_monthly):
    if not goal or goal.monthly_contribution <= 0 or extra_monthly <= 0:
        return None
    remaining = max(goal.target_amount - goal.current_amount, 0)
    current_months = remaining / goal.monthly_contribution
    new_months = remaining / (goal.monthly_contribution + extra_monthly)
    return round(current_months - new_months, 1)


def _detect_subscriptions(txns, goals):
    """Recurring same-merchant charges are likely subscriptions."""
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
            label = merchant or category or "Unknown"
            text = f"'{label}' is a recurring Rs {monthly_amount:,.0f}/month charge."
            if accel:
                text += f" Cancelling it could reach '{top_goal.name}' about {accel} months earlier."
            insights.append({
                "type": "subscription",
                "title": f"Recurring charge: {label}",
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
            text = f"'{category}' makes up {share * 100:.0f}% of your spending (Rs {total:,.0f})."
            if accel:
                text += (
                    f" Reducing by 20% (Rs {reducible:,.0f}/month) gets you to "
                    f"'{top_goal.name}' {accel} months sooner."
                )
            else:
                text += f" A 20% cut would free up Rs {reducible:,.0f}/month."
            insights.append({
                "type": "spending_leak",
                "title": f"Spending leak: {category}",
                "description": text,
                "monthly_impact": reducible,
            })
    return insights


def _detect_unusual_spending(txns):
    """Flag transactions much larger than the usual spend in that category."""
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
                        f"A Rs {amt:,.0f} transaction in '{category}' is over 2.5x "
                        f"your typical Rs {avg:,.0f} spend."
                    ),
                    "monthly_impact": 0,
                })
                break
    return insights
