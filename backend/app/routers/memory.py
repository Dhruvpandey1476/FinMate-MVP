from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from .. import schemas, models
from ..database import get_db
from ..auth import get_current_user
from ..services import memory_engine

router = APIRouter(prefix="/api/memory", tags=["Memory Engine"])


@router.get("/timeline", response_model=List[schemas.MemoryOut])
def timeline(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return memory_engine.get_timeline(db, user.id)


@router.get("/by-type/{memory_type}", response_model=List[schemas.MemoryOut])
def by_type(memory_type: str, db: Session = Depends(get_db),
            user: models.User = Depends(get_current_user)):
    return memory_engine.get_all_by_type(db, user.id, memory_type)
