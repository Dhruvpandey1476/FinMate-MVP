"""
Scenario Simulator Agent — AI-enhanced financial projections.

The math/projection logic is solid (kept from original).
NEW: LLM generates contextual narrative summaries instead of template strings.
"""
from sqlalchemy.orm import Session
from ..services import financial_twin, llm_client


def simulate(db: Session, user_id: int, scenario_type: str, amount: float | None,
             percent_change: float | None, months_ahead: int = 12) -> dict:
    snapshot = financial_twin.get_snapshot(db, user_id)
    income = snapshot["total_income_month"]
    expense = snapshot["total_expense_month"]
    net_worth = snapshot["net_worth"]

    if scenario_type == "purchase":
        result = _simulate_purchase(income, expense, net_worth, amount or 0, months_ahead)
    elif scenario_type == "salary_change":
        result = _simulate_salary_change(income, expense, net_worth, percent_change or 0, months_ahead)
    elif scenario_type == "investment":
        result = _simulate_investment(income, expense, net_worth, amount or 0, months_ahead)
    elif scenario_type == "savings":
        result = _simulate_savings(income, expense, net_worth, amount or 0, months_ahead)
    else:
        return {"error": f"Unknown scenario_type '{scenario_type}'"}

    # AI-enhance the summary
    result["summary"] = _ai_enhance_summary(result, snapshot, scenario_type)
    return result


def _ai_enhance_summary(result: dict, snapshot: dict, scenario_type: str) -> str:
    """Use LLM to generate a more insightful scenario summary."""
    baseline_end = result.get("baseline", [{}])[-1].get("projected_net_worth", 0)
    projected_end = result.get("projected", [{}])[-1].get("projected_net_worth", 0)
    delta = projected_end - baseline_end

    prompt = f"""You are a financial advisor analyzing a scenario simulation. Generate a 2-3 sentence summary.

Scenario: {scenario_type}
Current monthly income: ₹{snapshot['total_income_month']:,.0f}
Current monthly expenses: ₹{snapshot['total_expense_month']:,.0f}
Current savings rate: {snapshot['savings_rate']:.1f}%
Current net worth: ₹{snapshot['net_worth']:,.0f}

Simulation result:
- Baseline net worth after projection: ₹{baseline_end:,.0f}
- Projected net worth after scenario: ₹{projected_end:,.0f}  
- Net impact: ₹{delta:,.0f}
- Original summary: {result.get('summary', '')}

Write a concise, actionable 2-3 sentence summary using ₹ with Indian number formatting. Be specific with numbers."""

    return llm_client.generate(
        prompt=prompt,
        fallback=result.get("summary", "Simulation complete."),
        system_prompt="You are FinMate, an AI financial advisor. Be concise and data-driven.",
        temperature=0.5,
    )


def _project(income, expense, net_worth, months, monthly_delta=0.0, one_time_hit=0.0, growth_rate=0.0):
    series = []
    nw = net_worth - one_time_hit
    for m in range(1, months + 1):
        cash_flow = (income - expense) + monthly_delta
        nw += cash_flow
        nw *= (1 + growth_rate)
        series.append({"month": m, "projected_net_worth": round(nw, 2), "monthly_cash_flow": round(cash_flow, 2)})
    return series


def _simulate_purchase(income, expense, net_worth, amount, months_ahead):
    baseline = _project(income, expense, net_worth, months_ahead)
    with_purchase = _project(income, expense, net_worth, months_ahead, one_time_hit=amount)
    delta_at_end = baseline[-1]["projected_net_worth"] - with_purchase[-1]["projected_net_worth"]
    return {
        "scenario": "purchase",
        "summary": (
            f"A one-time ₹{amount:,.0f} purchase reduces your projected net worth by roughly "
            f"₹{delta_at_end:,.0f} over {months_ahead} months."
        ),
        "baseline": baseline,
        "projected": with_purchase,
    }


def _simulate_salary_change(income, expense, net_worth, percent_change, months_ahead):
    new_income = income * (1 + percent_change / 100)
    baseline = _project(income, expense, net_worth, months_ahead)
    projected = _project(new_income, expense, net_worth, months_ahead)
    extra = new_income - income
    return {
        "scenario": "salary_change",
        "summary": (
            f"A {percent_change:+.0f}% salary change moves monthly income from ₹{income:,.0f} to ₹{new_income:,.0f}, "
            f"adding ₹{extra:,.0f}/month."
        ),
        "baseline": baseline,
        "projected": projected,
    }


def _simulate_investment(income, expense, net_worth, monthly_amount, months_ahead, annual_return=0.10):
    monthly_growth = annual_return / 12
    baseline = _project(income, expense, net_worth, months_ahead)
    projected = _project(income, expense, net_worth, months_ahead, monthly_delta=-monthly_amount)
    invested_value = 0.0
    invest_series = []
    for m in range(1, months_ahead + 1):
        invested_value = (invested_value + monthly_amount) * (1 + monthly_growth)
        invest_series.append({"month": m, "invested_value": round(invested_value, 2)})
    return {
        "scenario": "investment",
        "summary": (
            f"Investing ₹{monthly_amount:,.0f}/month at 10% annual return grows to ₹{invested_value:,.0f} "
            f"after {months_ahead} months."
        ),
        "baseline": baseline,
        "projected": projected,
        "investment_growth": invest_series,
    }


def _simulate_savings(income, expense, net_worth, extra_monthly_savings, months_ahead):
    baseline = _project(income, expense, net_worth, months_ahead)
    projected = _project(income, expense, net_worth, months_ahead, monthly_delta=extra_monthly_savings)
    gain = projected[-1]["projected_net_worth"] - baseline[-1]["projected_net_worth"]
    return {
        "scenario": "savings",
        "summary": (
            f"Saving an extra ₹{extra_monthly_savings:,.0f}/month adds ₹{gain:,.0f} to your net worth "
            f"over {months_ahead} months."
        ),
        "baseline": baseline,
        "projected": projected,
    }
