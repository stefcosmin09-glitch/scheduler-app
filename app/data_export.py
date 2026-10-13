"""Full export of one user's data as a ZIP of CSV files.

Available to every account, including read-only ones: a user whose trial has
ended must always be able to take their data away. Columns are read from the
table definitions rather than listed by hand, so a new column is exported
without anyone remembering to add it. Password hashes are never included.
"""
import csv
import io
import zipfile

from app.models import BusinessProfile, Expense, Invoice, Job, Payment, User

_EXCLUDED_COLUMNS = {
    User: {'password', 'calendar_token', 'stripe_customer_id', 'stripe_subscription_id'},
}


def _csv_bytes(model, rows):
    excluded = _EXCLUDED_COLUMNS.get(model, set())
    columns = [c.name for c in model.__table__.columns if c.name not in excluded]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(getattr(row, name)) for name in columns])
    return out.getvalue().encode('utf-8-sig')


def _cell(value):
    if value is None:
        return ''
    return value


def build_export(user):
    """Return a BytesIO holding the ZIP, positioned at the start."""
    tables = [
        ('account.csv', User, [user]),
        ('business_profile.csv', BusinessProfile,
         BusinessProfile.query.filter_by(user_id=user.id).all()),
        ('jobs.csv', Job, Job.query.filter_by(user_id=user.id).all()),
        ('invoices.csv', Invoice, Invoice.query.filter_by(user_id=user.id).all()),
        ('payments.csv', Payment,
         Payment.query.join(Invoice, Payment.invoice_id == Invoice.id)
         .filter(Invoice.user_id == user.id).all()),
        ('expenses.csv', Expense, Expense.query.filter_by(user_id=user.id).all()),
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as archive:
        for filename, model, rows in tables:
            archive.writestr(filename, _csv_bytes(model, rows))
    buf.seek(0)
    return buf
