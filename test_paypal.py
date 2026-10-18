import os
import requests
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv("PAYPAL_CLIENT_ID")
secret = os.getenv("PAYPAL_CLIENT_SECRET")

resp = requests.post(
    "https://api-m.sandbox.paypal.com/v1/oauth2/token",
    auth=(client_id, secret),
    data={"grant_type": "client_credentials"},
    timeout=30,
)

print("Status:", resp.status_code)
if resp.ok:
    print("Keys work! Token starts with:", resp.json()["access_token"][:12], "...")
else:
    print(resp.text)