"""Verify the time-tracking migration: declared DDL, data preservation, reversibility.

The round-trip half needs a database at the revision just before this feature.
One cannot be built from scratch, because the first migration in the chain
(5ef06c7f0676) creates `invoice` with a foreign key to `job` without ever
creating `job` or `user`. Until that history is squashed, the only honest
baseline is a copy of instance/scheduler.db, so those tests skip when it is
absent rather than pretending to cover a fresh install.

The DDL assertions below need no database and always run, which is where the
real regression risk lives: a dropped index, a missing server_default, an
ondelete quietly changed to RESTRICT.
"""
import os
import re
import shutil
import sqlite3
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(ROOT, 'instance', 'scheduler.db')
MIGRATION = os.path.join(
    ROOT, 'migrations', 'versions',
    'e5f6a7b8c9d0_add_time_tracking_and_calendar.py')

needs_baseline = pytest.mark.skipif(
    not os.path.exists(BASELINE),
    reason='no instance/scheduler.db to use as a pre-feature baseline; the '
           'migration chain cannot be built from scratch (see 5ef06c7f0676)')


def _source():
    with open(MIGRATION, encoding='utf-8') as handle:
        return handle.read()


def _flat():
    """The migration is wrapped across lines, so match on collapsed text."""
    return re.sub(r'\s+', ' ', _source())


def test_declares_the_table_and_columns():
    flat = _flat()
    assert "op.create_table( 'time_entry'" in flat, 'creates time_entry'
    assert "'duration_minutes'" in flat, 'adds job.duration_minutes'
    assert "'calendar_token'" in flat, 'adds user.calendar_token'


def test_duration_has_a_server_default():
    """Existing rows must land on a usable duration, not NULL."""
    assert 'server_default' in _flat(), 'a server_default is declared'


def test_declares_the_cascade_and_indexes():
    flat = _flat()
    assert "ondelete='CASCADE'" in flat, 'ON DELETE CASCADE on job_id'
    assert "op.create_index('ix_user_calendar_token'" in flat, \
        'indexes calendar_token'
    assert "op.create_index('ix_time_entry_user_open'" in flat, \
        'indexes the open-timer lookup'


def test_calendar_token_index_is_unique():
    """Two users without a calendar must both be allowed, so the token column
    stays nullable while the index enforces uniqueness for the ones that have
    one.
    """
    flat = _flat()
    assert re.search(
        r"op\.create_index\('ix_user_calendar_token', 'user', "
        r"\['calendar_token'\], unique=True\)", flat), \
        'the calendar token index is unique'


# --- round-trip, needs a real pre-feature database --------------------------

@pytest.fixture
def baseline_copy(tmp_path):
    """A throwaway copy of the pre-feature database.

    The migration subprocess runs from the project root so that `flask db` can
    import the app and find migrations/, which means a relative sqlite URL would
    land in instance/. An absolute path keeps the copy in the tmp directory
    instead, so a test run never touches the real one.
    """
    target = tmp_path / 'migration.db'
    shutil.copyfile(BASELINE, str(target))
    return str(target)


