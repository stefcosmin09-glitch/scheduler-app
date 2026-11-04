# TradeScheduler

A job management and invoicing web app for UK tradespeople — electricians, plumbers, builders, roofers. Built as an affordable alternative to tools like Jobber, with AI-powered quoting and receipt scanning.

**Live:** https://thetradescheduler.com

## Features

- **Job scheduling** — book jobs with activity type, price, duration, and address; see your day and week at a glance.
- **Quotes** — turn a job into a professional quote, then a PDF invoice with VAT. Send it from your phone.
- **Invoicing** — generate invoices with VAT, send them by email, track paid/unpaid/overdue.
- **Online payments** — customers pay from the invoice link; record bank transfers, cash, or card.
- **Expense tracking** — log costs by job, scan receipts with AI, categorise automatically.
- **AI quote generation** — describe a job in one line and get a priced quote draft.
- **AI receipt scanning** — photo a receipt, AI reads supplier, date, and amount.
- **AI message reading** — paste a client message, get a structured job.
- **Time tracking** — start/stop timers per job, manual entries, weekly/monthly totals.
- **Accounting & VAT reports** — profit & loss, VAT reports, CSV/PDF export for your accountant.
- **Calendar feed** — subscribe to your jobs in any calendar app (ICS).
- **14-day free trial** — no credit card required. Starter £12.99/mo, Pro £22.99/mo.
- **Mobile-friendly** — works in your browser, installable as a PWA.

## Tech Stack

- **Backend:** Python, Flask, SQLAlchemy, Alembic (migrations)
- **Database:** PostgreSQL (production), SQLite (dev/tests)
- **Auth:** Flask-Login, Flask-WTF (CSRF)
- **Email:** Resend API (transactional), Flask-Mail/SMTP (reminders)
- **PDF:** ReportLab
- **Payments:** Stripe (Checkout, Billing Portal, Webhooks)
- **AI:** OpenAI API (GPT-4o-mini)
- **Analytics:** Google Analytics 4, Google Ads, Microsoft Clarity
- **i18n:** Flask-Babel (English, with Romanian on standby)
- **Deployment:** Docker, Railway, GitHub Actions CI/CD

## Local Setup

```bash
git clone https://github.com/stefcosmin09-glitch/scheduler-app
cd scheduler-app
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
python run.py
```

The app runs at `http://127.0.0.1:5000`.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Flask session signing key. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | Yes | PostgreSQL connection string (or SQLite for dev) |
| `RESEND_API_KEY` | Yes | Resend API key for transactional email |
| `MAIL_DEFAULT_SENDER` | Yes | Sender address for emails |
| `STRIPE_API_KEY` | Yes | Stripe secret key |
| `STRIPE_WEBHOOK_SECRET` | Yes | Stripe webhook signing secret |
| `OPENAI_API_KEY` | No | OpenAI API key for AI features (optional) |
| `SUPPORT_EMAIL` | Yes* | Contact email shown on legal pages |
| `LEGAL_ENTITY_NAME` | Yes* | Your name or company name (sole trader OK) |
| `COMPANY_NUMBER` | No | Company registration number (optional for sole traders) |
| `LEGAL_LAST_UPDATED` | No | Date shown on legal pages |
| `LEGAL_DRAFT` | No | Set to `0` to remove the DRAFT banner (default: `1`) |

\* Required in production. If missing, legal pages return 404 and footer links are hidden.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite builds its own SQLite database in a temporary directory and never touches `instance/`. It sets its own `SECRET_KEY` and `DATABASE_URL`, so it does not need a `.env`.

Tests also run on every push to `main` and on every pull request (`.github/workflows/tests.yml`), on Python 3.11 to match the Dockerfile. The workflow also builds a database from nothing with `migrate.py` and checks that `requirements.txt` is fully pinned.

## Migrations

The history is a single initial migration generated from the models:

```bash
python migrate.py     # what the container runs on every deploy
```

`migrate.py` handles three situations: empty database (run migrations), database with a squashed revision (re-stamp then upgrade), and normal upgrade. It exists because `flask db upgrade` alone fails on databases created before a squash.

## Legal Pages (Fail-Safe)

`/privacy`, `/terms`, `/cookies`, `/about` and `/compare` return 404 unless `SUPPORT_EMAIL` and `LEGAL_ENTITY_NAME` are set. Footer legal links are hidden in that case. `COMPANY_NUMBER` is optional. `LEGAL_DRAFT=0` removes the DRAFT banner after legal review.

## Sign-in Throttling

Repeated failures are counted in the `login_attempt` table on two separate counters:

| Counter | Limit | Catches |
|---|---|---|
| Per email | 5 in 15 min | one account sprayed from many addresses |
| Per IP address | 20 in 15 min | one address spraying many accounts |

Counters are in the database (not in-process) because gunicorn can scale to multiple workers. `ProxyFix` is used so `request.remote_addr` is the real client IP.

## Deployment

- **Platform:** Railway (Docker)
- **CI/CD:** GitHub Actions on push to `main` and on PRs
- **Auto-deploy:** Railway deploys from `main` on push

```bash
# Dockerfile runs:
python migrate.py && gunicorn run:app
```

## Project Structure

```
app/
  __init__.py        # app factory, config, context processors
  routes.py           # all routes (auth + main blueprints)
  models.py           # SQLAlchemy models
  markets.py          # enabled currencies/languages/tax countries
  invoice.py          # PDF invoice generation (ReportLab)
  ai_service.py       # OpenAI integration (quotes, receipts, messages)
  email_service.py    # Resend transactional email
  notifications.py    # email reminders
  templates/          # Jinja2 templates
  static/             # CSS, JS, images, icons
tests/                # pytest suite (200+ tests)
tools/                # demo server, screenshot capture, seed scripts
migrations/           # Alembic migration history
```

## License

Private project. All rights reserved.