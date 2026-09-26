from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, send_from_directory, Response, abort, jsonify, make_response
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.currency import convert_to_base
from app.limits import (consume, dashboard_state, is_pro, is_unmetered,
                        new_customer_block, reached)
from itsdangerous import URLSafeTimedSerializer
from app.models import User, Job, Invoice, Payment, TimeEntry, ACTIVITY_TYPES, EXPENSE_CATEGORIES
from app.ics import build_feed, jobs_in_window
from app.notifications import send_overdue_invoice_reminders
from datetime import datetime, timedelta
from urllib.parse import urlparse
from flask import current_app
from flask_babel import _ 
from threading import Thread
from app import db, format_money, csrf
from functools import wraps
from sqlalchemy import func
import os
import secrets

# How many tracked entries the free plan can see. Tracking itself is open to
# everyone; this only limits the history behind the report.
FREE_TIME_ENTRIES = 5

def trial_info(user):
    if user.plan == 'pro':
        return False, 0, None
    if not user.trial_ends_at:
        return False, 0, None
    remaining = (user.trial_ends_at - datetime.utcnow()).total_seconds()
    if remaining <= 0:
        return False, 0, user.trial_ends_at
    days = int(remaining // 86400) + 1
    return True, days, user.trial_ends_at

def can_add_jobs(user):
    # Pro and a live trial are both unmetered, so the caps only start applying
    # once the trial has lapsed and the account falls back to the free plan.
    if is_unmetered(user):
        return True
    return not reached(user, 'jobs')

def pro_required(view):
    """Gate a feature behind Pro. On the free plan, send the user to billing."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.plan == 'pro':
            return view(*args, **kwargs)
        flash(_('This is a Pro feature. Upgrade to unlock it.'))
        return redirect(url_for('main.business_settings'))
    return wrapped

auth = Blueprint('auth', __name__)
main = Blueprint('main', __name__)

# ─── AUTH ───────────────────────────────────────────

@auth.route('/register', methods=['GET', 'POST'])
def register():
    import os
    if os.getenv('SIGNUP_OPEN', '1').strip().lower() in ('0', 'false', 'no'):
        flash(_('New registrations are currently disabled.'))
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if User.query.filter_by(email=email).first():
            flash(_('Email already used.'))
            return redirect(url_for('auth.register'))

        from datetime import timedelta
        user = User(
            username=username,
            email=email,
            password=generate_password_hash(password),
            plan='trial',
            trial_ends_at=datetime.utcnow() + timedelta(days=14)
        )
        detected = request.cookies.get('ts_currency')
        if detected in ('GBP', 'USD', 'RON', 'EUR'):
            user.currency = detected
        db.session.add(user)
        db.session.commit()
        from app.email_service import send_welcome
        try:
            send_welcome(email)
        except Exception:
            pass

        if request.args.get('upgrade') == '1':
            login_user(user)
            return redirect(url_for('main.billing_checkout'))

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
def dashboard():
    from datetime import timedelta
    if not current_user.is_authenticated:
        return render_template('landing.html')

    from app.notifications import send_overdue_invoice_reminders, send_trial_expiry_reminders
    send_overdue_invoice_reminders(current_app._get_current_object())
    send_trial_expiry_reminders(current_app._get_current_object())

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

    trial_active, trial_days, trial_end = trial_info(current_user)

    # ── Money you're owed (real invoices, no mock data) ──
    from app.models import Invoice
    unpaid_invoices = Invoice.query.filter_by(user_id=current_user.id).filter(
        Invoice.status.notin_(['paid', 'cancelled'])
    ).all()
    today = datetime.utcnow().date()
    money = {'total': 0.0, 'overdue': 0.0, 'due_soon': 0.0, 'upcoming': 0.0}
    counts = {'overdue': 0, 'due_soon': 0, 'upcoming': 0}
    money_rows = []
    bucket_order = {'overdue': 0, 'due_soon': 1, 'upcoming': 2}
    for inv in unpaid_invoices:
        paid = sum(float(p.amount) for p in inv.payments)
        outstanding = float(inv.total_amount) - paid
        if outstanding <= 0:
            continue
        due = inv.due_date.date() if inv.due_date else None
        days = (due - today).days if due else None
        if due is not None and due < today:
            bucket = 'overdue'
        elif due is not None and days <= 7:
            bucket = 'due_soon'
        else:
            bucket = 'upcoming'
        money[bucket] += outstanding
        money['total'] += outstanding
        counts[bucket] += 1
        money_rows.append({
            'invoice': inv,
            'outstanding': outstanding,
            'due_date': inv.due_date,
            'days': days,
            'bucket': bucket,
        })
    money_rows.sort(key=lambda r: (bucket_order[r['bucket']], r['days'] is None, r['days'] or 0))
    money_counts = counts

    # Timer state and tracked totals for the job cards. One aggregate query
    # rather than a lookup per job.
    running_entry = TimeEntry.running_for(current_user.id)
    tracked = {}
    if jobs:
        rows = (db.session.query(TimeEntry.job_id,
                                 func.coalesce(func.sum(TimeEntry.minutes), 0))
                .filter(TimeEntry.user_id == current_user.id,
                        TimeEntry.job_id.in_([j.id for j in jobs]))
                .group_by(TimeEntry.job_id).all())
        tracked = {row[0]: int(row[1] or 0) for row in rows}

    return render_template('dashboard.html',
                           jobs=jobs,
                           activity_types=ACTIVITY_TYPES,
                           filter_type=filter_type,
                           filter_status=filter_status,
                           weekly_total=weekly_total,
                           monthly_total=monthly_total,
                           billing_configured=bool(os.getenv('STRIPE_API_KEY') and os.getenv('STRIPE_PRO_PRICE_ID')),
                           trial_active=trial_active,
                           trial_days=trial_days,
                           limits=dashboard_state(current_user),
                           money=money,
                           money_counts=money_counts,
                           money_rows=money_rows,
                           running_entry=running_entry,
                           tracked=tracked)


@main.route('/job/add', methods=['GET', 'POST'])
@login_required
def add_job():
    if not can_add_jobs(current_user):
        flash(_('You have reached the free plan limit. Subscribe to add new jobs.'))
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        blocked = new_customer_block(current_user, request.form.get('client_name'))
        if blocked:
            flash(blocked)
            return redirect(url_for('main.add_job'))
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
            duration_minutes=_parse_duration(request.form.get('duration_minutes')),
            user_id=current_user.id
        )
        db.session.add(job)
        db.session.commit()
        flash(_('Job added!'))
        return redirect(url_for('main.dashboard'))

    return render_template('add_job.html', activity_types=ACTIVITY_TYPES)


def _parse_duration(raw):
    """Minutes from a form field, falling back to a sane default."""
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        return 60
    if minutes <= 0 or minutes > 24 * 60:
        return 60
    return minutes


@main.route('/time')
@login_required
def time_tracking():
    """Tracked time: a live timer, recent entries and per-job totals.

    The free plan can track time but only sees its five most recent entries;
    the totals and the calendar feed are Pro.
    """
    running = TimeEntry.running_for(current_user.id)
    pro = is_pro(current_user)

    recent_q = (TimeEntry.query.filter_by(user_id=current_user.id)
                .order_by(TimeEntry.created_at.desc()))
    if pro:
        recent = recent_q.all()
        visible = recent
        hidden = 0
        total_entries = len(recent)
    else:
        # Only fetch the rows we are going to show: a long history must not
        # turn the free page into a full-table read.
        visible = recent_q.limit(FREE_TIME_ENTRIES).all()
        total_entries = recent_q.count()
        hidden = max(0, total_entries - len(visible))

    jobs = Job.query.filter_by(user_id=current_user.id).order_by(Job.date).all()

    # Totals only mean something with the whole history behind them, so they
    # are part of Pro rather than a teaser.
    totals_by_job = []
    weekly_minutes = 0
    if pro:
        per_job = {}
        for entry in recent:
            job = entry.job
            if job is None:
                continue
            row = per_job.setdefault(job.id, {'job': job, 'minutes': 0})
            row['minutes'] += entry.duration_minutes
        totals_by_job = sorted(per_job.values(),
                               key=lambda r: r['minutes'], reverse=True)
        week_start = datetime.utcnow() - timedelta(days=7)
        weekly_minutes = sum(e.duration_minutes for e in recent
                             if e.created_at and e.created_at >= week_start)

    return render_template('time.html',
                           running=running,
                           entries=visible,
                           hidden=hidden,
                           total_entries=total_entries,
                           jobs=jobs,
                           totals_by_job=totals_by_job,
                           weekly_minutes=weekly_minutes,
                           free_limit=FREE_TIME_ENTRIES,
                           pro=pro)


def _owned_job(job_id):
    job = Job.query.get(job_id)
    if job is None or job.user_id != current_user.id:
        return None
    return job


def _back(default_endpoint):
    """Return to the page a form was submitted from, but stay on this site.

    The Referer header is supplied by the caller, so a cross-origin value would
    turn these redirects into a way to bounce people off to another site.
    """
    target = request.referrer or ''
    if target:
        parsed = urlparse(target)
        if not parsed.netloc or parsed.netloc == request.host:
            return redirect(target)
    return redirect(url_for(default_endpoint))


@main.route('/time/start/<int:job_id>', methods=['POST'])
@login_required
def start_timer(job_id):
    job = _owned_job(job_id)
    if job is None:
        flash(_('You do not have permission.'))
        return redirect(url_for('main.dashboard'))

    running = TimeEntry.running_for(current_user.id)
    if running is not None:
        # One timer at a time. A second start would orphan the first as an
        # entry that never ends, so make them stop it first.
        if running.job_id == job.id:
            flash(_('The timer is already running for this job.'))
        else:
            flash(_('Stop the timer on the other job before starting a new one.'))
        return redirect(url_for('main.time_tracking'))

    db.session.add(TimeEntry(user_id=current_user.id, job_id=job.id,
                             started_at=datetime.utcnow()))
    db.session.commit()
    flash(_('Timer started.'))
    return _back('main.time_tracking')


@main.route('/time/stop', methods=['POST'])
@login_required
def stop_timer():
    running = TimeEntry.running_for(current_user.id)
    if running is None:
        flash(_('No timer is running.'))
        return redirect(url_for('main.time_tracking'))

    running.ended_at = datetime.utcnow()
    minutes = int((running.ended_at - running.started_at).total_seconds() // 60)
    # Rounding a few seconds up to a minute beats reporting zero for a task
    # someone really did.
    running.minutes = max(1, minutes)
    note = (request.form.get('note') or '').strip()
    if note:
        running.note = note
    db.session.commit()

    hours = running.minutes // 60
    rest = running.minutes % 60
    length = ('%dh %02dm' % (hours, rest)) if hours else ('%d min' % running.minutes)
    flash(_('Logged %(length)s on this job.', length=length))
    return _back('main.time_tracking')


@main.route('/time/manual', methods=['POST'])
@login_required
def add_time_manual():
    job = _owned_job(request.form.get('job_id', type=int))
    if job is None:
        flash(_('You do not have permission.'))
        return redirect(url_for('main.time_tracking'))

    hours = request.form.get('hours', type=float) or 0
    minutes = request.form.get('minutes', type=int) or 0
    total = int(round(hours * 60)) + minutes
    if total <= 0:
        flash(_('Enter how much time you spent.'))
        return redirect(url_for('main.time_tracking'))
    if total > 24 * 60:
        flash(_('That is more than a day. Check the hours.'))
        return redirect(url_for('main.time_tracking'))

    db.session.add(TimeEntry(user_id=current_user.id, job_id=job.id,
                             minutes=total,
                             note=(request.form.get('note') or '').strip() or None))
    db.session.commit()
    flash(_('Time added.'))
    return redirect(url_for('main.time_tracking'))


@main.route('/time/delete/<int:entry_id>', methods=['POST'])
@login_required
def delete_time_entry(entry_id):
    entry = TimeEntry.query.get(entry_id)
    if entry is None or entry.user_id != current_user.id:
        flash(_('You do not have permission.'))
        return redirect(url_for('main.time_tracking'))
    db.session.delete(entry)
    db.session.commit()
    flash(_('Entry removed.'))
    return redirect(url_for('main.time_tracking'))


def _calendar_owner(token):
    """The Pro user a calendar token belongs to, if it is still valid.

    Checking the plan here means a subscription stops working on its own if
    someone downgrades, without waiting for a token to expire.
    """
    if not token:
        return None
    user = User.query.filter_by(calendar_token=token).first()
    if user is None or not is_pro(user):
        return None
    return user


@main.route('/calendar/<token>.ics')
def calendar_feed(token):
    user = _calendar_owner(token)
    if user is None:
        return ('Not found', 404, {'Content-Type': 'text/plain; charset=utf-8'})

    jobs = (Job.query.filter_by(user_id=user.id)
            .order_by(Job.date).all())
    name = 'TradeScheduler Jobs'
    business = user.business
    if business:
        label = business.trading_name or business.legal_name
        if label:
            name = '%s Jobs' % label

    feed = build_feed(jobs_in_window(jobs), name)
    response = make_response(feed)
    response.headers['Content-Type'] = 'text/calendar; charset=utf-8'
    # No caching: the point of the feed is that a rescheduled job shows up.
    response.headers['Cache-Control'] = 'no-cache, max-age=0'
    return response


@main.route('/calendar/link', methods=['POST'])
@login_required
@pro_required
def create_calendar_link():
    if not current_user.calendar_token:
        current_user.calendar_token = secrets.token_urlsafe(24)
        db.session.commit()
    flash(_('Calendar link ready.'))
    return _back('main.business_settings')


@main.route('/calendar/link/reset', methods=['POST'])
@login_required
@pro_required
def reset_calendar_link():
    current_user.calendar_token = secrets.token_urlsafe(24)
    db.session.commit()
    flash(_('New calendar link created. The old one no longer works.'))
    return redirect(url_for('main.business_settings'))


# POST, not GET: a destructive action reachable by GET can be fired from any
# <img src> or link on any page, with the victim's session attached and no
# token to forge.
@main.route('/job/done/<int:job_id>', methods=['POST'])
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


@main.route('/job/delete/<int:job_id>', methods=['POST'])
@login_required
def delete_job(job_id):
    job = Job.query.get_or_404(job_id)
    if job.user_id != current_user.id:
        flash(_('You do not have permission to delete this job.'))
        return redirect(url_for('main.dashboard'))
    if Invoice.query.filter_by(job_id=job.id).first():
        flash(_('This job has an invoice and cannot be deleted.'))
        return redirect(url_for('main.dashboard'))
    tracked = len(job.time_entries)
    db.session.delete(job)
    db.session.commit()
    if tracked:
        flash(_('Job deleted, along with %(count)d time entries.',
               count=tracked))
    else:
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
    buffer = generate_invoice(job, current_user, invoice=invoice)
    pdf_bytes = buffer.getvalue()

    if job.client_email:
        try:
            from app.email_service import send_email_with_attachment
            pay_url = business.payment_link_url if business else ''
            if current_user.language == 'ro':
                subject = f'Factura {invoice.invoice_number}'
                body = f"""Bună ziua {job.client_name},

Găsiți atașată factura pentru lucrările finalizate pe {job.date.strftime('%d/%m/%Y')}.

Număr factură: {invoice.invoice_number}
Suma de plată: {format_money(invoice.total_amount, job.currency)}
Scadența: {invoice.due_date.strftime('%d/%m/%Y') if invoice.due_date else '—'}""" + (f"""
Plătește online: {pay_url}""" if pay_url else "") + f"""

Vă mulțumim pentru colaborare!
{business.trading_name or business.legal_name if business else current_user.username}"""
            else:
                subject = f'Invoice {invoice.invoice_number}'
                body = f"""Dear {job.client_name},

Please find attached your invoice for the work completed on {job.date.strftime('%d/%m/%Y')}.

Invoice Number: {invoice.invoice_number}
Amount Due: {format_money(invoice.total_amount, job.currency)}
Due Date: {invoice.due_date.strftime('%d/%m/%Y') if invoice.due_date else '—'}""" + (f"""
Pay online: {pay_url}""" if pay_url else "") + f"""

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

@main.route('/invoices/<int:invoice_id>/view')
@login_required
def view_invoice(invoice_id):
    from app.models import Invoice, Job, BusinessProfile
    invoice = Invoice.query.get_or_404(invoice_id)
    if invoice.user_id != current_user.id:
        flash(_('You do not have permission.'))
        return redirect(url_for('main.invoices'))
    job = invoice.job if invoice.job else Job.query.get(invoice.job_id)
    from app.invoice import generate_invoice
    pdf_bytes = generate_invoice(job, current_user, invoice=invoice).getvalue()
    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={
            'Content-Disposition': f'inline; filename={invoice.invoice_number}.pdf',
            'Content-Type': 'application/pdf'
        }
    )

