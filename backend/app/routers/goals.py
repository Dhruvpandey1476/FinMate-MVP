from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import schemas, models
from ..database import get_db
from ..auth import get_current_user
from ..agents import goal_planner

router = APIRouter(prefix="/api/goals", tags=["Goals"])


@router.get("/", response_model=List[schemas.GoalOut])
def list_goals(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.Goal).filter(models.Goal.user_id == user.id).order_by(models.Goal.priority).all()


@router.post("/", response_model=schemas.GoalOut)
def create_goal(goal: schemas.GoalCreate, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    new_goal = models.Goal(user_id=user.id, **goal.model_dump())
    db.add(new_goal)
    db.commit()
    db.refresh(new_goal)
    return new_goal


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
    goal = db.query(models.Goal).filter(models.Goal.id == goal_id, models.Goal.user_id == user.id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    db.delete(goal)
    db.commit()
    return {"ok": True}
