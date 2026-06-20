from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from .. import schemas
from ..database import get_db
from ..services import memory_engine

router = APIRouter(prefix="/api/memory", tags=["Memory Engine"])

DEMO_USER_ID = 1


@router.get("/timeline", response_model=List[schemas.MemoryOut])
def timeline(db: Session = Depends(get_db)):
    return memory_engine.get_timeline(db, DEMO_USER_ID)


@router.get("/by-type/{memory_type}", response_model=List[schemas.MemoryOut])
def by_type(memory_type: str, db: Session = Depends(get_db)):
    return memory_engine.get_all_by_type(db, DEMO_USER_ID, memory_type)
