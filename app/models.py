from app import db, login_manager
from flask_login import UserMixin
from datetime import datetime
from decimal import Decimal

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    language = db.Column(db.String(10), default='en')
    jobs = db.relationship('Job', backref='owner', lazy=True)
    business = db.relationship('BusinessProfile', backref='user', uselist=False)
    invoices = db.relationship('Invoice', backref='user', lazy=True)
    currency = db.Column(db.String(10), nullable=False, server_default='GBP', default='GBP')
    plan = db.Column(db.String(20), default='free')
    trial_ends_at = db.Column(db.DateTime)
    stripe_customer_id = db.Column(db.String(100))
    stripe_subscription_id = db.Column(db.String(100))
    stripe_subscription_status = db.Column(db.String(50))

class BusinessProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    business_type = db.Column(db.String(20), default='sole_trader')
    legal_name = db.Column(db.String(200))
    trading_name = db.Column(db.String(200))
    tax_country = db.Column(db.String(10), default='UK', nullable=False, server_default='UK')
    address = db.Column(db.Text)
    phone = db.Column(db.String(50))
    business_email = db.Column(db.String(120))
    company_number = db.Column(db.String(50))
    vat_registered = db.Column(db.Boolean, default=False)
    vat_number = db.Column(db.String(50))
    vat_rate = db.Column(db.Numeric(5, 2), default=20.00)
    invoice_prefix = db.Column(db.String(20), default='INV')
    next_invoice_number = db.Column(db.Integer, default=1)
    payment_terms = db.Column(db.String(20), default='30')
    show_bank_details = db.Column(db.Boolean, default=False)
    account_name = db.Column(db.String(100))
    sort_code = db.Column(db.String(20))
    account_number = db.Column(db.String(20))
    payment_link_url = db.Column(db.String(500))
    logo = db.Column(db.LargeBinary)
    logo_mime = db.Column(db.String(32))

class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    issue_date = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime)
    subtotal = db.Column(db.Numeric(10, 2), default=0)
    vat_amount = db.Column(db.Numeric(10, 2), default=0)
    total_amount = db.Column(db.Numeric(10, 2), default=0)
    status = db.Column(db.String(20), default='draft')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime)
    reminder_sent = db.Column(db.Boolean, default=False)
    payment_link = db.Column(db.String(500))
    job = db.relationship('Job', backref='invoice', uselist=False)
    payments = db.relationship('Payment', backref='invoice', lazy=True)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_method = db.Column(db.String(50), default='bank_transfer')
    reference = db.Column(db.String(100))
    notes = db.Column(db.Text)

ACTIVITY_TYPES = [
    ('electric', '⚡ Electrical'),
    ('plumbing', '🔧 Plumbing'),
    ('construction', '🏗️ Construction'),
    ('carpentry', '🪟 Carpentry'),
    ('decorating', '🎨 Decorating'),
    ('general', '🔩 General Repairs'),
    ('other', '➕ Other'),
]

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(100), nullable=False)
    client_email = db.Column(db.String(120))
    address = db.Column(db.String(200), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    description = db.Column(db.Text)
    activity_type = db.Column(db.String(50), default='other')
    price = db.Column(db.Numeric(10, 2), default=0.0)
    currency = db.Column(db.String(10), default='GBP', server_default='GBP')
    status = db.Column(db.String(20), default='pending')
    reminder_sent = db.Column(db.Boolean, default=False)
    quote_status = db.Column(db.String(20), default='none')
    quote_token = db.Column(db.String(64))
    quote_price = db.Column(db.Numeric(10, 2), default=0.0)
    quote_description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)