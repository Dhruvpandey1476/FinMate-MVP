from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
)
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="Demo User")
    email = Column(String, unique=True, default="demo@finmate.ai")
    monthly_income = Column(Float, default=0.0)
    risk_profile = Column(String, default="moderate")  # conservative | moderate | aggressive
    created_at = Column(DateTime, default=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    assets = relationship("Asset", back_populates="user", cascade="all, delete-orphan")
    liabilities = relationship("Liability", back_populates="user", cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="user", cascade="all, delete-orphan")


class Transaction(Base):
    """Edges in the Wealth Graph: Transaction -> ExpenseCategory / IncomeSource"""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(DateTime, default=datetime.utcnow)
    amount = Column(Float, nullable=False)  # negative = expense, positive = income
    category = Column(String, index=True)   # e.g. "Food Delivery", "Salary", "Rent"
    type = Column(String)                   # income | expense
    merchant = Column(String, nullable=True)
    is_recurring = Column(Boolean, default=False)
    note = Column(String, nullable=True)

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
    interest_rate = Column(Float, default=0.0)
    monthly_payment = Column(Float, default=0.0)

    user = relationship("User", back_populates="liabilities")


class Memory(Base):
    """
    Unified memory store for the Memory Engine.
    memory_type: episodic | semantic | behavioral
    Episodic  -> specific events ("User bought a laptop for ₹85,000 on 12 Mar")
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

    user = relationship("User", back_populates="memories")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    role = Column(String)  # user | assistant
    content = Column(Text)
    reasoning_trace = Column(Text, nullable=True)  # JSON string of agent reasoning steps
    created_at = Column(DateTime, default=datetime.utcnow)
