import os
import re
import sys
import threading
import time

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "https://api-m.sandbox.paypal.com"
TIMEOUT = 30

_token_lock = threading.Lock()
_token = {"value": None, "expires": 0.0}
_local = threading.local()


def last_error():
    """Friendly reason for the most recent failed PayPal call in this thread."""
    return getattr(_local, "error", None)


def _fail(message):
    _local.error = message
    print("PayPal problem:", message)


def _fail_response(r):
    _fail(_explain(r))
    print("PayPal said:", r.status_code, (r.text or "")[:500])


def _explain(r):
    """Turn a PayPal error response into a message a person can act on."""
    text = r.text or ""
    if "INR_FOREIGN_CURRENCY_BLOCKED" in text:
        return (
            "PayPal blocks invoices to customers in India. "
            "Use an email from a US sandbox personal account."
        )
    if r.status_code == 401:
        return "PayPal rejected the API keys. Check PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in .env."
    if r.status_code == 403:
        return "PayPal says this app is not allowed to do that (permissions)."
    if r.status_code == 429:
        return "PayPal is limiting requests right now. Wait a minute and try again."
    if r.status_code >= 500:
        return "PayPal had a server problem. Try again shortly."
    issue = None
    try:
        data = r.json()
        details = data.get("details") or [{}]
        issue = details[0].get("issue") or data.get("name")
    except (ValueError, AttributeError, IndexError, TypeError):
        pass
    suffix = f": {issue}" if issue else ""
    return f"PayPal rejected the request ({r.status_code}{suffix})."


def _valid_id(invoice_id):
    return isinstance(invoice_id, str) and re.fullmatch(r"[A-Za-z0-9-]{5,64}", invoice_id) is not None


def get_token():
    with _token_lock:
        if _token["value"] and time.time() < _token["expires"] - 60:
            return _token["value"]
        client_id = os.getenv("PAYPAL_CLIENT_ID")
        secret = os.getenv("PAYPAL_CLIENT_SECRET")
        if not client_id or not secret:
            raise RuntimeError(
                "PayPal keys are missing. Check PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in .env."
            )
        r = requests.post(
            f"{BASE}/v1/oauth2/token",
            auth=(client_id, secret),
            data={"grant_type": "client_credentials"},
            timeout=TIMEOUT,
        )
        if not r.ok:
            raise RuntimeError(_explain(r))
        try:
            data = r.json()
            _token["value"] = data["access_token"]
            _token["expires"] = time.time() + int(data.get("expires_in", 300))
        except (ValueError, KeyError, TypeError):
            raise RuntimeError("PayPal sent an unexpected login reply.")
        return _token["value"]


def _call(method, path, json_body=None):
    """Call PayPal. Returns a Response, or None after recording a friendly error."""
    _local.error = None
    for attempt in (1, 2):
        try:
            token = get_token()
            r = requests.request(
                method,
                f"{BASE}{path}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=json_body,
                timeout=TIMEOUT,
            )
        except RuntimeError as e:
            _fail(str(e))
            return None
        except requests.RequestException:
            _fail("Could not reach PayPal. Check your internet connection.")
            return None
        if r.status_code == 401 and attempt == 1:
            _token["value"] = None  # token expired early: fetch a new one and retry once
            continue
        return r
    return None


def create_draft_invoice(client_name, client_email, description, amount_usd):
    body = {
        "detail": {"currency_code": "USD", "note": "Thank you for your business!"},
        "primary_recipients": [
            {
                "billing_info": {
                    "name": {"given_name": str(client_name)[:140]},
                    "email_address": client_email,
                }
            }
        ],
        "items": [
            {
                "name": str(description)[:200],
                "quantity": "1",
                "unit_amount": {"currency_code": "USD", "value": f"{float(amount_usd):.2f}"},
            }
        ],
    }
    r = _call("POST", "/v2/invoicing/invoices", body)
    if r is None:
        return None
    if not r.ok:
        _fail_response(r)
        return None
    try:
        return r.json()
    except ValueError:
        _fail("PayPal sent an unexpected reply.")
        return None


def invoice_id_from(result):
    try:
        return result["href"].rstrip("/").split("/")[-1]
    except (KeyError, TypeError, AttributeError):
        return None


def send_invoice(invoice_id):
    if not _valid_id(invoice_id):
        _fail("Invalid invoice ID.")
        return False
    r = _call("POST", f"/v2/invoicing/invoices/{invoice_id}/send", {"send_to_recipient": True})
    if r is None:
        return False
    if not r.ok:
        _fail_response(r)
        return False
    return True


def delete_invoice(invoice_id):
    """Best-effort cleanup of a draft that could not be sent."""
    if not _valid_id(invoice_id):
        return False
    r = _call("DELETE", f"/v2/invoicing/invoices/{invoice_id}")
    return bool(r is not None and r.ok)


def get_invoice(invoice_id):
    if not _valid_id(invoice_id):
        _fail("Invalid invoice ID.")
        return None
    r = _call("GET", f"/v2/invoicing/invoices/{invoice_id}")
    if r is None:
        return None
    if not r.ok:
        _fail_response(r)
        return None
    try:
        return r.json()
    except ValueError:
        _fail("PayPal sent an unexpected reply.")
        return None


def get_status(invoice_id):
    data = get_invoice(invoice_id)
    if not isinstance(data, dict):
        return "UNKNOWN"
    return data.get("status") or "UNKNOWN"


def get_pay_link(invoice_id):
    data = get_invoice(invoice_id)
    if not isinstance(data, dict):
        return None
    return (data.get("detail") or {}).get("metadata", {}).get("recipient_view_url")


def send_reminder(invoice_id, subject, note):
    if not _valid_id(invoice_id):
        _fail("Invalid invoice ID.")
        return False
    r = _call(
        "POST",
        f"/v2/invoicing/invoices/{invoice_id}/remind",
        {"subject": subject, "note": note, "send_to_invoicer": False},
    )
    if r is None:
        return False
    if not r.ok:
        _fail_response(r)
        return False
    return True


if __name__ == "__main__":
    # Check an existing invoice:  python invoices.py status INV2-XXXX
    if len(sys.argv) == 3 and sys.argv[1] == "status":
        print("Status:", get_status(sys.argv[2]))
        sys.exit()

    # Otherwise create and send a new test invoice (use a US sandbox buyer email)
    buyer = os.getenv("DEFAULT_CLIENT_EMAIL", "")
    if not buyer:
        sys.exit("Set DEFAULT_CLIENT_EMAIL in .env to a US sandbox personal account email.")
    result = create_draft_invoice("Rahul", buyer, "Logo design", 50)
    if result:
        inv = invoice_id_from(result)
        print("Invoice ID:", inv)
        print("Draft status:", get_status(inv))
        send_invoice(inv)
        print("After send:", get_status(inv))
        print("Pay here:", get_pay_link(inv))