@main.route('/invoices/<int:invoice_id>/download')
@login_required
def download_invoice_pdf(invoice_id):
    from app.models import Invoice, Job
    invoice = Invoice.query.get_or_404(invoice_id)
    if invoice.user_id != current_user.id:
        flash(_('You do not have permission.'))
        return redirect(url_for('main.invoices'))
    job = invoice.job if invoice.job else Job.query.get(invoice.job_id)
    from app.invoice import generate_invoice
    pdf_bytes = generate_invoice(job, current_user, invoice=invoice).getvalue()
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


@main.route('/quote/ai-generate/<int:job_id>', methods=['POST'])
@login_required
def ai_generate_quote(job_id):
    from app.ai_service import generate_quote, AIServiceError, ai_configured
    job = Job.query.get_or_404(job_id)
    if job.user_id != current_user.id:
        return jsonify({'error': _('You do not have permission.')}), 403
    description = request.form.get('description', '')
    if not ai_configured():
        return jsonify({'error': _('AI is not configured. Set the AI_API_KEY environment variable.')}), 400
    blocked = consume(current_user, 'ai_quote')
    if blocked:
        return jsonify({'error': blocked, 'upgrade': True}), 402
    try:
        result = generate_quote(current_user, description)
        return jsonify({'ok': True, 'data': result})
    except AIServiceError as e:
        return jsonify({'error': str(e)}), 400
    except Exception:
        return jsonify({'error': _('Could not generate the quote. Please try again.')}), 400

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
        business.payment_link_url = request.form.get('payment_link_url')

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

    if request.args.get('billing') == 'success':
        flash(_('Your Pro plan is now active. Welcome!'))

    return render_template('business_settings.html', business=business,
                           calendar_token=current_user.calendar_token,
                           pro=is_pro(current_user),
                           billing_configured=bool(os.getenv('STRIPE_API_KEY') and os.getenv('STRIPE_PRO_PRICE_ID')),
                           trial_active=trial_info(current_user)[0],
                           trial_days=trial_info(current_user)[1])

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
    from app.models import Invoice, BusinessProfile
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

    business = BusinessProfile.query.filter_by(user_id=current_user.id).first()
    pay_url = business.payment_link_url if business else ''
    
    return render_template('invoices.html', invoices=all_invoices, pay_url=pay_url)

