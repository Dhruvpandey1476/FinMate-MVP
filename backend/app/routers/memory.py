"""
Memory Engine router.

Read *and* write: a user must be able to correct or delete what the twin
believes about them. A memory store the user cannot inspect or fix is a trust
problem, and it is also the clearest differentiator versus a generic chatbot.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, models
from ..database import get_db
from ..auth import get_current_user
from ..services import memory_engine

router = APIRouter(prefix="/api/memory", tags=["Memory Engine"])


@router.get("/timeline", response_model=List[schemas.MemoryOut])
def timeline(limit: int = 200, offset: int = 0, db: Session = Depends(get_db),
             user: models.User = Depends(get_current_user)):
    return memory_engine.get_timeline(db, user.id, limit=limit, offset=offset)


@router.get("/count")
def count(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return {"total": memory_engine.count_memories(db, user.id)}


@router.get("/by-type/{memory_type}", response_model=List[schemas.MemoryOut])
def by_type(memory_type: str, limit: int = 200, offset: int = 0,
            db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if memory_type not in ("episodic", "semantic", "behavioral"):
        raise HTTPException(status_code=400, detail="Unknown memory type.")
    return memory_engine.get_all_by_type(db, user.id, memory_type, limit=limit, offset=offset)


@router.post("/", response_model=schemas.MemoryOut)
def create(payload: schemas.MemoryCreate, db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)):
    """Teach the twin something directly, without going through chat."""
    if payload.memory_type not in ("episodic", "semantic", "behavioral"):
        raise HTTPException(status_code=400, detail="Unknown memory type.")
    return memory_engine.add_memory(
        db, user.id, payload.memory_type, payload.content.strip(),
        importance=payload.importance, source="user",
    )


@router.patch("/{memory_id}", response_model=schemas.MemoryOut)
def update(memory_id: int, payload: schemas.MemoryUpdate, db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)):
    """Correct, pin, or mute a memory."""
    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="Nothing to update.")
    mem = memory_engine.update_memory(db, user.id, memory_id, **fields)
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found.")
    return mem


@router.delete("/{memory_id}")
def delete(memory_id: int, db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)):
    """Forget permanently - removed from the database and the vector index."""
    if not memory_engine.delete_memory(db, user.id, memory_id):
        raise HTTPException(status_code=404, detail="Memory not found.")
    return {"ok": True}
