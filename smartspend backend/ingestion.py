import io
import re
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

    try:
        import llm_coach
        llm_coach._ensure_configured()
        import google.generativeai as genai
        model = genai.GenerativeModel(llm_coach.MODEL_NAME)
        categories = list(CATEGORY_KEYWORDS.keys()) + ["Other"]
        prompt = (
            f"Classify this bank transaction merchant/description into exactly one "
            f"of these categories: {', '.join(categories)}.\n"
            f"Merchant/description: \"{merchant_text}\"\n"
            f"Reply with only the category name, nothing else."
        )
        response = model.generate_content(prompt)
        guess = response.text.strip().split("\n")[0].strip()
        if guess in categories:
            return guess
        return "Other"
    except Exception:
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
        amount = float(amount_match.group(1).replace(",", ""))

        merchant_match = MERCHANT_PATTERN.search(line)
        merchant = merchant_match.group(1).strip() if merchant_match else "Unknown"

        date_match = DATE_PATTERN.search(line)
        txn_date = _parse_date_flexible(date_match.group(1), today) if date_match else today

        category = categorize_with_llm_fallback(merchant)

        results.append({
            "amount": amount,
            "category": category,
            "merchant": merchant,
            "date": txn_date.isoformat(),
            "note": None,
            "source": "sms",
        })

    return results


# ---------- Statement parsing (CSV / PDF) ----------

DATE_COL_HINTS = ["date", "txn date", "transaction date", "value date"]
DESC_COL_HINTS = ["narration", "description", "particulars", "details", "remarks"]
DEBIT_COL_HINTS = ["debit", "withdrawal", "dr amt", "withdrawal amt", "amount"]


def _find_column(columns: list[str], hints: list[str]) -> str | None:
    lowered = {c: c.lower().strip() for c in columns}
    for col, low in lowered.items():
        for hint in hints:
            if hint in low:
                return col
    return None


def _dataframe_to_transactions(df: pd.DataFrame, today: date) -> list[dict]:
    columns = list(df.columns)
    date_col = _find_column(columns, DATE_COL_HINTS)
    desc_col = _find_column(columns, DESC_COL_HINTS)
    debit_col = _find_column(columns, DEBIT_COL_HINTS)

    if not desc_col or not debit_col:
        return []

    results = []
    for _, row in df.iterrows():
        raw_amount = row.get(debit_col)
        if pd.isna(raw_amount):
            continue
        try:
            amount = float(str(raw_amount).replace(",", "").replace("₹", "").strip())
        except ValueError:
            continue
        if amount <= 0:
            continue

        description = str(row.get(desc_col, "")).strip()
        if not description or description.lower() == "nan":
            continue

        txn_date = today
        if date_col:
            raw_date = row.get(date_col)
            parsed = pd.to_datetime(raw_date, errors="coerce", dayfirst=True)
            if pd.notna(parsed):
                txn_date = parsed.date()

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
        for page in pdf.pages:
            table = page.extract_table()
            if not table or len(table) < 2:
                continue
            header, *rows = table
            header = [h.strip() if h else "" for h in header]
            df = pd.DataFrame(rows, columns=header)
            all_transactions.extend(_dataframe_to_transactions(df, today))

    return all_transactions
