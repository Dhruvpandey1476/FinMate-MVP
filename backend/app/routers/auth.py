"""Auth Router — signup, login, magic-link, current-user."""
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, models, auth
from ..database import get_db
from ..services import email_service

router = APIRouter(prefix="/api/auth", tags=["Auth"])

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")


def _user_dict(u: models.User) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "monthly_income": u.monthly_income,
        "risk_profile": u.risk_profile,
    }


@router.post("/signup", response_model=schemas.AuthResponse)
def signup(req: schemas.SignupRequest, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Please enter a valid email.")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
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
    return {"token": auth.create_token(user.id), "user": _user_dict(user)}


@router.post("/login", response_model=schemas.AuthResponse)
def login(req: schemas.LoginRequest, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not auth.verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return {"token": auth.create_token(user.id), "user": _user_dict(user)}


@router.post("/magic/request")
def magic_request(req: schemas.MagicRequest, db: Session = Depends(get_db)):
    """Passwordless login: email the user a one-tap login link. Creates the
    account on first request. In DEV mode (no email provider) returns the link."""
    email = req.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Please enter a valid email.")

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        user = models.User(name=(req.name or "").strip() or email.split("@")[0], email=email)
        db.add(user)
        db.commit()
        db.refresh(user)

    token = auth.create_magic_token(user.id)
    link = f"{FRONTEND_ORIGIN}/login?magic={token}"
    sent = email_service.send_magic_link(email, link)
    result = {"sent": sent, "email": email}
    if not sent:
        result["dev_link"] = link  # so you can test without an email provider
    return result


@router.post("/magic/verify", response_model=schemas.AuthResponse)
def magic_verify(req: schemas.MagicVerify, db: Session = Depends(get_db)):
    user_id = auth.verify_magic_token(req.token)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Account not found.")
    return {"token": auth.create_token(user.id), "user": _user_dict(user)}


@router.get("/me")
def me(user: models.User = Depends(auth.get_current_user)):
    return _user_dict(user)
