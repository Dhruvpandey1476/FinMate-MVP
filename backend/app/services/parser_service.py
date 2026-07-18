"""
Parser Service — Bank statement CSV/PDF parser with AI-powered categorization.

Supports:
- Generic CSV (auto-detects columns)
- Common Indian bank formats (SBI, HDFC, ICICI, Axis)
- UPI transaction CSVs
- PDF bank statements (via pdfplumber)
"""
import io
import logging
import re
from datetime import datetime
from typing import Optional

import pandas as pd
from ..services import llm_client

logger = logging.getLogger("finmate.parser")

# Common column name patterns
DATE_PATTERNS = ["date", "txn date", "transaction date", "value date", "posting date", "txn_date"]
AMOUNT_PATTERNS = ["amount", "txn amount", "transaction amount", "debit/credit", "withdrawal", "deposit"]
DEBIT_PATTERNS = ["debit", "withdrawal", "dr", "debit amount", "withdrawal amt"]
CREDIT_PATTERNS = ["credit", "deposit", "cr", "credit amount", "deposit amt"]
DESC_PATTERNS = ["description", "narration", "particulars", "remarks", "details", "transaction details", "merchant"]
BALANCE_PATTERNS = ["balance", "closing balance", "available balance"]


def parse_csv(file_content: bytes, filename: str = "") -> list[dict]:
    """
    Parse a bank statement CSV and return normalized transactions.
    Auto-detects column mapping. Returns list of dicts with:
    {date, amount, category, type, merchant, note}
    """
    try:
        # Decode with a tolerant set of encodings
        text = None
        for encoding in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
            try:
                text = file_content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("Could not decode CSV with any supported encoding")

        # Bank statements often have preamble/summary rows above the real table
        # and ragged columns — locate the header row and skip bad lines.
        df = _read_transactions_frame(text)
        if df is None or df.empty:
            return []

        # Normalize column names
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        # Auto-detect column mapping
        date_col = _find_column(df.columns, DATE_PATTERNS)
        desc_col = _find_column(df.columns, DESC_PATTERNS)
        
        # Check for separate debit/credit columns vs single amount
        debit_col = _find_column(df.columns, DEBIT_PATTERNS)
        credit_col = _find_column(df.columns, CREDIT_PATTERNS)
        amount_col = _find_column(df.columns, AMOUNT_PATTERNS)
        
        if not date_col:
            raise ValueError("Could not identify date column in CSV")
        
        transactions = []
        for _, row in df.iterrows():
            try:
                # Parse date
                date = _parse_date(str(row[date_col]))
                if not date:
                    continue
                
                # Parse amount
                if debit_col and credit_col:
                    debit = _parse_amount(row.get(debit_col, 0))
                    credit = _parse_amount(row.get(credit_col, 0))
                    amount = credit - debit if credit > 0 else -debit
                elif amount_col:
                    amount = _parse_amount(row[amount_col])
                else:
                    continue
                
                if amount == 0:
                    continue
                
                # Parse description
                description = str(row.get(desc_col, "")) if desc_col else ""
                merchant = _extract_merchant(description)
                
                txn = {
                    "date": date.isoformat(),
                    "amount": round(amount, 2),
                    "type": "income" if amount > 0 else "expense",
                    "merchant": merchant,
                    "note": description[:200] if description else None,
                    "category": "Uncategorized",  # Will be AI-categorized
                    "is_recurring": False,
                }
                transactions.append(txn)
            except Exception as e:
                logger.debug("Skipping row: %s", e)
                continue
        
        # AI-categorize all transactions in batch
        if transactions:
            transactions = categorize_transactions(transactions)
        
        logger.info("Parsed %d transactions from CSV '%s'", len(transactions), filename)
        return transactions
        
    except Exception as e:
        logger.error("CSV parsing failed: %s", e)
        raise ValueError(f"Failed to parse CSV: {str(e)}")


def _read_transactions_frame(text: str):
    """Locate the header row (skipping bank preamble) and parse tolerantly."""
    lines = text.splitlines()
    value_patterns = AMOUNT_PATTERNS + DEBIT_PATTERNS + CREDIT_PATTERNS + DESC_PATTERNS
    header_idx = 0
    for i, line in enumerate(lines[:50]):
        low = line.lower()
        if any(p in low for p in DATE_PATTERNS) and any(p in low for p in value_patterns):
            header_idx = i
            break

    for sep in [",", ";", "\t", "|"]:
        try:
            df = pd.read_csv(
                io.StringIO(text),
                skiprows=header_idx,
                sep=sep,
                engine="python",
                on_bad_lines="skip",
            )
            if df.shape[1] >= 2:
                return df
        except Exception:
            continue
    return None


