import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("finmate")

from .database import Base, engine, get_service_status
from . import seed_data
from .routers import twin, chat, goals, simulate, insights, memory, profile, upload
from .services.memory_engine import ensure_collection, reindex_all
from .services.wealth_graph import sync_graph

app = FastAPI(
    title="FinMate API",
    description="Agentic Financial Operating System — Financial Twin, Memory Engine, AI CFO, "
                 "Scenario Simulator, Goal Planner, Opportunity Discovery.",
    version="2.0.0",
)

origins = [
    os.getenv("FRONTEND_ORIGIN", "http://localhost:3000"),
    "http://127.0.0.1:3000",
    "http://localhost:3001",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(twin.router)
app.include_router(chat.router)
app.include_router(goals.router)
app.include_router(simulate.router)
app.include_router(insights.router)
app.include_router(memory.router)
app.include_router(profile.router)
app.include_router(upload.router)


@app.on_event("startup")
def on_startup():
    # Create tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified.")

    # Seed demo data
    seed_data.seed()

    # Initialize Qdrant collection + reindex memories
    if ensure_collection():
        from .database import SessionLocal
        db = SessionLocal()
        try:
            reindex_all(db)
        finally:
            db.close()

    # Sync Neo4j wealth graph
    try:
        from .database import SessionLocal
        db = SessionLocal()
        try:
            sync_graph(db, user_id=1)
        finally:
            db.close()
    except Exception as e:
        logger.warning("Neo4j graph sync skipped: %s", e)

    # Log service status
    status = get_service_status()
    logger.info("Service Status: %s", status)


@app.get("/")
def root():
    return {
        "name": "FinMate API",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "agents": ["AI CFO (LangGraph)", "Scenario Simulator", "Goal Planner", "Opportunity Discovery"],
        "infrastructure": ["PostgreSQL", "Qdrant Vector DB", "Neo4j Graph DB"],
    }


@app.get("/api/health")
def health():
    from .services.llm_client import get_last_provider, LLM_PROVIDER, GROQ_API_KEY, GEMINI_API_KEY
    
    services = get_service_status()
    
    llm_configured = bool(
        (GROQ_API_KEY and GROQ_API_KEY != "YOUR_GROQ_API_KEY_HERE") or GEMINI_API_KEY
    )
    
    return {
        "status": "ok",
        "services": services,
        "llm": {
            "provider": LLM_PROVIDER,
            "configured": llm_configured,
            "last_used": get_last_provider(),
        },
    }
