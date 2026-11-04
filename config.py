import os

from db_url import resolve_url


def _database_uri():
    # db_url.resolve_url pins a postgres URL to the psycopg2 driver the project
    # ships. SQLAlchemy 2.1 made psycopg (v3) the default for a bare postgres
    # URL, so without the pin the first create_engine() raises
    # ModuleNotFoundError; that is what took the migration probe down at deploy.
    return resolve_url(os.environ.get('DATABASE_URL'))

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

    # Legal pages are drafts until the owner reviews them. Flip to 0 to remove
    # the "DRAFT" banner everywhere at once.
    LEGAL_DRAFT = os.environ.get('LEGAL_DRAFT', '1') != '0'

    # Payments. Off by default: the app is free at launch. Set to 1 to re-enable
    # Stripe billing, trials, plans and the read-only-after-trial behaviour.
    PAYMENTS_ENABLED = os.environ.get('PAYMENTS_ENABLED', '0') == '1'

    # Contact and legal identity. Required in production: if SUPPORT_EMAIL or
    # LEGAL_ENTITY_NAME is missing, the legal pages 404 and the footer links
    # are hidden. COMPANY_NUMBER is optional (sole traders have none).
    SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL', '').strip()
    LEGAL_ENTITY_NAME = os.environ.get('LEGAL_ENTITY_NAME', '').strip()
    COMPANY_NUMBER = os.environ.get('COMPANY_NUMBER', '').strip()
    LEGAL_LAST_UPDATED = os.environ.get('LEGAL_LAST_UPDATED', '').strip()


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