@main.route('/stripe/webhook', methods=['POST'])
@csrf.exempt
def stripe_webhook():
    import os
    import stripe
    from app.models import Invoice, Payment
    payload = request.get_data()
    sig = request.headers.get('Stripe-Signature')
    secret = os.getenv('STRIPE_WEBHOOK_SECRET')
    if not secret:
        return Response('Webhook secret not configured', status=400)
    try:
        stripe.api_key = os.getenv('STRIPE_API_KEY')
        event = stripe.Webhook.construct_event(payload, sig, secret)
    except Exception as e:
        print(f">>> Stripe webhook signature error: {e}")
        return Response('Invalid signature', status=400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        if hasattr(session, 'to_dict'):
            session = session.to_dict()
        inv_no = (session.get('metadata') or {}).get('invoice_number')
        if inv_no:
            invoice = Invoice.query.filter_by(invoice_number=inv_no).first()
            if invoice and invoice.status not in ('paid', 'cancelled'):
                payment = Payment(
                    invoice_id=invoice.id,
                    amount=invoice.total_amount,
                    payment_method='card',
                    reference=f'Stripe {session.get("id", "")}',
                )
                db.session.add(payment)
                invoice.status = 'paid'
                invoice.paid_at = datetime.utcnow()
                db.session.commit()
                print(f">>> Stripe payment recorded for {inv_no}")
        else:
            uid = (session.get('metadata') or {}).get('user_id') or session.get('client_reference_id')
            sub_id = session.get('subscription')
            user = None
            if uid:
                user = User.query.get(int(uid))
            if user:
                user.plan = 'pro'
                if sub_id:
                    user.stripe_subscription_id = sub_id
                user.stripe_subscription_status = 'active'
                db.session.commit()
                print(f">>> User {user.username} upgraded to Pro (sub {sub_id})")
    elif event['type'] in ('customer.subscription.deleted', 'customer.subscription.updated'):
        sub = event['data']['object']
        if hasattr(sub, 'to_dict'):
            sub = sub.to_dict()
        status = sub.get('status')
        sub_id = sub.get('id')
        user = User.query.filter_by(stripe_subscription_id=sub_id).first()
        if user:
            user.stripe_subscription_status = status
            if status in ('canceled', 'unpaid', 'incomplete_expired'):
                user.plan = 'free'
            elif status == 'active':
                user.plan = 'pro'
            db.session.commit()
            print(f">>> User {user.username} subscription status -> {status}")
    return Response('ok', status=200)

@main.route('/visitor-currency', methods=['POST'])
def visitor_currency():
    currency = request.form.get('currency')
    if currency not in ('GBP', 'USD', 'RON', 'EUR'):
        currency = 'GBP'
    resp = make_response(redirect(request.form.get('next') or url_for('main.dashboard')))
    resp.set_cookie('ts_currency', currency, max_age=60 * 60 * 24 * 365, samesite='Lax')
    return resp

@main.route('/billing/checkout', methods=['GET', 'POST'])
@login_required
def billing_checkout():
    import os
    import stripe
    if not os.getenv('STRIPE_API_KEY') or not os.getenv('STRIPE_PRO_PRICE_ID'):
        flash(_('Billing is not configured yet.'))
        return redirect(url_for('main.business_settings'))
    stripe.api_key = os.getenv('STRIPE_API_KEY')
    currency = (request.args.get('currency') or current_user.currency or 'GBP').upper()
    price_env = {'GBP': 'STRIPE_PRO_PRICE_ID', 'USD': 'STRIPE_PRO_PRICE_ID_USD', 'RON': 'STRIPE_PRO_PRICE_ID_RON'}
    price_id = os.getenv(price_env.get(currency, '')) or os.getenv('STRIPE_PRO_PRICE_ID')
    if not current_user.stripe_customer_id:
        customer = stripe.Customer.create(
            email=current_user.email,
            name=current_user.username,
        )
        current_user.stripe_customer_id = customer.id
        db.session.commit()
    try:
        session_kwargs = {}
        trial_active, trial_days, _ = trial_info(current_user)
        if trial_active:
            session_kwargs['subscription_data'] = {'trial_period_days': max(int(trial_days), 1)}
        session = stripe.checkout.Session.create(
            customer=current_user.stripe_customer_id,
            mode='subscription',
            line_items=[{'price': price_id, 'quantity': 1}],
            metadata={'user_id': current_user.id, 'plan': 'pro'},
            client_reference_id=str(current_user.id),
            success_url=url_for('main.business_settings', _external=True) + '?billing=success&session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('main.business_settings', _external=True),
            **session_kwargs,
        )
    except Exception as e:
        print(f">>>> Billing checkout error: {e}")
        flash(_('Could not start checkout.'))
        return redirect(url_for('main.business_settings'))
    return redirect(session.url, code=303)

@main.route('/billing/portal', methods=['POST'])
@login_required
def billing_portal():
    import os
    import stripe
    if not os.getenv('STRIPE_API_KEY') or not current_user.stripe_customer_id:
        flash(_('Billing is not configured yet.'))
        return redirect(url_for('main.business_settings'))
    stripe.api_key = os.getenv('STRIPE_API_KEY')
    try:
        session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=url_for('main.business_settings', _external=True),
        )
    except Exception as e:
        print(f">>>> Billing portal error: {e}")
        flash(_('Could not open billing portal.'))
        return redirect(url_for('main.business_settings'))
    return redirect(session.url, code=303)

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
    return redirect(request.form.get('next') or url_for('main.invoices'))

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

