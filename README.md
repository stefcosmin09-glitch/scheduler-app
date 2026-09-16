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