"""
Scenario Simulator Agent.

The previous version projected a single deterministic line at a hardcoded 10%
annual return, with no inflation, no tax and no loan amortisation. That flatters
every scenario and is not something an advisory product can put in front of a
user making a real decision.

This version adds:
  * inflation-adjusted (real) values alongside nominal
  * Indian capital-gains treatment on investment gains
  * Monte Carlo bands instead of a single deterministic line
  * real EMI amortisation for debt prepayment scenarios

The LLM only narrates the result - it never produces the numbers.
"""
import math
import random
import statistics

from sqlalchemy.orm import Session

from .. import models
from ..services import financial_twin, llm_client, debt, entitlements, prompt_safety

# Defaults tuned for an Indian retail investor. All overridable per request.
DEFAULT_ANNUAL_RETURN = 0.10
DEFAULT_INFLATION = 0.06
DEFAULT_VOLATILITY = 0.15
# Long-term capital gains on equity: 12.5% over the Rs 1.25L annual exemption.
LTCG_RATE = 0.125
LTCG_EXEMPTION = 125_000

MONTE_CARLO_RUNS = 500


def simulate(db: Session, user_id: int, scenario_type: str, amount=None,
             percent_change=None, months_ahead: int = 12, annual_return=None,
             inflation=None, monte_carlo: bool = False, volatility=None,
             liability_id=None, user=None) -> dict:
    snapshot = financial_twin.get_snapshot(db, user_id)
    income = snapshot["total_income_month"]
    expense = snapshot["total_expense_month"]
    net_worth = snapshot["net_worth"]

    annual_return = DEFAULT_ANNUAL_RETURN if annual_return is None else float(annual_return)
    inflation = DEFAULT_INFLATION if inflation is None else float(inflation)
    volatility = DEFAULT_VOLATILITY if volatility is None else float(volatility)
    months_ahead = max(1, min(int(months_ahead or 12), 600))

    # Monte Carlo is a paid feature; deterministic projection stays free.
    if monte_carlo and user is not None and not entitlements.feature_enabled(user, "monte_carlo"):
        monte_carlo = False

    ctx = dict(
        income=income, expense=expense, net_worth=net_worth,
        months=months_ahead, annual_return=annual_return,
        inflation=inflation, volatility=volatility,
    )

    if scenario_type == "purchase":
        result = _simulate_purchase(amount or 0, **ctx)
    elif scenario_type == "salary_change":
        result = _simulate_salary_change(percent_change or 0, **ctx)
    elif scenario_type == "investment":
        result = _simulate_investment(amount or 0, monte_carlo=monte_carlo, **ctx)
    elif scenario_type == "savings":
        result = _simulate_savings(amount or 0, **ctx)
    elif scenario_type == "prepay_debt":
        result = _simulate_prepay_debt(db, user_id, amount or 0, liability_id, **ctx)
    else:
        return {"error": f"Unknown scenario_type '{scenario_type}'"}

    if "error" in result:
        return result

    result["assumptions"] = {
        "annual_return": annual_return,
        "inflation": inflation,
        "volatility": volatility if monte_carlo else None,
        "ltcg_rate": LTCG_RATE,
        "monte_carlo_runs": MONTE_CARLO_RUNS if monte_carlo else None,
        "note": (
            "Projections are estimates. Returns are not guaranteed and real "
            "values are adjusted for assumed inflation."
        ),
    }
    result["summary"] = _ai_enhance_summary(result, snapshot, scenario_type, db, user_id)
    return result


# --- Projection primitives -------------------------------------------------

def _real_value(nominal: float, inflation: float, months: int) -> float:
    """Today's purchasing power of a future nominal amount."""
    return nominal / ((1 + inflation) ** (months / 12.0))


def _project(income, expense, net_worth, months, monthly_delta=0.0,
             one_time_hit=0.0, inflation=0.0, expense_inflates=True):
    """
    Baseline net-worth path.

    Expenses grow with inflation unless told otherwise - holding them flat for
    30 years was the single most misleading part of the old model.
    """
    series = []
    nw = net_worth - one_time_hit
    monthly_inflation = (1 + inflation) ** (1 / 12) - 1 if expense_inflates else 0.0
    current_expense = expense

    for m in range(1, months + 1):
        current_expense *= (1 + monthly_inflation)
        cash_flow = (income - current_expense) + monthly_delta
        nw += cash_flow
        series.append({
            "month": m,
            "projected_net_worth": round(nw, 2),
            "real_net_worth": round(_real_value(nw, inflation, m), 2),
            "monthly_cash_flow": round(cash_flow, 2),
        })
    return series


