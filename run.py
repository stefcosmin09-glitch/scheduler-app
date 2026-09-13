from app import create_app, db, scheduler
from app.notifications import send_due_job_reminders
from flask_migrate import upgrade
from dotenv import load_dotenv
import os

load_dotenv()

app = create_app()

def _start_scheduler():
    with app.app_context():
        scheduler.add_job(
            func=send_due_job_reminders,
            trigger='interval',
            minutes=1,
            args=[app],
            id='job_reminders',
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=10,
        )
    scheduler.start()
    print(">>> Scheduler started")

def _try_acquire_lock():
    if os.name == 'posix':
        try:
            import fcntl
            global _lock_handle
            _lock_handle = open(os.getenv('SCHEDULER_LOCK', '/tmp/scheduler.lock'), 'w')
            fcntl.flock(_lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False
    return True

if _try_acquire_lock():
    with app.app_context():
        upgrade()
    _start_scheduler()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    app.run(debug=True, use_reloader=False)