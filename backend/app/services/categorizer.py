"""
Transaction categorisation with a per-user correction loop.

Two layers, cheapest first:

  1. A user's own correction for that merchant. When someone recategorises a
     transaction, the mapping is remembered and wins from then on.
  2. Keyword matching on the merchant/description.

The correction loop is the part that matters. A categoriser that gets Swiggy
wrong once and keeps getting it wrong is worse than useless; one that is
corrected once and never repeats the mistake is the whole "it learns you"
claim, and it costs a lookup table rather than a model.
"""
import logging
import re

from sqlalchemy.orm import Session

from .. import models
from .dedupe import normalize_description

logger = logging.getLogger("finmate.categorizer")

CATEGORIES = [
    "Salary", "Freelance", "Investment Returns", "Other Income",
    "Rent", "Groceries", "Food Delivery", "Transport", "Utilities",
    "Entertainment", "Shopping", "Subscriptions", "Health",
    "Education", "Insurance", "EMI/Loan", "Transfer", "Other",
]

# Ordered: the first match wins, so put specific merchants above generic words.
KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("Food Delivery", ("swiggy", "zomato", "eatsure", "dominos", "pizza",
                       "mcdonald", "kfc", "burger", "dinner", "lunch",
                       "breakfast", "restaurant", "cafe", "coffee", "starbucks",
                       "food", "snack", "chai", "biryani")),
    ("Groceries", ("bigbasket", "blinkit", "zepto", "dmart", "grocer",
                   "supermarket", "instamart", "vegetable", "milk", "kirana")),
    ("Transport", ("uber", "ola", "rapido", "auto", "cab", "taxi", "metro",
                   "petrol", "diesel", "fuel", "irctc", "train", "bus",
                   "flight", "indigo", "parking", "toll")),
    ("Subscriptions", ("netflix", "spotify", "prime", "hotstar", "youtube",
                       "subscription", "icloud", "jiosaavn", "gym membership")),
    ("Utilities", ("electricity", "bescom", "water bill", "broadband", "wifi",
                   "airtel", "jio", "vodafone", "vi recharge", "recharge",
                   "gas bill", "lpg", "utility")),
    ("Rent", ("rent", "landlord", "maintenance", "society")),
    ("Health", ("apollo", "pharmeasy", "1mg", "pharmacy", "doctor", "hospital",
                "clinic", "medicine", "medical", "dental")),
    ("Entertainment", ("bookmyshow", "movie", "cinema", "pvr", "inox", "game",
                       "concert", "outing", "party")),
    ("Shopping", ("amazon", "flipkart", "myntra", "ajio", "nykaa", "meesho",
                  "shopping", "clothes", "shoes", "electronics", "decathlon")),
    ("Education", ("course", "udemy", "coursera", "tuition", "school", "college",
                   "exam", "book")),
    ("Insurance", ("insurance", "policy", "premium", "lic")),
    ("EMI/Loan", ("emi", "loan", "credit card bill", "repayment")),
    ("Salary", ("salary", "payroll", "stipend")),
    ("Freelance", ("freelance", "invoice", "consulting", "client")),
    ("Investment Returns", ("dividend", "interest credit", "mutual fund",
                            "sip redemption", "capital gain")),
    ("Transfer", ("transfer", "upi to", "sent to", "imps", "neft", "rtgs")),
]


def _lookup_rule(db: Session, user_id: int, merchant_key: str):
    if not merchant_key:
        return None
    return (
        db.query(models.MerchantRule)
        .filter(
            models.MerchantRule.user_id == user_id,
            models.MerchantRule.merchant_key == merchant_key,
        )
        .first()
    )


def categorize(db: Session, user_id: int, text: str, amount: float = 0.0) -> dict:
    """
    Categorise from free text. Returns {category, source, confidence}.

    `source` is reported so the UI can say "you taught me this" rather than
    presenting a learned rule and a keyword guess as the same thing.
    """
    key = normalize_description(text)

    rule = _lookup_rule(db, user_id, key)
    if rule:
        return {"category": rule.category, "source": "user_rule", "confidence": 1.0}

    lowered = (text or "").lower()
    for category, words in KEYWORDS:
        if any(w in lowered for w in words):
            # An inflow matched against an expense keyword is almost always
            # income that happens to share a word ("salary from client").
            if amount > 0 and category not in (
                "Salary", "Freelance", "Investment Returns", "Other Income", "Transfer"
            ):
                continue
            return {"category": category, "source": "keyword", "confidence": 0.7}

    default = "Other Income" if amount > 0 else "Other"
    return {"category": default, "source": "default", "confidence": 0.3}


def learn(db: Session, user_id: int, text: str, category: str) -> None:
    """
    Remember a user's correction for this merchant.

    Upsert rather than insert: correcting the same merchant twice should
    replace the rule, not accumulate conflicting ones.
    """
    key = normalize_description(text)
    if not key or category not in CATEGORIES:
        return

    rule = _lookup_rule(db, user_id, key)
    if rule:
        rule.category = category
        rule.hit_count = (rule.hit_count or 0) + 1
    else:
        db.add(models.MerchantRule(
            user_id=user_id, merchant_key=key, category=category, hit_count=1,
        ))
    db.commit()
    logger.info("Learned %s -> %s for user %s", key, category, user_id)


def rules_for(db: Session, user_id: int) -> list:
    return (
        db.query(models.MerchantRule)
        .filter(models.MerchantRule.user_id == user_id)
        .order_by(models.MerchantRule.hit_count.desc())
        .all()
    )
