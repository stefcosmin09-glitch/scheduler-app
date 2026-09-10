from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, Response
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from itsdangerous import URLSafeTimedSerializer
from app.models import User, Job, ACTIVITY_TYPES
from app.notifications import schedule_reminder
from datetime import datetime
from flask import current_app
from threading import Thread

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
            flash('Email deja folosit.')
            return redirect(url_for('auth.register'))

        user = User(
            username=username,
            email=email,
            password=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        flash('Cont creat cu succes!')
        return redirect(url_for('auth.login'))

    return render_template('register.html')


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password, password):
            flash('Email sau parolă greșită.')
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
            body = f"""Hi {user.username},

Click the link below to reset your password. The link expires in 1 hour.

{reset_url}

If you didn't request this, ignore this email."""
            app = current_app._get_current_object()
            def send_reset(app, to, body):
                with app.app_context():
                    from app.email_service import send_email
                    send_email(to, 'Reset your password - Scheduler App', body)
            Thread(target=send_reset, args=(app, email, body)).start()
        flash('If that email exists, you will receive a reset link shortly.')
        return redirect(url_for('auth.login'))

    return render_template('forgot_password.html')


@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        s = get_serializer()
        email = s.loads(token, salt='password-reset', max_age=3600)
    except Exception:
        flash('Link invalid sau expirat.')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user:
            user.password = generate_password_hash(password)
            db.session.commit()
            flash('Parola schimbată cu succes!')
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
        job = Job(
            client_name=request.form.get('client_name'),
            client_email=request.form.get('client_email'),
            address=request.form.get('address'),
            date=datetime.strptime(request.form.get('date'), '%Y-%m-%dT%H:%M'),
            description=request.form.get('description'),
            activity_type=request.form.get('activity_type', 'altele'),
            price=float(request.form.get('price') or 0),
            user_id=current_user.id
        )
        db.session.add(job)
        db.session.commit()
        schedule_reminder(current_app._get_current_object(), job)
        flash('Job adăugat!')
        return redirect(url_for('main.dashboard'))

    return render_template('add_job.html', activity_types=ACTIVITY_TYPES)


@main.route('/job/done/<int:job_id>')
@login_required
def mark_done(job_id):
    job = Job.query.get_or_404(job_id)
    if job.user_id != current_user.id:
        flash('Nu ai permisiunea.')
        return redirect(url_for('main.dashboard'))
    job.status = 'done'
    db.session.commit()
    flash('Job marcat ca finalizat!')
    return redirect(url_for('main.dashboard'))


@main.route('/job/delete/<int:job_id>')
@login_required
def delete_job(job_id):
    job = Job.query.get_or_404(job_id)
    if job.user_id != current_user.id:
        flash('Nu ai permisiunea să ștergi acest job.')
        return redirect(url_for('main.dashboard'))
    db.session.delete(job)
    db.session.commit()
    flash('Job șters.')
    return redirect(url_for('main.dashboard'))


@main.route('/job/invoice/<int:job_id>')
@login_required
def download_invoice(job_id):
    job = Job.query.get_or_404(job_id)
    if job.user_id != current_user.id:
        flash('Nu ai permisiunea.')
        return redirect(url_for('main.dashboard'))

    from app.invoice import generate_invoice
    buffer = generate_invoice(job, current_user)

    if job.client_email:
        try:
            from app.email_service import send_email
            body = f"""Dear {job.client_name},

Please find your invoice for the work completed on {job.date.strftime('%d/%m/%Y')}.

Address: {job.address}
Amount: £{job.price:.2f}

Thank you for your business!
{current_user.username}"""
            app = current_app._get_current_object()
            def send_inv(app, to, body):
                with app.app_context():
                    send_email(to, f'Invoice - {job.description or job.activity_type}', body)
            Thread(target=send_inv, args=(app, job.client_email, body)).start()
            flash('Invoice descărcat și trimis pe email!')
        except Exception as e:
            print(f">>> Invoice email error: {e}")
            flash('Invoice descărcat.')

    buffer.seek(0)
    return Response(
        buffer.getvalue(),
        mimetype='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename=invoice_{job.id}.pdf',
            'Content-Type': 'application/pdf'
        }
    )


@main.route('/job/quote/<int:job_id>', methods=['GET', 'POST'])
@login_required
def send_quote(job_id):
    job = Job.query.get_or_404(job_id)
    if job.user_id != current_user.id:
        flash('Nu ai permisiunea.')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        quote_price = float(request.form.get('quote_price') or 0)
        quote_description = request.form.get('quote_description')

        job.quote_price = quote_price
        job.quote_description = quote_description
        job.quote_status = 'sent'
        db.session.commit()

        accept_url = url_for('main.quote_response', job_id=job.id, response='accepted', _external=True)
        decline_url = url_for('main.quote_response', job_id=job.id, response='declined', _external=True)

        if job.client_email:
            body = f"""Dear {job.client_name},

You have received a quote for the following work:

Address: {job.address}
Description: {quote_description}
Price: £{quote_price:.2f}

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
            Thread(target=send_async, args=(app, job.client_email, f'Quote from {username}', body)).start()
            flash('Quote sent successfully!')
        else:
            flash('No client email — quote saved but not sent.')

        return redirect(url_for('main.dashboard'))

    return render_template('send_quote.html', job=job)


@main.route('/job/quote/<int:job_id>/response/<response>')
def quote_response(job_id, response):
    job = Job.query.get_or_404(job_id)
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

        db.session.commit()
        flash('Business settings saved!')
        return redirect(url_for('main.business_settings'))

    return render_template('business_settings.html', business=business)