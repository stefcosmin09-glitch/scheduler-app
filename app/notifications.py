from flask_mail import Message
from app import mail, db, scheduler
from app.models import Job
from datetime import datetime, timedelta

def send_reminder(app, job_id):
    with app.app_context():
        job = Job.query.get(job_id)
        if not job or job.status == 'done':
            return

        if not job.client_email:
            return

        msg = Message(
            subject='Reminder: Job în 40 de minute',
            recipients=[job.client_email],
            body=f"""
Bună ziua {job.client_name},

Acesta este un reminder că meșterul dvs. va ajunge în aproximativ 40 de minute.

📍 Adresă: {job.address}
📅 Ora programată: {job.date.strftime('%d/%m/%Y %H:%M')}

Vă mulțumim!
            """
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