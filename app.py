import json
import os
import time

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

from ai_parser import parse_request
from invoices import (
    create_draft_invoice,
    get_pay_link,
    get_status,
    invoice_id_from,
    send_invoice,
)

load_dotenv()
app = Flask(__name__, static_folder="static")
STORE = "invoices.json"


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


if __name__ == "__main__":
    app.run(debug=False, port=5000)