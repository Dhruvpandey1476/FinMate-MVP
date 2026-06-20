"""
Memory Engine — Qdrant vector search with PostgreSQL fallback.

Memory Types:
  - Episodic:   Specific events ("User bought a laptop for ₹85,000 on 12 Mar")
  - Semantic:   Durable facts/preferences ("User prefers low-risk investments")
  - Behavioral: Detected patterns ("User overspends on food delivery near month-end")

When Qdrant is available:
  → Memories are embedded via Gemini text-embedding-004 and stored as vectors
  → Retrieval uses cosine similarity for true semantic search

When Qdrant is unavailable:
  → Falls back to keyword overlap scoring (same as before, but now explicitly a fallback)
"""
import re
import logging
from sqlalchemy.orm import Session
from sqlalchemy import or_
from .. import models
from ..database import get_qdrant
from ..services import llm_client

logger = logging.getLogger("finmate.memory")

COLLECTION_NAME = "finmate_memories"
STOPWORDS = {"the", "a", "an", "is", "are", "i", "to", "for", "of", "and", "my", "on", "in", "do", "can", "what", "how", "why"}

def ensure_collection():
    qdrant = get_qdrant()
    if not qdrant:
        return False

    try:
        from qdrant_client.models import Distance, VectorParams

        collections = [c.name for c in qdrant.get_collections().collections]

        if COLLECTION_NAME not in collections:
            qdrant.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=llm_client.EMBEDDING_DIM,
                    distance=Distance.COSINE,
                ),
            )

            logger.info("Created Qdrant collection '%s'", COLLECTION_NAME)
        else:
            logger.info("Qdrant collection already exists")

    except Exception as e:
        logger.warning("Failed to ensure Qdrant collection: %s", e)
        return False

    qdrant.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="user_id",
        field_schema="integer",
    )    


def add_memory(db: Session, user_id: int, memory_type: str, content: str, importance: float = 0.5) -> models.Memory:
    """
    Add a memory to both PostgreSQL (source of truth) and Qdrant (vector index).
    memory_type: episodic | semantic | behavioral
    """
    # Always store in PostgreSQL
    mem = models.Memory(
        user_id=user_id,
        memory_type=memory_type,
        content=content,
        importance=importance,
        embedding_keywords=_keywords(content),
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)

    # Also index in Qdrant if available
    _index_in_qdrant(mem)

    return mem


def _index_in_qdrant(mem: models.Memory):
    """Index a single memory in Qdrant."""
    qdrant = get_qdrant()
    if not qdrant:
        return
    
    try:
        from qdrant_client.models import PointStruct
        
        embedding = llm_client.get_embedding(mem.content)
        if not embedding:
            return
        
        qdrant.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=mem.id,
                    vector=embedding,
                    payload={
                        "user_id": mem.user_id,
                        "memory_type": mem.memory_type,
                        "content": mem.content,
                        "importance": mem.importance,
                    },
                )
            ],
        )
        logger.debug("Indexed memory %d in Qdrant", mem.id)
    except Exception as e:
        logger.warning("Failed to index memory %d in Qdrant: %s", mem.id, e)


def retrieve_relevant(db: Session, user_id: int, query: str, top_k: int = 6) -> list:
    """
    Retrieve relevant memories using vector similarity (Qdrant) or keyword fallback.
    """
    # Try Qdrant vector search first
    qdrant = get_qdrant()
    if qdrant:
        try:
            results = _vector_search(qdrant, user_id, query, top_k)
            if results:
                logger.info("Retrieved %d memories via Qdrant vector search", len(results))
                return results
        except Exception as e:
            logger.warning("Qdrant search failed: %s — falling back to keywords", e)
    
    # Fallback: keyword-based search
    return _keyword_search(db, user_id, query, top_k)


def _vector_search(qdrant, user_id: int, query: str, top_k: int) -> list:
    """Semantic search using Qdrant vectors."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    query_embedding = llm_client.get_embedding(query)
    if not query_embedding:
        return []
    
    results = qdrant.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_embedding,
        query_filter=Filter(
            must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        ),
        limit=top_k,
        score_threshold=0.3,
    )
    
    if not results:
        return []
    
    # Convert Qdrant results back to Memory-like objects for compatibility
    memory_ids = [r.id for r in results]
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        memories = db.query(models.Memory).filter(models.Memory.id.in_(memory_ids)).all()
        # Maintain Qdrant's relevance ordering
        id_to_mem = {m.id: m for m in memories}
        return [id_to_mem[mid] for mid in memory_ids if mid in id_to_mem]
    finally:
        db.close()


def _keyword_search(db: Session, user_id: int, query: str, top_k: int) -> list:
    """Fallback: keyword overlap + importance scoring."""
    query_kw = set(_keywords(query).split())
    all_memories = db.query(models.Memory).filter(models.Memory.user_id == user_id).all()

    scored = []
    for m in all_memories:
        mem_kw = set((m.embedding_keywords or "").split())
        overlap = len(query_kw & mem_kw)
        score = overlap * 2 + m.importance
        scored.append((score, m))

    scored.sort(key=lambda x: -x[0])
    return [m for _, m in scored[:top_k]]


def reindex_all(db: Session):
    """Reindex all memories in Qdrant (used during startup/migration)."""
    if not ensure_collection():
        return 0
    
    all_memories = db.query(models.Memory).all()
    count = 0
    for mem in all_memories:
        _index_in_qdrant(mem)
        count += 1
    
    logger.info("Reindexed %d memories in Qdrant", count)
    return count


def _keywords(text: str) -> str:
    words = re.findall(r"[a-zA-Z₹]+", text.lower())
    return " ".join(w for w in words if w not in STOPWORDS and len(w) > 2)


def get_all_by_type(db: Session, user_id: int, memory_type: str) -> list:
    return (
        db.query(models.Memory)
        .filter(models.Memory.user_id == user_id, models.Memory.memory_type == memory_type)
        .order_by(models.Memory.created_at.desc())
        .all()
    )


def get_timeline(db: Session, user_id: int) -> list:
    return (
        db.query(models.Memory)
        .filter(models.Memory.user_id == user_id)
        .order_by(models.Memory.created_at.desc())
        .all()
    )
