# TradeScheduler 🔧

A job scheduling web app for tradespeople — electricians, plumbers, builders.
Built as an alternative to Jobber (£39/mo) at a fraction of the cost.

🌐 **Live:** https://thetradescheduler.com

## Features

- ✅ Job scheduling with activity type and price
- ✅ Email reminder 40 minutes before each job
- ✅ Quote system — send quotes, client accepts/declines via email
- ✅ Invoice PDF generation + auto-send to client
- ✅ Weekly and monthly earnings dashboard
- ✅ Forgot password via email

## Tech Stack

- **Backend:** Python, Flask, SQLAlchemy
- **Database:** PostgreSQL
- **Email:** Resend API
- **PDF:** ReportLab
- **Auth:** Flask-Login
- **Deployment:** Docker, Railway
- **CI/CD:** GitHub → Railway auto-deploy

## Local Setup

```bash
git clone https://github.com/stefcosmin09-glitch/scheduler-app
cd scheduler-app
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add your keys
python3 run.py
```

## Environment Variables

```
SECRET_KEY=
DATABASE_URL=
RESEND_API_KEY=
MAIL_DEFAULT_SENDER=
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite builds its own SQLite database in a temporary directory and never
touches `instance/`, so it is safe to run against a real checkout.

| File | Covers |
| --- | --- |
| `test_time_tracking.py` | End-to-end: manual entries, timers, plan limits, ownership, CSRF, calendar feed |
| `test_calendar_ics.py` | The iCalendar generator against RFC 5545 |
| `test_pages.py` | Every page touched by the feature still renders |
| `test_dashboard_actions.py` | Job actions render as forms, not GET links |
| `test_fk_cascade.py` | `ON DELETE CASCADE` behaves the way Postgres will |
| `test_migrations.py` | Migration DDL, data preservation, reversibility |
| `test_encoding.py` | Sources stay valid UTF-8, no mojibake |
| `test_no_secrets.py` | No credential-shaped literals are committed |

The four round-trip migration tests need `instance/scheduler.db` as a
pre-feature baseline and skip without it, with the reason printed. A fresh
database cannot be built from scratch today because the first migration in the
chain creates a foreign key to a table it never creates.
