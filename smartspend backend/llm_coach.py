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

print(GEMINI_API_KEY)