"""
Family Wealth - linked accounts with explicit, granular consent.

Shared finances are the norm for Indian households, so this is real linking
rather than a preview: invite by email, the invitee accepts, and the owner
controls exactly what is visible.

Two rules the rest of the code depends on:

  * Nothing is shared until status is "accepted". A pending invite grants
    nothing, so an invite sent to the wrong address leaks nothing.
  * Consent is per data type. Net worth alone is a very different disclosure
    from every transaction, and a single "share my finances" flag would be too
    blunt to be honest.
"""
import logging
import secrets
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from . import financial_twin

logger = logging.getLogger("finmate.family")

ROLES = ("viewer", "contributor")


def invite(db: Session, owner_id: int, email: str, display_name: str = None,
           role: str = "viewer", share_net_worth: bool = True,
           share_goals: bool = True, share_transactions: bool = False):
    """Invite someone to the family view. Re-inviting updates the grant."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("A valid email is required.")
    if role not in ROLES:
        raise ValueError("Unknown role.")

    existing = (
        db.query(models.FamilyMember)
        .filter(models.FamilyMember.owner_id == owner_id,
                models.FamilyMember.invited_email == email)
        .first()
    )
    link = existing or models.FamilyMember(owner_id=owner_id, invited_email=email)

    link.display_name = display_name or link.display_name or email.split("@")[0]
    link.role = role
    link.share_net_worth = share_net_worth
    link.share_goals = share_goals
    link.share_transactions = share_transactions
    if link.status != "accepted":
        link.status = "pending"
        link.invite_token = secrets.token_urlsafe(24)

    # If that email already has an account, link it now so acceptance is a
    # single tap rather than an email round trip.
    account = db.query(models.User).filter(models.User.email == email).first()
    if account:
        link.member_user_id = account.id

    if not existing:
        db.add(link)
    db.commit()
    db.refresh(link)
    return link


def accept(db: Session, user: models.User, token: str):
    """Accept an invite. Only the invited address can accept it."""
    link = (
        db.query(models.FamilyMember)
        .filter(models.FamilyMember.invite_token == token)
        .first()
    )
    if not link:
        raise ValueError("This invite is not valid.")
    if link.invited_email != (user.email or "").lower():
        raise ValueError("This invite was sent to a different email address.")

    link.member_user_id = user.id
    link.status = "accepted"
    link.accepted_at = datetime.utcnow()
    db.commit()
    db.refresh(link)
    return link


def revoke(db: Session, owner_id: int, link_id: int) -> bool:
    """
    Revoke access.

    Marked revoked rather than deleted so the owner keeps a record that access
    was once granted - quietly erasing that would be the wrong default for a
    consent trail.
    """
    link = (
        db.query(models.FamilyMember)
        .filter(models.FamilyMember.id == link_id,
                models.FamilyMember.owner_id == owner_id)
        .first()
    )
    if not link:
        return False
    link.status = "revoked"
    link.invite_token = None
    db.commit()
    return True


def members(db: Session, owner_id: int) -> list:
    return (
        db.query(models.FamilyMember)
        .filter(models.FamilyMember.owner_id == owner_id,
                models.FamilyMember.status != "revoked")
        .all()
    )


def shared_with_me(db: Session, user: models.User) -> list:
    """Accounts that have shared with this user."""
    return (
        db.query(models.FamilyMember)
        .filter(models.FamilyMember.status == "accepted",
                or_(models.FamilyMember.member_user_id == user.id,
                    models.FamilyMember.invited_email == (user.email or "").lower()))
        .all()
    )


def _member_snapshot(db: Session, link: models.FamilyMember, viewer_is_owner: bool) -> dict:
    """
    One member's contribution to the family view, filtered by their grant.

    The owner sees their own figures in full; everyone else sees only what the
    grant allows, and the response says which fields were withheld rather than
    silently returning zeros.
    """
    user_id = link.member_user_id
    out = {
        "link_id": link.id,
        "name": link.display_name or link.invited_email,
        "email": link.invited_email,
        "role": link.role,
        "status": link.status,
        "linked": user_id is not None,
        "shares": {
            "net_worth": link.share_net_worth,
            "goals": link.share_goals,
            "transactions": link.share_transactions,
        },
    }

    if link.status != "accepted" or not user_id:
        out["net_worth"] = None
        out["note"] = "Invite pending - nothing is shared until it is accepted."
        return out

    if link.share_net_worth or viewer_is_owner:
        snapshot = financial_twin.get_snapshot(db, user_id)
        out["net_worth"] = snapshot["net_worth"]
        out["monthly_cash_flow"] = snapshot["cash_flow"]
        out["health_score"] = snapshot["financial_health_score"]
    else:
        out["net_worth"] = None
        out["note"] = "This member has not shared their net worth."

    if link.share_goals or viewer_is_owner:
        goals = db.query(models.Goal).filter(models.Goal.user_id == user_id).all()
        out["goals"] = [
            {"name": g.name, "target": g.target_amount, "saved": g.current_amount,
             "percent": round((g.current_amount / g.target_amount * 100), 1)
             if g.target_amount else 0}
            for g in goals
        ]
    else:
        out["goals"] = None

    return out


def family_twin(db: Session, owner: models.User) -> dict:
    """
    The combined household picture.

    Totals only include members who actually shared the relevant figure, and
    the response reports how many were excluded - a total that quietly omits
    someone is worse than one that says it is partial.
    """
    links = members(db, owner.id)

    own = financial_twin.get_snapshot(db, owner.id)
    people = [{
        "link_id": None,
        "name": owner.name or "You",
        "email": owner.email,
        "role": "owner",
        "status": "accepted",
        "linked": True,
        "is_owner": True,
        "net_worth": own["net_worth"],
        "monthly_cash_flow": own["cash_flow"],
        "health_score": own["financial_health_score"],
        "goals": [
            {"name": g.name, "target": g.target_amount, "saved": g.current_amount,
             "percent": round((g.current_amount / g.target_amount * 100), 1)
             if g.target_amount else 0}
            for g in db.query(models.Goal).filter(models.Goal.user_id == owner.id).all()
        ],
        "shares": {"net_worth": True, "goals": True, "transactions": True},
    }]

    for link in links:
        people.append(_member_snapshot(db, link, viewer_is_owner=False))

    contributing = [p for p in people if p.get("net_worth") is not None]
    withheld = len(people) - len(contributing)

    return {
        "members": people,
        "combined_net_worth": round(sum(p["net_worth"] for p in contributing), 2),
        "combined_monthly_cash_flow": round(
            sum(p.get("monthly_cash_flow") or 0 for p in contributing), 2
        ),
        "counted": len(contributing),
        "withheld": withheld,
        "pending_invites": len([p for p in people if p["status"] == "pending"]),
        "note": (
            f"{withheld} member(s) have not shared their net worth, so the "
            f"combined figure is partial."
            if withheld else "All linked members are included."
        ),
    }
