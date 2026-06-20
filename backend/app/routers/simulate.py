from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from .. import schemas
from ..database import get_db
from ..agents import scenario_simulator

router = APIRouter(prefix="/api/simulate", tags=["Scenario Simulator"])

DEMO_USER_ID = 1


@router.post("/")
def simulate(req: schemas.SimulationRequest, db: Session = Depends(get_db)):
    return scenario_simulator.simulate(
        db, DEMO_USER_ID, req.scenario_type, req.amount, req.percent_change, req.months_ahead
    )
