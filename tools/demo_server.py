"""Serve the app on localhost against a throw-away database.

Used to take product screenshots for the marketing pages: it gives a real,
signed-in view of the app without touching a live account or sending a single
email.

    python tools/demo_server.py             seed if needed, then serve
    python tools/demo_server.py --reseed    rebuild the database from scratch

The database lives outside the repository, in the system temp directory, so a
demo run can never be mistaken for, or overwrite, real data. Point DEMO_DB
somewhere else to move it.
"""
import argparse
import os
import pathlib
import secrets
import sys
import tempfile
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DB_PATH = pathlib.Path(
    os.environ.get('DEMO_DB')
    or (pathlib.Path(tempfile.gettempdir()) / 'tradescheduler-demo.db')
)

# Must be set before app.config is imported: Config reads the environment when
# the module loads. The key is generated per run and never stored, so this can
# never sign anything real.
os.environ.setdefault('SECRET_KEY', secrets.token_hex(32))
os.environ['DATABASE_URL'] = 'sqlite:///' + str(DB_PATH).replace('\\', '/')
# A demo server must never be able to reach a mail server.
os.environ.pop('MAIL_PASSWORD', None)
os.environ.pop('STRIPE_API_KEY', None)

# A loopback-only demo login, for a database that lives outside the repository.
# Nothing here is a real secret, and both values stay overridable so nobody has
# to sign in with a password written down in a public file.
DEMO_USERNAME = os.environ.get('DEMO_USERNAME', 'demo')
DEMO_PASSWORD = os.environ.get('DEMO_PASSWORD', 'demo-password-123')

# A fictional business, so the screenshots show plausible UK trade data without
# standing in for a real customer.
JOBS = [
    # client, address, days from today, activity, description, price, status, quote
    ('Sarah Pemberton', '14 Beech Road, Reading RG6 1PA', -9, 'plumbing',
     'Annual boiler service and gas safety check', 320, 'done', 'accepted'),
    ('Neil Carter', '3 Orchard Close, Bracknell RG12 7TT', 0, 'plumbing',
     'Leaking radiator valve in the front room', 240, 'pending', 'accepted'),
    ('Helen Whitfield', '5 Grange Avenue, Wokingham RG40 2DL', 2, 'plumbing',
     'Replace combi boiler, supply and fit', 2450, 'pending', 'accepted'),
    ('Mark Davies', '27 Kings Road, Slough SL1 2QP', -6, 'plumbing',
     'Bathroom tap replacement and reseal', 185, 'done', 'accepted'),
    ('Priya Nair', '19 Elm Grove, Reading RG4 8SS', 3, 'plumbing',
     'Fit outside tap and isolator', 160, 'pending', 'sent'),
    ('Tom Reeves', '88 London Road, Camberley GU15 3JP', -4, 'plumbing',
     'Power flush, 8 radiators and inhibitor', 480, 'done', 'accepted'),
    ('David Okafor', '41 Ash Way, Maidenhead SL6 4RB', -2, 'plumbing',
     'Shower pump replacement', 420, 'done', 'accepted'),
    ('Claire Bennett', '7 Vicarage Road, Henley RG9 1HF', 5, 'plumbing',
     'Immersion heater replacement', 310, 'pending', 'accepted'),
    ('James Hollis', '62 Bath Road, Reading RG30 2EU', -12, 'plumbing',
     'Emergency leak repair, burst pipe', 210, 'done', 'accepted'),
    ('Rebecca Lyons', '15 Sandford Lane, Wokingham RG41 1NR', 7, 'plumbing',
     'Replace 6 radiator valves and balance system', 275, 'pending', 'none'),
    ('Ian Mercer', '9 Chapel Street, Twyford RG10 9EB', 9, 'plumbing',
     'Unvented cylinder replacement', 1180, 'pending', 'sent'),
    ('Fiona Grant', '33 Church Lane, Earley RG6 5QH', 12, 'plumbing',
     'Landlord gas safety certificate', 95, 'pending', 'accepted'),
]

# Invoices are raised against jobs that are already done.
INVOICES = [
    # job client, issue days ago, due days ago, status, paid?
    ('James Hollis', 11, 4, 'sent', False),        # will read as overdue
    ('Sarah Pemberton', 9, 2, 'sent', False),      # will read as overdue
    ('Mark Davies', 6, -1, 'sent', False),         # due tomorrow
    ('Tom Reeves', 4, -10, 'sent', False),         # due in 10 days
    ('David Okafor', 2, -12, 'paid', True),
]

EXPENSES = [
    ('Screwfix', 'Copper pipe, fittings and PTFE tape', -3, 84.20, 14.03, 'Materials'),
    ('City Plumbing', 'Worcester Bosch 8000 combi boiler', -5, 1180.00, 196.67, 'Materials'),
    ('Shell', 'Van diesel, Reading to Bracknell', -2, 68.40, 11.40, 'Fuel / Vehicle'),
    ('Toolstation', 'Knipex wrench set and pipe cutter', -8, 142.99, 23.83, 'Tools'),
    ('AxA Trade Insurance', 'Public liability, monthly', -15, 47.50, 0.00, 'Insurance'),
    ('B&Q', 'Sundries and dust sheets', -1, 31.75, 5.29, 'Materials'),
    ('Vodafone', 'Business mobile, monthly', -18, 28.00, 4.67, 'Phone / Internet'),
    ('Gas Safe Register', 'Annual registration fee', -30, 66.00, 11.00, 'Trade body / Courses'),
]

