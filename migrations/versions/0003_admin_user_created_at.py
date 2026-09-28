"""Signup date and the read-only user list.

Adds user.created_at, which nothing had, and user.is_admin, which gates the
admin view. Existing rows are recovered rather than left null, using the best
evidence available per account:

  trial_ends_at - 14 days   exact. Set once at registration to utcnow + 14 days
                            and never touched again anywhere in the code, so
                            subtracting the trial gives the signup moment back.
  earliest job.created_at   a lower bound, not the date. The account cannot
                            have been created before its first job, so this is
                            the latest possible signup for that account.
  earliest invoice.created_at  same, lower bound.
  null                     nothing to derive from. Stays null rather than
                            guessed, because a wrong signup date is worse than
                            a missing one.

The bounds are not equivalent and the migration says so in the log, because the
difference between "signed up then" and "signed up no later than" is the whole
reason to be careful with the column.

The recovery is done in Python rather than in SQL because "14 days ago" is
PostgreSQL syntax and the suite runs these against SQLite, and because a user
table is small enough that reading it into memory is not the thing that will
ever be a problem here.

is_admin defaults to false on every row, including the ones backfilled here.
Granting it is a deliberate act, not a side effect of adding the column.
"""
from alembic import op
from datetime import timedelta
import sqlalchemy as sa

revision = '0003_admin_user_created_at'
down_revision = '0002_login_throttle'
branch_labels = None
depends_on = None

# Length of the trial, which is what makes trial_ends_at a recoverable signup
# date. Must match TRIAL_DAYS in the register route.
TRIAL_DAYS = 14


def _columns(conn, table_name):
    """Which columns a table really has.

    The deploy entrypoint can run 0003 on a database that predates the squash,
    whose user table is only (id, username, email). Recovery sources that are
    not there must be skipped rather than made to crash the whole migration.
    """
    from sqlalchemy import inspect
    try:
        return {c['name'] for c in inspect(conn).get_columns(table_name)}
    except Exception:
        return set()


def _still_missing(conn, user):
    return [row[0] for row in conn.execute(
        sa.select(user.c.id).where(user.c.created_at.is_(None)))]


def _recover_from_trial(conn, user, log):
    """Exact, for accounts that went through the trial."""
    if 'trial_ends_at' not in _columns(conn, user.name):
        return
    rows = conn.execute(sa.select(user.c.id, user.c.trial_ends_at).where(
        user.c.trial_ends_at.isnot(None))).fetchall()
    for user_id, trial_ends_at in rows:
        conn.execute(user.update().where(user.c.id == user_id).values(
            created_at=trial_ends_at - timedelta(days=TRIAL_DAYS)))
    log('  %d conturi au data exacta, din trial_ends_at - %d zile'
        % (len(rows), TRIAL_DAYS))


def _recover_from_activity(conn, user, log):
    """A lower bound, for accounts that never had a trial."""
    for name in ('job', 'invoice'):
        child_cols = _columns(conn, name)
        if {'user_id', 'created_at'} - child_cols:
            continue
        child = sa.table(name,
                         sa.column('user_id', sa.Integer),
                         sa.column('created_at', sa.DateTime))
        earliest = dict(conn.execute(
            sa.select(child.c.user_id, sa.func.min(child.c.created_at))
            .group_by(child.c.user_id)).fetchall())

        missing = _still_missing(conn, user)
        recovered = 0
        for user_id in missing:
            when = earliest.get(user_id)
            if when is None:
                continue
            conn.execute(user.update().where(user.c.id == user_id).values(
                created_at=when))
            recovered += 1
        if recovered:
            log('  %d conturi au primit o limita inferioara din %s, nu o '
                'data exacta' % (recovered, name))


def upgrade():
    op.add_column('user', sa.Column('created_at', sa.DateTime(), nullable=True))
    op.add_column('user', sa.Column(
        'is_admin', sa.Boolean(), nullable=False, server_default='0'))
    op.create_index('ix_user_created_at', 'user', ['created_at'], unique=False)

    conn = op.get_bind()
    # A typed table() so SQLAlchemy converts between the database string and a
    # datetime in both directions. Without the types SQLite hands back strings
    # and "trial_ends_at - 14 days" blows up on a str.
    user = sa.table('user',
                    sa.column('id', sa.Integer),
                    sa.column('trial_ends_at', sa.DateTime),
                    sa.column('created_at', sa.DateTime))

    def log(message):
        # Straight to stdout, which is what a deploy log is made of.
        print('migrate 0003: %s' % message)

    log('recuper data de inregistrare')
    _recover_from_trial(conn, user, log)
    _recover_from_activity(conn, user, log)

    left = len(_still_missing(conn, user))
    if left:
        log('ATENTIE: %d conturi au ramas fara data, pentru ca nu au trial si '
            'nicio activitate din care sa o deducem. Au ramas null, nu '
            'inventate.' % left)
    else:
        log('toate conturile au primit o data')


def downgrade():
    op.drop_index('ix_user_created_at', table_name='user')
    op.drop_column('user', 'is_admin')
    op.drop_column('user', 'created_at')
