"""Failed sign-in counters for the login throttle.

The first migration after the squash, and the reason migrate.py stamps a
squashed database to 0001 rather than to head. A database built before the
squash has the schema 0001 describes and nothing after it, so writing 0002 onto
it directly would mark a migration as applied that never ran, and the table
below would never exist.

Revision ID: 0002_login_throttle
Revises: 0001_initial_schema
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0002_login_throttle'
down_revision = '0001_initial_schema'
branch_labels = None
depends_on = None


def upgrade():
    # The unique constraint is also the lookup index: every read of this table
    # is "one scope, one key", and the periodic prune sweeps last_attempt_at.
    op.create_table(
        'login_attempt',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scope', sa.String(length=10), nullable=False),
        sa.Column('key', sa.String(length=255), nullable=False),
        sa.Column('failed_count', sa.Integer(), nullable=False),
        sa.Column('window_started_at', sa.DateTime(), nullable=False),
        sa.Column('locked_until', sa.DateTime(), nullable=True),
        sa.Column('last_attempt_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scope', 'key', name='uq_login_attempt_scope_key'),
    )


def downgrade():
    op.drop_table('login_attempt')
