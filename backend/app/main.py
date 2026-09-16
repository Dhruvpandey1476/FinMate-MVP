import os
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("finmate")

from .database import engine, get_service_status, SessionLocal  # noqa: E402
from . import seed_data, models  # noqa: E402
from .database_migrations import ensure_schema, post_migration_backfill  # noqa: E402
from .routers import (  # noqa: E402
    twin, chat, goals, simulate, insights, memory, profile, upload, waitlist,
    forecast, debt, notifications, dashboard, quickadd, reports, auth as auth_router,
)
from .services.memory_engine import ensure_collection, reindex_all  # noqa: E402
from .services.wealth_graph import sync_graph  # noqa: E402

ENV = os.getenv("ENV", "development")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup/shutdown. Replaces the deprecated @app.on_event("startup") hook.

    Schema comes from Alembic rather than create_all(), so a column added to a
    model actually reaches a live database instead of silently going missing.
    """
    try:
        ensure_schema()
    except Exception as e:
        # Falling back to create_all() here used to hide a failed migration:
        # it creates missing *tables* but never adds a column to an existing
        # one, so the app booted against a half-old schema and died later on a
        # confusing "column does not exist". Only an empty database is safe to
        # bootstrap this way; anything else must fail loudly.
        from sqlalchemy import inspect as _inspect

        try:
            existing = set(_inspect(engine).get_table_names()) - {"alembic_version"}
        except Exception:
            existing = {"unknown"}

        if existing:
            logger.error("Migration failed against a populated database: %s", e, exc_info=True)
            raise RuntimeError(
                "Database migration failed and the schema is already populated. "
                "Refusing to start with a possibly-stale schema. "
                "Check that alembic.ini and alembic/ are present in the image "
                "(see backend/Dockerfile) and that DATABASE_URL is correct."
            ) from e

        logger.warning("Migration unavailable on an empty database (%s) - bootstrapping with create_all().", e)
        models.Base.metadata.create_all(bind=engine)

    try:
        post_migration_backfill()
    except Exception as e:
        logger.warning("Post-migration backfill skipped: %s", e)

    seed_data.seed()

    if ensure_collection():
        db = SessionLocal()
        try:
            reindex_all(db)
        finally:
            db.close()

    try:
        db = SessionLocal()
        try:
            demo = db.query(models.User).filter(models.User.email == seed_data.DEMO_EMAIL).first()
            if demo:
                sync_graph(db, demo.id)
        finally:
            db.close()
    except Exception as e:
        logger.warning("Neo4j graph sync skipped: %s", e)

    logger.info("Service Status: %s", get_service_status())
    _warn_on_insecure_config()

    yield

    logger.info("FinMate API shutting down.")


def _warn_on_insecure_config() -> None:
    """Fail loudly in production rather than quietly running with dev defaults."""
    problems = []
    if os.getenv("JWT_SECRET", "") in ("", "dev-insecure-secret-change-in-production"):
        problems.append("JWT_SECRET is unset or still the development default")
    if not os.getenv("ADMIN_KEY"):
        problems.append("ADMIN_KEY is unset - admin endpoints are disabled")
    if not os.getenv("CRON_KEY"):
        problems.append("CRON_KEY is unset - the digest cron endpoint is disabled")

    for p in problems:
        logger.warning("CONFIG: %s", p)

    if ENV == "production" and os.getenv("JWT_SECRET", "") in (
        "", "dev-insecure-secret-change-in-production"
    ):
        raise RuntimeError(
            "JWT_SECRET must be set to a strong random value in production. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )


app = FastAPI(
    title="FinMate API",
    description="Agentic Financial Operating System - Financial Twin, Memory Engine, AI CFO, "
                "Scenario Simulator, Goal Planner, Opportunity Discovery, Cash-Flow Forecast, "
                "Debt Optimizer.",
    version="3.0.0",
    lifespan=lifespan,
)

origins = [
    os.getenv("FRONTEND_ORIGIN", "http://localhost:3000"),
    "http://127.0.0.1:3000",
    "http://localhost:3001",
]
extra = os.getenv("EXTRA_ORIGINS", "")
if extra:
    origins += [o.strip() for o in extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """
    Attach a request id and log slow requests.

    Without this there is no way to correlate a user's report with a log line,
    and no visibility into which endpoints are slow.
    """
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        elapsed = (time.monotonic() - started) * 1000
        logger.exception("Unhandled error [%s] %s %s after %.0fms",
                         request_id, request.method, request.url.path, elapsed)
        return JSONResponse(
            status_code=500,
            content={"detail": "Something went wrong on our end.", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )

    elapsed = (time.monotonic() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    if elapsed > 2000:
        logger.warning("Slow request [%s] %s %s took %.0fms",
                       request_id, request.method, request.url.path, elapsed)
    return response


app.include_router(auth_router.router)
app.include_router(waitlist.router)
app.include_router(twin.router)
app.include_router(chat.router)
app.include_router(goals.router)
app.include_router(simulate.router)
app.include_router(insights.router)
app.include_router(memory.router)
app.include_router(profile.router)
app.include_router(upload.router)
app.include_router(forecast.router)
app.include_router(debt.router)
app.include_router(notifications.router)
app.include_router(dashboard.router)
app.include_router(quickadd.router)
app.include_router(reports.router)


@app.get("/")
def root():
    return {
        "name": "FinMate API",
        "version": "3.0.0",
        "status": "running",
        "docs": "/docs",
        "agents": [
            "AI CFO (LangGraph)", "Scenario Simulator", "Goal Planner",
            "Opportunity Discovery", "Cash-Flow Forecast", "Debt Optimizer",
            "Safe-to-Spend", "Early Warning", "Time Machine", "Next Best Action",
        ],
        "infrastructure": ["PostgreSQL", "Qdrant Vector DB", "Neo4j Graph DB"],
    }


@app.get("/api/health")
def health():
    from .services import llm_client
    from .database_migrations import current_revision

    try:
        revision = current_revision()
    except Exception:
        revision = None

    return {
        "status": "ok",
        "version": "3.0.0",
        "schema_revision": revision,
        "services": get_service_status(),
        "llm": {
            "provider": llm_client.LLM_PROVIDER,
            "configured": llm_client.llm_configured(),
            "last_used": llm_client.get_last_provider(),
        },
    }
