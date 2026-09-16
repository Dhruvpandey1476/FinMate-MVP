"""
Curated Indian tax knowledge base.

Hand-authored, dated, and deliberately small. Every entry carries an
`as_of_date` and a `source` so anything shown to a user can say which rule it
came from and when that rule was current - the same transparency principle as
the CFO's reasoning trace.

This is a retrieval corpus, not a tax engine. FinMate organises records and
flags items that may be relevant when filing; it does not compute anyone's tax
liability, and no output here should ever be worded as if it does.
"""
from datetime import date

AS_OF = "2025-04-01"  # start of FY 2025-26
FINANCIAL_YEAR = "2025-26"

# Categories whose spending is commonly relevant at filing time, mapped to the
# section a user or their accountant would look at. Presence here means "worth
# reviewing", never "this is deductible" - eligibility depends on the
# instrument and the taxpayer, which FinMate does not know.
CATEGORY_FLAGS = {
    "Insurance": {
        "sections": ["80C", "80D"],
        "note": "Life premiums commonly fall under 80C; health premiums under 80D. "
                "Which applies depends on the policy.",
    },
    "Health": {
        "sections": ["80D"],
        "note": "Preventive health check-ups and medical insurance may be relevant "
                "under 80D. Ordinary medical bills usually are not.",
    },
    "Education": {
        "sections": ["80E", "80C"],
        "note": "Interest on an education loan may be relevant under 80E; tuition "
                "fees for children under 80C.",
    },
    "EMI/Loan": {
        "sections": ["24(b)", "80C", "80E"],
        "note": "Home loan interest may be relevant under 24(b) and principal under "
                "80C; education loan interest under 80E. Personal loans are not.",
    },
    "Rent": {
        "sections": ["HRA", "80GG"],
        "note": "Rent paid may support an HRA claim if your salary includes it, or "
                "80GG if it does not.",
    },
    "Donation": {
        "sections": ["80G"],
        "note": "Only donations to institutions registered under 80G qualify, and "
                "the rate varies by institution.",
    },
}

# Facts the AI CFO and the tax export retrieve from. Keep every entry dated.
FACTS = [
    {
        "id": "80c-limit",
        "topic": "80C",
        "text": "Section 80C allows a deduction of up to Rs 1,50,000 per financial "
                "year, covering instruments such as EPF, PPF, ELSS, life insurance "
                "premiums, principal repayment on a home loan and children's tuition "
                "fees. Available under the old regime only.",
        "as_of_date": AS_OF,
        "source": "Income Tax Act, s.80C",
    },
    {
        "id": "80d-limit",
        "topic": "80D",
        "text": "Section 80D allows up to Rs 25,000 for health insurance premiums for "
                "self, spouse and children, and a further Rs 25,000 for parents "
                "(Rs 50,000 where the parents are senior citizens). Old regime only.",
        "as_of_date": AS_OF,
        "source": "Income Tax Act, s.80D",
    },
    {
        "id": "standard-deduction",
        "topic": "Standard deduction",
        "text": "Salaried taxpayers receive a standard deduction of Rs 75,000 under "
                "the new regime and Rs 50,000 under the old regime.",
        "as_of_date": AS_OF,
        "source": "Finance Act 2024",
    },
    {
        "id": "new-regime-default",
        "topic": "Regime",
        "text": "The new tax regime is the default. The old regime must be opted "
                "into, and is generally only worthwhile where total deductions "
                "(80C, 80D, HRA, home loan interest) are substantial.",
        "as_of_date": AS_OF,
        "source": "Income Tax Act, s.115BAC",
    },
    {
        "id": "24b-home-loan",
        "topic": "24(b)",
        "text": "Interest on a home loan for a self-occupied property is deductible "
                "up to Rs 2,00,000 per year under section 24(b), under the old "
                "regime.",
        "as_of_date": AS_OF,
        "source": "Income Tax Act, s.24(b)",
    },
    {
        "id": "80g-donations",
        "topic": "80G",
        "text": "Donations to institutions registered under 80G may be deducted at "
                "50% or 100% depending on the institution, sometimes subject to a "
                "cap of 10% of adjusted gross total income. Cash donations above "
                "Rs 2,000 do not qualify.",
        "as_of_date": AS_OF,
        "source": "Income Tax Act, s.80G",
    },
    {
        "id": "80e-education-loan",
        "topic": "80E",
        "text": "Interest on an education loan is deductible under section 80E with "
                "no upper limit, for up to eight consecutive years from the year "
                "repayment begins. Principal is not covered.",
        "as_of_date": AS_OF,
        "source": "Income Tax Act, s.80E",
    },
    {
        "id": "80gg-rent",
        "topic": "80GG",
        "text": "Where no HRA is received, rent paid may be deducted under 80GG, "
                "limited to the least of Rs 60,000 per year, 25% of total income, or "
                "rent paid minus 10% of total income.",
        "as_of_date": AS_OF,
        "source": "Income Tax Act, s.80GG",
    },
    {
        "id": "ltcg-equity",
        "topic": "Capital gains",
        "text": "Long-term capital gains on listed equity and equity mutual funds are "
                "taxed at 12.5% above an annual exemption of Rs 1,25,000. Short-term "
                "gains are taxed at 20%.",
        "as_of_date": AS_OF,
        "source": "Finance Act 2024",
    },
    {
        "id": "tds-salary",
        "topic": "TDS",
        "text": "Employers deduct TDS on salary monthly based on the regime and "
                "declared investments. Under-declaring investments early in the year "
                "results in higher TDS that is only recovered as a refund.",
        "as_of_date": AS_OF,
        "source": "Income Tax Act, s.192",
    },
    {
        "id": "itr-deadline",
        "topic": "Filing",
        "text": "The usual deadline for individuals not requiring an audit is 31 July "
                "following the end of the financial year. A belated return may be "
                "filed later with a late fee.",
        "as_of_date": AS_OF,
        "source": "Income Tax Act, s.139",
    },
    {
        "id": "regime-comparison",
        "topic": "Regime",
        "text": "Choosing between regimes is an arithmetic comparison: total tax "
                "under the new regime's lower rates and higher standard deduction, "
                "against the old regime's rates after all eligible deductions.",
        "as_of_date": AS_OF,
        "source": "Income Tax Act, s.115BAC",
    },
]

# Old-regime deduction ceilings, used to show remaining headroom. These are
# limits on what may be claimed, not a statement that a user qualifies.
LIMITS = {
    "80C": 150_000,
    "80D": 25_000,
    "24(b)": 200_000,
}

DISCLAIMER = (
    "FinMate organises your financial records and flags items that may be "
    "relevant when filing. It does not calculate your tax or determine what is "
    "deductible - eligibility depends on your circumstances and the specific "
    f"instruments involved. Figures reflect rules as of {AS_OF} (FY {FINANCIAL_YEAR}). "
    "Confirm anything here with a qualified tax professional."
)


def search(query: str, limit: int = 3) -> list:
    """
    Keyword retrieval over the curated facts.

    Deliberately the same lightweight approach the memory engine falls back to:
    a corpus this small does not justify an embedding index, and keyword
    overlap keeps the retrieved fact explainable.
    """
    words = {w for w in (query or "").lower().split() if len(w) > 2}
    if not words:
        return []

    scored = []
    for fact in FACTS:
        haystack = f"{fact['topic']} {fact['text']}".lower()
        score = sum(1 for w in words if w in haystack)
        if score:
            scored.append((score, fact))

    scored.sort(key=lambda pair: -pair[0])
    return [fact for _, fact in scored[:limit]]


def flags_for_category(category: str):
    return CATEGORY_FLAGS.get(category)
