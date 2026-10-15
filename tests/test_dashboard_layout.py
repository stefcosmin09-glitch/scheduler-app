"""The dashboard has to fit a phone without scrolling sideways.

Every row that used to be a fixed two- or three-column grid now stacks until
the columns genuinely fit, and the one-column grid tracks are clamped with
minmax(0, 1fr) so a wide value cannot stretch a track past the viewport. A unit
test cannot measure layout, so these pin the markup and the CSS that make it
true: the bug was a page that scrolled sideways at 320px, and the way it comes
back is an edit that restores "grid grid-cols-2" or drops the wrapping.
"""
import os
import re
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from _support import app, check, db, login
from app.models import Invoice, Job, User

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_CSS = os.path.join(ROOT, 'app', 'static', 'app.css')
BASE_HTML = os.path.join(ROOT, 'app', 'templates', 'base.html')


def read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


def dashboard(client, days_overdue=1):
    """A signed-in dashboard holding exactly one overdue invoice."""
    with app.app_context():
        user = User(username='phone', email='phone@t.test',
                    password=generate_password_hash('pw'), plan='pro')
        db.session.add(user)
        db.session.flush()
        job = Job(user_id=user.id, client_name='Neil Carter',
                  address='3 Orchard Close, Bracknell RG12 7TT',
                  date=datetime.utcnow(), status='pending')
        db.session.add(job)
        db.session.flush()
        db.session.add(Invoice(
            invoice_number='INV-0001', user_id=user.id, job_id=job.id,
            issue_date=datetime.utcnow() - timedelta(days=30),
            due_date=datetime.utcnow() - timedelta(days=days_overdue),
            subtotal=576, vat_amount=0, total_amount=576, status='overdue'))
        db.session.commit()

    login(client, 'phone')
    response = client.get('/')
    check('dashboard renders', response.status_code, 200)
    return response.get_data(as_text=True)


def test_one_day_overdue_is_singular(client):
    body = dashboard(client, days_overdue=1)
    check('reads "1 day overdue"', '1 day overdue' in body, True)
    check('not the unpluralised form', '1 days overdue' in body, False)


def test_several_days_overdue_stay_plural(client):
    body = dashboard(client, days_overdue=3)
    check('reads "3 days overdue"', '3 days overdue' in body, True)


def test_card_rows_stack_instead_of_forcing_columns(client):
    body = dashboard(client)
    check('stat row uses the stacking class', 'ts-stat-grid' in body, True)
    check('money row uses the stacking class', 'ts-money-grid' in body, True)
    check('no fixed two-column stat row', 'grid-cols-2 gap-4' in body, False)
    check('no fixed three-column money row', 'grid-cols-3 gap-3' in body, False)


def test_job_card_wraps_and_its_track_is_clamped(client):
    body = dashboard(client)
    check('job card uses the stacking class', 'ts-job-card' in body, True)
    check('job actions use the wrapping class', 'ts-job-actions' in body, True)
    check('job list track cannot stretch', 'grid grid-cols-1 gap-4' in body, True)


def test_css_stacks_then_restores_the_columns():
    css = read(APP_CSS)
    for selector in ('.ts-stat-grid', '.ts-money-grid', '.ts-job-card',
                     '.ts-job-actions', '.ts-nav-row'):
        check('%s is defined' % selector, selector in css, True)
    check('one-column track is clamped',
          re.search(r'grid-template-columns: minmax\(0, 1fr\)', css)
          is not None, True)
    check('two stat cards return from 400px',
          re.search(r'@media \(min-width: 400px\) \{\s*\.ts-stat-grid', css)
          is not None, True)
    check('three money boxes return from 480px',
          re.search(r'@media \(min-width: 480px\) \{\s*\.ts-money-grid', css)
          is not None, True)
    check('job card returns to a right-hand action column from 640px',
          re.search(r'@media \(min-width: 640px\) \{\s*\.ts-job-card', css)
          is not None, True)


def test_nav_row_wraps_instead_of_overflowing():
    html = read(BASE_HTML)
    check('nav row may wrap', 'ts-nav-row' in html, True)
