import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from .. import schemas, models
from ..database import get_db
from ..auth import get_current_user
from ..agents import cfo_agent
from ..services import memory_engine

router = APIRouter(prefix="/api/chat", tags=["AI CFO Chat"])


@router.post("/", response_model=schemas.ChatResponse)
def chat(req: schemas.ChatRequest, db: Session = Depends(get_db),
         user: models.User = Depends(get_current_user)):
    result = cfo_agent.run(db, user.id, req.message)

    db.add(models.ChatMessage(user_id=user.id, role="user", content=req.message))
    db.add(models.ChatMessage(
        user_id=user.id, role="assistant", content=result["reply"],
        reasoning_trace=json.dumps(result["trace"]),
    ))
    db.commit()

    # Live memory: distill durable facts from what the user told us so future
    # sessions are personalized. Best-effort — never blocks the reply.
    try:
        memory_engine.distill_from_message(db, user.id, req.message)
    except Exception:
        pass

    return {"reply": result["reply"], "reasoning_trace": result["trace"]}


@router.get("/history")
def history(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    msgs = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.user_id == user.id)
        .order_by(models.ChatMessage.created_at)
        .all()
    )
    return [
        {
            "role": m.role,
            "content": m.content,
            "reasoning_trace": json.loads(m.reasoning_trace) if m.reasoning_trace else None,
            "created_at": m.created_at,
        }
        for m in msgs
    ]
