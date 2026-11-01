import os
import importlib
import threading
import time
import logging
import re
from startup_telemetry import startup_stage

GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or '').strip()
MODEL_NAME = (os.getenv("GEMINI_MODEL") or 'gemini-flash-lite-latest').strip() or 'gemini-flash-lite-latest'
GENERATION_CONFIG = {"max_output_tokens": 1200}
REQUEST_OPTIONS = {"timeout": 20, "retry": None}
FALLBACK_MODEL = os.getenv('GEMINI_FALLBACK_MODEL', 'gemini-flash-latest').strip()
_unavailable_until = {}
_provider_lock = threading.Lock()
logger = logging.getLogger(__name__)

_configured = False
genai = None
_initialization_started = False
_initialization_done = threading.Event()
_initialization_lock = threading.Lock()
AI_INITIALIZATION_TIMEOUT = 10


def _generate(operation, can_retry=lambda: True):
    """Try at most two models, cooling down failures without logging private data."""
    _ensure_configured()
    last_error = None
    for name in dict.fromkeys(filter(None, (MODEL_NAME, FALLBACK_MODEL))):
        with _provider_lock:
            cooling_down = _unavailable_until.get(name, 0) > time.monotonic()
        if cooling_down:
            continue
        try:
            text = operation(name).text
            if not text or not text.strip():
                raise ValueError('Empty AI response')
            return text.strip()[:8000]
        except Exception as error:
            last_error = error
            logger.warning('Coco provider attempt failed: model=%s error=%s', name, type(error).__name__)
            with _provider_lock:
                _unavailable_until[name] = time.monotonic() + 30
            if not can_retry():
                break
    raise RuntimeError('Coco is using recorded-data guidance') from last_error


def recorded_guidance(user_name, monthly_income, pace_data, total_spent=None,
                      remaining=None, recent_transactions=None, message=''):
    """Useful, explicit non-generative guidance; never invent facts or save expenses."""
    text = message.lower()
    has_records = total_spent is None or bool(pace_data or recent_transactions or total_spent)
    prefix = ('Using your saved records: ' if has_records else
              'You have no transactions or budgets recorded for the selected month yet. ')
    if re.search(r'^\s*(?:i|we)\s+(?:just\s+)?(?:spent|paid|bought)\b|^\s*(?:log|record|add)\b|^\s*(?:spent|paid)\s+\d', text):
        return (prefix + 'use Add transaction to enter the amount, category and date, then save it. '
                'I have not recorded an expense from this message.')
    if 'challenge' in text:
        return (prefix + 'try this 7-day savings challenge: track every expense today; review subscriptions tomorrow; '
                'plan meals on day 3; pause an optional purchase on day 4; choose a free activity on day 5; '
                'review category budgets on day 6; and compare your recorded spending on day 7. '
                'Keep essential bills covered throughout.')
    lines = []
    if total_spent is not None and has_records:
        lines.append(f'You have recorded INR {total_spent:,.2f} in spending for the selected month, '
                     f'with INR {remaining:,.2f} of your monthly income remaining.')
    if any(word in text for word in ('biggest', 'largest', 'most')) and recent_transactions:
        largest = max(recent_transactions, key=lambda txn: txn['amount'])
        lines.append(f"The largest of the recent transactions available here is INR {largest['amount']:,.2f} "
                     f"for {largest['category']} on {largest['date']}.")
    risks = [p for p in pace_data if p['status'] in ('at_risk', 'over_budget')]
    if risks:
        p = max(risks, key=lambda row: row['percent_of_budget_projected'])
        lines.append(f"Review {p['category']}: recorded spending is INR {p['spent_so_far']:,.2f} "
                     f"against a budget of INR {p['monthly_limit']:,.2f}.")
    elif pace_data:
        lines.append('Your budgeted categories are currently on track based on recorded spending and projections.')
    else:
        lines.append('Set category budgets to compare your spending with a monthly plan.')
    if any(word in text for word in ('save', 'saving', 'advice')) or total_spent is None:
        lines.append('Protect essential bills, review optional spending, and use Goals & insights for a savings plan based on your history.')
    lines.append('This is a summary of saved records; free-form AI advice will resume when available.'
                 if has_records else 'Add a transaction or set a budget to get started.')
    return prefix + ' '.join(lines)


def _initialize_sdk():
    global genai, _configured
    try:
        with startup_stage('optional_ai_initialization'):
            sdk = importlib.import_module('google.generativeai')
            sdk.configure(api_key=GEMINI_API_KEY)
            genai = sdk
            _configured = True
    except Exception:
        # No provider exception/configuration/prompt details escape this worker.
        pass
    finally:
        _initialization_done.set()


