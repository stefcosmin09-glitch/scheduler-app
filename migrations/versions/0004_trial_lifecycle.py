"""Trial lifecycle emails: remember which ones were sent.

Adds user.trial_emails_sent, a comma-separated list of the lifecycle emails
already delivered (d10, d13, expired, deletion_warning). The old boolean
trial_reminder_sent is kept so existing rows and code paths keep working; it is
no longer written by the new reminder logic.
"""
from alembic import op
import sqlalchemy as sa

revision = '0004_trial_lifecycle'
down_revision = '0003_admin_user_created_at'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user', sa.Column('trial_emails_sent', sa.String(length=100), nullable=True))


def downgrade():
    op.drop_column('user', 'trial_emails_sent')
