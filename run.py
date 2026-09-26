from app import create_app, db, scheduler
from app.notifications import send_due_job_reminders
from migrate import ensure_schema
from dotenv import load_dotenv
import logging
import os

load_dotenv()
logging.basicConfig(level=logging.INFO)

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
        from app.backup_service import run_auto_backup

        def _auto_backup():
            with app.app_context():
                run_auto_backup(app)

        scheduler.add_job(
            func=_auto_backup,
            trigger='cron',
            hour=3,
            minute=0,
            timezone='UTC',
            id='auto_backup',
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
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
    # ensure_schema(), not flask_migrate.upgrade(). This platform starts the
    # app with its own gunicorn command and never runs the CMD in the
    # Dockerfile, so this import is the only place migrations can be brought
    # up to date. upgrade() raised "Can't locate revision identified by
    # 'e5f6a7b8c9d0'" on a database that predates the migration squash, and
    # because this runs at import it killed every worker as it booted, over
    # and over, so the site did not come up at all.
    #
    # A failure here has to stop the worker. Booting against a schema that is
    # not the one the code expects is how a wrong column turns into a 500 in
    # the middle of a customer's day, and it fails quieter than this does.
    if ensure_schema() != 0:
        logging.error('migrate: schema nu a putut fi adusa la versiunea '
                      'curenta; opresc workerul')
        raise SystemExit(1)
    _start_scheduler()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    app.run(debug=True, use_reloader=False)