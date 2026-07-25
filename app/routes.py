from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, mail
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer
from app.models import User, Job, ACTIVITY_TYPES
from app.notifications import schedule_reminder
from datetime import datetime
from flask import current_app

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

    # Total câștigat
    now = datetime.utcnow()

    # Săptămâna curentă (luni - duminică)
    start_of_week = now - timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0)

    # Luna curentă
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0)

    weekly_jobs = Job.query.filter_by(
        user_id=current_user.id,
        status='done'
    ).filter(Job.date >= start_of_week).all()

    monthly_jobs = Job.query.filter_by(
        user_id=current_user.id,
        status='done'
    ).filter(Job.date >= start_of_month).all()

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
    from flask import Response
    from flask_mail import Message as MailMessage
    buffer = generate_invoice(job, current_user)

    # Trimite pe email daca clientul are email
    if job.client_email:
        try:
            msg = MailMessage(
                subject=f'Invoice - {job.description or job.activity_type}',
                recipients=[job.client_email],
                body=f"""
Dear {job.client_name},

Please find attached your invoice for the work completed on {job.date.strftime('%d/%m/%Y')}.

Address: {job.address}
Amount: £{job.price:.2f}

Thank you for your business!

{current_user.username}
                """
            )
            msg.attach(
                f'invoice_{job.id}.pdf',
                'application/pdf',
                buffer.getvalue()
            )
            mail.send(msg)
            flash('Invoice descărcat și trimis pe email clientului!')
        except Exception as e:
            print(f">>> Eroare email: {e}")
            flash('Invoice descărcat — emailul nu a putut fi trimis.')
    buffer.seek(0)
    return Response(
        buffer.getvalue(),
        mimetype='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename=invoice_{job.id}.pdf',
            'Content-Type': 'application/pdf'
        }
    ) 

def get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])

@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        print(f">>> User gasit: {user}")
        if user:
            s = get_serializer()
            token = s.dumps(email, salt='password-reset')
            reset_url = url_for('auth.reset_password', token=token, _external=True)

            msg = Message(
                subject='Reset your password - Scheduler App',
                recipients=[email],
                body=f"""
Hi {user.username},

Click the link below to reset your password. The link expires in 1 hour.

{reset_url}

If you didn't request this, ignore this email.
                """
            )
            mail.send(msg)
        print(f">>> Email reset trimis la {email}")
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
            from werkzeug.security import generate_password_hash
            user.password = generate_password_hash(password)
            db.session.commit()
            flash('Parola schimbată cu succes!')
            return redirect(url_for('auth.login'))

    return render_template('reset_password.html', token=token)
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
            try:
                msg = Message(
                    subject=f'Quote from {current_user.username}',
                    recipients=[job.client_email],
                    body=f"""
Dear {job.client_name},

You have received a quote for the following work:

📍 Address: {job.address}
🔧 Description: {quote_description}
💰 Price: £{quote_price:.2f}

To accept this quote, click here:
{accept_url}

To decline this quote, click here:
{decline_url}

Thank you,
{current_user.username}
                    """
                )
                mail.send(msg)
                flash('Quote sent successfully!')
            except Exception as e:
                print(f">>> Quote email error: {e}")
                flash(f'Quote saved but email failed: {e}')
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