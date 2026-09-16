"""
B2B Intelligence API - "give us transactions, get back intelligence".

A deliberately separate, versioned surface from the consumer routes. A partner
integrates against a stateless contract: they post a batch of transactions and
a little profile context, and get back the same analysis the consumer product
runs, with no FinMate account involved.

It reuses the existing services rather than reimplementing them, which is the
point: the intelligence a neobank would pay for is the intelligence the app
already computes.

Out of scope here and stated plainly: no partner dashboard, no billing, no
multi-tenant auth. The API key check below is a single shared demo key.
"""
import logging
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..services import financial_twin, categorizer
from ..services import next_best_action_stateless as nba_stateless

logger = logging.getLogger("finmate.b2b")

router = APIRouter(prefix="/api/v1/b2b", tags=["B2B Intelligence API"])

B2B_API_KEY = os.getenv("B2B_API_KEY", "demo-partner-key")


class TransactionIn(BaseModel):
    date: datetime = Field(..., description="Transaction date")
    amount: float = Field(..., description="Negative for spend, positive for income")
    description: str | None = Field(None, description="Merchant or narration")
    category: str | None = Field(None, description="Optional; inferred when absent")


class ProfileIn(BaseModel):
    monthly_income: float | None = Field(None, ge=0)
    total_assets: float | None = Field(None, ge=0)
    total_liabilities: float | None = Field(None, ge=0)
    monthly_obligations: float | None = Field(None, ge=0)
    goal_target: float | None = Field(None, ge=0, description="Optional savings goal")
    goal_saved: float | None = Field(None, ge=0)


class AnalyzeIn(BaseModel):
    external_user_ref: str = Field(..., max_length=120,
                                   description="Your own id for this customer")
    transactions: list[TransactionIn] = Field(..., min_length=1, max_length=5000)
    profile: ProfileIn = Field(default_factory=ProfileIn)


def _require_key(x_api_key: str | None):
    if not x_api_key or x_api_key != B2B_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key.")


@router.post("/analyze", summary="Analyse a customer's transactions")
def analyze(payload: AnalyzeIn, x_api_key: str | None = Header(None, alias="X-API-Key")):
    """
    Return FinMate's analysis for one customer, statelessly.

    Nothing is persisted: the batch is analysed and discarded. That keeps the
    contract simple for a partner and means this endpoint holds no personal
    data of theirs at rest.
    """
    _require_key(x_api_key)

    txns = payload.transactions
    profile = payload.profile

    # --- Normalised monthly figures ---------------------------------------
    by_month: dict[str, dict] = {}
    for t in txns:
        key = t.date.strftime("%Y-%m")
        bucket = by_month.setdefault(key, {"income": 0.0, "expense": 0.0})
        if t.amount > 0:
            bucket["income"] += t.amount
        else:
            bucket["expense"] += -t.amount

    months = max(len(by_month), 1)
    total_income = sum(b["income"] for b in by_month.values())
    total_expense = sum(b["expense"] for b in by_month.values())

    monthly_income = profile.monthly_income or (total_income / months)
    monthly_expense = total_expense / months
    cash_flow = monthly_income - monthly_expense
    savings_rate = (cash_flow / monthly_income * 100) if monthly_income > 0 else 0

    # --- Categories, inferred where the partner did not supply them -------
    categories: dict[str, float] = {}
    for t in txns:
        if t.amount >= 0:
            continue
        # Keyword matching only: a stateless call has no account, so there are
        # no per-user learned rules to consult.
        category = t.category or _keyword_only(t.description or "", t.amount)
        categories[category] = categories.get(category, 0) + abs(t.amount)

    top = sorted(categories.items(), key=lambda kv: -kv[1])[:5]

    # --- Health score, same function the consumer product uses ------------
    assets = profile.total_assets or 0
    liabilities = profile.total_liabilities or 0
    health = financial_twin.health_score_breakdown(
        savings_rate=savings_rate,
        net_worth=assets - liabilities,
        total_liabilities=liabilities,
        total_income_month=monthly_income,
    )

    action = nba_stateless.recommend(
        monthly_income=monthly_income,
        monthly_expense=monthly_expense,
        categories=categories,
        obligations=profile.monthly_obligations or 0,
        goal_target=profile.goal_target,
        goal_saved=profile.goal_saved,
    )

    goal_projection = None
    if profile.goal_target:
        remaining = max(profile.goal_target - (profile.goal_saved or 0), 0)
        months_needed = (remaining / cash_flow) if cash_flow > 0 else None
        goal_projection = {
            "target": profile.goal_target,
            "saved": profile.goal_saved or 0,
            "remaining": round(remaining, 2),
            "months_at_current_pace": round(months_needed, 1) if months_needed else None,
            "achievable": months_needed is not None,
        }

    return {
        "external_user_ref": payload.external_user_ref,
        "analysed_at": datetime.utcnow().isoformat(),
        "months_of_data": months,
        "financial_health_score": health["score"],
        "health_breakdown": health["components"],
        "savings_rate": round(savings_rate, 2),
        "monthly_income": round(monthly_income, 2),
        "monthly_expense": round(monthly_expense, 2),
        "monthly_cash_flow": round(cash_flow, 2),
        "top_categories": [
            {"category": c, "monthly_average": round(v / months, 2)} for c, v in top
        ],
        "top_next_best_action": action,
        "goal_projection_summary": goal_projection,
        "disclaimer": (
            "Derived from the transactions supplied in this request. Nothing is "
            "stored. Not investment advice."
        ),
    }


def _keyword_only(description: str, amount: float) -> str:
    """Category from keywords alone - no DB, so no per-user learned rules."""
    lowered = (description or "").lower()
    for category, words in categorizer.KEYWORDS:
        if any(w in lowered for w in words):
            if amount > 0 and category not in (
                "Salary", "Freelance", "Investment Returns", "Other Income", "Transfer"
            ):
                continue
            return category
    return "Other Income" if amount > 0 else "Other"


@router.get("/health", summary="Partner-facing health check")
def b2b_health(x_api_key: str | None = Header(None, alias="X-API-Key")):
    _require_key(x_api_key)
    return {"status": "ok", "version": "v1"}
