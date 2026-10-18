import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()


def parse_request(text):
    base = os.getenv("AI_BASE_URL").rstrip("/")
    r = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {os.getenv('AI_API_KEY')}"},
        json={
            "model": os.getenv("AI_MODEL"),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract an invoice request. Reply with ONLY JSON: "
                        '{"client": string, "client_email": string or null, '
                        '"description": string, "amount_usd": number}. '
                        "Use null for any field that is missing."
                    ),
                },
                {"role": "user", "content": text},
            ],
            "temperature": 0,
        },
        timeout=60,
    )
    if not r.ok:
        print("Error:", r.status_code, r.text)
        raise RuntimeError(f"AI error {r.status_code}")
    content = r.json()["choices"][0]["message"]["content"].strip()
    content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(content)


if __name__ == "__main__":
    print(parse_request("Invoice Aman 50 dollars for logo design"))