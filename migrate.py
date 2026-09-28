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

from db_url import resolve_url
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, inspect, text  # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VERSIONS_DIR = os.path.join(BASE_DIR, 'migrations', 'versions')

# A table that only exists in a migrated database, never in an empty one.
SENTINEL_TABLE = 'user'


def script_revisions():
    """revision id -> down_revision, for every migration on disk.

    Both halves are needed. Knowing which ids exist is what tells a squashed
    database apart from a current one; knowing which one has no parent is what
    says where the squash actually started.
    """
    found = {}
    if not os.path.isdir(VERSIONS_DIR):
        return found
    for name in sorted(os.listdir(VERSIONS_DIR)):
        if not name.endswith('.py'):
            continue
        revision = parent = None
        with open(os.path.join(VERSIONS_DIR, name), encoding='utf-8') as handle:
            for line in handle:
                stripped = line.strip()
                for attribute in ('revision', 'down_revision'):
                    if not stripped.startswith(attribute + ' '):
                        continue
                    _, _, value = stripped.partition('=')
                    value = value.strip().strip('\'"')
                    if value and value != 'None':
                        if attribute == 'revision':
                            revision = value
                        else:
                            parent = value
        if revision:
            found[revision] = parent
    return found


def squash_root(revisions):
    """The revision that starts the squashed history, or None if unclear.

    A database predating the squash has the schema that this revision builds,
    so it is stamped here and then upgraded normally. That is what makes a
    migration added after the squash actually run: stamping straight to head
    would write the newer id onto a database that never had that migration
    applied, and the table it creates would be missing forever after.
    """
    roots = [rev for rev, parent in revisions.items() if parent is None]
    if len(roots) == 1:
        return roots[0]
    return None


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
    """Run a flask db command in a subprocess.

    FLASK_APP is forced to the app package rather than left to the
    environment. Deployments that set FLASK_APP=run.py are common, and this
    subprocess would then import run.py, which calls ensure_schema() at import,
    which runs this again, until something gave up. The app package is what
    holds create_app either way, and loading it skips the import-time
    migration entirely.
    """
    env = dict(os.environ, FLASK_APP='app')
    return subprocess.call([sys.executable, '-m', 'flask', 'db'] + list(args),
                           env=env)


def ensure_schema(url=None):
    """Bring the database to the current revision. Returns an exit code.

    Callable, because the deploy target does not run this script. The platform
    starts the app with its own gunicorn command and ignores the CMD in the
    Dockerfile, so run.py calls this at import instead. Keeping the logic in
    one place means every way of starting the app gets the same treatment.
    """
    url = url or resolve_url(os.getenv('DATABASE_URL'))
    print('migrate: %s' % url.split('//')[0] + '//...')

    try:
        engine = create_engine(url)
        stamped = current_revision(engine)
        tables = has_app_tables(engine)
    except Exception as error:
        print('migrate: nu pot citi baza de date (%s), rulez upgrade oricum'
              % error)
        return flask('upgrade')

    revisions = script_revisions()
    known = set(revisions)
    print('migrate: revizia din baza = %s, cunoscute = %s'
          % (stamped or '(niciuna)', ', '.join(sorted(known)) or '(niciuna)'))

    if not stamped and not tables:
        print('migrate: baza goala, aplic migrarile')
        return flask('upgrade')

    # No marker but tables present is the same situation as an unknown marker,
    # and it is what a crash between clearing the marker and stamping it looks
    # like. Treating it as current would make alembic run every migration from
    # the base against tables that already exist, so it is handled the same
    # way: stamp the root, then upgrade.
    unknown = not stamped or stamped not in known
    if unknown:
        if not tables:
            print('migrate: revizia %s nu exista si nu exista tabele, '
                  'aplic migrarile' % stamped)
            return flask('upgrade')
        root = squash_root(revisions)
        if root is None:
            # Guessing here would either skip migrations or apply them twice.
            # A deploy that stops is better than a schema that is quietly wrong.
            print('migrate: nu pot stabili inceputul istoricului comprimat '
                  '(%d migrari fara parinte). Nu ating baza.' % len(revisions))
            return 1
        if stamped:
            print('migrate: baza are deja schema, dar revizia %s a fost '
                  'comprimata; fac stamp la %s' % (stamped, root))
        else:
            print('migrate: baza are schema, dar fara revizie (stamp '
                  'intrerupt); refac de la %s' % root)
        clear_version_marker(engine)
        code = flask('stamp', root)
        if code:
            return code
        # Anything committed after the squash still has to run.
        return flask('upgrade')

    print('migrate: aplic migrarile')
    return flask('upgrade')


def main():
    return ensure_schema()


if __name__ == '__main__':
    sys.exit(main())
