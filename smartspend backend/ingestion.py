import io
import re
from decimal import Decimal
from datetime import date, datetime

import pandas as pd

# ---------- Categorization ----------

CATEGORY_KEYWORDS = {
    "Food": [
        "swiggy", "zomato", "dominos", "domino's", "mcdonald", "kfc", "pizza",
        "restaurant", "cafe", "starbucks", "burger", "faasos", "eatsure",
    ],
    "Groceries": [
        "bigbasket", "blinkit", "zepto", "dmart", "grofers", "instamart",
        "grocery", "supermarket", "reliance fresh", "more retail",
    ],
    "Transport": [
        "uber", "ola", "rapido", "irctc", "indianoil", "bharat petroleum",
        "petrol", "diesel", "metro", "redbus", "fuel", "parking",
    ],
    "Shopping": [
        "amazon", "flipkart", "myntra", "ajio", "meesho", "nykaa",
        "shopping", "mall", "decathlon",
    ],
    "Entertainment": [
        "netflix", "spotify", "hotstar", "bookmyshow", "prime video",
        "pvr", "inox", "youtube premium", "gaana", "wynk",
    ],
    "Bills": [
        "electricity", "airtel", "jio", "vodafone", "vi ", "broadband",
        "recharge", "insurance", "wifi", "gas bill", "water bill",
    ],
    "Health": [
        "pharmacy", "apollo", "medplus", "hospital", "clinic", "medicine",
        "diagnostic", "practo",
    ],
}


def categorize_by_keywords(text: str) -> str | None:
    lowered = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in lowered:
                return category
    return None


def categorize_with_llm_fallback(merchant_text: str) -> str:
    """Try keyword match first; if nothing hits, ask the LLM to pick from the
    known category list. Falls back to 'Uncategorized' if the LLM is unavailable."""
    matched = categorize_by_keywords(merchant_text)
    if matched:
        return matched

    # Offline fallback avoids one AI request per unknown statement row.
    return "Uncategorized"


# ---------- SMS parsing ----------

AMOUNT_PATTERN = re.compile(r"(?:Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)
MERCHANT_PATTERN = re.compile(
    r"(?:at|to|towards)\s+([A-Za-z0-9&.\-\s]+?)(?:\s+on\s|\s+dated\s|\s+A/c|\s+Avl|\.|$)",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})")
CREDIT_INDICATORS = ["credited", "refund", "cashback", "reversed"]
DEBIT_INDICATORS = ["debited", "spent", "paid", "purchase", "debit"]