def seed():
    from werkzeug.security import generate_password_hash

    from app import create_app, db
    from app.models import (BusinessProfile, Expense, Invoice, Job, Payment,
                            TimeEntry, User)

    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        user = User(
            username=DEMO_USERNAME,
            email='demo@thetradescheduler.com',
            password=generate_password_hash(DEMO_PASSWORD),
            language='en',
            currency='GBP',
            plan='pro',
            trial_ends_at=None,
        )
        db.session.add(user)
        db.session.flush()

        db.session.add(BusinessProfile(
            user_id=user.id,
            business_type='limited',
            legal_name='Northside Plumbing & Heating Ltd',
            trading_name='Northside Plumbing & Heating',
            tax_country='UK',
            address='12 Mill Lane\nReading\nRG1 4RT',
            phone='0118 496 0123',
            business_email='office@northsideplumbing.co.uk',
            company_number='11842207',
            vat_registered=True,
            vat_number='GB 412 8830 55',
            vat_rate=20,
            invoice_prefix='INV',
            next_invoice_number=13,
            payment_terms='14',
            show_bank_details=True,
            account_name='Northside Plumbing & Heating Ltd',
            sort_code='20-45-77',
            account_number='40718823',
        ))

        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        jobs_by_client = {}

        for client, address, offset, activity, description, price, status, quote in JOBS:
            job = Job(
                client_name=client,
                client_email='%s@example.co.uk' % client.split()[0].lower(),
                address=address,
                date=today + timedelta(days=offset, hours=8),
                description=description,
                activity_type=activity,
                price=price,
                currency='GBP',
                status=status,
                quote_status=quote,
                quote_price=price,
                quote_description=description,
                duration_minutes=120,
                user_id=user.id,
            )
            db.session.add(job)
            jobs_by_client[client] = job

        db.session.flush()

        vat_rate = 0.20
        for index, row in enumerate(INVOICES):
            client, issue_offset, due_offset, status, is_paid = row
            job = jobs_by_client[client]
            net = float(job.price)
            vat = round(net * vat_rate, 2)
            invoice = Invoice(
                invoice_number='INV-%04d' % (7 + index),
                user_id=user.id,
                job_id=job.id,
                issue_date=today + timedelta(days=issue_offset),
                due_date=today + timedelta(days=due_offset),
                subtotal=net,
                vat_amount=vat,
                total_amount=round(net + vat, 2),
                status=status,
                paid_at=today + timedelta(days=due_offset + 1) if is_paid else None,
                reminder_sent=True,
            )
            db.session.add(invoice)
            db.session.flush()

            if is_paid:
                db.session.add(Payment(
                    invoice_id=invoice.id,
                    amount=invoice.total_amount,
                    payment_date=today + timedelta(days=due_offset + 1),
                    payment_method='bank_transfer',
                    reference='FPS 240918',
                ))

        for merchant, description, offset, total, vat, category in EXPENSES:
            db.session.add(Expense(
                user_id=user.id,
                merchant=merchant,
                description=description,
                date=(today + timedelta(days=offset)).date(),
                total=total,
                vat_amount=vat,
                currency='GBP',
                category=category,
            ))

        for job in jobs_by_client.values():
            if job.status != 'done':
                continue
            start = job.date + timedelta(hours=1)
            db.session.add(TimeEntry(
                user_id=user.id,
                job_id=job.id,
                started_at=start,
                ended_at=start + timedelta(minutes=95),
                minutes=95,
                note='On site',
            ))

        db.session.commit()
        print('seeded %s (%d jobs)' % (DB_PATH, len(JOBS)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reseed', action='store_true',
                        help='rebuild the demo database before serving')
    parser.add_argument('--port', type=int,
                        default=int(os.environ.get('DEMO_PORT', '5055')))
    parser.add_argument('--seed-only', action='store_true')
    args = parser.parse_args()

    if args.reseed or not DB_PATH.exists():
        seed()
    else:
        print('using existing %s (pass --reseed to rebuild)' % DB_PATH)

    if args.seed_only:
        return

    from app import create_app
    app = create_app()

    @app.route('/__demo_login__')
    def _demo_login():
        """Sign the demo user in and bounce to a page, so a headless browser can
        photograph the signed-in app in a single navigation.

        The cookie is a session cookie, so a second browser run would arrive
        logged out; logging in and redirecting in one request keeps it alive.
        This route exists only in this file: the application itself never
        registers it. It is safe here because the demo server always binds to
        loopback and always runs against its own throw-away database.
        """
        from flask import redirect, request
        from flask_login import login_user

        from app.models import User

        user = User.query.filter_by(username=DEMO_USERNAME).first()
        if user is None:
            return 'demo user missing; run again with --reseed', 500
        login_user(user)
        target = request.args.get('next') or '/'
        if not target.startswith('/') or target.startswith('//'):
            target = '/'
        return redirect(target)

    @app.route('/__phone_frame__')
    def _phone_frame():
        """Show a page at phone width inside a host page.

        Headless Chrome will not lay a window out narrower than about 491px, so a
        390px capture is really laid out at 491px and then cropped, which clips the
        page. Framing the page in a 390px iframe inside a wider window gives it a
        true 390px layout. Like the login route, this exists only in this file.
        """
        from flask import request
        from markupsafe import escape

        target = request.args.get('next') or '/'
        if not target.startswith('/') or target.startswith('//'):
            target = '/'
        return ('<!doctype html><html><body style="margin:0;background:#fff">'
                '<iframe src="%s" width="390" height="844" '
                'style="border:0;display:block"></iframe></body></html>'
                % escape(target))

    print('login: %s / %s' % (DEMO_USERNAME, DEMO_PASSWORD))
    app.run(host='127.0.0.1', port=args.port, use_reloader=False, debug=False,
            threaded=True)


if __name__ == '__main__':
    main()
