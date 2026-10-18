import os
import requests
from dotenv import load_dotenv

load_dotenv()
base = os.getenv("AI_BASE_URL").rstrip("/")
r = requests.get(
    f"{base}/models",
    headers={"Authorization": f"Bearer {os.getenv('AI_API_KEY')}"},
    timeout=30,
)
print(r.status_code)
for m in r.json().get("data", []):
    print(m["id"])