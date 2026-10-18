import os
import requests
from dotenv import load_dotenv

load_dotenv()
BASE = "https://api-m.sandbox.paypal.com"


def get_token():
    r = requests.post(
        f"{BASE}/v1/oauth2/token",
        auth=(os.getenv("PAYPAL_CLIENT_ID"), os.getenv("PAYPAL_CLIENT_SECRET")),
        data={"grant_type": "client_credentials"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def create_draft_invoice(client_name, client_email, description, amount_usd):
    token = get_token()
    body = {
        "detail": {"currency_code": "USD", "note": "Thank you for your business!"},
        "primary_recipients": [
            {
                "billing_info": {
                    "name": {"given_name": client_name},
                    "email_address": client_email,
                }
            }
        ],
        "items": [
            {
                "name": description,
                "quantity": "1",
                "unit_amount": {"currency_code": "USD", "value": f"{amount_usd:.2f}"},
            }
        ],
    }
    r = requests.post(
        f"{BASE}/v2/invoicing/invoices",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    if not r.ok:
        print("Error:", r.status_code, r.text)
        return None
    return r.json()


def invoice_id_from(result):
    return result["href"].split("/")[-1]


def send_invoice(invoice_id):
    token = get_token()
    r = requests.post(
        f"{BASE}/v2/invoicing/invoices/{invoice_id}/send",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"send_to_recipient": True},
        timeout=30,
    )
    print("Send:", r.status_code, r.text)
    return r.ok


def get_status(invoice_id):
    token = get_token()
    r = requests.get(
        f"{BASE}/v2/invoicing/invoices/{invoice_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    return r.json().get("status") if r.ok else r.text


if __name__ == "__main__":
    result = create_draft_invoice(
        "Rahul", "sb-d47p2i53429636@personal.example.com", "Logo design", 50
    )
    if result:
        inv = invoice_id_from(result)
        print("Draft:", inv, get_status(inv))
        send_invoice(inv)
        print("After send:", get_status(inv))