def _ensure_configured():
    global _initialization_started
    if not GEMINI_API_KEY:
        raise RuntimeError('AI service is unavailable. Ask the operator to configure AI access.')
    if _configured:
        return
    with _initialization_lock:
        if not _initialization_started:
            _initialization_started = True
            threading.Thread(target=_initialize_sdk, name='optional-ai-init', daemon=True).start()
    if not _initialization_done.wait(AI_INITIALIZATION_TIMEOUT):
        raise RuntimeError('AI initialization is unavailable. Retry shortly or contact support.')
    if not _configured:
        raise RuntimeError('AI initialization failed. Ask the operator to check AI dependencies and restart the service.')


def build_prompt(user_name: str, monthly_income: float, pace_data: list[dict]) -> str:
    """Format live budget/spending data into a compact, structured prompt."""
    lines = [
        f"You are a friendly, practical financial coach for {user_name}, "
        f"who has a monthly income of INR {monthly_income:,.0f}.",
        "",
        "Here is their current spending status by category this month:",
    ]

    if not pace_data:
        lines.append("(No budgets or spending recorded yet this month.)")
    else:
        for p in pace_data:
            days_left = p["days_in_month"] - p["days_elapsed"]
            lines.append(
                f"- {p['category']}: budget INR {p['monthly_limit']:,.0f}, "
                f"spent INR {p['spent_so_far']:,.0f} so far "
                f"(day {p['days_elapsed']} of {p['days_in_month']}, {days_left} days left). "
                f"Projected month-end spend: INR {p['projected_spend']:,.0f} "
                f"({p['percent_of_budget_projected']:.0f}% of budget) — status: {p['status']}."
            )

    lines += [
        "",
        "Based on this, provide:",
        "1. A one-sentence overall assessment of how the month is going.",
        "2. 3 specific, actionable, friendly cost-cutting suggestions, prioritizing "
        "categories that are 'at_risk' or 'over_budget'. Be concrete (e.g., name realistic "
        "swaps, habits, or amounts), not generic advice like 'spend less'.",
        "3. One encouraging closing line.",
        "",
        "Keep the whole response under 150 words. Use a warm, conversational tone, no headers or markdown.",
    ]
    return "\n".join(lines)


def get_coaching_advice(user_name: str, monthly_income: float, pace_data: list[dict]) -> str:
    _ensure_configured()
    prompt = build_prompt(user_name, monthly_income, pace_data)
    return _generate(lambda name: genai.GenerativeModel(name).generate_content(
        prompt, generation_config=GENERATION_CONFIG, request_options=REQUEST_OPTIONS))


def build_digest_prompt(user_name: str, digest: dict) -> str:
    """Format the already-gathered weekly digest data into a prompt asking
    Gemini to write it up as a short, friendly weekly check-in message."""
    change = digest["total_this_week"] - digest["total_last_week"]
    if digest["total_last_week"] > 0:
        change_pct = (change / digest["total_last_week"]) * 100
    else:
        change_pct = None

    lines = [
        f"You are Coco, {user_name}'s financial coach, writing a short weekly check-in message "
        f"for the period {digest['period_start']} to {digest['period_end']}.",
        "",
        f"Total spent this week: INR {digest['total_this_week']:,.0f}",
        f"Total spent last week: INR {digest['total_last_week']:,.0f}",
        (f"Change vs last week: {change_pct:+.0f}%" if change_pct is not None else "Percentage change unavailable: last week was zero."),
        "Totals exclude monthly recurring payments; they describe non-monthly spending.",
        "",
        "Top spending categories this week:",
    ]
    if not digest["top_categories"]:
        lines.append("(No transactions logged this week.)")
    else:
        for c in digest["top_categories"]:
            lines.append(f"- {c['category']}: INR {c['amount']:,.0f}")

    if digest["anomalies"]:
        lines.append("")
        lines.append("Anomalies detected this month:")
        for a in digest["anomalies"]:
            lines.append(f"- {a['message']}")

    if digest["subscriptions"]:
        lines.append("")
        lines.append("Recurring subscriptions on file:")
        for s in digest["subscriptions"]:
            lines.append(f"- {s['message']}")

    if digest["bills_due_soon"]:
        lines.append("")
        lines.append("Bills due within the next week:")
        for b in digest["bills_due_soon"]:
            lines.append(f"- {b['name']} ({b['category']}): INR {b['amount']:,.0f}, due day {b['due_day']}, status {b['status']}.")

    lines += [
        "",
        "Write this as a warm, punchy weekly check-in (under 140 words, no markdown headers, "
        "no 'Subject:' line — this is chat text, not an email). Lead with the single most "
        "important thing (a concerning anomaly or bill takes priority over routine updates). "
        "Mention the week-over-week change. End on an encouraging or actionable note.",
    ]
    return "\n".join(lines)


