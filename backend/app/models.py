from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="Demo User")
    email = Column(String, unique=True, index=True, default="demo@finmate.ai")
    hashed_password = Column(String, default="")
    monthly_income = Column(Float, default=0.0)
    risk_profile = Column(String, default="moderate")  # conservative | moderate | aggressive
    created_at = Column(DateTime, default=datetime.utcnow)

    # Billing / entitlements. Free tier is metered; see services/entitlements.py.
    plan = Column(String, default="free", nullable=False)  # free | plus | pro
    plan_renews_at = Column(DateTime, nullable=True)

    # Bumped on logout-everywhere / password change to invalidate live JWTs.
    token_version = Column(Integer, default=0, nullable=False)

    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    assets = relationship("Asset", back_populates="user", cascade="all, delete-orphan")
    liabilities = relationship("Liability", back_populates="user", cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="user", cascade="all, delete-orphan")


class Transaction(Base):
    """Edges in the Wealth Graph: Transaction -> ExpenseCategory / IncomeSource"""
    __tablename__ = "transactions"
    __table_args__ = (
        # Re-importing the same statement must not duplicate rows. The hash is
        # derived from (date, amount, normalized merchant/note) - see
        # services/dedupe.py. Scoped per user so two users can share a hash.
        UniqueConstraint("user_id", "dedupe_hash", name="uq_txn_user_dedupe"),
        Index("ix_txn_user_date", "user_id", "date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(DateTime, default=datetime.utcnow)
    amount = Column(Float, nullable=False)  # negative = expense, positive = income
    category = Column(String, index=True)   # e.g. "Food Delivery", "Salary", "Rent"
    type = Column(String)                   # income | expense
    merchant = Column(String, nullable=True)
    is_recurring = Column(Boolean, default=False)
    note = Column(String, nullable=True)
    dedupe_hash = Column(String, nullable=True, index=True)

    user = relationship("User", back_populates="transactions")


class Goal(Base):
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)           # e.g. "Emergency Fund"
    goal_type = Column(String, default="custom")     # emergency_fund | vehicle | home | education | startup | custom
    target_amount = Column(Float, nullable=False)
    current_amount = Column(Float, default=0.0)
    target_date = Column(DateTime, nullable=True)
    monthly_contribution = Column(Float, default=0.0)
    priority = Column(Integer, default=2)            # 1 = high, 2 = medium, 3 = low
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="goals")


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    asset_type = Column(String, default="cash")  # cash | investment | property | other
    value = Column(Float, default=0.0)

    user = relationship("User", back_populates="assets")


class Liability(Base):
    __tablename__ = "liabilities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    liability_type = Column(String, default="loan")  # loan | credit_card | other
    amount = Column(Float, default=0.0)
    interest_rate = Column(Float, default=0.0)       # annual %, e.g. 9.5
    monthly_payment = Column(Float, default=0.0)

    user = relationship("User", back_populates="liabilities")


class Memory(Base):
    """
    Unified memory store for the Memory Engine.
    memory_type: episodic | semantic | behavioral
    Episodic  -> specific events ("User bought a laptop for 85,000 on 12 Mar")
    Semantic  -> durable facts/preferences ("User prefers low-risk investments")
    Behavioral-> detected patterns ("User overspends on food delivery near month-end")
    """
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    memory_type = Column(String, index=True)
    content = Column(Text, nullable=False)
    importance = Column(Float, default=0.5)  # 0-1, used for retrieval ranking
    embedding_keywords = Column(Text, default="")  # lightweight keyword index (stand-in for a vector DB)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Memory transparency: users can pin, edit, or mute what the twin believes.
    source = Column(String, default="system", nullable=False)  # system | user | chat | import
    pinned = Column(Boolean, default=False, nullable=False)
    muted = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="memories")


class Waitlist(Base):
    __tablename__ = "waitlist"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    note = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    role = Column(String)  # user | assistant
    content = Column(Text)
    reasoning_trace = Column(Text, nullable=True)  # JSON string of agent reasoning steps
    created_at = Column(DateTime, default=datetime.utcnow)


class UsageEvent(Base):
    """
    Every LLM call is metered here. Two jobs: enforce per-plan quotas, and make
    unit economics visible before pricing is set (you cannot price what you
    cannot measure).
    """
    __tablename__ = "usage_events"
    __table_args__ = (Index("ix_usage_user_created", "user_id", "created_at"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    kind = Column(String, index=True)      # chat | insights | simulate | goal_plan | parse | distill
    provider = Column(String, default="")  # groq | gemini | openai | rule_based
    model = Column(String, default="")
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    latency_ms = Column(Integer, default=0)
    ok = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class InsightCache(Base):
    """
    Opportunity Discovery output, keyed by a fingerprint of the underlying
    transactions. Stops the dashboard from firing an LLM call on every mount.
    """
    __tablename__ = "insight_cache"
    __table_args__ = (UniqueConstraint("user_id", "kind", name="uq_insight_user_kind"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    kind = Column(String, default="insights")
    fingerprint = Column(String, index=True)
    payload = Column(Text)  # JSON
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Notification(Base):
    """
    Proactive nudges produced by the digest engine. Stored so they can be
    delivered on any channel (in-app now; WhatsApp/push later) and so we never
    send the same nudge twice.
    """
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notif_user_created", "user_id", "created_at"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    kind = Column(String, index=True)   # low_balance | budget_overrun | subscription | goal_risk | win
    title = Column(String)
    body = Column(Text)
    severity = Column(String, default="info")  # info | warn | critical
    dedupe_key = Column(String, index=True)    # kind + period, so we nudge once per period
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AnalyticsEvent(Base):
    """
    Product funnel instrumentation. Local-first so the funnel works without a
    third-party key; forwards to PostHog when POSTHOG_API_KEY is set.
    """
    __tablename__ = "analytics_events"
    __table_args__ = (Index("ix_analytics_name_created", "name", "created_at"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String, index=True)  # signup | onboard_complete | upload_success | first_chat | ...
    props = Column(Text, default="{}")  # JSON
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class BalanceCheckpoint(Base):
    """
    A user-confirmed account balance at a point in time.

    Safe-to-Spend needs a trustworthy starting balance. Without Account
    Aggregator there is no live feed, so the user periodically confirms what
    their account actually says and the ledger accrues from there. Storing the
    checkpoint (rather than inferring a balance from transactions alone) is what
    lets the UI honestly label the figure "as of your last update".
    """
    __tablename__ = "balance_checkpoints"
    __table_args__ = (Index("ix_checkpoint_user_date", "user_id", "as_of"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    balance = Column(Float, nullable=False)
    as_of = Column(DateTime, default=datetime.utcnow, index=True)
    note = Column(String, nullable=True)
    source = Column(String, default="user")  # user | onboarding | import
    created_at = Column(DateTime, default=datetime.utcnow)


class MerchantRule(Base):
    """
    A user's own merchant -> category mapping, learned from their corrections.

    This is the correction loop: recategorise Swiggy once and it stays fixed,
    for that user only. Scoped per user because the same merchant name means
    different things to different people, and a shared rule would let one
    person's correction degrade everyone else's categorisation.
    """
    __tablename__ = "merchant_rules"
    __table_args__ = (
        UniqueConstraint("user_id", "merchant_key", name="uq_merchant_rule"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    merchant_key = Column(String, index=True)  # normalised, see services/dedupe
    category = Column(String, nullable=False)
    hit_count = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