@main.route('/invoice/<int:invoice_id>/send-reminder', methods=['POST'])
@login_required
def send_invoice_reminder(invoice_id):
    from app.models import BusinessProfile
    from app.email_service import send_email
    invoice = Invoice.query.get_or_404(invoice_id)
    if invoice.user_id != current_user.id:
        flash(_('You do not have permission.'))
        return redirect(url_for('main.dashboard'))
    job = invoice.job
    if not job or not job.client_email:
        flash(_('This invoice has no client email.'))
        return redirect(url_for('main.dashboard'))
    if invoice.status in ('paid', 'cancelled'):
        flash(_('This invoice does not need a reminder.'))
        return redirect(url_for('main.dashboard'))
    business = BusinessProfile.query.filter_by(user_id=current_user.id).first()
    amount = format_money(invoice.total_amount, current_user.currency)
    due = invoice.due_date.strftime('%d/%m/%Y') if invoice.due_date else '—'
    if current_user.language == 'ro':
        subject = f'Reminder: factură scadentă {invoice.invoice_number}'
        body = f"""Bună ziua {job.client_name},

Vă anunțăm că factura {invoice.invoice_number}, în valoare de {amount}, are scadența pe {due}.

Vă rugăm să efectuați plata cât mai curând posibil.

Vă mulțumim!
{business.trading_name or business.legal_name if business else current_user.username}"""
    else:
        subject = f'Reminder: invoice {invoice.invoice_number}'
        body = f"""Hi {job.client_name},

This is a reminder that invoice {invoice.invoice_number} for {amount} is due on {due}.

Please make your payment as soon as possible.

Thank you!
{business.trading_name or business.legal_name if business else current_user.username}"""
    ok = send_email(job.client_email, subject, body)
    if ok:
        invoice.reminder_sent = True
        db.session.commit()
        flash(_('Reminder sent to %(client)s.', client=job.client_name))
    else:
        flash(_('Could not send the reminder. Please try again.'))
    return redirect(request.form.get('next') or url_for('main.dashboard'))