def get_weekly_digest(user_name: str, digest: dict) -> str:
    _ensure_configured()
    prompt = build_digest_prompt(user_name, digest)
    return _generate(lambda name: genai.GenerativeModel(name).generate_content(
        prompt, generation_config=GENERATION_CONFIG, request_options=REQUEST_OPTIONS))


def build_goal_prompt(user_name: str, plan: dict) -> str:
    """Format an already-computed savings plan into a prompt asking Gemini to
    narrate it warmly — the model never does the math itself, only explains it."""
    lines = [
        f"You are Coco, {user_name}'s friendly financial coach. They just set a savings goal:",
        f"Save INR {plan['target_amount']:,.0f} in {plan['months']} month(s) "
        f"(INR {plan['monthly_savings_needed']:,.0f}/month).",
        "",
        f"Current monthly income: INR {plan['current_monthly_income']:,.0f}",
        f"Current average monthly spend: INR {plan['current_baseline_spend']:,.0f}",
        f"Current monthly savings at this pace: INR {plan['current_monthly_savings']:,.0f}",
        f"Additional monthly cut needed to hit the goal: INR {plan['additional_cut_needed']:,.0f}",
        f"Goal achievable within reasonable category cuts: {'yes' if plan['achievable'] else 'no — the cuts required exceed what is realistic in a single category'}",
        "",
        f"History qualification: {plan['baseline_note']}",
        "Never recommend cuts to rent, EMI, insurance, tuition or other fixed costs. Do not claim sparse history is reliable.",
        "Here is the exact cut plan already calculated per category (do not recalculate or "
        "change these numbers, just explain them):",
    ]
    if not plan["categories"]:
        lines.append("(No spending history yet to base a plan on.)")
    else:
        for c in plan["categories"]:
            if c["cut_amount"] <= 0:
                continue
            lines.append(
                f"- {c['category']}: currently INR {c['current_monthly_avg']:,.0f}/month, "
                f"cut to INR {c['target_monthly']:,.0f}/month (-{c['cut_percent']:.0f}%, "
                f"saves INR {c['cut_amount']:,.0f})."
            )

    lines += [
        "",
        "Write a short, encouraging explanation (under 130 words, no markdown headers) covering: "
        "whether the goal is realistic, which 1-3 categories matter most to cut and by how much "
        "(use the exact numbers above), and one practical tip to make the cuts easier. If the goal "
        "isn't achievable through cuts alone, gently suggest extending the timeline instead of "
        "pretending it's easy.",
    ]
    return "\n".join(lines)


def get_goal_advice(user_name: str, plan: dict) -> str:
    _ensure_configured()
    prompt = build_goal_prompt(user_name, plan)
    return _generate(lambda name: genai.GenerativeModel(name).generate_content(
        prompt, generation_config=GENERATION_CONFIG, request_options=REQUEST_OPTIONS))


