"""Bring the database up to date at deploy time.

`flask db upgrade` on its own is not safe here. The migration history was
squashed into a single initial revision, so a database that was created before
the squash is stamped with a revision id that no longer exists in the script
directory. Plain `flask db upgrade` answers that with

    Error: Can't locate revision identified by 'e5f6a7b8c9d0'

and the Dockerfile's `flask db upgrade && gunicorn ...` would short-circuit,
leaving the container without a web server.

The schema of such a database is already correct, so the right move is to
re-stamp it onto the new head rather than to run anything. This decides which
of the three situations it is in:

  no alembic_version and no app tables   empty database, run the migrations
  revision unknown to the script dir     schema predates the squash, stamp it
  anything else                          a normal upgrade

Run directly, it reports what it decided and why.
"""
import os
import subprocess
import sys

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, inspect, text  # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VERSIONS_DIR = os.path.join(BASE_DIR, 'migrations', 'versions')

# A table that only exists in a migrated database, never in an empty one.
SENTINEL_TABLE = 'user'


def resolve_url():
    url = os.getenv('DATABASE_URL') or 'sqlite:///scheduler.db'
    if url.startswith('sqlite:///'):
        path = url[len('sqlite:///'):]
        if not os.path.isabs(path) and not path.startswith('instance'):
            candidate = os.path.join(BASE_DIR, 'instance', path)
            if os.path.exists(candidate):
                return 'sqlite:///' + candidate.replace('\\', '/')
    return url


def known_revisions():
    """Revision ids the script directory can actually resolve."""
    found = set()
    if not os.path.isdir(VERSIONS_DIR):
        return found
    for name in os.listdir(VERSIONS_DIR):
        if not name.endswith('.py'):
            continue
        with open(os.path.join(VERSIONS_DIR, name), encoding='utf-8') as handle:
            for line in handle:
                stripped = line.strip()
                if stripped.startswith('revision'):
                    _, _, value = stripped.partition('=')
                    value = value.strip().strip('\'"')
                    if value and value != 'None':
                        found.add(value)
                    break
    return found


def current_revision(engine):
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text('select version_num from alembic_version')).fetchone()
    except Exception:
        return None
    return row[0] if row else None


def has_app_tables(engine):
    try:
        return SENTINEL_TABLE in inspect(engine).get_table_names()
    except Exception:
        return False


def clear_version_marker(engine):
    """Empty alembic_version so that `stamp` can run.

    Alembic resolves the revision already recorded in the database before it
    does anything else, so `stamp head` fails on an id it has never heard of,
    which is exactly the case this script exists to handle. The table holds
    nothing but a marker, and the new head is written to it immediately after,
    so clearing it loses no schema information and no data.
    """
    with engine.begin() as conn:
        conn.execute(text('delete from alembic_version'))


def flask(*args):
    return subprocess.call([sys.executable, '-m', 'flask', 'db'] + list(args))


def main():
    url = resolve_url()
    print('migrate: %s' % url.split('//')[0] + '//...')

    try:
        engine = create_engine(url)
        stamped = current_revision(engine)
        tables = has_app_tables(engine)
    except Exception as error:
        print('migrate: nu pot citi baza de date (%s), rulez upgrade oricum'
              % error)
        return flask('upgrade')

    known = known_revisions()
    print('migrate: revizia din baza = %s, cunoscute = %s'
          % (stamped or '(niciuna)', ', '.join(sorted(known)) or '(niciuna)'))

    if not stamped and not tables:
        print('migrate: baza goala, aplic migrarile')
        return flask('upgrade')

    if stamped and stamped not in known:
        if not tables:
            print('migrate: revizia %s nu exista si nu exista tabele, '
                  'aplic migrarile' % stamped)
            return flask('upgrade')
        print('migrate: baza are deja schema, dar revizia %s a fost '
              'comprimata; fac stamp la head' % stamped)
        clear_version_marker(engine)
        return flask('stamp', 'head')

    print('migrate: aplic migrarile')
    return flask('upgrade')


if __name__ == '__main__':
    sys.exit(main())
