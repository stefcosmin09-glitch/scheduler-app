"""add business payment link url

Revision ID: a1b2c3d4e5f6
Revises: 40239004c13c
Create Date: 2026-09-16 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '40239004c13c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('business_profile', schema=None) as batch_op:
        batch_op.add_column(sa.Column('payment_link_url', sa.String(length=500), nullable=True))


def downgrade():
    with op.batch_alter_table('business_profile', schema=None) as batch_op:
        batch_op.drop_column('payment_link_url')