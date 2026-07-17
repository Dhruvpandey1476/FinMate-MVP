from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from .. import schemas, models
from ..database import get_db
from ..auth import get_current_user
from ..agents import scenario_simulator

router = APIRouter(prefix="/api/simulate", tags=["Scenario Simulator"])


@router.post("/")
def simulate(req: schemas.SimulationRequest, db: Session = Depends(get_db),
             user: models.User = Depends(get_current_user)):
    return scenario_simulator.simulate(
        db, user.id, req.scenario_type, req.amount, req.percent_change, req.months_ahead
    )
