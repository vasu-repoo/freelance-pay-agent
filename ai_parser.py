import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()


def _chat_json(system_prompt, user_text):
    base = os.getenv("AI_BASE_URL").rstrip("/")
    r = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {os.getenv('AI_API_KEY')}"},
        json={
            "model": os.getenv("AI_MODEL"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.3,
        },
        timeout=60,
    )
    if not r.ok:
        raise RuntimeError(f"AI error {r.status_code}")
    content = r.json()["choices"][0]["message"]["content"].strip()
    content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(content)


def parse_request(text):
    return _chat_json(
        "Extract an invoice request. Reply with ONLY JSON: "
        '{"client": string, "client_email": string or null, '
        '"description": string, "amount_usd": number}. '
        "Use null for any field that is missing.",
        text,
    )


def draft_reminder(client, description, amount, tone):
    style = (
        "warm, friendly and brief"
        if tone == "friendly"
        else "polite but firm and professional, mentioning the invoice is overdue"
    )
    data = _chat_json(
        "You write payment reminder messages for a freelancer. "
        f"Tone: {style}. No threats, no invented dates or facts. "
        "The note must be under 80 words. "
        'Reply with ONLY JSON: {"subject": string, "note": string}.',
        f"Client: {client}\nItem: {description}\nAmount: ${amount:.2f} USD",
    )
    return str(data["subject"]), str(data["note"])


if __name__ == "__main__":
    print(parse_request("Invoice Aman 50 dollars for logo design"))