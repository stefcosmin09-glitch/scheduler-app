from flask_mail import Message
from app import mail, db, scheduler, format_money
from app.models import Job, Invoice
from datetime import datetime, timedelta

def send_reminder(app, job_id):
    with app.app_context():
        job = Job.query.get(job_id)
        if not job or job.status == 'done':
            return

        if not job.client_email:
            return

        lang = job.owner.language if job.owner else 'en'

        if lang == 'ro':
            subject = 'Reminder: Job în 40 de minute'
            body = f"""Bună ziua {job.client_name},

Acesta este un reminder că meșterul dvs. va ajunge în aproximativ 40 de minute.

📍 Adresă: {job.address}
📅 Ora programată: {job.date.strftime('%d/%m/%Y %H:%M')}

Vă mulțumim!
"""
        else:
            subject = 'Reminder: Job in 40 minutes'
            body = f"""Hi {job.client_name},

This is a reminder that your contractor will arrive in approximately 40 minutes.

📍 Address: {job.address}
📅 Scheduled time: {job.date.strftime('%d/%m/%Y %H:%M')}

Thank you!
"""
        msg = Message(
            subject=subject,
            recipients=[job.client_email],
            body=body
        )
        mail.send(msg)
        print(f">>> Email trimis pentru job {job_id}")

def schedule_reminder(app, job):
    reminder_time = job.date - timedelta(minutes=40)
    now = datetime.now()

    print(f">>> Ora acum: {now}")
    print(f">>> Reminder programat pentru: {reminder_time}")

    if reminder_time <= now:
        print(">>> Reminder in trecut, nu se programeaza")
        return

    scheduler.add_job(
        func=send_reminder,
        trigger='date',
        run_date=reminder_time,
        args=[app, job.id],
        id=f'reminder_{job.id}',
        replace_existing=True
    )
    print(f">>> Reminder adaugat in scheduler cu succes!")

def send_overdue_invoice_reminders(app):
    from app.email_service import send_email
    with app.app_context():
        now = datetime.now()
        overdue = Invoice.query.filter(
            Invoice.status.in_(('sent', 'overdue')),
            Invoice.due_date < now,
            Invoice.reminder_sent == False
        ).all()

        for invoice in overdue:
            job = invoice.job
            if not job or not job.client_email:
                continue
            owner = job.owner
            lang = owner.language if owner and owner.language else 'en'
            amount = format_money(invoice.total_amount, owner.currency if owner else 'GBP')
            due = invoice.due_date.strftime('%d/%m/%Y')

            if lang == 'ro':
                subject = f'Reminder: factură scadentă {invoice.invoice_number}'
                body = f"""Bună ziua {job.client_name},

Vă anunțăm că factura {invoice.invoice_number}, în valoare de {amount}, este scadentă din data de {due}.

Vă rugăm să efectuați plata cât mai curând posibil.

Vă mulțumim!
"""
            else:
                subject = f'Reminder: overdue invoice {invoice.invoice_number}'
                body = f"""Hi {job.client_name},

This is a reminder that invoice {invoice.invoice_number} for {amount} has been due since {due}.

Please make your payment as soon as possible.

Thank you!
"""
            ok = send_email(job.client_email, subject, body)
            if ok:
                invoice.reminder_sent = True
        db.session.commit()
        print(f">>> Overdue invoice reminders processed: {len(overdue)}")