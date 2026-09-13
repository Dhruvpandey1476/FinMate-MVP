/**
 * Shared API types.
 *
 * The previous client returned `any` everywhere, so a renamed backend field
 * failed silently at runtime instead of at compile time.
 */

export interface HealthComponent {
  label: string;
  points: number;
  detail: string;
}

export interface Snapshot {
  net_worth: number;
  total_income_month: number;
  total_expense_month: number;
  savings_rate: number;
  cash_flow: number;
  total_assets: number;
  total_liabilities: number;
  financial_health_score: number;
  health_breakdown: HealthComponent[];
  top_expense_categories: { category: string; amount: number }[];
}

export interface CashflowPoint {
  month: string;
  income: number;
  expense: number;
  savings: number;
}

export interface Transaction {
  id: number;
  date: string;
  amount: number;
  category: string;
  type: string;
  merchant?: string | null;
  is_recurring: boolean;
  note?: string | null;
}

export interface Goal {
  id: number;
  name: string;
  goal_type: string;
  target_amount: number;
  current_amount: number;
  target_date?: string | null;
  monthly_contribution: number;
  priority: number;
}

export interface Insight {
  type: string;
  title: string;
  description: string;
  monthly_impact: number;
  ai_enhanced?: boolean;
}

export interface Memory {
  id: number;
  memory_type: "episodic" | "semantic" | "behavioral";
  content: string;
  importance: number;
  created_at: string;
  source: string;
  pinned: boolean;
  muted: boolean;
}

export interface TraceStep {
  node: string;
  detail: string;
}

export interface ChatMessage {
  id?: number;
  role: "user" | "assistant";
  content: string;
  reasoning_trace?: TraceStep[] | null;
  created_at?: string;
  streaming?: boolean;
}

export interface ForecastEvent {
  label: string;
  amount: number;
  kind: "bill" | "income";
  date?: string;
}

export interface RecurringItem {
  label: string;
  category: string;
  cadence: string;
  period_days: number;
  amount: number;
  occurrences: number;
  last_seen: string;
  next_due: string;
  monthly_equivalent: number;
  confidence: number;
}

export interface Forecast {
  opening_balance: number;
  horizon_days: number;
  daily_discretionary_burn: number;
  monthly_committed: number;
  monthly_recurring_income: number;
  projected_monthly_surplus: number;
  low_balance_date: string | null;
  lowest_balance: number;
  lowest_balance_date: string;
  runway_days: number | null;
  series: { date: string; balance: number; events: ForecastEvent[] }[];
  recurring_expenses: RecurringItem[];
  recurring_income: { label: string; cadence: string; amount: number; next_due: string }[];
  upcoming_bills: ForecastEvent[];
  summary: string;
}

export interface BudgetCategory {
  category: string;
  spent_mtd: number;
  expected_by_now: number;
  monthly_average: number;
  projected_month_end: number;
  over_by: number;
  pct_of_average: number;
  days_left: number;
}

export interface DebtItem {
  id: number;
  name: string;
  type: string;
  balance: number;
  interest_rate: number;
  monthly_payment: number;
  priority: number;
  months_if_alone: number | null;
  interest_if_alone: number | null;
  payoff_month_in_plan: number | null;
}

export interface DebtPlan {
  strategy: string;
  debts: DebtItem[];
  total_debt: number;
  total_monthly_payment: number;
  extra_monthly: number;
  baseline: { months: number | null; total_interest: number | null };
  avalanche: { months: number | null; total_interest: number | null };
  snowball: { months: number | null; total_interest: number | null };
  interest_saved_vs_baseline: number | null;
  months_saved_vs_baseline: number | null;
  avalanche_advantage: number | null;
  summary: string;
  message?: string;
}

export interface Notification {
  id: number;
  kind: string;
  title: string;
  body: string;
  severity: "info" | "warn" | "critical";
  read: boolean;
  created_at: string;
}

export interface QuotaInfo {
  used: number;
  limit: number;
  remaining: number;
}

export interface PlanSummary {
  plan: string;
  label: string;
  price_inr_month: number;
  features: Record<string, boolean>;
  quotas: Record<string, QuotaInfo>;
}

export interface SimulationPoint {
  month: number;
  projected_net_worth: number;
  real_net_worth: number;
  monthly_cash_flow: number;
}

export interface MonteCarloBand {
  month: number;
  p10: number;
  p50: number;
  p90: number;
}

export interface SimulationResult {
  scenario: string;
  summary: string;
  baseline: SimulationPoint[];
  projected: SimulationPoint[];
  investment_growth?: { month: number; invested_value: number; real_value: number; contributed: number }[];
  monte_carlo?: {
    bands: MonteCarloBand[];
    final_p10: number;
    final_p50: number;
    final_p90: number;
    probability_of_loss: number;
  };
  assumptions: {
    annual_return: number;
    inflation: number;
    volatility: number | null;
    ltcg_rate: number;
    monte_carlo_runs: number | null;
    note: string;
  };
  // Scenario-specific extras
  opportunity_cost?: number;
  true_cost?: number;
  one_time_amount?: number;
  real_change_pct?: number;
  nominal_value?: number;
  post_tax_value?: number;
  real_value_today?: number;
  tax_paid?: number;
  total_contributed?: number;
  comparison?: Record<string, unknown>;
}

export interface User {
  name: string;
  email: string;
  monthly_income: number;
  risk_profile: string;
  plan: string;
  entitlements?: PlanSummary;
}