@main.route('/ai/job', methods=['GET', 'POST'])
@login_required
def ai_job():
    from app.ai_service import extract_job_from_message, ai_configured, AIServiceError
    from sqlalchemy import func
    if request.method == 'GET':
        return render_template('ai_job.html', ai_available=ai_configured())
    message = (request.form.get('message') or '').strip()
    if not message:
        flash(_('Paste the client message first.'))
        return redirect(url_for('main.ai_job'))
    if not ai_configured():
        flash(_('AI is not configured. Set the AI_API_KEY environment variable.'))
        return redirect(url_for('main.ai_job'))
    blocked = consume(current_user, 'ai_message')
    if blocked:
        flash(blocked)
        return redirect(url_for('main.ai_job'))
    try:
        res = extract_job_from_message(current_user, message)
    except AIServiceError as e:
        flash(str(e))
        return redirect(url_for('main.ai_job'))
    except Exception:
        flash(_('Could not read the message. Please try again.'))
        return redirect(url_for('main.ai_job'))
    if not isinstance(res, dict):
        res = {'customer_name': None, 'customer_email': None, 'address': None,
               'date': None, 'time': None, 'description': message[:500],
               'activity_type': 'other', 'uncertain_fields': ['customer_name', 'address', 'date'],
               'notes': None}
    client = (res.get('customer_name') or '').strip()
    match = None
    if client:
        existing = Job.query.filter(
            func.lower(Job.client_name) == client.lower(),
            Job.user_id == current_user.id
        ).first()
        if existing:
            match = existing.client_name
    return render_template('ai_review.html', data=res, match=match, message=message[:2000],
                           activity_types=ACTIVITY_TYPES)

