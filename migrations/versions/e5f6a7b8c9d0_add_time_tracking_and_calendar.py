"""add time tracking and calendar feed

Revision ID: e5f6a7b8c9d0
Revises: c3d4e5f6a7b8
Create Date: 2026-09-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'time_entry',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        # ended_at stays nullable on purpose: a started entry with no end is
        # the timer still running.
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('minutes', sa.Integer(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['job_id'], ['job.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.add_column('job',
                  sa.Column('duration_minutes', sa.Integer(), nullable=False,
                            server_default='60'))
    op.add_column('user',
                  sa.Column('calendar_token', sa.String(length=64), nullable=True))
    op.create_index('ix_user_calendar_token', 'user', ['calendar_token'],
                    unique=True)
    op.create_index('ix_time_entry_user_open', 'time_entry',
                    ['user_id', 'ended_at'])


def downgrade():
    op.drop_index('ix_time_entry_user_open', table_name='time_entry')
    op.drop_index('ix_user_calendar_token', table_name='user')
    op.drop_column('user', 'calendar_token')
    op.drop_column('job', 'duration_minutes')
    op.drop_table('time_entry')
