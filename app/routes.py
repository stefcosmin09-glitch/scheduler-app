from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, send_from_directory, Response, abort
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.currency import convert_to_base
from itsdangerous import URLSafeTimedSerializer
from app.models import User, Job, Invoice, Payment, ACTIVITY_TYPES
from app.notifications import send_overdue_invoice_reminders
from datetime import datetime
from flask import current_app
from flask_babel import _ 
from threading import Thread
from app import db, format_money

auth = Blueprint('auth', __name__)
main = Blueprint('main', __name__)

# ─── AUTH ───────────────────────────────────────────

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if User.query.filter_by(email=email).first():
            flash(_('Email already used.'))
            return redirect(url_for('auth.register'))

        user = User(
            username=username,
            email=email,
            password=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        flash(_('Account created successfully!'))
        return redirect(url_for('auth.login'))

    return render_template('register.html')


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password, password):
            flash(_('Wrong email or password.'))
            return redirect(url_for('auth.login'))

        login_user(user)
        return redirect(url_for('main.dashboard'))

    return render_template('login.html')


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


def get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        if user:
            s = get_serializer()
            token = s.dumps(email, salt='password-reset')
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            if user.language == 'ro':
                subject = 'Resetare parolă - Scheduler App'
                body = f"""Bună ziua {user.username},

Click pe link-ul de mai jos pentru a vă reseta parola. Link-ul expiră în 1 oră.

{reset_url}

Dacă nu ați solicitat acest lucru, ignorați acest email."""
            else:
                subject = 'Reset your password - Scheduler App'
                body = f"""Hi {user.username},

Click the link below to reset your password. The link expires in 1 hour.

{reset_url}

If you didn't request this, ignore this email."""
            app = current_app._get_current_object()
            def send_reset(app, to, subject, body):
                with app.app_context():
                    from app.email_service import send_email
                    send_email(to, subject, body)
            Thread(target=send_reset, args=(app, email, subject, body)).start()
            flash(_('If that email exists, you will receive a reset link shortly.'))
        return redirect(url_for('auth.login'))

    return render_template('forgot_password.html')


@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        s = get_serializer()
        email = s.loads(token, salt='password-reset', max_age=3600)
    except Exception:
        flash(_('Invalid or expired link.'))
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user:
            user.password = generate_password_hash(password)
            db.session.commit()
            flash(_('Password changed successfully!'))
            return redirect(url_for('auth.login'))

    return render_template('reset_password.html', token=token)


# ─── MAIN ───────────────────────────────────────────

@main.route('/')
@login_required
def dashboard():
    from datetime import timedelta
    filter_type = request.args.get('type', 'all')
    filter_status = request.args.get('status', 'active')

    query = Job.query.filter_by(user_id=current_user.id)

    if filter_type != 'all':
        query = query.filter_by(activity_type=filter_type)

    if filter_status == 'active':
        query = query.filter_by(status='pending')
    elif filter_status == 'done':
        query = query.filter_by(status='done')

    jobs = query.order_by(Job.date).all()

    now = datetime.utcnow()
    from datetime import timedelta
    start_of_week = now - timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0)

    weekly_jobs = Job.query.filter_by(user_id=current_user.id, status='done').filter(Job.date >= start_of_week).all()
    monthly_jobs = Job.query.filter_by(user_id=current_user.id, status='done').filter(Job.date >= start_of_month).all()

    weekly_total = sum(j.price for j in weekly_jobs if j.price)
    monthly_total = sum(j.price for j in monthly_jobs if j.price)

    return render_template('dashboard.html',
                           jobs=jobs,
                           activity_types=ACTIVITY_TYPES,
                           filter_type=filter_type,
                           filter_status=filter_status,
                           weekly_total=weekly_total,
                           monthly_total=monthly_total)


