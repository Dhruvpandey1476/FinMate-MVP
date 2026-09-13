from pydantic import BaseModel, Field
from typing import Optional, List, Any
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


class GoalUpdate(BaseModel):
    name: Optional[str] = None
    goal_type: Optional[str] = None
    target_amount: Optional[float] = None
    current_amount: Optional[float] = None
    monthly_contribution: Optional[float] = None
    priority: Optional[int] = None


class AssetOut(BaseModel):
    id: int
    name: str
    asset_type: str
    value: float

    class Config:
        from_attributes = True


class AssetCreate(BaseModel):
    name: str
    asset_type: str = "cash"
    value: float = 0.0


class LiabilityOut(BaseModel):
    id: int
    name: str
    liability_type: str
    amount: float
    interest_rate: float
    monthly_payment: float

    class Config:
        from_attributes = True


class LiabilityCreate(BaseModel):
    name: str
    liability_type: str = "loan"
    amount: float = 0.0
    interest_rate: float = 0.0
    monthly_payment: float = 0.0


class FinancialTwinSnapshot(BaseModel):
    net_worth: float
    total_income_month: float
    total_expense_month: float
    savings_rate: float
    cash_flow: float
    total_assets: float
    total_liabilities: float
    financial_health_score: int
    health_breakdown: List[dict] = []
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
    message: str = Field(..., min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    reply: str
    reasoning_trace: List[dict]


class SimulationRequest(BaseModel):
    scenario_type: str  # purchase | salary_change | investment | savings | prepay_debt
    amount: Optional[float] = None
    percent_change: Optional[float] = None
    months_ahead: int = Field(12, ge=1, le=600)
    # Realism controls. Defaults match Indian long-run averages; the simulator
    # used to assume zero inflation and zero tax, which flatters every result.
    annual_return: Optional[float] = None     # e.g. 0.10
    inflation: Optional[float] = None         # e.g. 0.06
    monte_carlo: bool = False
    volatility: Optional[float] = None        # annual stdev, e.g. 0.15
    liability_id: Optional[int] = None        # for prepay_debt


class GoalPlanRequest(BaseModel):
    goal_id: int


class MemoryOut(BaseModel):
    id: int
    memory_type: str
    content: str
    importance: float
    created_at: datetime
    source: str = "system"
    pinned: bool = False
    muted: bool = False

    class Config:
        from_attributes = True


class MemoryCreate(BaseModel):
    memory_type: str = "semantic"
    content: str = Field(..., min_length=3, max_length=2000)
    importance: float = Field(0.6, ge=0.0, le=1.0)


class MemoryUpdate(BaseModel):
    content: Optional[str] = Field(None, min_length=3, max_length=2000)
    memory_type: Optional[str] = None
    importance: Optional[float] = Field(None, ge=0.0, le=1.0)
    pinned: Optional[bool] = None
    muted: Optional[bool] = None


class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    body: str
    severity: str
    read: bool
    created_at: datetime

    class Config:
        from_attributes = True
