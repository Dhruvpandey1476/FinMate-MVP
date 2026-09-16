"""
Wedding contributors, Family Wealth, Credit Health and donations.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..auth import get_current_user
from ..services import family as family_service, credit_health, cache, analytics

logger = logging.getLogger("finmate.tier4")

router = APIRouter(prefix="/api", tags=["Family, Credit & Giving"])


# --- Wedding / shared-goal contributors -------------------------------------

class ContributorIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    relationship_label: str = Field("family", max_length=40)
    monthly_amount: float = Field(0, ge=0)
    committed_lump_sum: float = Field(0, ge=0)
    contributed_so_far: float = Field(0, ge=0)


def _owned_goal(db: Session, user_id: int, goal_id: int) -> models.Goal:
    goal = (
        db.query(models.Goal)
        .filter(models.Goal.id == goal_id, models.Goal.user_id == user_id)
        .first()
    )
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found.")
    return goal


@router.get("/goals/{goal_id}/contributors")
def list_contributors(goal_id: int, db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)):
    goal = _owned_goal(db, user.id, goal_id)
    rows = db.query(models.GoalContributor).filter(
        models.GoalContributor.goal_id == goal.id
    ).all()

    pledged_monthly = sum(c.monthly_amount or 0 for c in rows)
    pledged_lump = sum(c.committed_lump_sum or 0 for c in rows)
    contributed = sum(c.contributed_so_far or 0 for c in rows)
    remaining = max(goal.target_amount - goal.current_amount, 0)

    return {
        "goal": {"id": goal.id, "name": goal.name, "target": goal.target_amount,
                 "saved": goal.current_amount, "remaining": round(remaining, 2)},
        "contributors": [
            {"id": c.id, "name": c.name, "relationship": c.relationship_label,
             "monthly_amount": c.monthly_amount,
             "committed_lump_sum": c.committed_lump_sum,
             "contributed_so_far": c.contributed_so_far,
             "share_of_monthly": round(
                 (c.monthly_amount / pledged_monthly * 100), 1
             ) if pledged_monthly else 0}
            for c in rows
        ],
        "pledged_monthly": round(pledged_monthly, 2),
        "pledged_lump_sum": round(pledged_lump, 2),
        "contributed_so_far": round(contributed, 2),
        "months_to_target": (
            round(max(remaining - pledged_lump, 0) / pledged_monthly, 1)
            if pledged_monthly > 0 else None
        ),
    }


@router.post("/goals/{goal_id}/contributors")
def add_contributor(goal_id: int, payload: ContributorIn,
                    db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    goal = _owned_goal(db, user.id, goal_id)
    row = models.GoalContributor(goal_id=goal.id, **payload.model_dump())
    db.add(row)

    # The goal's own monthly contribution is the sum of what everyone pledged,
    # so the planner and every projection stay consistent with the line items.
    db.flush()
    total = sum(
        c.monthly_amount or 0
        for c in db.query(models.GoalContributor).filter(
            models.GoalContributor.goal_id == goal.id)
    )
    goal.monthly_contribution = total
    db.commit()
    db.refresh(row)

    cache.invalidate(db, user.id)
    return {"ok": True, "id": row.id, "goal_monthly_contribution": total}


@router.delete("/goals/{goal_id}/contributors/{contributor_id}")
def remove_contributor(goal_id: int, contributor_id: int,
                       db: Session = Depends(get_db),
                       user: models.User = Depends(get_current_user)):
    goal = _owned_goal(db, user.id, goal_id)
    row = (
        db.query(models.GoalContributor)
        .filter(models.GoalContributor.id == contributor_id,
                models.GoalContributor.goal_id == goal.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Contributor not found.")
    db.delete(row)
    db.flush()
    goal.monthly_contribution = sum(
        c.monthly_amount or 0
        for c in db.query(models.GoalContributor).filter(
            models.GoalContributor.goal_id == goal.id)
    )
    db.commit()
    cache.invalidate(db, user.id)
    return {"ok": True}


# --- Family Wealth ----------------------------------------------------------

class InviteIn(BaseModel):
    email: str
    display_name: str | None = Field(None, max_length=80)
    role: str = "viewer"
    share_net_worth: bool = True
    share_goals: bool = True
    share_transactions: bool = False


@router.get("/family")
def family_view(db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    """The household picture, filtered by what each member actually shared."""
    return {
        **family_service.family_twin(db, user),
        "shared_with_me": [
            {"owner_id": l.owner_id, "role": l.role, "since": l.accepted_at}
            for l in family_service.shared_with_me(db, user)
        ],
    }


@router.post("/family/invite")
def invite_member(payload: InviteIn, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    try:
        link = family_service.invite(
            db, user.id, payload.email, payload.display_name, payload.role,
            payload.share_net_worth, payload.share_goals, payload.share_transactions,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    analytics.track(db, user.id, "family_invite_sent", {"role": payload.role})
    return {
        "ok": True,
        "id": link.id,
        "status": link.status,
        # Surfaced so an invite can be shared directly. A real deployment would
        # email this rather than return it.
        "invite_token": link.invite_token,
        "message": f"Invited {link.invited_email}. Nothing is shared until they accept.",
    }


@router.post("/family/accept")
def accept_invite(token: str, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    try:
        link = family_service.accept(db, user, token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    analytics.track(db, user.id, "family_invite_accepted")
    return {"ok": True, "owner_id": link.owner_id, "role": link.role}


@router.delete("/family/{link_id}")
def revoke_member(link_id: int, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    if not family_service.revoke(db, user.id, link_id):
        raise HTTPException(status_code=404, detail="Member not found.")
    return {"ok": True}


# --- Credit Health ----------------------------------------------------------

@router.get("/credit-health")
def credit(db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)):
    """FinMate's own credit-readiness assessment. Not a bureau score."""
    return credit_health.assess(db, user.id)


