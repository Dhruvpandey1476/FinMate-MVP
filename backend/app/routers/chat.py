"""
AI CFO Chat router.

Two endpoints over the same agent:
  POST /api/chat/         - blocking, returns the whole reply (kept for clients
                            that cannot consume SSE)
  POST /api/chat/stream   - Server-Sent Events; emits each reasoning node as it
                            completes, then the answer token by token

Streaming matters here beyond polish: the blocking call could sit for 30s behind
a slow provider with no feedback, which reads as a hung app.
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import schemas, models
from ..database import get_db, SessionLocal
from ..auth import get_current_user, require_quota
from ..agents import cfo_agent
from ..services import memory_engine, entitlements, analytics

logger = logging.getLogger("finmate.chat")

router = APIRouter(prefix="/api/chat", tags=["AI CFO Chat"])

MAX_MESSAGE_CHARS = 2000


def _validate(message: str) -> str:
    msg = (message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    if len(msg) > MAX_MESSAGE_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Message is too long (max {MAX_MESSAGE_CHARS} characters).",
        )
    return msg


def _persist(db: Session, user_id: int, message: str, reply: str, trace: list) -> None:
    db.add(models.ChatMessage(user_id=user_id, role="user", content=message))
    db.add(models.ChatMessage(
        user_id=user_id, role="assistant", content=reply,
        reasoning_trace=json.dumps(trace, default=str),
    ))
    db.commit()


def _post_turn(db: Session, user_id: int, message: str, result_meta) -> None:
    """Metering, funnel events and memory distillation - all best-effort."""
    if result_meta is not None:
        entitlements.record_usage(
            db, user_id, "chat",
            getattr(result_meta, "provider", ""), getattr(result_meta, "model", ""),
            getattr(result_meta, "prompt_tokens", 0), getattr(result_meta, "completion_tokens", 0),
            getattr(result_meta, "latency_ms", 0), getattr(result_meta, "ok", True),
        )
    else:
        entitlements.record_usage(db, user_id, "chat", "rule_based", "", 0, 0, 0, False)

    try:
        analytics.track_once(db, user_id, "first_chat")
    except Exception:
        pass

    # Live memory: distil durable facts so future sessions are personalised.
    try:
        memory_engine.distill_from_message(db, user_id, message)
    except Exception as e:
        logger.debug("Memory distillation skipped: %s", e)


@router.post("/", response_model=schemas.ChatResponse)
def chat(
    req: schemas.ChatRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_quota("chat")),
):
    message = _validate(req.message)
    result = cfo_agent.run(db, user.id, message)

    _persist(db, user.id, message, result["reply"], result["trace"])
    _post_turn(db, user.id, message, result.get("llm_result"))

    return {"reply": result["reply"], "reasoning_trace": result["trace"]}


@router.post("/stream")
def chat_stream(
    req: schemas.ChatRequest,
    request: Request,
    user: models.User = Depends(require_quota("chat")),
):
    """
    Stream the CFO pipeline as SSE.

    Event payloads (one JSON object per `data:` line):
      {"type":"trace","step":{"node":..,"detail":..}}
      {"type":"token","text":".."}
      {"type":"done","reply":"..","trace":[..]}
      {"type":"error","detail":".."}

    The generator owns its own session: the request-scoped one from Depends is
    closed as soon as the response starts, and this body runs after that.
    """
    message = _validate(req.message)
    user_id = user.id

    def event_stream():
        db = SessionLocal()
        try:
            trace, reply, meta = [], "", None
            for chunk in cfo_agent.run_streaming(db, user_id, message):
                ctype = chunk.get("type")
                if ctype == "trace":
                    trace.append(chunk["step"])
                    yield f"data: {json.dumps({'type': 'trace', 'step': chunk['step']})}\n\n"
                elif ctype == "token":
                    yield f"data: {json.dumps({'type': 'token', 'text': chunk['text']})}\n\n"
                elif ctype == "done":
                    reply = chunk.get("reply", "")
                    trace = chunk.get("trace", trace)
                    meta = chunk.get("llm_result")

            _persist(db, user_id, message, reply, trace)
            _post_turn(db, user_id, message, meta)

            yield f"data: {json.dumps({'type': 'done', 'reply': reply, 'trace': trace}, default=str)}\n\n"
        except Exception as e:
            logger.error("Chat stream failed: %s", e, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'detail': 'The AI CFO agent hit an error. Please try again.'})}\n\n"
        finally:
            db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # stop nginx/proxies buffering the stream
        },
    )


@router.get("/history")
def history(
    limit: int = 100,
    before_id: int = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Newest-last page of chat history. `before_id` walks backwards."""
    limit = max(1, min(int(limit or 100), 200))
    q = db.query(models.ChatMessage).filter(models.ChatMessage.user_id == user.id)
    if before_id:
        q = q.filter(models.ChatMessage.id < before_id)

    msgs = q.order_by(models.ChatMessage.id.desc()).limit(limit).all()
    msgs.reverse()

    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "reasoning_trace": json.loads(m.reasoning_trace) if m.reasoning_trace else None,
            "created_at": m.created_at,
        }
        for m in msgs
    ]


@router.delete("/history")
def clear_history(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Let users wipe their conversation. Memories are managed separately."""
    deleted = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.user_id == user.id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"ok": True, "deleted": deleted}
