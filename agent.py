import os
from dotenv import load_dotenv
from ai_parser import parse_request
from invoices import create_draft_invoice, invoice_id_from, send_invoice, get_status, get_pay_link

load_dotenv()


def main():
    text = input("What do you want to invoice? > ")
    data = parse_request(text)

    missing = [k for k in ("client", "description", "amount_usd") if not data.get(k)]
    if missing:
        print("I couldn't find:", ", ".join(missing), "- try again with more detail.")
        return

    email = data.get("client_email") or os.getenv("DEFAULT_CLIENT_EMAIL")
    amount = float(data["amount_usd"])

    print("\n--- Draft invoice ---")
    print("Client:", data["client"])
    print("Email :", email)
    print("Item  :", data["description"])
    print("Amount: $%.2f" % amount)

    if input("\nSend this invoice? (y/n) > ").strip().lower() != "y":
        print("Cancelled. Nothing was sent.")
        return

    result = create_draft_invoice(data["client"], email, data["description"], amount)
    if not result:
        return
    inv = invoice_id_from(result)
    send_invoice(inv)
    print("Invoice ID:", inv)
    print("Status:", get_status(inv))
    print("Pay here:", get_pay_link(inv))


if __name__ == "__main__":
    main()