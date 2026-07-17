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


def distill_from_message(db: Session, user_id: int, user_message: str):
    """
    Turn a user's chat message into durable memories — this is what makes FinMate
    actually *remember* users across sessions. Best-effort: never breaks the chat.

    Extracts up to 3 durable facts (semantic/behavioral/episodic) and stores only
    genuinely new ones (dedup against existing content).
    """
    msg = (user_message or "").strip()
    if len(msg) < 15:
        return

    prompt = f"""A user said the following to their AI financial advisor:
"{msg}"

Extract 0-3 DURABLE facts worth remembering long-term about this user's finances,
preferences, life plans, or behavior. Ignore one-off questions with no lasting signal.

Respond as a JSON array of objects with keys:
- "memory_type": one of "semantic" (stable preference/fact), "behavioral" (a pattern), "episodic" (a specific event/plan)
- "content": a concise third-person statement (e.g. "User plans to buy a house in 2 years")
- "importance": 0.3-0.9

Return [] if nothing is worth remembering."""

    try:
        result = llm_client.generate_json(prompt=prompt, fallback=[])
    except Exception:
        return
    if not isinstance(result, list):
        return

    existing = {m.content.strip().lower() for m in
                db.query(models.Memory).filter(models.Memory.user_id == user_id).all()}

    for item in result[:3]:
        content = (item.get("content") or "").strip()
        mtype = item.get("memory_type", "episodic")
        if mtype not in ("semantic", "behavioral", "episodic"):
            mtype = "episodic"
        if not content or content.lower() in existing:
            continue
        try:
            imp = float(item.get("importance", 0.5))
        except (TypeError, ValueError):
            imp = 0.5
        add_memory(db, user_id, mtype, content, max(0.3, min(imp, 0.9)))
        existing.add(content.lower())


def detect_behavioral_patterns(db: Session, user_id: int):
    """
    Derive behavioral memories from transaction data (runs after an import).
    Deterministic + cheap — no LLM needed. Dedups against existing memories.
    """
    from collections import defaultdict
    txns = db.query(models.Transaction).filter(models.Transaction.user_id == user_id).all()
    if len(txns) < 5:
        return

    cat_totals = defaultdict(float)
    cat_counts = defaultdict(int)
    for t in txns:
        if t.amount < 0:
            cat_totals[t.category] += -t.amount
            cat_counts[t.category] += 1
    total = sum(cat_totals.values()) or 1

    existing = {m.content.strip().lower() for m in
                db.query(models.Memory).filter(models.Memory.user_id == user_id).all()}
    facts = []
    for cat, amt in cat_totals.items():
        share = amt / total
        if share > 0.15 and cat_counts[cat] >= 3:
            facts.append((f"User consistently spends a large share ({share*100:.0f}%) of expenses on '{cat}'.", 0.7))

    recurring = {t.merchant or t.category for t in txns if t.is_recurring and t.amount < 0}
    if recurring:
        facts.append((f"User has recurring charges from: {', '.join(sorted(recurring))[:120]}.", 0.6))

    for content, imp in facts:
        if content.lower() not in existing:
            add_memory(db, user_id, "behavioral", content, imp)
            existing.add(content.lower())


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
