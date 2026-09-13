"""
Tier 1 Core Loop endpoints: Safe-to-Spend, Early Warning, Time Machine,
Next Best Action.

These are the four faces of one continuously-reasoning system - understand,
predict, decide, warn - so they share a router and a `/api/dashboard/core`
aggregate that the new Dashboard can fetch in a single round trip.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..auth import get_current_user, require_quota
from ..services import safe_to_spend as sts_service, cache, financial_twin
from ..agents import early_warning, next_best_action, scenario_simulator

logger = logging.getLogger("finmate.dashboard")

router = APIRouter(prefix="/api", tags=["Core Loop"])


# --- Safe-to-Spend ---------------------------------------------------------

@router.get("/safe-to-spend")
def get_safe_to_spend(horizon_days: int = 14, db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)):
    """Spendable today, with the full breakdown behind the number."""
    return sts_service.compute(db, user.id, horizon_days=horizon_days)


class CheckpointIn(BaseModel):
    balance: float = Field(..., ge=0)
    as_of: datetime | None = None
    note: str | None = Field(None, max_length=200)


@router.post("/balance-checkpoint")
def add_checkpoint(payload: CheckpointIn, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    """
    Confirm the real account balance.

    Without an Account Aggregator feed this is how the ledger stays anchored to
    reality; the UI nudges for it weekly but never requires it.
    """
    checkpoint = sts_service.add_checkpoint(
        db, user.id, payload.balance, as_of=payload.as_of, note=payload.note,
    )
    cache.invalidate(db, user.id)
    return {
        "ok": True,
        "checkpoint": {
            "id": checkpoint.id,
            "balance": checkpoint.balance,
            "as_of": checkpoint.as_of,
        },
        "safe_to_spend": sts_service.compute(db, user.id),
    }


@router.get("/balance-checkpoint")
def latest_checkpoint(db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)):
    checkpoint = sts_service.latest_checkpoint(db, user.id)
    if not checkpoint:
        return {"exists": False}
    return {
        "exists": True,
        "balance": checkpoint.balance,
        "as_of": checkpoint.as_of,
        "stale_days": (datetime.utcnow() - checkpoint.as_of).days,
    }


# --- Early Warning ---------------------------------------------------------

@router.get("/early-warning")
def get_early_warning(db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)):
    """Active nudges, most urgent first."""
    warnings = early_warning.check(db, user.id)
    return {
        "count": len(warnings),
        "highest_severity": warnings[0]["severity"] if warnings else None,
        "warnings": warnings,
    }


# --- Time Machine ----------------------------------------------------------

class TimeMachineIn(BaseModel):
    months: int = Field(12, ge=1, le=360)
    what_if_amount: float | None = Field(None, description="A one-off purchase to model")
    what_if_monthly: float | None = Field(None, description="A recurring monthly change")


def _time_machine(db: Session, user_id: int, months: int,
                  what_if_amount=None, what_if_monthly=None) -> dict:
    """
    Friendlier shape over the existing scenario simulator.

    No new projection maths - agents/scenario_simulator already models
    inflation, tax and compounding, and duplicating it here would guarantee the
    two drift apart.
    """
    base = scenario_simulator.simulate(
        db, user_id, "savings", amount=0, months_ahead=months,
    )
    if "error" in base:
        raise HTTPException(status_code=400, detail=base["error"])

    baseline = [p["projected_net_worth"] for p in base["baseline"]]
    real = [p["real_net_worth"] for p in base["baseline"]]

    projected = baseline
    what_if = None
    if what_if_amount:
        scenario = scenario_simulator.simulate(
            db, user_id, "purchase", amount=what_if_amount, months_ahead=months,
        )
        projected = [p["projected_net_worth"] for p in scenario["projected"]]
        what_if = {
            "type": "purchase",
            "amount": what_if_amount,
            "delta_at_end": round(projected[-1] - baseline[-1], 2),
            "opportunity_cost": scenario.get("opportunity_cost"),
            "true_cost": scenario.get("true_cost"),
            "summary": scenario.get("summary"),
        }
    elif what_if_monthly:
        scenario = scenario_simulator.simulate(
            db, user_id, "savings", amount=what_if_monthly, months_ahead=months,
        )
        projected = [p["projected_net_worth"] for p in scenario["projected"]]
        what_if = {
            "type": "monthly_savings",
            "amount": what_if_monthly,
            "delta_at_end": round(projected[-1] - baseline[-1], 2),
            "summary": scenario.get("summary"),
        }

    now = datetime.utcnow()
    labels = []
    for i in range(1, months + 1):
        m = now.month - 1 + i
        labels.append(f"{now.year + m // 12}-{m % 12 + 1:02d}")

    return {
        "months": months,
        "month_labels": labels,
        "baseline_net_worth": baseline,
        "projected_net_worth": projected,
        "real_net_worth": real,
        "key_moments": _key_moments(db, user_id, projected, labels),
        "what_if": what_if,
        "assumptions": base.get("assumptions", {}),
        "headline": (
            f"{months} months from now, at your current pace, your net worth is "
            f"projected to be Rs {baseline[-1]:,.0f}."
        ),
    }


def _key_moments(db: Session, user_id: int, series: list, labels: list) -> list:
    """Mark the month each goal is reached along the projection."""
    moments = []
    try:
        snapshot = financial_twin.get_snapshot(db, user_id)
        start = snapshot.get("net_worth", 0)

        goals = db.query(models.Goal).filter(models.Goal.user_id == user_id).all()
        for goal in goals:
            remaining = max(goal.target_amount - goal.current_amount, 0)
            if remaining <= 0:
                moments.append({"month_index": 0, "label": labels[0] if labels else "",
                                "title": f"'{goal.name}' already funded", "kind": "goal"})
                continue
            for i, value in enumerate(series):
                if value - start >= remaining:
                    moments.append({
                        "month_index": i,
                        "label": labels[i] if i < len(labels) else "",
                        "title": f"'{goal.name}' reached",
                        "kind": "goal",
                    })
                    break

        monthly_expense = snapshot.get("total_expense_month", 0)
        if monthly_expense > 0:
            target = monthly_expense * 3
            for i, value in enumerate(series):
                if value - start >= target:
                    moments.append({
                        "month_index": i,
                        "label": labels[i] if i < len(labels) else "",
                        "title": "3 months of expenses covered",
                        "kind": "emergency_fund",
                    })
                    break
    except Exception as e:
        logger.warning("Key moments failed for user %s: %s", user_id, e)

    moments.sort(key=lambda m: m["month_index"])
    return moments


@router.get("/time-machine")
def time_machine_get(months: int = 12, db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)):
    return _time_machine(db, user.id, months)


@router.post("/time-machine")
def time_machine_post(payload: TimeMachineIn,
                      db: Session = Depends(get_db),
                      user: models.User = Depends(require_quota("simulate"))):
    """What-if runs are metered like any other simulation."""
    return _time_machine(db, user.id, payload.months,
                         payload.what_if_amount, payload.what_if_monthly)


# --- Next Best Action ------------------------------------------------------

@router.get("/next-best-action")
def get_next_best_action(refresh: bool = False, db: Session = Depends(get_db),
                         user: models.User = Depends(get_current_user)):
    """
    The single highest-value thing to do next.

    Cached against the transaction fingerprint: the ranking is deterministic,
    so recomputing it on every dashboard mount would re-bill the phrasing call
    for an identical answer.
    """
    fingerprint = financial_twin.transactions_fingerprint(db, user.id)
    if not refresh:
        cached = cache.get(db, user.id, "next_best_action", fingerprint)
        if cached is not None:
            return cached

    result = next_best_action.run(db, user.id, user=user)
    cache.put(db, user.id, "next_best_action", fingerprint, result)
    return result


@router.get("/next-best-action/candidates")
def get_candidates(db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    """
    Every candidate with its score.

    Exposed deliberately: it makes the claim "a deterministic function decides,
    the model only explains" checkable rather than asserted.
    """
    return {"candidates": next_best_action.collect_candidates(db, user.id, user)}


# --- Aggregate -------------------------------------------------------------

@router.get("/dashboard/core")
def core_loop(db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user)):
    """Everything the new Dashboard hero needs, in one round trip."""
    out = {}
    for key, fn in (
        ("safe_to_spend", lambda: sts_service.compute(db, user.id)),
        ("early_warning", lambda: early_warning.check(db, user.id)),
        ("time_machine", lambda: _time_machine(db, user.id, 12)),
        ("next_best_action", lambda: get_next_best_action(False, db, user)),
    ):
        try:
            out[key] = fn()
        except Exception as e:
            # One failing panel must not blank the whole dashboard.
            logger.error("Core loop section '%s' failed: %s", key, e, exc_info=True)
            out[key] = None
    return out