def parse_pdf(file_content: bytes, filename: str = "") -> list[dict]:
    """Parse bank statement PDF using pdfplumber."""
    try:
        import pdfplumber
        
        transactions = []
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    
                    # Try to parse table as transaction data
                    headers = [str(h).strip().lower() if h else "" for h in table[0]]
                    
                    for row in table[1:]:
                        try:
                            row_dict = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
                            
                            date_col = _find_column(headers, DATE_PATTERNS)
                            if not date_col or not row_dict.get(date_col):
                                continue
                            
                            date = _parse_date(str(row_dict[date_col]))
                            if not date:
                                continue
                            
                            debit_col = _find_column(headers, DEBIT_PATTERNS)
                            credit_col = _find_column(headers, CREDIT_PATTERNS)
                            amount_col = _find_column(headers, AMOUNT_PATTERNS)
                            
                            if debit_col and credit_col:
                                debit = _parse_amount(row_dict.get(debit_col, 0))
                                credit = _parse_amount(row_dict.get(credit_col, 0))
                                amount = credit - debit if credit > 0 else -debit
                            elif amount_col:
                                amount = _parse_amount(row_dict.get(amount_col, 0))
                            else:
                                continue
                            
                            if amount == 0:
                                continue
                            
                            desc_col = _find_column(headers, DESC_PATTERNS)
                            description = str(row_dict.get(desc_col, "")) if desc_col else ""
                            
                            transactions.append({
                                "date": date.isoformat(),
                                "amount": round(amount, 2),
                                "type": "income" if amount > 0 else "expense",
                                "merchant": _extract_merchant(description),
                                "note": description[:200] if description else None,
                                "category": "Uncategorized",
                                "is_recurring": False,
                            })
                        except Exception:
                            continue
        
        # Many statements (e.g. PhonePe/GPay) are text lists, not tables.
        if not transactions:
            transactions = _parse_pdf_text(io.BytesIO(file_content))

        if transactions:
            transactions = categorize_transactions(transactions)

        logger.info("Parsed %d transactions from PDF '%s'", len(transactions), filename)
        return transactions

    except ImportError:
        raise ValueError("PDF parsing requires pdfplumber. Install with: pip install pdfplumber")
    except Exception as e:
        logger.error("PDF parsing failed: %s", e)
        raise ValueError(f"Failed to parse PDF: {str(e)}")


_PDF_DATE_RE = re.compile(
    r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}'
    r'|\d{4}-\d{2}-\d{2}'
    r'|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}'
    r'|\d{1,2}\s+[A-Za-z]{3,9},?\s+\d{4})'
)
_PDF_AMT_RE = re.compile(r'(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)', re.I)


def _parse_pdf_text(fp) -> list[dict]:
    """Fallback for text-list PDFs (PhonePe/GPay). Tracks the current date and
    emits a transaction whenever a ₹ amount appears on/under it."""
    import pdfplumber
    lines = []
    with pdfplumber.open(fp) as pdf:
        for page in pdf.pages:
            lines.extend((page.extract_text() or "").split("\n"))

    txns = []
    current_date = None
    for line in lines:
        dm = _PDF_DATE_RE.search(line)
        if dm:
            d = _parse_date(dm.group(1).replace(",", ""))
            if d:
                current_date = d
        am = _PDF_AMT_RE.search(line)
        if am and current_date:
            amount = _parse_amount(am.group(1))
            if amount == 0:
                continue
            low = line.lower()
            is_income = any(w in low for w in
                            ["credit", "received", "refund", "cashback", "deposit", "added", "money received"])
            desc = line.strip()[:150]
            txns.append({
                "date": current_date.isoformat(),
                "amount": round(amount if is_income else -amount, 2),
                "type": "income" if is_income else "expense",
                "merchant": _extract_merchant(desc),
                "note": desc,
                "category": "Uncategorized",
                "is_recurring": False,
            })
    return txns


