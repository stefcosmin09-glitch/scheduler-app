"""Invoice PDF generation must not crash (regression: missing active_tax_country import)."""
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

from _support import app, check, db, login, reset_db
from app.models import BusinessProfile, Invoice, Job, User


def test_invoice_pdf_generates():
    reset_db()
    with app.app_context():
        user = User(username='inv', email='inv@t.test',
                    password=generate_password_hash('pw'), plan='pro')
        db.session.add(user)
        db.session.flush()
        job = Job(user_id=user.id, client_name='Sarah Whitfield',
                  address='14 Elm Close, Reading', date=datetime.utcnow(),
                  price=665, status='pending')
        db.session.add(job)
        db.session.flush()
        job_id = job.id
        bp = BusinessProfile(user_id=user.id, legal_name='Demo Trades',
                             vat_registered=True, vat_rate=20.00,
                             invoice_prefix='INV', next_invoice_number=10)
        db.session.add(bp)
        inv = Invoice(invoice_number='INV-000010', user_id=user.id, job_id=job.id,
                      issue_date=datetime.utcnow(), due_date=datetime.utcnow() + timedelta(days=14),
                      subtotal=665, vat_amount=133, total_amount=798, status='sent')
        db.session.add(inv)
        db.session.commit()
    client = app.test_client()
    login(client, 'inv', 'pw')
    response = client.get('/job/invoice/%d' % job_id)
    check('invoice returns 200', response.status_code, 200)
    check('invoice is a pdf', response.mimetype, 'application/pdf')