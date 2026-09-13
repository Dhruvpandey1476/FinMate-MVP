"""
Authentication - JWT bearer tokens + PBKDF2 password hashing (stdlib, no native deps).
Provides the `get_current_user` dependency used by every protected router.

Tokens carry a `ver` claim matching User.token_version. Bumping that column
invalidates every live token for the user, which is what makes "log out
everywhere" and post-password-change revocation actually work - a stateless JWT
is otherwise valid until it expires no matter what happens to the account.
"""
import os
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .database import get_db
from . import models
from .services import entitlements

SECRET_KEY = os.getenv("JWT_SECRET", "dev-insecure-secret-change-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "30"))
PBKDF2_ROUNDS = 200_000

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ROUNDS)
    return f"pbkdf2${PBKDF2_ROUNDS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verifies both the current format and the original 2-field legacy format."""
    if not stored:
        return False
    parts = stored.split("$")
    try:
        if len(parts) == 4 and parts[0] == "pbkdf2":
            rounds, salt, expected = int(parts[1]), parts[2], parts[3]
        elif len(parts) == 2:
            rounds, salt, expected = 100_000, parts[0], parts[1]  # legacy hashes
        else:
            return False
    except (ValueError, IndexError):
        return False

    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), rounds)
    return hmac.compare_digest(dk.hex(), expected)


def needs_rehash(stored: str) -> bool:
    """True for legacy hashes, so we can upgrade them on next successful login."""
    return bool(stored) and not stored.startswith("pbkdf2$")


def create_token(user_id: int, token_version: int = 0) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": str(user_id),
        "purpose": "session",
        "ver": int(token_version or 0),
        "exp": now + timedelta(days=TOKEN_EXPIRE_DAYS),
        "iat": now,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_magic_token(user_id: int, minutes: int = 20) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": str(user_id),
        "purpose": "magic",
        "exp": now + timedelta(minutes=minutes),
        "iat": now,
        "jti": secrets.token_urlsafe(8),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_magic_token(token: str) -> int:
    """Return the user_id for a valid magic token, else raise 401."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("purpose") != "magic":
            raise ValueError("wrong purpose")
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="This login link is invalid or has expired.")


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> models.User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not creds or not creds.credentials:
        raise exc
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("purpose") != "session":
            raise exc
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise exc

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise exc

    # Reject tokens issued before the last revocation.
    if int(payload.get("ver", 0)) != int(user.token_version or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def client_ip(request: Request) -> str:
    """Best-effort client IP, honouring one proxy hop (Render/Vercel/Fly)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(kind: str = "default"):
    """
    Dependency factory: burst-limits a route per authenticated user.

    Use `rate_limit_anon` for routes that run before authentication.
    """
    def _dep(request: Request, user: models.User = Depends(get_current_user)) -> models.User:
        verdict = entitlements.check_burst(str(user.id), kind)
        if not verdict["allowed"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. Try again in {verdict['retry_after']}s.",
                headers={"Retry-After": str(verdict["retry_after"])},
            )
        return user
    return _dep


def rate_limit_anon(kind: str = "auth"):
    """Burst-limit an unauthenticated route by client IP."""
    def _dep(request: Request) -> None:
        verdict = entitlements.check_burst(client_ip(request), kind)
        if not verdict["allowed"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. Try again in {verdict['retry_after']}s.",
                headers={"Retry-After": str(verdict["retry_after"])},
            )
    return _dep


def require_quota(kind: str):
    """
    Dependency factory: enforce the monthly plan allowance for a metered action.

    Returns the user so routes can depend on this instead of get_current_user.
    """
    def _dep(
        request: Request,
        db: Session = Depends(get_db),
        user: models.User = Depends(get_current_user),
    ) -> models.User:
        burst = entitlements.check_burst(str(user.id), kind)
        if not burst["allowed"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. Try again in {burst['retry_after']}s.",
                headers={"Retry-After": str(burst["retry_after"])},
            )

        quota = entitlements.check_quota(db, user, kind)
        if not quota["allowed"]:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=(
                    f"You've used all {quota['limit']} {kind} actions on the "
                    f"{entitlements.plan_for(user)['label']} plan this month. "
                    f"Upgrade for more."
                ),
            )
        return user
    return _dep