def categorize_transactions(transactions: list[dict]) -> list[dict]:
    """
    Use LLM to auto-categorize transactions based on merchant/description.
    Processes in batches for efficiency.
    """
    CATEGORIES = [
        "Salary", "Freelance", "Investment Returns", "Other Income",
        "Rent", "Groceries", "Food Delivery", "Transport", "Utilities",
        "Entertainment", "Shopping", "Subscriptions", "Health",
        "Education", "Insurance", "EMI/Loan", "Transfer", "Other"
    ]
    
    # Build batch prompt
    batch_items = []
    for i, txn in enumerate(transactions[:100]):  # Limit to 100 per batch
        desc = txn.get("note", "") or txn.get("merchant", "") or "Unknown"
        amt = txn["amount"]
        batch_items.append(f"{i}. Amount: ₹{amt:,.0f} | Description: {desc[:80]}")
    
    prompt = f"""Categorize these bank transactions. Available categories:
{', '.join(CATEGORIES)}

Transactions:
{chr(10).join(batch_items)}

Respond with a JSON array of objects: [{{"index": 0, "category": "...", "merchant": "...", "is_recurring": false}}]
- "merchant" should be a clean merchant name extracted from the description
- "is_recurring" should be true for rent, subscriptions, EMIs, salary, etc.
Keep it simple and accurate."""

    try:
        result = llm_client.generate_json(prompt=prompt, fallback=[])
        
        if isinstance(result, list):
            for item in result:
                idx = item.get("index", -1)
                if 0 <= idx < len(transactions):
                    transactions[idx]["category"] = item.get("category", "Other")
                    if item.get("merchant"):
                        transactions[idx]["merchant"] = item["merchant"]
                    if item.get("is_recurring") is not None:
                        transactions[idx]["is_recurring"] = item["is_recurring"]
    except Exception as e:
        logger.warning("AI categorization failed: %s — using defaults", e)
        # Fallback: simple keyword-based categorization
        for txn in transactions:
            txn["category"] = _keyword_categorize(txn)
    
    return transactions


def _keyword_categorize(txn: dict) -> str:
    """Simple keyword-based fallback categorization."""
    text = (txn.get("note", "") + " " + (txn.get("merchant", "") or "")).lower()
    
    if any(w in text for w in ["salary", "payroll", "employer"]):
        return "Salary"
    if any(w in text for w in ["swiggy", "zomato", "food", "restaurant", "cafe"]):
        return "Food Delivery"
    if any(w in text for w in ["uber", "ola", "metro", "petrol", "fuel", "parking"]):
        return "Transport"
    if any(w in text for w in ["rent", "landlord", "housing"]):
        return "Rent"
    if any(w in text for w in ["netflix", "spotify", "prime", "subscription", "hotstar"]):
        return "Subscriptions"
    if any(w in text for w in ["amazon", "flipkart", "myntra", "shopping"]):
        return "Shopping"
    if any(w in text for w in ["electricity", "water", "gas", "internet", "wifi", "jio", "airtel"]):
        return "Utilities"
    if any(w in text for w in ["hospital", "doctor", "pharmacy", "medicine", "health"]):
        return "Health"
    if any(w in text for w in ["emi", "loan", "repayment"]):
        return "EMI/Loan"
    if any(w in text for w in ["mutual fund", "sip", "investment", "stock"]):
        return "Investment Returns" if txn["amount"] > 0 else "Other"
    if txn["amount"] > 0:
        return "Other Income"
    return "Other"


def _find_column(columns, patterns) -> Optional[str]:
    """Find a column that matches any of the given patterns."""
    for col in columns:
        col_clean = str(col).strip().lower()
        for pattern in patterns:
            if pattern in col_clean or col_clean in pattern:
                return col
    return None


def _parse_date(date_str: str) -> Optional[datetime]:
    """Try multiple date formats common in Indian bank/UPI statements."""
    formats = [
        "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y",
        "%d %b %Y", "%d-%b-%Y", "%d %B %Y", "%Y-%m-%dT%H:%M:%S",
        "%m/%d/%Y", "%d/%m/%Y %H:%M:%S",
        "%b %d %Y", "%B %d %Y",
    ]
    # Normalize: drop commas, collapse whitespace, keep only the date part
    # (statements often append a time like "Jul 05, 2025 10:31 AM").
    raw = str(date_str).strip()
    normalized = re.sub(r"\s+", " ", raw.replace(",", "")).strip()
    candidates = [raw, normalized]
    # Also try just the first 3 tokens (date without trailing time)
    parts = normalized.split(" ")
    if len(parts) > 3:
        candidates.append(" ".join(parts[:3]))
    for cand in candidates:
        for fmt in formats:
            try:
                return datetime.strptime(cand, fmt)
            except ValueError:
                continue
    return None


def _parse_amount(value) -> float:
    """Parse amount from various formats."""
    if pd.isna(value) or value is None or str(value).strip() == "":
        return 0.0
    s = str(value).strip()
    s = s.replace(",", "").replace("₹", "").replace("INR", "").replace("Rs.", "").replace("Rs", "")
    s = re.sub(r"[^\d.\-+]", "", s)
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def _extract_merchant(description: str) -> Optional[str]:
    """Extract merchant name from transaction description."""
    if not description:
        return None
    
    # UPI patterns
    upi_match = re.search(r"(?:UPI[/-])?(?:.*?[-/])?\s*([A-Za-z][A-Za-z\s]+?)(?:\s*[-/@]|$)", description)
    if upi_match:
        merchant = upi_match.group(1).strip()
        if len(merchant) > 2:
            return merchant[:50]
    
    # Take first meaningful words
    words = description.split()[:4]
    return " ".join(words)[:50] if words else None
