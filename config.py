import os

def _database_uri():
    raw = os.environ.get('DATABASE_URL') or 'sqlite:///scheduler.db'
    # SQLAlchemy 2.1 flipped the default PostgreSQL driver to psycopg 3, but we
    # ship psycopg2-binary. Pin the driver so a rebuild cannot swap it underneath
    # us and take the whole app down at import time.
    if '+' not in raw.split('://', 1)[0]:
        for scheme in ('postgres://', 'postgresql://'):
            if raw.startswith(scheme):
                return 'postgresql+psycopg2://' + raw[len(scheme):]
    return raw

class Config:
    # No fallback. A key committed to the repository signs every session and
    # every CSRF token with something published on GitHub, so anyone who
    # deployed without setting SECRET_KEY would have had forgeable sessions.
    # There used to be a 'dev-key-schimba-in-productie' default here, and it
    # was worse than useless: create_app() overwrote it with os.getenv(...),
    # which is None when the variable is unset, so the app ran with no key at
    # all and every login failed with a bare "Session backend did not open a
    # session". _require_secret_key() turns that into a message that says what
    # to do. Generating one: python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Receipt photos are base64-encoded before reaching the AI, so cap the whole
    # request body. 10 MB leaves room for a modern phone photo plus form fields.
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024

    # Email
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.sendgrid.net'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 465)
    MAIL_USE_TLS = False
    MAIL_USE_SSL = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or 'apikey'
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'stef.cosmin09@gmail.com'


def _require_secret_key(value):
    """Refuse to build an app that cannot sign a session.

    Flask reports a missing key much later and much less clearly, as a 500 on
    the login page. Failing here means the mistake surfaces on the first
    command that touches the app, including in CI where nothing is set.
    """
    if not value:
        raise RuntimeError(
            'SECRET_KEY is not set. Copy .env.example to .env and fill in '
            'SECRET_KEY, or set it in the environment. Generate one with: '
            'python -c "import secrets; print(secrets.token_hex(32))"')
    return value