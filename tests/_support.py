"""Shared setup for the test suite.

The application is built once per session and the schema is rebuilt around
every test, so each test can assume an empty database and that the first user
it registers lands on id 1.

Nothing here reads or writes the real database in instance/; the suite points
DATABASE_URL at a scratch file in the system temp directory before the app
loads its config.
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Must be set before create_app() reads the config, and must not point at
# instance/ or a test run would rewrite the developer's real data.
_SCRATCH = tempfile.mkdtemp(prefix='tradescheduler-tests-')
_DB_PATH = os.path.join(_SCRATCH, 'test.db').replace('\\', '/')
os.environ['DATABASE_URL'] = 'sqlite:///' + _DB_PATH
# The app refuses to start without a key, and the suite must not depend on a
# SECRET_KEY happening to be in the developer's .env, or in CI where there is
# no .env at all. A fixed value is correct here: every session in the run is
# thrown away with the scratch directory.
os.environ['SECRET_KEY'] = 'test-key-not-used-outside-this-scratch-directory'
# The welcome email would otherwise block on a DNS timeout per registration.
os.environ['MAIL_SUPPRESS_SEND'] = '1'
os.environ['MAIL_DEFAULT_SENDER'] = 'tests@example.invalid'

from itsdangerous import URLSafeTimedSerializer  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402


@event.listens_for(Engine, 'connect')
def _foreign_keys_on(dbapi_connection, _record):
    """Make SQLite enforce foreign keys.

    SQLite leaves them off by default, so a missing ON DELETE CASCADE would
    pass every test in this suite and then fail in production on Postgres.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute('PRAGMA foreign_keys=ON')
    cursor.close()


from app import create_app, db  # noqa: E402
from app.models import Job, TimeEntry, User  # noqa: E402

app = create_app()
app.config.update(
    TESTING=True,
    # A rejected CSRF token is asserted as a 400 response, so exceptions must
    # not propagate. Genuine failures still surface as 500s.
    PROPAGATE_EXCEPTIONS=False,
    # Left on deliberately: the POST-only job actions exist because of it, and
    # switching it off would make those tests pass for the wrong reason.
    WTF_CSRF_ENABLED=True,
    MAIL_SUPPRESS_SEND=True,
    TEMPLATES_AUTO_RELOAD=True,
    SEND_FILE_MAX_AGE_DEFAULT=0,
)


def reset_db():
    """Drop and recreate every table, leaving a clean slate for one test."""
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.create_all()


def check(label, got, want=True):
    """Assert with a readable label.

    Same shape as the ad-hoc checker this replaced, except a mismatch now
    fails the test instead of printing a line nobody was reading.
    """
    assert got == want, '%s -> got %r, want %r' % (label, got, want)


def csrf(client):
    """Return a form token shaped the way validate_csrf() reads it.

    The session holds the raw token and the form carries it signed with the
    app secret under the "wtf-csrf-token" salt, so a plain string is refused.
    """
    raw = 'r' * 64
    with client.session_transaction() as session:
        session['csrf_token'] = raw
    signer = URLSafeTimedSerializer(app.secret_key, salt='wtf-csrf-token')
    return signer.dumps(raw)


def make_user(username, plan='free', token=None):
    with app.app_context():
        user = User(username=username, email='%s@t.test' % username,
                    password='x', plan=plan)
        if token:
            user.calendar_token = token
        db.session.add(user)
        db.session.commit()
        uid = user.id
        db.session.expunge_all()
        return uid


def make_job(uid, name='Client', days=0, duration=60, status='pending'):
    from datetime import datetime, timedelta
    with app.app_context():
        job = Job(user_id=uid, client_name=name, address='Adresa 1',
                  date=datetime.utcnow() + timedelta(days=days),
                  duration_minutes=duration, status=status)
        db.session.add(job)
        db.session.commit()
        jid = job.id
        db.session.expunge_all()
        return jid


def login(client, username, password='pw'):
    """Sign in by email: the login form has no username field."""
    return client.post('/login',
                       data={'email': '%s@t.test' % username,
                             'password': password,
                             'csrf_token': csrf(client)},
                       follow_redirects=True)


def register(client, username, password='pw'):
    """Register then sign in: /register deliberately does not log you in."""
    client.post('/register',
                data={'username': username, 'email': '%s@t.test' % username,
                      'password': password, 'csrf_token': csrf(client)},
                follow_redirects=True)
    return login(client, username, password)
