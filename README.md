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
SUPPORT_EMAIL=
LEGAL_ENTITY_NAME=
COMPANY_NUMBER=
LEGAL_LAST_UPDATED=
LEGAL_DRAFT=
```

## Legal pages (fail-safe)

`/privacy`, `/terms`, `/cookies`, `/about` and `/compare` return 404 unless
`SUPPORT_EMAIL` and `LEGAL_ENTITY_NAME` are set. The footer legal links are
hidden in that case, so an unconfigured deploy cannot leak raw placeholders.
`COMPANY_NUMBER` is optional (sole traders have none). `LEGAL_DRAFT=0`
removes the "DRAFT" banner once the text is reviewed.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite builds its own SQLite database in a temporary directory and never
touches `instance/`. It sets its own `SECRET_KEY` and `DATABASE_URL`, so it
does not need a `.env` either, which is what lets it run in CI.

Tests also run on every push to `main` and on every pull request
(`.github/workflows/tests.yml`), on Python 3.11 to match the Dockerfile. Beyond
the suite, the workflow builds a database from nothing with `migrate.py` and
checks that `requirements.txt` is still fully pinned. The build step is the one
that matters most: the migration history was broken for a long time and only a
fresh checkout could show it, because every developer already had a database.

`SECRET_KEY` has no default. The app exits with an error rather than start
without one, because a committed key would sign every session and CSRF token
with a value published on GitHub. Generate one with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
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
| `test_migrations.py` | A fresh database builds, matches the models, survives a downgrade, and the deploy entrypoint moves an old one over |
| `test_encoding.py` | Sources stay valid UTF-8, no mojibake |
| `test_no_secrets.py` | No credential-shaped literals are committed |
| `test_secret_key.py` | The app refuses to start without `SECRET_KEY`, and no default is committed |
| `test_login_throttle.py` | Sign-in stops answering after repeated failures, and cannot be used to list who has an account |

## Migrations

The history is a single `0001_initial_schema`, generated from the models.
Before that it was fifteen migrations that could not build a database from
scratch, because the first one created a foreign key to a table nothing in the
chain ever created.

```bash
python migrate.py     # what the container runs on every deploy
```

`migrate.py` exists because `flask db upgrade` alone is not safe after a
squash. A database created before the squash is stamped with a revision id the
script directory no longer has, and plain `upgrade` answers that with
`Can't locate revision identified by ...`, which would stop the container from
starting. The entrypoint tells the three situations apart: an empty database
gets the migrations, a database carrying a squashed revision gets re-stamped,
and anything else gets a normal upgrade. An existing database is never altered,
because its schema is already correct.

A squashed database is stamped to the **root** of the history and then upgraded,
not stamped to head. Stamping head would write the newest id onto a database
that never ran the newer migrations, and the tables they create would be missing
from then on. This is why `0002_login_throttle`, the first migration added after
the squash, works on the production database.

The Dockerfile runs it in place of `flask db upgrade` for that reason. Do not
change it back.

## Sign-in throttling

Repeated failures are counted in the `login_attempt` table, on two separate
counters, and both have to be under their limit:

| counter | limit | catches |
| --- | --- | --- |
| per email | 5 in 15 minutes | one account sprayed from many addresses |
| per address | 20 in 15 minutes | one address spraying many accounts |

The per-address limit is much looser on purpose. Offices and mobile carriers put
many unrelated people behind one address, and a tight limit there locks out
honest users over somebody else's typos. The first lockout is one minute and
doubles with every further failure up to four hours, so waiting is not a
workaround.

The counters are in the database, not in the worker, because gunicorn runs one
worker today but Railway can scale the service out and `--workers` is one flag
away. An in-process counter would hand every caller N times the allowance while
still looking like protection.

Two things depend on `ProxyFix` in `create_app()`. Without it `request.remote_addr`
is the address of the proxy in front of the app, every caller counts as one, and
a single attacker locks out the entire user base. The same fix also stops
externally generated links from saying `http`.

