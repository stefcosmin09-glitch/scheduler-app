"""Starting the app must never leave the database behind.

run.py brings the schema up to date at import, because that import is what
gunicorn does when it boots a worker and the deploy target does not run the CMD
in the Dockerfile. That put `flask_migrate.upgrade()` on the startup path, and
it raised

    Can't locate revision identified by 'e5f6a7b8c9d0'

on a database that predates the migration squash. The worker died, the flock was
released, the next worker took the lock and died the same way, and the site did
not come up at all.

Each test here imports run.py in a subprocess, which is the whole boot sequence,
and then checks the schema and the rows. Three states matter: a database from
before the squash, one whose marker was lost halfway through a re-stamp, and
one that is already current.
"""
import os
import sqlite3
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEAD = '0002_login_throttle'
ROOT_REVISION = '0001_initial_schema'


def _url(path):
    return 'sqlite:///' + path.replace('\\', '/')


def _squashed(path):
    """A database as the fifteen-migration history left it: the tables exist and
    the marker names a revision the script directory no longer has."""
    conn = sqlite3.connect(path)
    conn.execute('create table user (id integer primary key, username varchar, '
                 'email varchar, password varchar)')
    conn.execute('create table alembic_version (version_num varchar(32) '
                 'primary key)')
    conn.execute("insert into alembic_version values ('e5f6a7b8c9d0')")
    conn.execute("insert into user (username, email, password) values "
                 "('real', 'real@example.test', 'h')")
    conn.commit()
    conn.close()


def _boot(path):
    """Import run:app the way gunicorn does."""
    env = dict(os.environ, DATABASE_URL=_url(path), SECRET_KEY='probe')
    # Set on purpose. Deployments that export FLASK_APP=run.py are the norm, and
    # that is what made the migration subprocess import run.py again.
    env['FLASK_APP'] = 'run.py'
    return subprocess.run(
        [sys.executable, '-c', 'import run; print("BOOTED")'],
        cwd=ROOT, env=env, capture_output=True, text=True)


def _state(path):
    conn = sqlite3.connect(path)
    try:
        tables = {r[0] for r in conn.execute(
            "select name from sqlite_master where type='table'")}
        row = conn.execute(
            'select version_num from alembic_version').fetchone()
        return tables, (row[0] if row else None)
    finally:
        conn.close()


def _assert_healthy(result, path, expect_rows=None):
    output = result.stdout + result.stderr
    assert result.returncode == 0, (
        'the app refused to start, which is what happened in production:\n%s'
        % output[-2500:])
    tables, stamped = _state(path)
    assert stamped == HEAD, (
        'booted on revision %r, expected %r' % (stamped, HEAD))
    # The table the login throttle needs. Missing it means the database was
    # marked as up to date without the migration that creates it ever running,
    # which only shows up as an error on the first failed sign-in.
    assert 'login_attempt' in tables, 'login_attempt was never created'
    if expect_rows is not None:
        conn = sqlite3.connect(path)
        try:
            assert conn.execute('select count(*) from user').fetchone()[0] == expect_rows
        finally:
            conn.close()


def test_boots_on_a_database_from_before_the_squash(tmp_path):
    path = str(tmp_path / 'squashed.db')
    _squashed(path)

    result = _boot(path)

    assert 'stamp la %s' % ROOT_REVISION in result.stdout, (
        'expected a re-stamp to the root of the history:\n%s'
        % (result.stdout + result.stderr)[-1500:])
    _assert_healthy(result, path, expect_rows=1)


def test_boots_when_the_stamp_was_interrupted(tmp_path):
    """A crash between clearing the marker and writing the new one leaves the
    tables with no revision at all. Left alone, alembic would treat that as
    'nothing applied' and run every migration from the base against tables that
    already exist."""
    path = str(tmp_path / 'interrupted.db')
    _squashed(path)
    conn = sqlite3.connect(path)
    conn.execute('delete from alembic_version')
    conn.commit()
    conn.close()

    result = _boot(path)

    assert 'stamp intrerupt' in result.stdout, result.stdout
    _assert_healthy(result, path, expect_rows=1)


def test_boots_on_an_already_current_database(tmp_path):
    """The common case, and the one that must stay quiet: nothing to do, and
    certainly no attempt to re-create what is already there."""
    path = str(tmp_path / 'current.db')
    prepared = subprocess.run(
        [sys.executable, '-m', 'flask', 'db', 'upgrade'], cwd=ROOT,
        env=dict(os.environ, DATABASE_URL=_url(path), SECRET_KEY='probe',
                 FLASK_APP='app'),
        capture_output=True, text=True)
    assert prepared.returncode == 0, prepared.stderr[-1500:]

    result = _boot(path)

    _assert_healthy(result, path)
    assert 'stamp' not in result.stdout, \
        'a current database was re-stamped instead of left alone'


def test_an_empty_database_is_built_from_nothing(tmp_path):
    path = str(tmp_path / 'empty.db')
    result = _boot(path)
    _assert_healthy(result, path)
    assert 'baza goala' in result.stdout, result.stdout


def test_the_migration_subprocess_does_not_reimport_run(tmp_path):
    """With FLASK_APP=run.py in the environment, an inherited one would import
    run.py, which calls ensure_schema at import, which spawns it again. The
    subprocess forces FLASK_APP=app, so the recursion is impossible."""
    path = str(tmp_path / 'recursion.db')
    _squashed(path)
    result = _boot(path)
    assert result.returncode == 0, (
        'boot failed, which is what a runaway recursion looks like:\n%s'
        % (result.stdout + result.stderr)[-2000:])
    assert result.stdout.count('BOOTED') == 1, \
        'run.py was imported more than once'


@pytest.mark.parametrize('revision,expected', [
    ('e5f6a7b8c9d0', 'stamp la 0001_initial_schema'),
    (None, 'stamp intrerupt'),
    ('0001_initial_schema', 'aplic migrarile'),
])
def test_each_startup_state_is_recognised(tmp_path, revision, expected):
    """One line of output per state, so a deploy log says what happened rather
    than leaving it to be inferred from an absence."""
    path = str(tmp_path / 'state.db')
    _squashed(path)
    if revision is None:
        conn = sqlite3.connect(path)
        conn.execute('delete from alembic_version')
        conn.commit()
        conn.close()
    elif revision != 'e5f6a7b8c9d0':
        # Already on the root: the tables for 0002 are missing on purpose, so
        # the upgrade has something to do.
        conn = sqlite3.connect(path)
        conn.execute('delete from alembic_version')
        conn.execute("insert into alembic_version values (?)", (revision,))
        conn.commit()
        conn.close()

    result = _boot(path)
    assert expected in result.stdout, (
        'expected %r, got:\n%s' % (expected, result.stdout))