@main.route('/job/add', methods=['GET', 'POST'])
@login_required
def add_job():
    if request.method == 'POST':
        currency = request.form.get('price_currency', 'GBP')
        job = Job(
            client_name=request.form.get('client_name'),
            client_email=request.form.get('client_email'),
            address=request.form.get('address'),
            date=datetime.strptime(request.form.get('date'), '%Y-%m-%dT%H:%M'),
            description=request.form.get('description'),
            activity_type=request.form.get('activity_type', 'altele'),
            price=float(convert_to_base(request.form.get('price') or 0, currency)),
            currency=currency,
            user_id=current_user.id
        )
        db.session.add(job)
        db.session.commit()
        flash(_('Job added!'))
        return redirect(url_for('main.dashboard'))

    return render_template('add_job.html', activity_types=ACTIVITY_TYPES)


@main.route('/job/done/<int:job_id>')
@login_required
def mark_done(job_id):
    job = Job.query.get_or_404(job_id)
    if job.user_id != current_user.id:
        flash(_('You do not have permission.'))
        return redirect(url_for('main.dashboard'))
    job.status = 'done'
    db.session.commit()
    flash(_('Job marked as completed!'))
    return redirect(url_for('main.dashboard'))


@main.route('/job/delete/<int:job_id>')
@login_required
def delete_job(job_id):
    job = Job.query.get_or_404(job_id)
    if job.user_id != current_user.id:
        flash(_('You do not have permission to delete this job.'))
        return redirect(url_for('main.dashboard'))
    if Invoice.query.filter_by(job_id=job.id).first():
        flash(_('This job has an invoice and cannot be deleted.'))
        return redirect(url_for('main.dashboard'))
    db.session.delete(job)
    db.session.commit()
    flash(_('Job deleted.'))
    return redirect(url_for('main.dashboard'))


@main.route('/job/invoice/<int:job_id>')
@login_required
def download_invoice(job_id):
    from app.models import Invoice, BusinessProfile
    from datetime import timedelta
    import base64

    job = Job.query.get_or_404(job_id)
    if job.user_id != current_user.id:
        flash(_('You do not have permission.'))
        return redirect(url_for('main.dashboard'))

    business = BusinessProfile.query.filter_by(user_id=current_user.id).first()

    # Verificam daca exista deja un invoice pentru acest job
    existing_invoice = Invoice.query.filter_by(job_id=job.id).first()

    if not existing_invoice:
        # Generam numar invoice (sari peste numere duplicate)
        if business:
            while True:
                invoice_number = f"{business.invoice_prefix}-{str(business.next_invoice_number).zfill(6)}"
                business.next_invoice_number += 1
                if not Invoice.query.filter_by(invoice_number=invoice_number).first():
                    break
        else:
            invoice_number = f"INV-{str(job.id).zfill(6)}"

        # Calculam due date
        issue_date = datetime.utcnow()
        days = int(business.payment_terms) if business and business.payment_terms else 30
        due_date = issue_date + timedelta(days=days)

        # Calculam VAT
        subtotal = float(job.price or 0)
        vat_amount = 0
        if business and business.vat_registered and business.vat_rate:
            vat_amount = subtotal * float(business.vat_rate) / 100
        total = subtotal + vat_amount

        # Cream invoice record
        invoice = Invoice(
            invoice_number=invoice_number,
            user_id=current_user.id,
            job_id=job.id,
            issue_date=issue_date,
            due_date=due_date,
            subtotal=subtotal,
            vat_amount=vat_amount,
            total_amount=total,
            status='sent'
        )
        db.session.add(invoice)
        db.session.commit()
    else:
        invoice = existing_invoice

    from app.invoice import generate_invoice
    buffer = generate_invoice(job, current_user)
    pdf_bytes = buffer.getvalue()

    if job.client_email:
        try:
            from app.email_service import send_email_with_attachment
            if current_user.language == 'ro':
                subject = f'Factura {invoice.invoice_number}'
                body = f"""Bună ziua {job.client_name},

Găsiți atașată factura pentru lucrările finalizate pe {job.date.strftime('%d/%m/%Y')}.

Număr factură: {invoice.invoice_number}
Suma de plată: {format_money(invoice.total_amount, job.currency)}
Scadența: {invoice.due_date.strftime('%d/%m/%Y')}

Vă mulțumim pentru colaborare!
{business.trading_name or business.legal_name if business else current_user.username}"""
            else:
                subject = f'Invoice {invoice.invoice_number}'
                body = f"""Dear {job.client_name},

Please find attached your invoice for the work completed on {job.date.strftime('%d/%m/%Y')}.

Invoice Number: {invoice.invoice_number}
Amount Due: {format_money(invoice.total_amount, job.currency)}
Due Date: {invoice.due_date.strftime('%d/%m/%Y')}

Thank you for your business!
{business.trading_name or business.legal_name if business else current_user.username}"""
            app = current_app._get_current_object()
            pdf_b64 = base64.b64encode(pdf_bytes).decode()
            def send_inv(app, to, subject, body, pdf_b64, inv_number):
                with app.app_context():
                    send_email_with_attachment(to, subject, body, pdf_b64, f'{inv_number}.pdf')
            Thread(target=send_inv, args=(app, job.client_email, subject, body, pdf_b64, invoice.invoice_number)).start()
            flash(_('Invoice downloaded and sent to client!'))
        except Exception as e:
            print(f">>> Invoice email error: {e}")
            flash(_('Invoice downloaded.'))

    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename={invoice.invoice_number}.pdf',
            'Content-Type': 'application/pdf'
        }
    )