@main.route('/ai/job/confirm', methods=['POST'])
@login_required
def ai_job_confirm():
    if not can_add_jobs(current_user):
        flash(_('You have reached the free plan limit. Subscribe to create jobs.'))
        return redirect(url_for('main.dashboard'))
    client = (request.form.get('client_name') or '').strip()
    address = (request.form.get('address') or '').strip()
    if not client or not address:
        flash(_('Client name and address are required.'))
        return redirect(url_for('main.ai_job'))
    blocked = new_customer_block(current_user, client)
    if blocked:
        flash(blocked)
        return redirect(url_for('main.ai_job'))
    date_str = request.form.get('date') or ''
    try:
        job_date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
    except (ValueError, TypeError):
        try:
            job_date = datetime.strptime(date_str, '%Y-%m-%d')
        except (ValueError, TypeError):
            flash(_('Please pick a date and time for the job.'))
            return redirect(url_for('main.ai_job'))
    activity = request.form.get('activity_type') or 'other'
    if activity not in dict(ACTIVITY_TYPES):
        activity = 'other'
    currency = current_user.currency or 'GBP'
    job = Job(
        client_name=client,
        client_email=(request.form.get('client_email') or '').strip() or None,
        address=address,
        date=job_date,
        description=(request.form.get('description') or '').strip() or None,
        activity_type=activity,
        price=float(convert_to_base(request.form.get('price') or 0, currency)),
        currency=currency,
        user_id=current_user.id,
    )
    db.session.add(job)
    db.session.commit()
    flash(_('Job created from the message!'))
    return redirect(url_for('main.dashboard'))

