from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, models
from ..database import get_db
from ..auth import get_current_user
from ..agents import goal_planner
from ..services import cache, analytics

router = APIRouter(prefix="/api/goals", tags=["Goals"])


@router.get("/", response_model=List[schemas.GoalOut])
def list_goals(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return (
        db.query(models.Goal)
        .filter(models.Goal.user_id == user.id)
        .order_by(models.Goal.priority)
        .all()
    )


@router.post("/", response_model=schemas.GoalOut)
def create_goal(goal: schemas.GoalCreate, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    if goal.target_amount <= 0:
        raise HTTPException(status_code=400, detail="Target amount must be greater than zero.")
    if goal.current_amount < 0 or goal.monthly_contribution < 0:
        raise HTTPException(status_code=400, detail="Amounts cannot be negative.")

    new_goal = models.Goal(user_id=user.id, **goal.model_dump())
    db.add(new_goal)
    db.commit()
    db.refresh(new_goal)

    cache.invalidate(db, user.id)
    analytics.track(db, user.id, "goal_created", {"goal_type": goal.goal_type})
    return new_goal


@router.patch("/{goal_id}", response_model=schemas.GoalOut)
def update_goal(goal_id: int, payload: schemas.GoalUpdate, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    """Edit a goal - progress changes constantly and had no endpoint before."""
    goal = (
        db.query(models.Goal)
        .filter(models.Goal.id == goal_id, models.Goal.user_id == user.id)
        .first()
    )
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="Nothing to update.")
    if fields.get("target_amount", 1) <= 0:
        raise HTTPException(status_code=400, detail="Target amount must be greater than zero.")

    for key, value in fields.items():
        setattr(goal, key, value)
    db.commit()
    db.refresh(goal)

    cache.invalidate(db, user.id)
    return goal


@router.get("/{goal_id}/plan")
def get_goal_plan(goal_id: int, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    plan = goal_planner.plan_for_goal(db, user.id, goal_id)
    if "error" in plan:
        raise HTTPException(status_code=404, detail=plan["error"])
    return plan


@router.delete("/{goal_id}")
def delete_goal(goal_id: int, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    goal = (
        db.query(models.Goal)
        .filter(models.Goal.id == goal_id, models.Goal.user_id == user.id)
        .first()
    )
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    db.delete(goal)
    db.commit()
    cache.invalidate(db, user.id)
    return {"ok": True}