@main.route('/job/quote/<int:job_id>', methods=['GET', 'POST'])
@login_required
def send_quote(job_id):
    job = Job.query.get_or_404(job_id)
    if job.user_id != current_user.id:
        flash(_('You do not have permission.'))
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        quote_price = float(convert_to_base(request.form.get('quote_price') or 0, request.form.get('price_currency', 'GBP')))
        quote_description = request.form.get('quote_description')

        job.quote_price = quote_price
        job.quote_description = quote_description
        job.quote_status = 'sent'
        import secrets
        job.quote_token = secrets.token_urlsafe(16)
        db.session.commit()

        accept_url = url_for('main.quote_response', job_id=job.id, response='accepted', token=job.quote_token, _external=True)
        decline_url = url_for('main.quote_response', job_id=job.id, response='declined', token=job.quote_token, _external=True)

        if job.client_email:
            if current_user.language == 'ro':
                subject = f'Ofertă de la {current_user.username}'
                body = f"""Bună ziua {job.client_name},

Ați primit o ofertă pentru următoarele lucrări:

Adresă: {job.address}
Descriere: {quote_description}
Preț: {format_money(quote_price, current_user.currency)}

Pentru a accepta: {accept_url}
Pentru a refuza: {decline_url}

Vă mulțumim,
{current_user.username}"""
            else:
                subject = f'Quote from {current_user.username}'
                body = f"""Dear {job.client_name},

You have received a quote for the following work:

Address: {job.address}
Description: {quote_description}
Price: {format_money(quote_price, current_user.currency)}

To accept: {accept_url}
To decline: {decline_url}

Thank you,
{current_user.username}"""
            app = current_app._get_current_object()
            username = current_user.username
            def send_async(app, to, subject, body):
                with app.app_context():
                    from app.email_service import send_email
                    send_email(to, subject, body)
            Thread(target=send_async, args=(app, job.client_email, subject, body)).start()
            flash(_('Quote sent successfully!'))
        else:
            flash(_('No client email — quote saved but not sent.'))

        return redirect(url_for('main.dashboard'))

    return render_template('send_quote.html', job=job)


@main.route('/job/quote/<int:job_id>/response/<response>')
def quote_response(job_id, response):
    job = Job.query.get_or_404(job_id)
    token = request.args.get('token')
    if not job.quote_token or token != job.quote_token:
        abort(404)
    if response in ['accepted', 'declined']:
        job.quote_status = response
        db.session.commit()
    return render_template('quote_response.html', job=job, response=response)

