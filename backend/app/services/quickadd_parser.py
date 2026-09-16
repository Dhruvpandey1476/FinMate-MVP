"""
Quick Add parser - "300 auto" or "spent 1200 on dinner with friends".

Rules first, model only as a fallback. Most quick entries are two tokens and an
amount; sending those to an LLM would add a network round trip and a cost to
something a regex answers in microseconds. The model is reserved for sentences
the rules genuinely cannot read.

Which path handled an entry is recorded on the result and logged, so the rule
coverage can be measured and improved rather than guessed at.
"""
import logging
import re

from sqlalchemy.orm import Session

from . import categorizer, llm_client, prompt_safety

logger = logging.getLogger("finmate.quickadd")

# "1.2k" / "1,200" / "₹1200" / "rs 1200"
_AMOUNT = re.compile(
    r"(?:rs\.?|inr|₹)?\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(k|l|lakh|lac)?\b",
    re.IGNORECASE,
)

# Words that mark direction, and are not part of the description.
_INCOME_WORDS = ("received", "got", "credited", "earned", "refund", "cashback",
                 "salary", "income", "from client", "paid me")
_EXPENSE_WORDS = ("spent", "paid", "bought", "gave", "sent", "for", "on")

_NOISE = re.compile(
    r"\b(spent|paid|bought|gave|sent|received|got|credited|earned|"
    r"rs\.?|inr|today|yesterday|for|on|at|to|the|a|an|of|my|some)\b",
    re.IGNORECASE,
)


def _scale(raw: str, suffix: str | None) -> float:
    value = float(raw.replace(",", ""))
    if not suffix:
        return value
    s = suffix.lower()
    if s == "k":
        return value * 1_000
    if s in ("l", "lakh", "lac"):
        return value * 100_000
    return value


def _clean_description(text: str, amount_span: tuple[int, int]) -> str:
    """Everything that isn't the amount or a filler word."""
    without_amount = text[: amount_span[0]] + " " + text[amount_span[1]:]
    cleaned = _NOISE.sub(" ", without_amount)
    cleaned = re.sub(r"[^\w\s&'-]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_with_rules(text: str) -> dict | None:
    """Return a parsed entry, or None when the rules cannot read it."""
    raw = (text or "").strip()
    if not raw:
        return None

    match = _AMOUNT.search(raw)
    if not match:
        return None

    amount = _scale(match.group(1), match.group(2))
    if amount <= 0:
        return None

    lowered = raw.lower()
    is_income = any(w in lowered for w in _INCOME_WORDS)

    description = _clean_description(raw, match.span())
    if not description:
        return None

    return {
        "amount": amount if is_income else -amount,
        "description": description,
        "is_income": is_income,
        "path": "rules",
    }


def parse_with_llm(text: str) -> dict | None:
    """Fallback for sentences the rules cannot read. Never invents an amount."""
    if not llm_client.llm_configured():
        return None

    prompt = f"""Extract one transaction from this message.

{prompt_safety.fence("user message", prompt_safety.scrub(text, 400))}

Respond with JSON only:
{{"amount": <positive number>, "description": "<merchant or what it was for>",
  "is_income": <true if money came in, false if it went out>}}

If there is no clear amount, respond {{"amount": 0}}."""

    try:
        parsed = llm_client.generate_json(
            prompt=prompt,
            system_prompt=(
                "You extract a single transaction from a short message. "
                "Output JSON only, and never invent an amount that is not stated."
                + prompt_safety.UNTRUSTED_DATA_NOTICE
            ),
            fallback={},
        )
        amount = float(parsed.get("amount") or 0)
        description = str(parsed.get("description") or "").strip()
        if amount <= 0 or not description:
            return None
        is_income = bool(parsed.get("is_income"))
        return {
            "amount": amount if is_income else -amount,
            "description": description[:120],
            "is_income": is_income,
            "path": "llm",
        }
    except Exception as e:
        logger.warning("Quick Add LLM fallback failed: %s", e)
        return None


def parse(db: Session, user_id: int, text: str) -> dict | None:
    """
    Parse a quick-add message into a categorised transaction draft.

    Returns None when no amount can be found - better to ask again than to
    log a transaction the user did not mean.
    """
    result = parse_with_rules(text) or parse_with_llm(text)
    if not result:
        logger.info("Quick Add could not parse: %r", (text or "")[:80])
        return None

    verdict = categorizer.categorize(db, user_id, result["description"], result["amount"])
    result["category"] = verdict["category"]
    result["category_source"] = verdict["source"]
    result["merchant"] = result["description"][:80]

    logger.info(
        "Quick Add parsed via %s: %s %s -> %s (%s)",
        result["path"], result["amount"], result["merchant"],
        result["category"], verdict["source"],
    )
    return result


CATEGORY_EMOJI = {
    "Food Delivery": "🍔", "Groceries": "🛒", "Transport": "🚗",
    "Subscriptions": "📺", "Utilities": "💡", "Rent": "🏠",
    "Health": "💊", "Entertainment": "🎬", "Shopping": "🛍️",
    "Education": "📚", "Insurance": "🛡️", "EMI/Loan": "🏦",
    "Salary": "💰", "Freelance": "💼", "Investment Returns": "📈",
    "Transfer": "🔁", "Other Income": "💰", "Other": "📌",
}


def confirmation(amount: float, category: str) -> str:
    emoji = CATEGORY_EMOJI.get(category, "📌")
    verb = "Added" if amount < 0 else "Recorded"
    return f"{verb} Rs {abs(amount):,.0f} -> {category} {emoji}"