def _run(db_path, *args):
    env = dict(os.environ, DATABASE_URL='sqlite:///' + db_path.replace('\\', '/'))
    result = subprocess.run(
        [sys.executable, '-m', 'flask', 'db'] + list(args),
        cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    return result


def _tables(db_path):
    with sqlite3.connect(db_path) as connection:
        return {row[0] for row in connection.execute(
            "select name from sqlite_master where type='table'")}


def _columns(db_path, table):
    with sqlite3.connect(db_path) as connection:
        return [row[1] for row in
                connection.execute('PRAGMA table_info(%s)' % table)]


def _indexes(db_path):
    with sqlite3.connect(db_path) as connection:
        return sorted(row[0] for row in connection.execute(
            "select name from sqlite_master where type='index' "
            "and name like 'ix_%'"))


def _revision(db_path):
    with sqlite3.connect(db_path) as connection:
        return connection.execute(
            'select version_num from alembic_version').fetchone()[0]


@needs_baseline
def test_downgrade_removes_everything_it_added(baseline_copy):
    db_path = baseline_copy

    _run(db_path, 'downgrade', 'c3d4e5f6a7b8')
    assert _revision(db_path) == 'c3d4e5f6a7b8'
    assert 'time_entry' not in _tables(db_path), 'time_entry dropped'
    assert 'duration_minutes' not in _columns(db_path, 'job'), 'column dropped'
    assert 'calendar_token' not in _columns(db_path, 'user'), 'token dropped'


@needs_baseline
def test_upgrade_over_existing_rows_preserves_them(baseline_copy):
    db_path = baseline_copy

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "insert into user (username,email,password,currency) "
            "values ('u','u@t','x','GBP')")
        connection.execute(
            "insert into job (client_name,address,date,user_id) values "
            "('Client Test','Strada 1','2026-09-26 10:00:00',1)")
        connection.execute(
            "insert into job (client_name,address,date,user_id) values "
            "('Client Fara Durata','Strada 2','2026-09-26 11:00:00',1)")
        connection.commit()

    _run(db_path, 'upgrade')
    assert _revision(db_path) == 'e5f6a7b8c9d0'
    assert 'time_entry' in _tables(db_path), 'time_entry created'

    with sqlite3.connect(db_path) as connection:
        assert connection.execute('select count(*) from job').fetchone()[0] == 2, \
            'jobs kept'
        assert connection.execute('select count(*) from user').fetchone()[0] == 1, \
            'user kept'
        durations = dict(connection.execute(
            'select client_name, duration_minutes from job'))
    assert durations['Client Test'] == 60, 'existing row backfilled'
    assert durations['Client Fara Durata'] == 60, 'new row gets the default'


@needs_baseline
def test_a_running_timer_is_expressible(baseline_copy):
    db_path = baseline_copy

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            'insert into user (username,email,password,currency) '
            "values ('u','u@t','x','GBP')")
        connection.execute(
            "insert into job (client_name,address,date,user_id) values "
            "('C','A','2026-09-26 10:00:00',1)")
        connection.commit()
    _run(db_path, 'upgrade')

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            'insert into time_entry (user_id,job_id,started_at) values (1,1,?)',
            ('2026-09-26 10:00:00',))
        connection.commit()
        row = connection.execute(
            'select started_at, ended_at, minutes from time_entry').fetchone()

    assert row[0] is not None, 'started_at set'
    assert row[1] is None, 'ended_at still null'
    assert row[2] is None, 'minutes still null'


@needs_baseline
def test_indexes_created_and_upgrade_is_idempotent(baseline_copy):
    db_path = baseline_copy

    _run(db_path, 'downgrade', 'c3d4e5f6a7b8')
    _run(db_path, 'upgrade')
    indexes = _indexes(db_path)
    assert 'ix_user_calendar_token' in indexes, 'calendar token indexed'
    assert 'ix_time_entry_user_open' in indexes, 'open-timer lookup indexed'

    with sqlite3.connect(db_path) as connection:
        before = connection.execute('select count(*) from user').fetchone()[0]
        connection.execute(
            "insert into user (username,email,password,currency) "
            "values ('v','v@t','x','GBP')")
        connection.execute(
            "insert into user (username,email,password,currency) "
            "values ('w','w@t','x','GBP')")
        connection.commit()
        after = connection.execute('select count(*) from user').fetchone()[0]
        # A unique index rejects duplicate values but not duplicate NULLs, so
        # every user without a calendar has to be insertable.
        assert after == before + 2, 'two users without a token are allowed'
        tokens = [row[0] for row in connection.execute(
            "select calendar_token from user where username in ('v','w')")]
        assert tokens == [None, None], 'both tokens left null'
        unique = connection.execute(
            'select count(*) from pragma_index_list("user") '
            'where name="ix_user_calendar_token" and "unique"=1').fetchone()[0]
    assert unique == 1, 'the token index is unique'

    _run(db_path, 'upgrade')
    assert _revision(db_path) == 'e5f6a7b8c9d0', 're-running upgrade is a no-op'