def _parse_date_flexible(date_str: str, fallback: date) -> date:
    for fmt in ("%d-%m-%y", "%d-%m-%Y", "%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return fallback


def parse_sms_text(raw_text: str, today: date = None) -> list[dict]:
    """Parses one bank SMS per line into structured transactions.
    Skips lines that look like credits/refunds rather than spends."""
    if today is None:
        today = date.today()

    results = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue

        lowered = line.lower()
        if any(word in lowered for word in CREDIT_INDICATORS):
            continue
        if not any(word in lowered for word in DEBIT_INDICATORS):
            continue

        amount_match = AMOUNT_PATTERN.search(line)
        if not amount_match:
            continue
        amount = Decimal(amount_match.group(1).replace(",", ""))
        if amount <= 0 or amount > 1000000000:
            continue

        merchant_match = MERCHANT_PATTERN.search(line)
        merchant = merchant_match.group(1).strip() if merchant_match else "Unknown"

        date_match = DATE_PATTERN.search(line)
        txn_date = _parse_date_flexible(date_match.group(1), None) if date_match else today
        if txn_date is None:
            continue

        category = categorize_with_llm_fallback(merchant)

        results.append({
            "amount": amount,
            "category": category,
            "merchant": merchant,
            "date": txn_date.isoformat(),
            "note": None,
            "source": "sms",
        })

    if len(results) > 500:
        raise ValueError("SMS batch exceeds 500 debit messages")
    return results


# ---------- Statement parsing (CSV / PDF) ----------

DATE_COL_HINTS = ["date", "txn date", "transaction date", "value date"]
DESC_COL_HINTS = ["narration", "description", "particulars", "details", "remarks"]
DEBIT_COL_HINTS = ["debit amount", "withdrawal amount", "debit", "withdrawal", "dr amt", "withdrawal amt"]
CREDIT_COL_HINTS = ["credit", "deposit", "cr amt"]


def _find_column(columns: list[str], hints: list[str]) -> str | None:
    lowered = {c: c.lower().strip() for c in columns}
    for hint in hints:
        for col, low in lowered.items():
            if hint in low:
                return col
    return None


def _dataframe_to_transactions(df: pd.DataFrame, today: date) -> list[dict]:
    columns = list(df.columns)
    date_col = _find_column(columns, DATE_COL_HINTS)
    desc_col = _find_column(columns, DESC_COL_HINTS)
    debit_columns = [c for c in columns if not any(h in c.lower() for h in ("credit", "deposit", "balance"))]
    debit_col = _find_column(debit_columns, DEBIT_COL_HINTS)
    credit_col = _find_column(columns, CREDIT_COL_HINTS)
    amount_col = next((c for c in columns if c.lower().strip() in {"amount", "transaction amount", "signed amount"}), None)
    type_col = next((c for c in columns if c.lower().strip() in {"type", "transaction type", "dr/cr", "debit/credit"}), None)
    if len(df) > 500:
        raise ValueError("Statement exceeds 500 rows; split it before importing")

    if not date_col or not desc_col or (not debit_col and not amount_col):
        return []

    results = []
    for _, row in df.iterrows():
        raw_amount = row.get(debit_col or amount_col)
        if pd.isna(raw_amount):
            continue
        try:
            amount = Decimal(str(raw_amount).replace(",", "").replace("₹", "").strip())
        except Exception:
            continue
        if not amount.is_finite() or abs(amount) > 1000000000 or amount != amount.quantize(Decimal("0.01")):
            continue
        if not debit_col:
            kind = str(row.get(type_col, "")).strip().lower() if type_col else ""
            if kind in {"credit", "cr", "deposit", "income"}:
                continue
            if kind in {"debit", "dr", "withdrawal", "expense"}:
                amount = abs(amount)
            elif type_col:
                continue
            elif amount < 0:
                amount = -amount
            else:
                # Unsigned generic amounts cannot prove expense direction.
                continue
        if amount <= 0:
            continue

        description = str(row.get(desc_col, "")).strip()
        if not description or description.lower() == "nan":
            continue

        txn_date = today
        if date_col:
            raw_date = row.get(date_col)
            try:
                txn_date = date.fromisoformat(str(raw_date).strip())
            except ValueError:
                txn_date = _parse_date_flexible(str(raw_date).strip(), None)
                if txn_date is None:
                    continue

        category = categorize_with_llm_fallback(description)

        results.append({
            "amount": amount,
            "category": category,
            "merchant": description[:80],
            "date": txn_date.isoformat(),
            "note": None,
            "source": "statement",
        })

    return results


def parse_csv_statement(file_bytes: bytes, today: date = None) -> list[dict]:
    if today is None:
        today = date.today()
    df = pd.read_csv(io.BytesIO(file_bytes))
    return _dataframe_to_transactions(df, today)


def parse_pdf_statement(file_bytes: bytes, today: date = None) -> list[dict]:
    if today is None:
        today = date.today()
    import pdfplumber

    all_transactions = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        if len(pdf.pages) > 30:
            raise ValueError("PDF exceeds 30 pages")
        for page in pdf.pages:
            table = page.extract_table()
            if not table or len(table) < 2:
                continue
            header, *rows = table
            header = [h.strip() if h else "" for h in header]
            df = pd.DataFrame(rows, columns=header)
            all_transactions.extend(_dataframe_to_transactions(df, today))
            if len(all_transactions) > 500:
                raise ValueError("PDF exceeds 500 debit rows")

    return all_transactions