def _monte_carlo_paths(monthly_amount, months, annual_return, volatility, runs=MONTE_CARLO_RUNS):
    """
    SIP outcomes under randomised monthly returns (log-normal).

    Returns p10/p50/p90 bands. A single deterministic line implies a certainty
    that does not exist; the spread is the actual information.
    """
    monthly_mu = (1 + annual_return) ** (1 / 12) - 1
    monthly_sigma = volatility / math.sqrt(12)
    rng = random.Random(42)  # deterministic output for a given input

    all_paths = []
    for _ in range(runs):
        value = 0.0
        path = []
        for _m in range(months):
            shock = rng.gauss(monthly_mu, monthly_sigma)
            value = (value + monthly_amount) * (1 + shock)
            path.append(value)
        all_paths.append(path)

    bands = []
    for m in range(months):
        column = sorted(p[m] for p in all_paths)
        bands.append({
            "month": m + 1,
            "p10": round(column[int(runs * 0.10)], 2),
            "p50": round(column[int(runs * 0.50)], 2),
            "p90": round(column[int(runs * 0.90)], 2),
        })

    finals = [p[-1] for p in all_paths]
    return {
        "bands": bands,
        "final_p10": round(sorted(finals)[int(runs * 0.10)], 2),
        "final_p50": round(statistics.median(finals), 2),
        "final_p90": round(sorted(finals)[int(runs * 0.90)], 2),
        "probability_of_loss": round(
            sum(1 for f in finals if f < monthly_amount * months) / runs, 3
        ),
    }


def _apply_ltcg(gain: float) -> float:
    """Post-tax gain under India's LTCG regime for equity."""
    taxable = max(0.0, gain - LTCG_EXEMPTION)
    return gain - taxable * LTCG_RATE


# --- Scenarios -------------------------------------------------------------

def _simulate_purchase(amount, income, expense, net_worth, months,
                       annual_return, inflation, volatility):
    baseline = _project(income, expense, net_worth, months, inflation=inflation)
    with_purchase = _project(income, expense, net_worth, months,
                             one_time_hit=amount, inflation=inflation)
    delta = baseline[-1]["projected_net_worth"] - with_purchase[-1]["projected_net_worth"]

    # The true cost is the purchase plus the growth it displaced.
    opportunity_cost = amount * ((1 + annual_return) ** (months / 12.0)) - amount

    return {
        "scenario": "purchase",
        "summary": (
            f"A one-time Rs {amount:,.0f} purchase reduces projected net worth by "
            f"Rs {delta:,.0f} over {months} months, including "
            f"Rs {opportunity_cost:,.0f} of forgone growth."
        ),
        "one_time_amount": round(amount, 2),
        "opportunity_cost": round(opportunity_cost, 2),
        "true_cost": round(amount + opportunity_cost, 2),
        "baseline": baseline,
        "projected": with_purchase,
    }


def _simulate_salary_change(percent_change, income, expense, net_worth, months,
                            annual_return, inflation, volatility):
    new_income = income * (1 + percent_change / 100)
    baseline = _project(income, expense, net_worth, months, inflation=inflation)
    projected = _project(new_income, expense, net_worth, months, inflation=inflation)
    extra = new_income - income

    # A raise that trails inflation is a real-terms pay cut - say so.
    real_change = (1 + percent_change / 100) / (1 + inflation) - 1

    return {
        "scenario": "salary_change",
        "summary": (
            f"A {percent_change:+.0f}% salary change moves monthly income from "
            f"Rs {income:,.0f} to Rs {new_income:,.0f} (Rs {extra:+,.0f}/month). "
            f"After {inflation * 100:.0f}% inflation that is a "
            f"{real_change * 100:+.1f}% change in real terms."
        ),
        "new_monthly_income": round(new_income, 2),
        "extra_monthly": round(extra, 2),
        "real_change_pct": round(real_change * 100, 2),
        "baseline": baseline,
        "projected": projected,
    }


def _simulate_investment(monthly_amount, income, expense, net_worth, months,
                         annual_return, inflation, volatility, monte_carlo=False):
    baseline = _project(income, expense, net_worth, months, inflation=inflation)
    projected = _project(income, expense, net_worth, months,
                         monthly_delta=-monthly_amount, inflation=inflation)

    monthly_growth = (1 + annual_return) ** (1 / 12) - 1
    invested_value = 0.0
    invest_series = []
    for m in range(1, months + 1):
        invested_value = (invested_value + monthly_amount) * (1 + monthly_growth)
        invest_series.append({
            "month": m,
            "invested_value": round(invested_value, 2),
            "real_value": round(_real_value(invested_value, inflation, m), 2),
            "contributed": round(monthly_amount * m, 2),
        })

    contributed = monthly_amount * months
    gain = invested_value - contributed
    post_tax_value = contributed + _apply_ltcg(gain)

    result = {
        "scenario": "investment",
        "summary": (
            f"Investing Rs {monthly_amount:,.0f}/month at {annual_return * 100:.0f}% grows to "
            f"Rs {invested_value:,.0f} after {months} months "
            f"(Rs {post_tax_value:,.0f} post-tax, "
            f"Rs {_real_value(post_tax_value, inflation, months):,.0f} in today's money)."
        ),
        "total_contributed": round(contributed, 2),
        "nominal_value": round(invested_value, 2),
        "post_tax_value": round(post_tax_value, 2),
        "real_value_today": round(_real_value(post_tax_value, inflation, months), 2),
        "gain": round(gain, 2),
        "tax_paid": round(gain - _apply_ltcg(gain), 2),
        "baseline": baseline,
        "projected": projected,
        "investment_growth": invest_series,
    }

    if monte_carlo:
        result["monte_carlo"] = _monte_carlo_paths(
            monthly_amount, months, annual_return, volatility
        )
    return result


