"""Exercise ON DELETE CASCADE the way Postgres will.

SQLite leaves foreign keys off by default, so a missing ondelete clause would
never surface here; conftest turns the pragma on for every test. The DDL the
migration declares is covered in test_migrations.py, and the last check keeps
the two definitions from drifting apart.
"""
from datetime import datetime

from sqlalchemy import text

from _support import app, check, db
from app.models import Job, User


def _seed():
    with app.app_context():
        db.session.execute(text('PRAGMA foreign_keys=ON'))
        user = User(username='fk1', email='fk1@t.test', password='x')
        db.session.add(user)
        db.session.flush()
        job = Job(user_id=user.id, client_name='C', address='A',
                  date=datetime.utcnow())
        db.session.add(job)
        db.session.commit()
        return job.id, user.id


def test_foreign_keys_are_actually_enforced():
    with app.app_context():
        check('pragma foreign_keys is on',
              db.session.execute(text('PRAGMA foreign_keys')).scalar(), 1)


def test_time_entry_requires_a_job():
    job_id, user_id = _seed()
    with app.app_context():
        try:
            db.session.execute(text(
                'INSERT INTO time_entry (user_id, job_id, minutes) '
                'VALUES (:u, NULL, 30)'), {'u': user_id})
            db.session.commit()
            rejected = False
        except Exception:
            db.session.rollback()
            rejected = True
        check('null job_id refused', rejected, True)
        check('no orphan row written', db.session.execute(
            text('SELECT COUNT(*) FROM time_entry')).scalar(), 0)


def test_unknown_job_is_refused():
    job_id, user_id = _seed()
    with app.app_context():
        try:
            db.session.execute(text(
                'INSERT INTO time_entry (user_id, job_id, minutes) '
                'VALUES (:u, 99999, 30)'), {'u': user_id})
            db.session.commit()
            rejected = False
        except Exception:
            db.session.rollback()
            rejected = True
        check('unknown job_id refused', rejected, True)


def test_database_cascades_the_delete():
    job_id, user_id = _seed()
    with app.app_context():
        db.session.execute(text(
            'INSERT INTO time_entry (user_id, job_id, minutes) '
            'VALUES (:u, :j, 45)'), {'u': user_id, 'j': job_id})
        db.session.commit()
        check('entry inserted', db.session.execute(
            text('SELECT COUNT(*) FROM time_entry')).scalar(), 1)

        # Raw SQL on purpose: the ORM cascade is bypassed, so only the
        # database-level ondelete clause can make this succeed.
        db.session.execute(text('DELETE FROM job WHERE id = :j'), {'j': job_id})
        db.session.commit()
        check('job gone', db.session.execute(
            text('SELECT COUNT(*) FROM job WHERE id = :j'),
            {'j': job_id}).scalar(), 0)
        check('entry cascaded by the database', db.session.execute(
            text('SELECT COUNT(*) FROM time_entry')).scalar(), 0)


def test_migration_declares_the_same_clause():
    """Guards against the model and the migration disagreeing."""
    import os
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'migrations', 'versions',
        'e5f6a7b8c9d0_add_time_tracking_and_calendar.py')
    with open(path, encoding='utf-8') as handle:
        migration = handle.read()
    lines = [line for line in migration.splitlines()
             if 'job_id' in line and 'ondelete' in line and 'CASCADE' in line.upper()]
    check('exactly one ON DELETE CASCADE on job_id', len(lines), 1)