@main.route('/business-settings', methods=['GET', 'POST'])
@login_required
def business_settings():
    from app.models import BusinessProfile
    business = BusinessProfile.query.filter_by(user_id=current_user.id).first()

    if request.method == 'POST':
        if not business:
            business = BusinessProfile(user_id=current_user.id)
            db.session.add(business)

        business.business_type = request.form.get('business_type', 'sole_trader')
        business.legal_name = request.form.get('legal_name')
        business.trading_name = request.form.get('trading_name')
        business.address = request.form.get('address')
        business.phone = request.form.get('phone')
        business.business_email = request.form.get('business_email')
        business.company_number = request.form.get('company_number')
        business.tax_country = request.form.get('tax_country', 'UK')
        business.vat_registered = 'vat_registered' in request.form
        business.vat_number = request.form.get('vat_number')
        business.vat_rate = request.form.get('vat_rate') or 20.00
        business.invoice_prefix = request.form.get('invoice_prefix', 'INV')
        business.next_invoice_number = int(request.form.get('next_invoice_number') or 1)
        business.payment_terms = request.form.get('payment_terms', '30')
        business.show_bank_details = 'show_bank_details' in request.form
        business.account_name = request.form.get('account_name')
        business.sort_code = request.form.get('sort_code')
        business.account_number = request.form.get('account_number')

        logo_file = request.files.get('logo')
        if logo_file and logo_file.filename:
            data = logo_file.read()
            mime = logo_file.mimetype or 'image/png'
            if len(data) > 1_500_000:
                flash(_('Logo too large. Max 1.5MB.'))
                return redirect(url_for('main.business_settings'))
            if mime not in ('image/png', 'image/jpeg'):
                flash(_('Logo must be PNG or JPG.'))
                return redirect(url_for('main.business_settings'))
            business.logo = data
            business.logo_mime = mime
        else:
            if request.form.get('remove_logo'):
                business.logo = None
                business.logo_mime = None

        db.session.commit()
        flash(_('Business settings saved!'))
        return redirect(url_for('main.business_settings'))

    return render_template('business_settings.html', business=business)

@main.route('/business-logo')
@login_required
def business_logo():
    from app.models import BusinessProfile
    business = BusinessProfile.query.filter_by(user_id=current_user.id).first()
    if not business or not business.logo:
        abort(404)
    return Response(business.logo, mimetype=business.logo_mime or 'image/png')

@main.route('/invoices')
@login_required
def invoices():
    from app.models import Invoice
    from datetime import date
    from app.notifications import send_overdue_invoice_reminders
    send_overdue_invoice_reminders(current_app._get_current_object())
    
    all_invoices = Invoice.query.filter_by(user_id=current_user.id).order_by(Invoice.issue_date.desc()).all()
    
    # Mark overdue
    today = datetime.utcnow()
    for inv in all_invoices:
        if inv.status not in ('paid', 'cancelled', 'partially_paid') and inv.due_date and inv.due_date < today:
            inv.status = 'overdue'
    db.session.commit()
    
    return render_template('invoices.html', invoices=all_invoices)

@main.route('/payments')
@login_required
def payments():
    payments = (
        Payment.query
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .filter(Invoice.user_id == current_user.id)
        .order_by(Payment.payment_date.desc())
        .all()
    )
    total_received = sum(float(p.amount) for p in payments)
    return render_template('payments.html', payments=payments, total_received=total_received)


@main.route('/invoice/<int:invoice_id>/mark-paid', methods=['POST'])
@login_required
def mark_invoice_paid(invoice_id):
    from app.models import Invoice, Payment
    invoice = Invoice.query.get_or_404(invoice_id)
    if invoice.user_id != current_user.id:
        flash(_('You do not have permission.'))
        return redirect(url_for('main.invoices'))
    if invoice.status == 'paid':
        flash(_('This invoice is already fully paid.'))
        return redirect(url_for('main.invoices'))
    
    amount = float(request.form.get('amount') or invoice.total_amount)
    method = request.form.get('payment_method', 'bank_transfer')
    reference = request.form.get('reference', '')
    
    payment = Payment(
        invoice_id=invoice.id,
        amount=amount,
        payment_method=method,
        reference=reference,
        payment_date=datetime.utcnow()
    )
    db.session.add(payment)
    
    # Calculam total platit
    total_paid = sum(float(p.amount) for p in invoice.payments) + amount
    if total_paid >= float(invoice.total_amount):
        invoice.status = 'paid'
        invoice.paid_at = datetime.utcnow()
    else:
        invoice.status = 'partially_paid'
    
    db.session.commit()
    flash(_('Payment recorded!'))
    return redirect(url_for('main.invoices'))

