import os
import sys
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


def get_invoice(invoice_id):
    token = get_token()
    r = requests.get(
        f"{BASE}/v2/invoicing/invoices/{invoice_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    return r.json() if r.ok else None


def get_status(invoice_id):
    data = get_invoice(invoice_id)
    return data.get("status") if data else "Could not fetch invoice"


def get_pay_link(invoice_id):
    data = get_invoice(invoice_id)
    if not data:
        return None
    return data.get("detail", {}).get("metadata", {}).get("recipient_view_url")

def send_reminder(invoice_id, subject, note):
    token = get_token()
    r = requests.post(
        f"{BASE}/v2/invoicing/invoices/{invoice_id}/remind",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"subject": subject, "note": note, "send_to_invoicer": False},
        timeout=30,
    )
    print("Reminder:", r.status_code, r.text)
    return r.ok

if __name__ == "__main__":
    # Check an existing invoice:  python invoices.py status INV2-XXXX
    if len(sys.argv) == 3 and sys.argv[1] == "status":
        print("Status:", get_status(sys.argv[2]))
        sys.exit()

    # Otherwise create and send a new test invoice
    result = create_draft_invoice(
        "Rahul", "sb-pxyja53423498@personal.example.com", "Logo design", 50
    )
    if result:
        inv = invoice_id_from(result)
        print("Invoice ID:", inv)
        print("Draft status:", get_status(inv))
        send_invoice(inv)
        print("After send:", get_status(inv))
        print("Pay here:", get_pay_link(inv))