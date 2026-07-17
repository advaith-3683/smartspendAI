import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-flash-latest"

_configured = False


def _ensure_configured():
    global _configured
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add it to a .env file in the backend folder: "
            "GEMINI_API_KEY=your_key_here"
        )
    if not _configured:
        genai.configure(api_key=GEMINI_API_KEY)
        _configured = True


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
    model = genai.GenerativeModel(MODEL_NAME)
    response = model.generate_content(prompt)
    return response.text.strip()


def build_digest_prompt(user_name: str, digest: dict) -> str:
    """Format the already-gathered weekly digest data into a prompt asking
    Gemini to write it up as a short, friendly weekly check-in message."""
    change = digest["total_this_week"] - digest["total_last_week"]
    if digest["total_last_week"] > 0:
        change_pct = (change / digest["total_last_week"]) * 100
    else:
        change_pct = 0.0

    lines = [
        f"You are Coco, {user_name}'s financial coach, writing a short weekly check-in message "
        f"for the period {digest['period_start']} to {digest['period_end']}.",
        "",
        f"Total spent this week: INR {digest['total_this_week']:,.0f}",
        f"Total spent last week: INR {digest['total_last_week']:,.0f}",
        f"Change vs last week: {change_pct:+.0f}%",
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
    model = genai.GenerativeModel(MODEL_NAME)
    response = model.generate_content(prompt)
    return response.text.strip()


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
    model = genai.GenerativeModel(MODEL_NAME)
    response = model.generate_content(prompt)
    return response.text.strip()


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
        "You have a log_expense tool. Whenever the user tells you about something they spent "
        "money on (e.g. 'I had breakfast today, it cost 200 rupees'), call log_expense to save "
        "it as a transaction — don't just acknowledge it in words without calling the tool. Pick "
        "the best-fit category yourself from what's already budgeted above (or Miscellaneous if "
        "nothing fits), infer the merchant/note from context, and default the date to today if "
        "the user doesn't give one. After the tool runs, confirm what you logged in one short, "
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
    tools = [log_expense_fn] if log_expense_fn else None
    model = genai.GenerativeModel(MODEL_NAME, system_instruction=system_context, tools=tools)

    chat_history = [
        {"role": turn["role"], "parts": [turn["content"]]}
        for turn in history
        if turn.get("content")
    ]

    chat = model.start_chat(
        history=chat_history,
        enable_automatic_function_calling=bool(log_expense_fn),
    )
    response = chat.send_message(message)
    return response.text.strip()