# PayDay Agent

AI agent that helps freelancers invoice and get paid through PayPal.
Type "Invoice Aman 75 dollars for website design", review the draft, approve,
and PayPal sends it. Unpaid invoices get AI-drafted reminders you approve too.

[2-3 sentences in your own words: who this is for and why you built it.]

## How it uses PayPal and AI
- PayPal Invoicing API (sandbox): create, send, track and remind.
- AI model (gemini-flash-latest, via Google AI Studio free tier): parses plain English
  into invoice fields and drafts payment reminders.
- Human approval before every invoice and every reminder is sent.

## Setup
1. Python 3.11+. `pip install -r requirements.txt`
2. Create a PayPal sandbox app at developer.paypal.com and note the Client ID and Secret.
3. Create a US *personal* sandbox account (PayPal blocks invoices to customers in India).
4. Get a free API key from Google AI Studio.
5. Copy `.env.example` to `.env` and fill in the values.
6. Run `python app.py` and open http://127.0.0.1:5000

## Tech
Python, Flask, AG Grid (community edition), PayPal sandbox, Gemini API.

## License
MIT