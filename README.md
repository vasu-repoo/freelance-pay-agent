# PayDay Agent

PayDay Agent helps freelancers get paid without awkward follow-ups. Late payments are a real problem: Bonsai analysed three years of invoicing data from 100,000 freelancers and found that 29% of invoices were paid after they were due.[^1]

A freelancer types one simple sentence, such as: "Invoice Rahul $75 for website design." The AI turns that sentence into a clear invoice. When a payment is late, the AI also drafts a friendly or firm reminder.

The freelancer reviews and approves everything before anything is sent. After approval, PayDay Agent uses the PayPal Invoicing API to create and send the invoice with a secure PayPal payment link.[^2]

This saves freelancers time, makes payment follow-up less uncomfortable, and helps them get paid faster. PayPal reports that 79% of its invoices are paid within one day of being sent.[^3]

Built for the PayPal AI Hackathon.

## Why I built this

I built PayDay Agent because I have seen friends hesitate to ask clients for money, even after completing their work. This project makes that conversation easier by preparing professional invoices and reminders automatically.

## How it works

1. The freelancer types a short instruction.
2. The AI extracts the client name, amount, and service (and an email if one is given).
3. The freelancer checks the draft and approves it.
4. PayDay Agent creates and sends the invoice through the PayPal Invoicing API.
5. A table tracks every invoice (Sent, Paid and so on) and refreshes the live status from PayPal.
6. For unpaid invoices, the freelancer picks a friendly or firm tone, the AI drafts a reminder, and it is sent only after approval.

## Tech

| Part | What it uses |
|---|---|
| Payments | PayPal Invoicing API v2 (sandbox) |
| AI model | Google Gemini `gemini-flash-lite-latest` through Google AI Studio (OpenAI-compatible API), with `gemini-flash-latest` as an optional backup model |
| Backend | Python, Flask |
| Frontend | HTML and JavaScript, AG Grid for the invoice table |
| Tests | pytest (77 tests, using fake PayPal and AI, so no real accounts are needed) |
| AI coding assistant | Claude (Anthropic) helped in writing and testing the code. The idea, setup, testing and decisions are mine. |

## Built to be reliable and safe

- Nothing is sent without the user's approval. AI-drafted text can be edited first.
- Only USD invoices are supported. Other currencies are refused instead of guessed.
- A safety limit on invoice amounts (default $10,000) blocks typos like an extra zero.
- Double-clicks cannot create duplicate invoices. Reminders have a cooldown and a maximum of 3 per invoice, and are only offered for unpaid invoices.
- Text in a request cannot give the AI new instructions (prompt-injection protection).
- If the AI is busy or the free tier is limited, the app retries, switches to the backup model, and then shows a clear message instead of crashing.
- If the AG Grid file cannot load, the page falls back to a plain table.

## Run it yourself

You need Python 3.10 or newer, a free PayPal sandbox app, and a free Google AI Studio key.

1. Get the code:
   ```
   git clone https://github.com/<vasu-repoo>/freelance-pay-agent.git
   cd freelance-pay-agent
   ```
2. Create and activate a virtual environment, then install the packages:
   ```
   python -m venv .venv
   .venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in the values:

   | Setting | Meaning |
   |---|---|
   | `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | From a sandbox app on the [PayPal Developer Dashboard](https://developer.paypal.com/) |
   | `AI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai` |
   | `AI_API_KEY` | A key from [Google AI Studio](https://aistudio.google.com/) |
   | `AI_MODEL` | `gemini-flash-lite-latest` |
   | `AI_FALLBACK_MODEL` | Optional backup, for example `gemini-flash-latest` |
   | `DEFAULT_CLIENT_EMAIL` | Sandbox personal (buyer) account email, used when a request has no email |

4. Start the app and open http://127.0.0.1:5000:
   ```
   python app.py
   ```
   The red "development server" warning in the terminal is normal for this local demo. It is not an error.

### PayPal sandbox notes

- Use a sandbox **business** account to send invoices and a sandbox **personal** account to pay them.
- The buyer account must be in a different country from the business account. In some countries, such as India, PayPal blocks invoices between two accounts in the same country (`INR_FOREIGN_CURRENCY_BLOCKED`). A US sandbox buyer works.
- Invoices are in USD only.

### Troubleshooting

- **503 or "The AI is unavailable"**: Google's free tier is busy. Wait a minute and try again, or set `AI_FALLBACK_MODEL`.
- **404 for a model**: Google has retired some older models for new accounts. Use `gemini-flash-lite-latest`.
- **A VPN can block Google or PayPal**: turn it off.

### Run the tests

```
pip install -r requirements-dev.txt
python -m pytest -q
```

## License

MIT. See [LICENSE](LICENSE).

## Sources

[^1]: Bonsai, ["How often do freelancers get paid late?"](https://www.hellobonsai.com/blog/late-freelance-payment) (January 2026). "We found that 29% of invoices were paid after they were due."
[^2]: PayPal, [Invoicing API reference](https://developer.paypal.com/invoicing/reference).
[^3]: PayPal, [Invoicing for business](https://www.paypal.com/ie/business/accept-payments/invoice). "79% of PayPal invoices are paid within one day of sending the invoice", based on PayPal internal data from 1 August 2023 to 31 July 2024.