@main.route('/invoice/<int:invoice_id>/cancel', methods=['POST'])
@login_required
def cancel_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    if invoice.user_id != current_user.id:
        flash(_('You do not have permission.'))
        return redirect(url_for('main.invoices'))
    if invoice.status == 'paid':
        flash(_('Cannot cancel an invoice that is already paid.'))
        return redirect(url_for('main.invoices'))
    invoice.status = 'cancelled'
    db.session.commit()
    flash(_('Invoice cancelled.'))
    return redirect(url_for('main.invoices'))

@main.route('/accounting')
@login_required
def accounting():
    from app.models import Invoice
    from datetime import date
    import calendar

    # Luna curenta
    now = datetime.utcnow()
    year = int(request.args.get('year', now.year))
    month = int(request.args.get('month', now.month))

    # Prima si ultima zi din luna
    first_day = datetime(year, month, 1)
    last_day = datetime(year, month, calendar.monthrange(year, month)[1], 23, 59, 59)

    # Invoicele lunii
    monthly_invoices = Invoice.query.filter_by(user_id=current_user.id).filter(
        Invoice.issue_date >= first_day,
        Invoice.issue_date <= last_day,
        Invoice.status != 'cancelled'
    ).all()

    # Calcule
    total_invoiced = sum(float(inv.total_amount) for inv in monthly_invoices)
    total_paid = sum(
        sum(float(p.amount) for p in inv.payments)
        for inv in monthly_invoices
    )
    total_outstanding = total_invoiced - total_paid
    invoice_count = len(monthly_invoices)
    paid_count = sum(1 for inv in monthly_invoices if inv.status == 'paid')
    outstanding_count = sum(1 for inv in monthly_invoices if inv.status in ['sent', 'overdue', 'partially_paid'])

    # Luna anterioara si urmatoare
    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year

    if month == 12:
        next_month, next_year = 1, year + 1
    else:
        next_month, next_year = month + 1, year

    month_name = first_day.strftime('%B %Y')

    return render_template('accounting.html',
        invoices=monthly_invoices,
        total_invoiced=total_invoiced,
        total_paid=total_paid,
        total_outstanding=total_outstanding,
        invoice_count=invoice_count,
        paid_count=paid_count,
        outstanding_count=outstanding_count,
        month_name=month_name,
        prev_month=prev_month, prev_year=prev_year,
        next_month=next_month, next_year=next_year,
        year=year, month=month
    )

@main.route('/accounting/export')
@login_required
def accounting_export():
    from app.models import Invoice
    import csv
    import io
    import calendar

    year = int(request.args.get('year', datetime.utcnow().year))
    month = int(request.args.get('month', datetime.utcnow().month))

    first_day = datetime(year, month, 1)
    last_day = datetime(year, month, calendar.monthrange(year, month)[1], 23, 59, 59)

    invoices = Invoice.query.filter_by(user_id=current_user.id).filter(
        Invoice.issue_date >= first_day,
        Invoice.issue_date <= last_day,
        Invoice.status != 'cancelled'
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Invoice Number', 'Invoice Date', 'Due Date', 'Client',
                     'Description', 'Subtotal', 'VAT', 'Total', 'Amount Paid',
                     'Outstanding', 'Status', 'Payment Date'])

    for inv in invoices:
        total_paid = sum(float(p.amount) for p in inv.payments)
        outstanding = float(inv.total_amount) - total_paid
        payment_date = inv.paid_at.strftime('%d/%m/%Y') if inv.paid_at else ''

        writer.writerow([
            inv.invoice_number,
            inv.issue_date.strftime('%d/%m/%Y'),
            inv.due_date.strftime('%d/%m/%Y') if inv.due_date else '',
            inv.job.client_name,
            inv.job.description or inv.job.activity_type,
            f'{inv.subtotal:.2f}',
            f'{inv.vat_amount:.2f}',
            f'{inv.total_amount:.2f}',
            f'{total_paid:.2f}',
            f'{outstanding:.2f}',
            inv.status,
            payment_date
        ])

    output.seek(0)
    month_name = first_day.strftime('%B_%Y')
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=accounting_{month_name}.csv'}
    )