def build_system_context(
    user_name: str,
    monthly_income: float,
    pace_data: list[dict],
    total_spent: float,
    remaining: float,
    recent_transactions: list[dict],
    anomalies: list[dict] | None = None,
    subscriptions: list[dict] | None = None,
) -> str:
    """Compact system-level context describing who Coco is talking to and their live numbers."""
    lines = [
        f"You are Coco, a friendly, sharp financial coach chatting live with {user_name}.",
        "",
        "THEIR OVERALL PICTURE THIS MONTH:",
        f"- Monthly income: INR {monthly_income:,.0f}",
        f"- Total spent so far (all categories): INR {total_spent:,.0f}",
        f"- Remaining balance: INR {remaining:,.0f}"
        + (" (already over budget for the month)" if remaining < 0 else ""),
        "",
        "SPENDING BY BUDGETED CATEGORY:",
    ]

    if not pace_data:
        lines.append("(No budgets set for this month yet.)")
    else:
        for p in pace_data:
            days_left = p["days_in_month"] - p["days_elapsed"]
            lines.append(
                f"- {p['category']}: budget INR {p['monthly_limit']:,.0f}, "
                f"spent INR {p['spent_so_far']:,.0f} so far "
                f"(day {p['days_elapsed']} of {p['days_in_month']}, {days_left} days left). "
                f"Projected month-end spend: INR {p['projected_spend']:,.0f} "
                f"({p['percent_of_budget_projected']:.0f}% of budget) — status: {p['status']}."
            )

    lines.append("")
    lines.append("RECENT TRANSACTIONS (most recent first):")
    if not recent_transactions:
        lines.append("(No transactions logged yet.)")
    else:
        for t in recent_transactions:
            merchant = f" at {t['merchant']}" if t.get("merchant") else ""
            lines.append(f"- {t['date']}: INR {t['amount']:,.0f} on {t['category']}{merchant}")

    if anomalies:
        lines.append("")
        lines.append("DETECTED ANOMALIES THIS MONTH (unusual spending patterns):")
        for a in anomalies:
            lines.append(f"- [{a['category']}] {a['message']}")

    if subscriptions:
        lines.append("")
        lines.append("DETECTED RECURRING SUBSCRIPTIONS (repeating merchant charges):")
        for s in subscriptions:
            lines.append(f"- {s['message']}")

    lines += [
        "",
        "Ground every answer in these real numbers when relevant — cite specific categories, "
        "amounts, and transactions rather than generic advice like 'spend less'. If asked how "
        "much is left, what they've spent, or about a specific purchase, answer directly from "
        "the numbers above. Keep replies conversational and short — 2-5 sentences unless the "
        "user asks for a breakdown or list. No markdown headers. You're texting with a friend "
        "who happens to be great with money, not writing a report.",
        "",
        "If there are detected anomalies or subscriptions above and the user hasn't already been "
        "told about them in this conversation, proactively bring up the single most important one "
        "early in your reply — don't wait to be asked. Otherwise weave them in only when relevant.",
        "",
        "The log_expense tool only creates a proposal, never spending. Only the user pressing Save records an expense. Never claim a proposal is logged or saved; ask the user to review Save/Cancel controls.",
        "You have a log_expense tool. Whenever the user tells you about something they spent "
        "money on (e.g. 'I had breakfast today, it cost 200 rupees'), call log_expense to propose "
        "it as a transaction — don't just acknowledge it in words without calling the tool. Pick "
        "the meaningful category of the expense, even if it has no budget (or Uncategorized if "
        "nothing fits), infer the merchant/note from context, and default the date to today if "
        "the user doesn't give one. After the tool runs, say the expense is ready for review in one short, "
        "natural sentence — don't recite the tool's raw output.",
    ]
    return "\n".join(lines)


def chat_reply(
    user_name: str,
    monthly_income: float,
    pace_data: list[dict],
    total_spent: float,
    remaining: float,
    recent_transactions: list[dict],
    history: list[dict],
    message: str,
    anomalies: list[dict] | None = None,
    subscriptions: list[dict] | None = None,
    log_expense_fn=None,
) -> str:
    """Continue a multi-turn conversation with Coco, grounded in live budget data.

    history: list of {"role": "user"|"model", "content": str}, oldest first.
    log_expense_fn: optional callable Coco can invoke as a tool to save a new
    expense it hears about mid-conversation (see main.py for the closure that
    actually writes to the database). When provided, the SDK's automatic
    function calling handles invoking it and feeding the result back to the
    model before the final reply is produced.
    """
    _ensure_configured()
    system_context = build_system_context(
        user_name, monthly_income, pace_data, total_spent, remaining, recent_transactions,
        anomalies, subscriptions,
    )
    tool_used = False
    def log_expense(amount: float, category: str, merchant: str = None, note: str = None, txn_date: str = None) -> dict:
        """Propose an expense for review; only the user's Save action records spending."""
        nonlocal tool_used
        tool_used = True
        return log_expense_fn(amount=amount, category=category, merchant=merchant, note=note, txn_date=txn_date)
    tools = [log_expense] if log_expense_fn else None

    chat_history = [
        {"role": turn["role"], "parts": [turn["content"]]}
        for turn in history
        if turn.get("content")
    ]

    def send(name):
        model = genai.GenerativeModel(name, system_instruction=system_context, tools=tools)
        chat = model.start_chat(history=chat_history,
                                enable_automatic_function_calling=bool(log_expense_fn))
        return chat.send_message(message, generation_config=GENERATION_CONFIG, request_options=REQUEST_OPTIONS)
    return _generate(send, can_retry=lambda: not tool_used)
