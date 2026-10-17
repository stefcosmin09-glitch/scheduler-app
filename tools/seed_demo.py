"""Seed a LOCAL demo database for recording the TradeScheduler demo video.

This script only ever touches a SQLite file in the system temp directory. It
refuses to run if DATABASE_URL points at a production (Postgres/Railway) host,
and it never sends email (MAIL_SUPPRESS_SEND is forced on).

Usage:
    python tools/seed_demo.py               # uses the default demo db
    python tools/seed_demo.py --db path.db  # custom SQLite file
    python tools/seed_demo.py --reset        # wipe and reseed

The demo server (tools/demo_server.py) can serve this database by pointing
DEMO_DB at the same file.
"""
import argparse
import os
import pathlib
import secrets
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Safety: refuse to run against a production database.
_db_url = os.environ.get('DATABASE_URL', '')
if 'postgres' in _db_url.lower() or 'railway' in _db_url.lower() or 'psycopg' in _db_url.lower():
    print('ERROR: DATABASE_URL looks like production (%s). Refusing to run.' % _db_url)
    sys.exit(1)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--db', default=None, help='SQLite file to seed (default: temp demo db)')
parser.add_argument('--reset', action='store_true', help='wipe the database first')
args = parser.parse_args()

if args.db:
    db_path = pathlib.Path(args.db).resolve()
else:
    db_path = pathlib.Path(tempfile.gettempdir()) / 'tradescheduler-demo-video.db'

# Force SQLite + safety flags before the app imports config.
os.environ['DATABASE_URL'] = 'sqlite:///' + str(db_path).replace('\\', '/')
os.environ.setdefault('SECRET_KEY', secrets.token_hex(32))
os.environ['MAIL_SUPPRESS_SEND'] = '1'
os.environ['MAIL_DEFAULT_SENDER'] = 'demo@example.com'

from datetime import datetime, timedelta
from decimal import Decimal

