import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from .. import schemas, models
from ..database import get_db
from ..agents import cfo_agent

router = APIRouter(prefix="/api/chat", tags=["AI CFO Chat"])

DEMO_USER_ID = 1


@router.post("/", response_model=schemas.ChatResponse)
def chat(req: schemas.ChatRequest, db: Session = Depends(get_db)):
    result = cfo_agent.run(db, DEMO_USER_ID, req.message)

    db.add(models.ChatMessage(user_id=DEMO_USER_ID, role="user", content=req.message))
    db.add(models.ChatMessage(
        user_id=DEMO_USER_ID, role="assistant", content=result["reply"],
        reasoning_trace=json.dumps(result["trace"]),
    ))
    db.commit()

    return {"reply": result["reply"], "reasoning_trace": result["trace"]}


@router.get("/history")
def history(db: Session = Depends(get_db)):
    msgs = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.user_id == DEMO_USER_ID)
        .order_by(models.ChatMessage.created_at)
        .all()
    )
    out = []
    for m in msgs:
        out.append({
            "role": m.role,
            "content": m.content,
            "reasoning_trace": json.loads(m.reasoning_trace) if m.reasoning_trace else None,
            "created_at": m.created_at,
        })
    return out