# --- Donations (DAAN) -------------------------------------------------------

class DonationIn(BaseModel):
    recipient: str = Field(..., min_length=1, max_length=120)
    amount: float = Field(..., gt=0)
    donated_on: datetime | None = None
    is_80g_eligible: bool = False
    receipt_ref: str | None = Field(None, max_length=80)
    note: str | None = Field(None, max_length=200)


@router.get("/donations")
def list_donations(db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    rows = (
        db.query(models.Donation)
        .filter(models.Donation.user_id == user.id)
        .order_by(models.Donation.donated_on.desc())
        .all()
    )
    total = sum(d.amount for d in rows)
    eligible = sum(d.amount for d in rows if d.is_80g_eligible)
    return {
        "donations": [
            {"id": d.id, "recipient": d.recipient, "amount": d.amount,
             "donated_on": d.donated_on, "is_80g_eligible": d.is_80g_eligible,
             "receipt_ref": d.receipt_ref, "note": d.note}
            for d in rows
        ],
        "total": round(total, 2),
        "eligible_total": round(eligible, 2),
        "note": (
            "80G eligibility is whatever you marked it as. Whether an institution "
            "is registered under 80G is a fact about that institution which "
            "FinMate cannot verify - check your receipt."
        ),
    }


@router.post("/donations")
def add_donation(payload: DonationIn, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    row = models.Donation(
        user_id=user.id,
        recipient=payload.recipient,
        amount=payload.amount,
        donated_on=payload.donated_on or datetime.utcnow(),
        is_80g_eligible=payload.is_80g_eligible,
        receipt_ref=payload.receipt_ref,
        note=payload.note,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    cache.invalidate(db, user.id)
    return {"ok": True, "id": row.id}


@router.delete("/donations/{donation_id}")
def delete_donation(donation_id: int, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    row = (
        db.query(models.Donation)
        .filter(models.Donation.id == donation_id,
                models.Donation.user_id == user.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Donation not found.")
    db.delete(row)
    db.commit()
    cache.invalidate(db, user.id)
    return {"ok": True}