from app import create_app, db
from app.models import User, Job, Invoice, BusinessProfile
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    if args.reset and db_path.exists():
        db_path.unlink()
        print('wiped %s' % db_path)

    db.create_all()

    # Demo user (never a real email).
    user = User.query.filter_by(email='demo@example.com').first()
    if user is None:
        user = User(
            username='demo',
            email='demo@example.com',
            password=generate_password_hash('demo-password-123'),
            plan='pro',
            trial_ends_at=datetime.utcnow() + timedelta(days=14),
            currency='GBP',
        )
        db.session.add(user)
        db.session.flush()
    else:
        # Reset jobs/invoices for a clean demo.
        Job.query.filter_by(user_id=user.id).delete()
        Invoice.query.filter_by(user_id=user.id).delete()
        BusinessProfile.query.filter_by(user_id=user.id).delete()
        db.session.commit()

    # Business profile for invoices.
    bp = BusinessProfile(
        user_id=user.id,
        business_type='sole_trader',
        legal_name='Demo Trades',
        trading_name='Demo Trades',
        address='1 Demo Street, Reading',
        phone='07700 900000',
        business_email='demo@example.com',
        vat_registered=True,
        vat_number='GB123456789',
        vat_rate=20.00,
        invoice_prefix='INV',
        next_invoice_number=10,
        payment_terms='30',
        show_bank_details=True,
        account_name='Demo Trades',
        sort_code='12-34-56',
        account_number='12345678',
    )
    db.session.add(bp)

    today = datetime.utcnow()

    clients = [
        ('Sarah Whitfield', 'sarah.whitfield@example.com', '14 Elm Close, Reading RG1 4AB', '07700 900001'),
        ('Neil Carter', 'neil.carter@example.com', '3 Orchard Close, Bracknell RG12 7TT', '07700 900002'),
        ('James Okafor', 'james.okafor@example.com', '22 Mill Lane, Oxford OX2 0HX', '07700 900003'),
        ('Priya Sharma', 'priya.sharma@example.com', '7 Cedar Avenue, Slough SL1 2AB', '07700 900004'),
        ('Tom Bradley', 'tom.bradley@example.com', '9 Willow Way, Newbury RG14 5HQ', '07700 900005'),
    ]

    # 6 jobs, mixed statuses
    jobs = []
    # Sarah Whitfield - consumer unit (quoted)
    j1 = Job(client_name='Sarah Whitfield', client_email='sarah.whitfield@example.com',
             address='14 Elm Close, Reading RG1 4AB', date=today + timedelta(days=1),
             description='Consumer unit replacement', activity_type='electric',
             price=620.00, currency='GBP', status='pending', user_id=user.id)
    jobs.append(j1)
    # Neil Carter - done (this week)
    j2 = Job(client_name='Neil Carter', client_email='neil.carter@example.com',
             address='3 Orchard Close, Bracknell RG12 7TT', date=today - timedelta(days=2),
             description='Full rewire of 3-bed semi', activity_type='electric',
             price=1240.00, currency='GBP', status='done', user_id=user.id)
    jobs.append(j2)
    # James Okafor - done (this month)
    j3 = Job(client_name='James Okafor', client_email='james.okafor@example.com',
             address='22 Mill Lane, Oxford OX2 0HX', date=today - timedelta(days=10),
             description='Bathroom installation', activity_type='plumbing',
             price=850.00, currency='GBP', status='done', user_id=user.id)
    jobs.append(j3)
    # Priya Sharma - pending
    j4 = Job(client_name='Priya Sharma', client_email='priya.sharma@example.com',
             address='7 Cedar Avenue, Slough SL1 2AB', date=today + timedelta(days=3),
             description='Fix leaking boiler', activity_type='plumbing',
             price=180.00, currency='GBP', status='pending', user_id=user.id)
    jobs.append(j4)
    # Tom Bradley - done
    j5 = Job(client_name='Tom Bradley', client_email='tom.bradley@example.com',
             address='9 Willow Way, Newbury RG14 5HQ', date=today - timedelta(days=5),
             description='Garden lighting install', activity_type='electric',
             price=320.00, currency='GBP', status='done', user_id=user.id)
    jobs.append(j5)
    # Sarah Whitfield - second job pending
    j6 = Job(client_name='Sarah Whitfield', client_email='sarah.whitfield@example.com',
             address='14 Elm Close, Reading RG1 4AB', date=today + timedelta(days=5),
             description='Kitchen sockets', activity_type='electric',
             price=90.00, currency='GBP', status='pending', user_id=user.id)
    jobs.append(j6)

    for j in jobs:
        db.session.add(j)
    db.session.flush()

    # 4 invoices: one paid, two overdue, one sent
    # Invoice 1: paid (Neil Carter)
    inv1 = Invoice(invoice_number='INV-000010', user_id=user.id, job_id=j2.id,
                   issue_date=today - timedelta(days=5), due_date=today - timedelta(days=2),
                   subtotal=1240, vat_amount=248, total_amount=1488, status='paid')
    db.session.add(inv1)
    # Invoice 2: overdue (Sarah Whitfield - consumer unit)
    inv2 = Invoice(invoice_number='INV-000011', user_id=user.id, job_id=j1.id,
                   issue_date=today - timedelta(days=14), due_date=today - timedelta(days=7),
                   subtotal=620, vat_amount=124, total_amount=744, status='overdue')
    db.session.add(inv2)
    # Invoice 3: overdue (James Okafor)
    inv3 = Invoice(invoice_number='INV-000012', user_id=user.id, job_id=j3.id,
                   issue_date=today - timedelta(days=12), due_date=today - timedelta(days=5),
                   subtotal=850, vat_amount=170, total_amount=1020, status='overdue')
    db.session.add(inv3)
    # Invoice 4: sent (Priya Sharma)
    inv4 = Invoice(invoice_number='INV-000013', user_id=user.id, job_id=j4.id,
                   issue_date=today - timedelta(days=1), due_date=today + timedelta(days=14),
                   subtotal=180, vat_amount=36, total_amount=216, status='sent')
    db.session.add(inv4)
    db.session.commit()

    # Scenario client: Sarah Whitfield, consumer unit replacement, specific invoice lines
    # Update job description to match the scenario
    j1.description = 'Consumer unit replacement'
    j1.price = 665.00
    # Add the specific invoice lines as a note? The invoice is already created.
    # Update inv2 to reflect the specific line items total: 480 + 2*45 + 95 = 665 + VAT
    inv2.subtotal = 665
    inv2.vat_amount = 133
    inv2.total_amount = 798
    db.session.commit()

    print('Seeded %s' % db_path)
    print('  user: demo@example.com / demo-password-123')
    print('  %d jobs, %d invoices' % (len(jobs), 4))