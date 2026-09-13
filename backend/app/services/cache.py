"""
Derived-output cache.

The dashboard calls /api/insights on mount, and Opportunity Discovery used to
run an LLM enrichment pass on every one of those calls. Identical input,
identical output, billed every time - and a slow dashboard on top.

Cached values are keyed by a fingerprint of the data they were derived from, so
they invalidate exactly when the underlying transactions change (import, manual
add, delete) and never otherwise.
"""
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .. import models

logger = logging.getLogger("finmate.cache")

# Even when the fingerprint is unchanged, expire eventually so time-sensitive
# copy ("9 days left in the month") does not go stale.
DEFAULT_TTL = timedelta(hours=12)


def get(db: Session, user_id: int, kind: str, fingerprint: str, ttl: timedelta = DEFAULT_TTL):
    """Return the cached payload, or None on miss/stale/expired."""
    row = (
        db.query(models.InsightCache)
        .filter(models.InsightCache.user_id == user_id, models.InsightCache.kind == kind)
        .first()
    )
    if not row or row.fingerprint != fingerprint:
        return None

    stamp = row.updated_at or row.created_at
    if stamp and datetime.utcnow() - stamp > ttl:
        return None

    try:
        return json.loads(row.payload or "null")
    except json.JSONDecodeError:
        logger.warning("Corrupt cache payload for user=%s kind=%s", user_id, kind)
        return None


def put(db: Session, user_id: int, kind: str, fingerprint: str, payload) -> None:
    """Upsert a cache entry. Never raises - a cache failure must not fail a request."""
    try:
        row = (
            db.query(models.InsightCache)
            .filter(models.InsightCache.user_id == user_id, models.InsightCache.kind == kind)
            .first()
        )
        encoded = json.dumps(payload, default=str)
        if row:
            row.fingerprint = fingerprint
            row.payload = encoded
            row.updated_at = datetime.utcnow()
        else:
            db.add(models.InsightCache(
                user_id=user_id, kind=kind, fingerprint=fingerprint, payload=encoded,
            ))
        db.commit()
    except Exception as e:
        logger.warning("Cache write failed (user=%s kind=%s): %s", user_id, kind, e)
        try:
            db.rollback()
        except Exception:
            pass


def invalidate(db: Session, user_id: int, kind: str = None) -> None:
    """Drop cached output for a user - call after an import or a data edit."""
    try:
        q = db.query(models.InsightCache).filter(models.InsightCache.user_id == user_id)
        if kind:
            q = q.filter(models.InsightCache.kind == kind)
        q.delete(synchronize_session=False)
        db.commit()
    except Exception as e:
        logger.warning("Cache invalidation failed for user=%s: %s", user_id, e)
        try:
            db.rollback()
        except Exception:
            pass