@main.route('/tools')
@login_required
def tools():
    from datetime import timedelta as _td
    from app.models import Job
    since = datetime.utcnow() - _td(days=365)
    invoices_12m = Invoice.query.filter_by(user_id=current_user.id).filter(
        Invoice.status != 'cancelled', Invoice.issue_date >= since
    ).all()
    invoiced_12m = sum(float(i.total_amount) for i in invoices_12m)
    jobs_12m = len(invoices_12m)
    return render_template('tools.html', invoiced_12m=invoiced_12m, jobs_12m=jobs_12m)

@main.route('/expenses', methods=['GET', 'POST'])
@login_required
def expenses():
    from app.models import Expense
    from datetime import date
    import calendar as cal
    if request.method == 'POST':
        merchant = (request.form.get('merchant') or '').strip() or None
        description = (request.form.get('description') or '').strip() or None
        date_str = request.form.get('date') or date.today().isoformat()
        try:
            d = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            d = date.today()
        try:
            total = float(request.form.get('total') or 0)
        except (ValueError, TypeError):
            total = 0
        vat_raw = (request.form.get('vat_amount') or '').strip()
        vat_val = None
        if vat_raw:
            try:
                vat_val = float(vat_raw)
            except ValueError:
                vat_val = None
        category = request.form.get('category') or 'Other'
        if category not in EXPENSE_CATEGORIES:
            category = 'Other'
        currency = request.form.get('currency') or 'GBP'
        if currency not in ('GBP', 'RON', 'EUR', 'USD'):
            currency = 'GBP'
        receipt_image = (request.form.get('receipt_image') or '').strip() or None
        exp = Expense(user_id=current_user.id, merchant=merchant, description=description,
                      date=d, total=total, vat_amount=vat_val, currency=currency,
                      category=category, receipt_image=receipt_image)
        db.session.add(exp)
        db.session.commit()
        flash(_('Expense saved!'))
        return redirect(url_for('main.expenses'))

    now = datetime.utcnow()
    year = int(request.args.get('year', now.year))
    month = int(request.args.get('month', now.month))
    first_day = date(year, month, 1)
    last_day = date(year, month, cal.monthrange(year, month)[1])
    items = (Expense.query.filter_by(user_id=current_user.id)
             .filter(Expense.date >= first_day, Expense.date <= last_day)
             .order_by(Expense.date.desc()).all())
    total_amount = sum(float(e.total) for e in items)
    month_name = first_day.strftime('%B %Y')
    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year
    if month == 12:
        next_month, next_year = 1, year + 1
    else:
        next_month, next_year = month + 1, year
    return render_template('expenses.html',
                           expenses=items, total_amount=total_amount, month_name=month_name,
                           prev_month=prev_month, prev_year=prev_year,
                           next_month=next_month, next_year=next_year,
                           year=year, month=month, categories=EXPENSE_CATEGORIES,
                           now_str=date.today().isoformat())

