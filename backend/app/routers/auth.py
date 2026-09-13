"""Auth Router - signup, login, magic-link, current-user, session revocation."""
import os
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import schemas, models, auth
from ..database import get_db
from ..services import email_service, analytics, entitlements

logger = logging.getLogger("finmate.auth")

router = APIRouter(prefix="/api/auth", tags=["Auth"])

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
MIN_PASSWORD_LEN = 8


def _user_dict(u: models.User) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "monthly_income": u.monthly_income,
        "risk_profile": u.risk_profile,
        "plan": u.plan or "free",
    }


def _issue(user: models.User) -> dict:
    return {"token": auth.create_token(user.id, user.token_version), "user": _user_dict(user)}


@router.post("/signup", response_model=schemas.AuthResponse,
             dependencies=[Depends(auth.rate_limit_anon("auth"))])
def signup(req: schemas.SignupRequest, request: Request, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Please enter a valid email.")
    if len(req.password) < MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {MIN_PASSWORD_LEN} characters.",
        )
    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    user = models.User(
        name=req.name.strip() or "New User",
        email=email,
        hashed_password=auth.hash_password(req.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    analytics.track(db, user.id, "signup", {"method": "password"})
    return _issue(user)


@router.post("/login", response_model=schemas.AuthResponse,
             dependencies=[Depends(auth.rate_limit_anon("auth"))])
def login(req: schemas.LoginRequest, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not auth.verify_password(req.password, user.hashed_password):
        # Same message either way - do not confirm which emails have accounts.
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    # Transparently upgrade legacy password hashes on successful login.
    if auth.needs_rehash(user.hashed_password):
        user.hashed_password = auth.hash_password(req.password)
        db.commit()

    analytics.track(db, user.id, "login", {"method": "password"})
    return _issue(user)


@router.post("/magic/request", dependencies=[Depends(auth.rate_limit_anon("auth"))])
def magic_request(req: schemas.MagicRequest, db: Session = Depends(get_db)):
    """Passwordless login: email the user a one-tap login link. Creates the
    account on first request. In DEV mode (no email provider) returns the link."""
    email = req.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Please enter a valid email.")

    user = db.query(models.User).filter(models.User.email == email).first()
    is_new = user is None
    if is_new:
        user = models.User(name=(req.name or "").strip() or email.split("@")[0], email=email)
        db.add(user)
        db.commit()
        db.refresh(user)

    token = auth.create_magic_token(user.id)
    link = f"{FRONTEND_ORIGIN}/login?magic={token}"
    sent = email_service.send_magic_link(email, link)

    if is_new:
        analytics.track(db, user.id, "signup", {"method": "magic_link"})

    result = {"sent": sent, "email": email}
    if not sent:
        # Dev convenience only - never leak a login link in a real deployment.
        if email_service.email_configured() or os.getenv("ENV", "dev") == "production":
            logger.error("Magic link could not be emailed to %s", email)
            raise HTTPException(
                status_code=502,
                detail="We couldn't send the login email. Please try again shortly.",
            )
        result["dev_link"] = link
    return result


@router.post("/magic/verify", response_model=schemas.AuthResponse,
             dependencies=[Depends(auth.rate_limit_anon("auth"))])
def magic_verify(req: schemas.MagicVerify, db: Session = Depends(get_db)):
    user_id = auth.verify_magic_token(req.token)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Account not found.")
    analytics.track(db, user.id, "login", {"method": "magic_link"})
    return _issue(user)


@router.get("/me")
def me(user: models.User = Depends(auth.get_current_user)):
    return _user_dict(user)


@router.post("/logout-all")
def logout_all(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    """
    Invalidate every existing session for this account.

    Bumping token_version makes all previously issued JWTs fail validation, so a
    leaked token stops working immediately instead of at its 30-day expiry.
    """
    user.token_version = int(user.token_version or 0) + 1
    db.commit()
    db.refresh(user)
    return {"ok": True, "token": auth.create_token(user.id, user.token_version)}


@router.get("/plan")
def plan(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    """Current plan, quota consumption and feature flags for the UI."""
    return entitlements.quota_summary(db, user)


@router.get("/plans")
def plans():
    """Public pricing table."""
    return [
        {"id": pid, **{k: v for k, v in p.items()}}
        for pid, p in entitlements.PLANS.items()
    ]
