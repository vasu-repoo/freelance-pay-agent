import json
import math
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from ai_parser import AIError, clean_text, draft_reminder, parse_request
from invoices import (
    create_draft_invoice,
    delete_invoice,
    get_pay_link,
    get_status,
    invoice_id_from,
    last_error,
    send_invoice,
    send_reminder,
)

load_dotenv()

app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024  # requests here are tiny; reject anything big


def _env_number(name, default, cast):
    try:
        return cast(os.getenv(name, default))
    except (TypeError, ValueError):
        return cast(default)


HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "invoices.json")
REMINDABLE = {"SENT", "UNPAID", "PARTIALLY_PAID"}
MAX_PROMPT = 500
MAX_ROWS = 50
MAX_AMOUNT = _env_number("MAX_INVOICE_USD", "10000", float)
MAX_REMINDERS = _env_number("MAX_REMINDERS", "3", int)
REMINDER_COOLDOWN = _env_number("REMINDER_COOLDOWN_SECONDS", "30", int)
DEDUPE_SECONDS = 20
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")

_store_lock = threading.RLock()
_recent = {}  # recently sent invoices, used to block double clicks


# ---------- small helpers ----------

def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def to_amount(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    return round(amount, 2) if math.isfinite(amount) else None


def amount_problem(amount):
    if amount is None:
        return "I could not understand the amount."
    if amount <= 0:
        return "The amount must be above zero."
    if amount > MAX_AMOUNT:
        return (
            f"Amounts above ${MAX_AMOUNT:,.0f} are blocked as a safety limit. "
            "Please check the amount."
        )
    return None


def load_store():
    with _store_lock:
        if not os.path.exists(STORE):
            return []
        try:
            with open(STORE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("not a list")
            return [i for i in data if isinstance(i, dict) and i.get("id")]
        except (OSError, ValueError):
            try:  # keep the unreadable file for inspection and start fresh
                os.replace(STORE, STORE + ".bak")
            except OSError:
                pass
            return []


def save_store(items):
    with _store_lock:
        tmp = STORE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items[:200], f, indent=2)
        os.replace(tmp, STORE)  # atomic: never leaves a half-written file


def find_item(items, inv_id):
    return next((i for i in items if i.get("id") == inv_id), None)


def reminder_problem(item):
    if item.get("reminders", 0) >= MAX_REMINDERS:
        return f"The limit of {MAX_REMINDERS} reminders for this invoice has been reached.", 409
    last = item.get("last_reminder_at")
    if isinstance(last, (int, float)):
        wait = REMINDER_COOLDOWN - (time.time() - last)
        if wait > 0:
            return f"Please wait {int(wait) + 1} seconds before sending another reminder.", 429
    return None


# ---------- pages and errors ----------

@app.get("/")
def home():
    return send_from_directory("static", "index.html")


@app.errorhandler(HTTPException)
def handle_http(e):
    return jsonify(error=e.description or e.name), e.code


@app.errorhandler(Exception)
def handle_any(e):
    app.logger.exception("Unhandled error")
    return jsonify(error="Something went wrong on the server. Please try again."), 500


@app.after_request
def add_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------- invoices ----------

@app.post("/api/parse")
def api_parse():
    text = body().get("text", "")
    if not isinstance(text, str) or not text.strip():
        return jsonify(error="Please type a request."), 400
    text = text.strip()
    if len(text) > MAX_PROMPT:
        return jsonify(error=f"Please keep the request under {MAX_PROMPT} characters."), 400

    try:
        data = parse_request(text)
    except AIError as e:
        app.logger.warning("AI parse failed: %s", e)
        return jsonify(error="The AI could not read that request. Please try again."), 502

    missing = []
    if not data.get("client"):
        missing.append("the client's name")
    if not data.get("description"):
        missing.append("what the invoice is for")
    if data.get("amount_raw") is None:
        missing.append("the amount")
    if missing:
        return jsonify(error="I could not find " + ", ".join(missing) + ". Please add it and try again."), 422

    currency = data.get("currency") or "USD"
    if currency != "USD":
        return jsonify(
            error=f"Only USD invoices are supported (the request looks like {currency}). "
            "Please give the amount in dollars."
        ), 422

    amount = to_amount(data["amount_raw"])
    problem = amount_problem(amount)
    if problem:
        return jsonify(error=problem), 422

    default_email = os.getenv("DEFAULT_CLIENT_EMAIL", "").strip()
    ai_email = (data.get("client_email") or "").strip()
    email = ai_email if EMAIL_RE.match(ai_email) else default_email
    return jsonify(client=data["client"], email=email, description=data["description"], amount=amount)


@app.post("/api/send")
def api_send():
    d = body()
    client = clean_text(d.get("client"), 140)
    description = clean_text(d.get("description"), 200)
    email = str(d.get("email") or "").strip()
    amount = to_amount(d.get("amount"))

    if not client or not description:
        return jsonify(error="Client name and description are required."), 400
    if len(email) > 254 or not EMAIL_RE.match(email):
        return jsonify(error="Please enter a valid customer email."), 400
    problem = amount_problem(amount)
    if problem:
        return jsonify(error=problem), 400

    key = (client.lower(), email.lower(), description.lower(), amount)
    now = time.time()
    with _store_lock:
        for k, t in list(_recent.items()):
            if now - t > DEDUPE_SECONDS:
                del _recent[k]
        if key in _recent:
            return jsonify(error="This exact invoice was just sent. Wait a few seconds before sending it again."), 409
        _recent[key] = now

    sent = False
    try:
        result = create_draft_invoice(client, email, description, amount)
        if not result:
            return jsonify(error=last_error() or "PayPal could not create the invoice."), 502
        inv = invoice_id_from(result)
        if not inv:
            return jsonify(error="PayPal replied in an unexpected way."), 502
        if not send_invoice(inv):
            reason = last_error() or "The invoice was created but could not be sent."
            delete_invoice(inv)  # do not leave a stray draft behind
            return jsonify(error=reason), 502
        sent = True
    finally:
        if not sent:
            with _store_lock:
                _recent.pop(key, None)  # allow a retry after a failure

    item = {
        "id": inv,
        "client": client,
        "description": description,
        "amount": amount,
        "link": get_pay_link(inv),
        "created": time.strftime("%Y-%m-%d %H:%M"),
        "reminders": 0,
    }
    try:
        with _store_lock:
            items = load_store()
            items.insert(0, item)
            save_store(items)
    except OSError:
        return jsonify(error=f"The invoice was sent (ID {inv}) but could not be saved to the local list."), 500
    return jsonify(item)


@app.get("/api/invoices")
def api_invoices():
    items = load_store()[:MAX_ROWS]

    def status_of(item):
        try:
            return get_status(item["id"])
        except Exception:
            return "UNKNOWN"  # one bad lookup must not break the whole table

    with ThreadPoolExecutor(max_workers=5) as pool:
        statuses = list(pool.map(status_of, items))
    return jsonify([{**item, "status": s} for item, s in zip(items, statuses)])


# ---------- reminders ----------

@app.post("/api/reminder/draft")
def api_reminder_draft():
    d = body()
    item = find_item(load_store(), str(d.get("id", "")))
    if not item:
        return jsonify(error="Invoice not found."), 404
    problem = reminder_problem(item)
    if problem:
        return jsonify(error=problem[0]), problem[1]

    tone = d.get("tone") if d.get("tone") in ("friendly", "firm") else "friendly"
    status = get_status(item["id"])
    if status == "UNKNOWN":
        return jsonify(error="I could not check this invoice with PayPal. Please try again."), 502
    if status not in REMINDABLE:
        return jsonify(error=f"No reminder needed. This invoice is {status}."), 409

    amount = to_amount(item.get("amount")) or 0.0
    try:
        subject, note = draft_reminder(item.get("client", ""), item.get("description", ""), amount, tone)
    except AIError as e:
        app.logger.warning("AI reminder failed: %s", e)
        return jsonify(error="The AI could not draft a reminder. Please try again."), 502
    return jsonify(id=item["id"], client=item.get("client", ""), subject=subject, note=note)


@app.post("/api/reminder/send")
def api_reminder_send():
    d = body()
    inv_id = str(d.get("id", ""))
    subject = clean_text(d.get("subject"), 200)
    note = clean_text(d.get("note"), 2000, multiline=True)
    if not subject or not note:
        return jsonify(error="Subject and message cannot be empty."), 400

    # claim the cooldown first, so a double click cannot send two reminders
    with _store_lock:
        items = load_store()
        item = find_item(items, inv_id)
        if not item:
            return jsonify(error="Invoice not found."), 404
        problem = reminder_problem(item)
        if problem:
            return jsonify(error=problem[0]), problem[1]
        previous = item.get("last_reminder_at")
        item["last_reminder_at"] = time.time()
        save_store(items)

    ok = False
    error = ("PayPal could not send the reminder.", 502)
    count = 0
    try:
        status = get_status(inv_id)
        if status == "UNKNOWN":
            error = ("I could not check this invoice with PayPal. Please try again.", 502)
        elif status not in REMINDABLE:
            error = ("This invoice no longer needs a reminder.", 409)
        elif send_reminder(inv_id, subject, note):
            ok = True
        else:
            error = (last_error() or error[0], 502)
    finally:
        with _store_lock:
            items = load_store()
            item = find_item(items, inv_id)
            if item:
                if ok:
                    item["reminders"] = item.get("reminders", 0) + 1
                    count = item["reminders"]
                elif previous is None:
                    item.pop("last_reminder_at", None)  # failed: release the cooldown
                else:
                    item["last_reminder_at"] = previous
                save_store(items)

    if not ok:
        return jsonify(error=error[0]), error[1]
    return jsonify(ok=True, reminders=count)


def check_env():
    required = ["PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "AI_BASE_URL", "AI_API_KEY", "AI_MODEL"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        sys.exit("Missing settings in .env: " + ", ".join(missing))
    if not os.getenv("DEFAULT_CLIENT_EMAIL"):
        print("Note: DEFAULT_CLIENT_EMAIL is empty, so you must type the customer's email each time.")


if __name__ == "__main__":
    check_env()
    app.run(host="127.0.0.1", port=_env_number("PORT", "5000", int), debug=False)