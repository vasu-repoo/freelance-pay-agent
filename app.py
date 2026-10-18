import json
import os
import time

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

from ai_parser import draft_reminder, parse_request
from invoices import (
    create_draft_invoice,
    get_pay_link,
    get_status,
    invoice_id_from,
    send_invoice,
    send_reminder,
)

load_dotenv()
app = Flask(__name__, static_folder="static")
STORE = "invoices.json"
REMINDABLE = {"SENT", "UNPAID", "PARTIALLY_PAID"}


def load_store():
    if not os.path.exists(STORE):
        return []
    with open(STORE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_store(items):
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)


@app.get("/")
def home():
    return send_from_directory("static", "index.html")


@app.post("/api/parse")
def api_parse():
    text = (request.get_json(silent=True) or {}).get("text", "").strip()
    if not text:
        return jsonify(error="Please type a request."), 400
    try:
        data = parse_request(text)
    except Exception:
        return jsonify(error="The AI could not read that request. Please try again."), 502
    missing = [k for k in ("client", "description", "amount_usd") if not data.get(k)]
    if missing:
        return jsonify(error="I could not find: " + ", ".join(missing)), 422
    try:
        amount = float(data["amount_usd"])
    except (TypeError, ValueError):
        return jsonify(error="I could not understand the amount."), 422
    if amount <= 0:
        return jsonify(error="The amount must be above zero."), 422
    return jsonify(
        client=str(data["client"]),
        email=data.get("client_email") or os.getenv("DEFAULT_CLIENT_EMAIL", ""),
        description=str(data["description"]),
        amount=amount,
    )


@app.post("/api/send")
def api_send():
    d = request.get_json(silent=True) or {}
    try:
        amount = float(d.get("amount"))
    except (TypeError, ValueError):
        return jsonify(error="Invalid amount."), 400
    if amount <= 0 or not d.get("client") or not d.get("email") or not d.get("description"):
        return jsonify(error="Missing or invalid fields."), 400
    result = create_draft_invoice(d["client"], d["email"], d["description"], amount)
    if not result:
        return jsonify(error="PayPal could not create the invoice."), 502
    inv = invoice_id_from(result)
    if not send_invoice(inv):
        return jsonify(error="The invoice was created but could not be sent."), 502
    item = {
        "id": inv,
        "client": d["client"],
        "description": d["description"],
        "amount": amount,
        "link": get_pay_link(inv),
        "created": time.strftime("%Y-%m-%d %H:%M"),
        "reminders": 0,
    }
    items = load_store()
    items.insert(0, item)
    save_store(items)
    return jsonify(item)


@app.get("/api/invoices")
def api_invoices():
    items = load_store()
    for it in items:
        it["status"] = get_status(it["id"])
    return jsonify(items)


def find_invoice(inv_id):
    return next((i for i in load_store() if i["id"] == inv_id), None)


@app.post("/api/reminder/draft")
def api_reminder_draft():
    d = request.get_json(silent=True) or {}
    item = find_invoice(str(d.get("id", "")))
    if not item:
        return jsonify(error="Invoice not found."), 404
    tone = d.get("tone") if d.get("tone") in ("friendly", "firm") else "friendly"
    status = get_status(item["id"])
    if status not in REMINDABLE:
        return jsonify(error=f"No reminder needed. This invoice is {status}."), 409
    try:
        subject, note = draft_reminder(item["client"], item["description"], item["amount"], tone)
    except Exception:
        return jsonify(error="The AI could not draft a reminder. Please try again."), 502
    return jsonify(id=item["id"], client=item["client"], subject=subject, note=note)


@app.post("/api/reminder/send")
def api_reminder_send():
    d = request.get_json(silent=True) or {}
    items = load_store()
    item = next((i for i in items if i["id"] == str(d.get("id", ""))), None)
    if not item:
        return jsonify(error="Invoice not found."), 404
    subject = str(d.get("subject", "")).strip()[:200]
    note = str(d.get("note", "")).strip()[:2000]
    if not subject or not note:
        return jsonify(error="Subject and message cannot be empty."), 400
    if get_status(item["id"]) not in REMINDABLE:
        return jsonify(error="This invoice no longer needs a reminder."), 409
    if not send_reminder(item["id"], subject, note):
        return jsonify(error="PayPal could not send the reminder."), 502
    item["reminders"] = item.get("reminders", 0) + 1
    save_store(items)
    return jsonify(ok=True, reminders=item["reminders"])


if __name__ == "__main__":
    app.run(debug=False, port=5000)