def _simulate_savings(extra_monthly_savings, income, expense, net_worth, months,
                      annual_return, inflation, volatility):
    baseline = _project(income, expense, net_worth, months, inflation=inflation)
    projected = _project(income, expense, net_worth, months,
                         monthly_delta=extra_monthly_savings, inflation=inflation)
    gain = projected[-1]["projected_net_worth"] - baseline[-1]["projected_net_worth"]

    return {
        "scenario": "savings",
        "summary": (
            f"Saving an extra Rs {extra_monthly_savings:,.0f}/month adds Rs {gain:,.0f} "
            f"to net worth over {months} months "
            f"(Rs {_real_value(gain, inflation, months):,.0f} in today's money)."
        ),
        "nominal_gain": round(gain, 2),
        "real_gain": round(_real_value(gain, inflation, months), 2),
        "baseline": baseline,
        "projected": projected,
    }


def _simulate_prepay_debt(db, user_id, amount, liability_id, income, expense,
                          net_worth, months, annual_return, inflation, volatility):
    """Prepay a loan versus investing the same amount - real amortisation."""
    comparison = debt.prepay_vs_invest(
        db, user_id, amount, annual_return=annual_return,
        tax_rate=LTCG_RATE, liability_id=liability_id,
    )
    if "error" in comparison:
        return comparison

    baseline = _project(income, expense, net_worth, months, inflation=inflation)
    # Prepaying removes the lump sum now but frees the EMI once the loan clears.
    projected = _project(income, expense, net_worth, months,
                         one_time_hit=amount, inflation=inflation)

    return {
        "scenario": "prepay_debt",
        "summary": comparison["summary"],
        "comparison": comparison,
        "baseline": baseline,
        "projected": projected,
    }


# --- Narrative -------------------------------------------------------------

def _ai_enhance_summary(result: dict, snapshot: dict, scenario_type: str,
                        db: Session, user_id: int) -> str:
    """Rewrite the computed summary as advice. Numbers come from the model above."""
    if not llm_client.llm_configured():
        return result.get("summary", "Simulation complete.")

    baseline_end = (result.get("baseline") or [{}])[-1].get("projected_net_worth", 0)
    projected_end = (result.get("projected") or [{}])[-1].get("projected_net_worth", 0)
    delta = projected_end - baseline_end

    prompt = f"""You are a financial advisor summarising a scenario simulation in 2-3 sentences.

Scenario: {scenario_type}
Current monthly income: Rs {snapshot['total_income_month']:,.0f}
Current monthly expenses: Rs {snapshot['total_expense_month']:,.0f}
Current savings rate: {snapshot['savings_rate']:.1f}%
Current net worth: Rs {snapshot['net_worth']:,.0f}

Computed result (these numbers are authoritative - do not change them):
- Baseline net worth at end of projection: Rs {baseline_end:,.0f}
- Projected net worth under this scenario: Rs {projected_end:,.0f}
- Net impact: Rs {delta:,.0f}
- Model summary: {prompt_safety.scrub(result.get('summary', ''), 500)}

Write a concise, actionable 2-3 sentence summary. Use Rs with Indian digit
grouping. Do not invent figures beyond those given. Do not recommend specific
stocks, funds or securities."""

    llm_result = llm_client.generate_detailed(
        prompt=prompt,
        fallback=result.get("summary", "Simulation complete."),
        system_prompt=(
            "You are FinMate, an AI financial advisor. Be concise and data-driven. "
            "You are not a SEBI-registered investment adviser; never name specific securities."
        ),
        temperature=0.5,
    )
    entitlements.record_usage(
        db, user_id, "simulate", llm_result.provider, llm_result.model,
        llm_result.prompt_tokens, llm_result.completion_tokens,
        llm_result.latency_ms, llm_result.ok,
    )
    return llm_result.text
