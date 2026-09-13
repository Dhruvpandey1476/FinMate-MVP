from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, models
from ..database import get_db
from ..auth import require_quota
from ..agents import scenario_simulator

router = APIRouter(prefix="/api/simulate", tags=["Scenario Simulator"])

VALID_SCENARIOS = {"purchase", "salary_change", "investment", "savings", "prepay_debt"}


@router.post("/")
def simulate(req: schemas.SimulationRequest, db: Session = Depends(get_db),
             user: models.User = Depends(require_quota("simulate"))):
    """
    Run a what-if projection.

    Supports inflation adjustment, Indian LTCG treatment, Monte Carlo bands and
    real loan amortisation - see agents/scenario_simulator.py.
    """
    if req.scenario_type not in VALID_SCENARIOS:
        raise HTTPException(
            status_code=400,
            detail=f"scenario_type must be one of: {', '.join(sorted(VALID_SCENARIOS))}",
        )

    result = scenario_simulator.simulate(
        db, user.id, req.scenario_type, req.amount, req.percent_change,
        req.months_ahead, annual_return=req.annual_return, inflation=req.inflation,
        monte_carlo=req.monte_carlo, volatility=req.volatility,
        liability_id=req.liability_id, user=user,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