@main.route('/expenses/<int:expense_id>/delete', methods=['POST'])
@login_required
def delete_expense(expense_id):
    from app.models import Expense
    e = Expense.query.get_or_404(expense_id)
    if e.user_id != current_user.id:
        flash(_('You do not have permission.'))
        return redirect(url_for('main.expenses'))
    if e.receipt_image:
        try:
            full = os.path.join(current_app.instance_path, 'uploads', e.receipt_image)
            if os.path.exists(full):
                os.remove(full)
        except Exception:
            pass
    db.session.delete(e)
    db.session.commit()
    flash(_('Expense deleted.'))
    return redirect(url_for('main.expenses'))

@main.route('/expenses/<int:expense_id>/receipt')
@login_required
def expense_receipt(expense_id):
    from app.models import Expense
    e = Expense.query.get_or_404(expense_id)
    if e.user_id != current_user.id:
        abort(404)
    if not e.receipt_image:
        abort(404)
    return send_from_directory(os.path.join(current_app.instance_path, 'uploads'), e.receipt_image)

@main.route('/expenses/uploads/<path:path>')
@login_required
def expense_receipt_upload(path):
    import posixpath
    safe = path.replace('\\', '/')
    if not safe.startswith('receipts/%d/' % current_user.id):
        abort(404)
    if '..' in safe.split('/'):
        abort(404)
    uploads = os.path.join(current_app.instance_path, 'uploads')
    target = os.path.abspath(os.path.join(uploads, safe))
    if not target.startswith(os.path.abspath(uploads) + os.sep):
        abort(404)
    if not os.path.exists(target):
        abort(404)
    return send_from_directory(uploads, safe)

@main.route('/expenses/scan', methods=['GET', 'POST'])
@login_required
def expense_scan():
    from app.ai_service import ai_configured, extract_receipt, AIServiceError
    import uuid
    if request.method == 'GET':
        return render_template('expense_scan.html', ai_available=ai_configured())
    file = request.files.get('receipt')
    if not file or not file.filename:
        flash(_('Please choose a receipt photo.'))
        return redirect(url_for('main.expense_scan'))
    mime = file.mimetype or 'image/jpeg'
    if mime not in ('image/jpeg', 'image/png', 'image/webp'):
        flash(_('Only JPEG, PNG or WEBP photos are supported.'))
        return redirect(url_for('main.expense_scan'))
    data = file.read()
    if len(data) > 8 * 1024 * 1024:
        flash(_('Photo too large — max 8MB.'))
        return redirect(url_for('main.expense_scan'))
    ext = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}[mime]
    rel = 'receipts/%d/%s.%s' % (current_user.id, uuid.uuid4().hex, ext)
    full = os.path.join(current_app.instance_path, 'uploads', rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'wb') as fh:
        fh.write(data)
    extracted = None
    scan_error = None
    if ai_configured():
        # The photo is already stored, so a free user who has run out of scans
        # still gets the manual form instead of a dead end.
        blocked = consume(current_user, 'ai_receipt')
        if blocked:
            scan_error = blocked
        else:
            try:
                extracted = extract_receipt(current_user, data, mime)
            except AIServiceError as e:
                scan_error = str(e)
            except Exception:
                scan_error = _('Could not scan the receipt. Please enter the details manually.')
    return render_template('expense_review.html', receipt_image=rel, extracted=extracted,
                           scan_error=scan_error, ai_available=ai_configured(),
                           categories=EXPENSE_CATEGORIES,
                           today=datetime.utcnow().date())


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

    # Cheltuieli din luna (Expense)
    from app.models import Expense
    month_expenses = sum(
        float(e.total)
        for e in Expense.query.filter_by(user_id=current_user.id).filter(
            Expense.date >= first_day.date(), Expense.date <= last_day.date()
        ).all()
    )
    net_total = total_invoiced - month_expenses

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
        year=year, month=month,
        month_expenses=month_expenses, net_total=net_total
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
@pro_required
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
    if currency in ('GBP', 'RON', 'EUR', 'USD', 'AUD'):
        current_user.currency = currency
        db.session.commit()
    next_url = request.args.get('next') or url_for('main.dashboard')
    if next_url.startswith('/'):
        return redirect(next_url)
    return redirect(url_for('main.dashboard'))