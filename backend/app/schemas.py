from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class TransactionOut(BaseModel):
    id: int
    date: datetime
    amount: float
    category: str
    type: str
    merchant: Optional[str] = None
    is_recurring: bool
    note: Optional[str] = None

    class Config:
        from_attributes = True


class TransactionCreate(BaseModel):
    amount: float
    category: str
    type: str
    merchant: Optional[str] = None
    is_recurring: bool = False
    note: Optional[str] = None
    date: Optional[datetime] = None


class GoalOut(BaseModel):
    id: int
    name: str
    goal_type: str
    target_amount: float
    current_amount: float
    target_date: Optional[datetime]
    monthly_contribution: float
    priority: int

    class Config:
        from_attributes = True


class GoalCreate(BaseModel):
    name: str
    goal_type: str = "custom"
    target_amount: float
    current_amount: float = 0.0
    monthly_contribution: float = 0.0
    priority: int = 2


class AssetOut(BaseModel):
    id: int
    name: str
    asset_type: str
    value: float

    class Config:
        from_attributes = True


class LiabilityOut(BaseModel):
    id: int
    name: str
    liability_type: str
    amount: float
    interest_rate: float
    monthly_payment: float

    class Config:
        from_attributes = True


class FinancialTwinSnapshot(BaseModel):
    net_worth: float
    total_income_month: float
    total_expense_month: float
    savings_rate: float
    cash_flow: float
    total_assets: float
    total_liabilities: float
    financial_health_score: int
    top_expense_categories: List[dict]


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user: dict


class MagicRequest(BaseModel):
    email: str
    name: Optional[str] = None


class MagicVerify(BaseModel):
    token: str


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    reasoning_trace: List[dict]


class SimulationRequest(BaseModel):
    scenario_type: str  # purchase | salary_change | investment | savings
    amount: Optional[float] = None
    percent_change: Optional[float] = None
    months_ahead: int = 12


class GoalPlanRequest(BaseModel):
    goal_id: int


class MemoryOut(BaseModel):
    id: int
    memory_type: str
    content: str
    importance: float
    created_at: datetime

    class Config:
        from_attributes = True
