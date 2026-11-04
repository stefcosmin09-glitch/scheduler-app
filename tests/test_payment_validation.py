"""Payment recording must not accept overpayments or invalid amounts."""
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

from _support import app, check, db, login, reset_db
from app.models import BusinessProfile, Invoice, Job, User


def _setup():
    reset_db()
    with app.app_context():
        user = User(username='pay', email='pay@t.test',
                    password=generate_password_hash('pw'), plan='pro')
        db.session.add(user)
        db.session.flush()
        job = Job(user_id=user.id, client_name='Sarah Whitfield',
                  address='14 Elm Close, Reading', date=datetime.utcnow(),
                  price=665, status='pending')
        db.session.add(job)
        db.session.flush()
        bp = BusinessProfile(user_id=user.id, legal_name='Demo Trades',
                             vat_registered=True, vat_rate=20.00,
                             invoice_prefix='INV', next_invoice_number=10)
        db.session.add(bp)
        inv = Invoice(invoice_number='INV-000010', user_id=user.id, job_id=job.id,
                      issue_date=datetime.utcnow(), due_date=datetime.utcnow() + timedelta(days=14),
                      subtotal=665, vat_amount=133, total_amount=798, status='sent')
        db.session.add(inv)
        db.session.commit()
        return job.id, inv.id
    return None, None


def _post_payment(client, inv_id, amount):
    from _support import csrf
    return client.post('/invoice/%d/mark-paid' % inv_id,
                      data={'amount': amount, 'payment_method': 'bank_transfer',
                            'csrf_token': csrf(client)},
                      follow_redirects=True)


def test_payment_greater_than_balance_rejected():
    job_id, inv_id = _setup()
    client = app.test_client()
    login(client, 'pay', 'pw')
    resp = _post_payment(client, inv_id, '900')
    body = resp.get_data(as_text=True)
    check('rejected message shown', 'Amount exceeds outstanding balance' in body, True)
    with app.app_context():
        from app.models import Payment
        check('no payment saved', Payment.query.filter_by(invoice_id=inv_id).count(), 0)


def test_payment_equal_to_balance_accepted():
    job_id, inv_id = _setup()
    client = app.test_client()
    login(client, 'pay', 'pw')
    resp = _post_payment(client, inv_id, '798')
    body = resp.get_data(as_text=True)
    check('payment recorded', 'Payment recorded!' in body, True)
    with app.app_context():
        from app.models import Invoice
        inv = Invoice.query.get(inv_id)
        check('invoice paid', inv.status, 'paid')


def test_payment_smaller_than_balance_accepted():
    job_id, inv_id = _setup()
    client = app.test_client()
    login(client, 'pay', 'pw')
    resp = _post_payment(client, inv_id, '300')
    body = resp.get_data(as_text=True)
    check('payment recorded', 'Payment recorded!' in body, True)
    with app.app_context():
        from app.models import Invoice
        inv = Invoice.query.get(inv_id)
        check('invoice partially paid', inv.status, 'partially_paid')


def test_payment_zero_rejected():
    job_id, inv_id = _setup()
    client = app.test_client()
    login(client, 'pay', 'pw')
    resp = _post_payment(client, inv_id, '0')
    body = resp.get_data(as_text=True)
    check('rejected', 'Amount must be greater than zero' in body, True)


def test_payment_negative_rejected():
    job_id, inv_id = _setup()
    client = app.test_client()
    login(client, 'pay', 'pw')
    resp = _post_payment(client, inv_id, '-50')
    body = resp.get_data(as_text=True)
    check('rejected', 'Amount must be greater than zero' in body, True)


def test_payment_non_numeric_rejected():
    job_id, inv_id = _setup()
    client = app.test_client()
    login(client, 'pay', 'pw')
    resp = _post_payment(client, inv_id, 'abc')
    body = resp.get_data(as_text=True)
    check('rejected', 'Please enter a valid amount' in body, True)


def test_second_partial_payment_exceeding_rejected():
    job_id, inv_id = _setup()
    client = app.test_client()
    login(client, 'pay', 'pw')
    _post_payment(client, inv_id, '300')
    resp = _post_payment(client, inv_id, '600')  # 300+600 > 798
    body = resp.get_data(as_text=True)
    check('rejected', 'Amount exceeds outstanding balance' in body, True)
