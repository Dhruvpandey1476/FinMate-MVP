"""
Database & infrastructure clients for FinMate.
- PostgreSQL via SQLAlchemy (primary data store)
- Qdrant client (vector memory)
- Neo4j driver (wealth graph)

Falls back gracefully: if Qdrant/Neo4j are unreachable, the app still works
with PostgreSQL-only mode (keyword search, relational queries).
"""
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger("finmate.database")

# ─── PostgreSQL ──────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./finmate.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── Qdrant Vector DB ───────────────────────────────────────────────────────
_qdrant_client = None


def get_qdrant():
    global _qdrant_client

    if _qdrant_client is not None:
        return _qdrant_client

    try:
        from qdrant_client import QdrantClient

        url = os.getenv("QDRANT_URL")
        api_key = os.getenv("QDRANT_API_KEY")

        if url:
            client = QdrantClient(
                url=url,
                api_key=api_key,
                timeout=10
            )
        else:
            host = os.getenv("QDRANT_HOST", "localhost")
            port = int(os.getenv("QDRANT_PORT", "6333"))

            client = QdrantClient(
                host=host,
                port=port,
                timeout=10
            )

        client.get_collections()

        _qdrant_client = client
        logger.info("Qdrant connected successfully")

        return client

    except Exception as e:
        logger.warning(
            "Qdrant unavailable (%s) — falling back to keyword search.",
            e
        )
        return None


# ─── Neo4j Graph DB ─────────────────────────────────────────────────────────
_neo4j_driver = None


def get_neo4j():
    global _neo4j_driver

    if _neo4j_driver is not None:
        return _neo4j_driver

    try:
        from neo4j import GraphDatabase

        uri = os.getenv("NEO4J_URI")
        user = os.getenv("NEO4J_USER")
        password = os.getenv("NEO4J_PASSWORD")

        print("URI:", uri)
        print("USER:", user)
        print("PASSWORD SET:", bool(password))

        driver = GraphDatabase.driver(
            uri,
            auth=(user, password)
        )

        driver.verify_connectivity()

        print("NEO4J VERIFIED")

        _neo4j_driver = driver
        return driver

    except Exception as e:
        print("NEO4J ERROR:", repr(e))
        logger.warning(
            "Neo4j unavailable (%s) — falling back to relational queries.",
            e
        )
        return None


def get_service_status() -> dict:
    """Reports connectivity status for all infrastructure services."""
    status = {"postgresql": False, "qdrant": False, "neo4j": False}

    # PostgreSQL
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status["postgresql"] = True
    except Exception:
        pass

    # Qdrant
    status["qdrant"] = get_qdrant() is not None

    # Neo4j
    status["neo4j"] = get_neo4j() is not None

    return status