@main.route('/accounting/vat-report')
@login_required
def vat_report():
    from app.models import Invoice
    import calendar
    from babel.dates import format_date

    year = int(request.args.get('year', datetime.utcnow().year))
    first_day = datetime(year, 1, 1)
    last_day = datetime(year, 12, 31, 23, 59, 59)

    invoices = Invoice.query.filter_by(user_id=current_user.id).filter(
        Invoice.issue_date >= first_day,
        Invoice.issue_date <= last_day,
        Invoice.status != 'cancelled'
    ).all()

    locale = current_user.language if current_user.language == 'ro' else 'en'

    rows = []
    totals = {'count': 0, 'subtotal': 0.0, 'vat': 0.0, 'total': 0.0}
    for m in range(1, 13):
        mf = datetime(year, m, 1)
        ml = datetime(year, m, calendar.monthrange(year, m)[1], 23, 59, 59)
        mins = [i for i in invoices if mf <= i.issue_date <= ml]
        subtotal = sum(float(i.subtotal) for i in mins)
        vat = sum(float(i.vat_amount) for i in mins)
        total = sum(float(i.total_amount) for i in mins)
        rows.append({
            'month': m,
            'name': format_date(mf, 'MMMM', locale=locale),
            'count': len(mins),
            'subtotal': subtotal,
            'vat': vat,
            'total': total,
        })
        totals['count'] += len(mins)
        totals['subtotal'] += subtotal
        totals['vat'] += vat
        totals['total'] += total

    return render_template('vat_report.html',
        year=year, prev_year=year - 1, next_year=year + 1,
        rows=rows, totals=totals)

@main.route('/accounting/vat-report/export')
@login_required
def vat_report_export():
    from app.models import Invoice
    import calendar
    import csv
    import io

    year = int(request.args.get('year', datetime.utcnow().year))
    first_day = datetime(year, 1, 1)
    last_day = datetime(year, 12, 31, 23, 59, 59)

    invoices = Invoice.query.filter_by(user_id=current_user.id).filter(
        Invoice.issue_date >= first_day,
        Invoice.issue_date <= last_day,
        Invoice.status != 'cancelled'
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Month', 'Invoices', 'Subtotal', 'VAT', 'Total'])

    totals = [0, 0.0, 0.0, 0.0]
    for m in range(1, 13):
        mf = datetime(year, m, 1)
        ml = datetime(year, m, calendar.monthrange(year, m)[1], 23, 59, 59)
        mins = [i for i in invoices if mf <= i.issue_date <= ml]
        subtotal = sum(float(i.subtotal) for i in mins)
        vat = sum(float(i.vat_amount) for i in mins)
        total = sum(float(i.total_amount) for i in mins)
        writer.writerow([mf.strftime('%B'), len(mins), f'{subtotal:.2f}', f'{vat:.2f}', f'{total:.2f}'])
        totals[0] += len(mins)
        totals[1] += subtotal
        totals[2] += vat
        totals[3] += total

    writer.writerow(['TOTAL', totals[0], f'{totals[1]:.2f}', f'{totals[2]:.2f}', f'{totals[3]:.2f}'])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=vat_report_{year}.csv'}
    )

@main.route('/sw.js')
def service_worker():
    return send_from_directory(current_app.static_folder, 'sw.js', mimetype='application/javascript')

@main.route('/set-language', methods=['POST'])
@login_required
def set_language():
    lang = request.form.get('language')
    if lang in ('en', 'ro'):
        current_user.language = lang
        db.session.commit()
    next_url = request.args.get('next') or url_for('main.dashboard')
    if next_url.startswith('/'):
        return redirect(next_url)
    return redirect(url_for('main.dashboard'))

@main.route('/set-currency', methods=['POST'])
@login_required
def set_currency():
    currency = request.form.get('currency')
    if currency in ('GBP', 'RON', 'EUR', 'USD'):
        current_user.currency = currency
        db.session.commit()
    next_url = request.args.get('next') or url_for('main.dashboard')
    if next_url.startswith('/'):
        return redirect(next_url)
    return redirect(url_for('main.dashboard'))