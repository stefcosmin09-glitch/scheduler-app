"""Trial lifecycle: reminder emails, read-only after the trial, export and deletion."""
import io
import os
import types
import zipfile
from datetime import datetime, timedelta

import pytest

from _support import app, check, csrf, db, login, make_job, make_user, register
from app import trial_lifecycle
from app.models import Job, User
from app.trial_lifecycle import next_stage, run_trial_lifecycle


@pytest.fixture(autouse=True)
def restore_retention_env():
    saved = os.environ.get('DATA_RETENTION_DELETE')
    yield
    if saved is None:
        os.environ.pop('DATA_RETENTION_DELETE', None)
    else:
        os.environ['DATA_RETENTION_DELETE'] = saved


def _account(ends_in_days, plan='free', sent=None):
    now = datetime.utcnow()
    return types.SimpleNamespace(plan=plan, trial_ends_at=now + timedelta(days=ends_in_days),
                                 trial_emails_sent=sent, language='en')


def test_day_10_email_when_four_days_left():
    check('four days left', next_stage(_account(3.5)), 'd10')


def test_day_13_email_when_one_day_left():
    check('one day left', next_stage(_account(0.5)), 'd13')


def test_no_email_early_in_trial():
    check('early trial', next_stage(_account(10)), None)


def test_expired_email_after_trial():
    check('expired', next_stage(_account(-1)), 'expired')


def test_each_stage_sent_once():
    check('d10 already sent', next_stage(_account(3.5, sent='d10')), None)
    check('d13 skips to its own', next_stage(_account(0.5, sent='d10')), 'd13')


def test_deletion_warning_after_53_days_expired():
    acct = _account(-54, sent='expired')
    check('warning due', next_stage(acct), 'deletion_warning')
    acct.trial_emails_sent = 'expired,deletion_warning'
    check('warning once', next_stage(acct), None)


def test_paid_plans_get_no_lifecycle_email():
    check('starter', next_stage(_account(0.5, plan='starter')), None)
    check('pro', next_stage(_account(-1, plan='pro')), None)


def test_read_only_account_cannot_add_jobs():
    client = app.test_client()
    register(client, 'ro1')
    _expire(1)
    client.post('/job/add', data=_job_form(client))
    with app.app_context():
        check('no job created', Job.query.count(), 0)


def test_read_only_redirects_to_settings_with_message():
    client = app.test_client()
    register(client, 'ro2')
    _expire(1)
    resp = client.post('/job/add', data=_job_form(client))
    check('redirect to settings', resp.status_code, 302)
    check('points at settings', resp.headers['Location'].endswith('/business-settings'), True)


def test_pro_account_can_add_jobs():
    client = app.test_client()
    register(client, 'pro1')
    _set(plan='pro', trial_ends_at=None)
    client.post('/job/add', data=_job_form(client))
    with app.app_context():
        check('job created', Job.query.count(), 1)


def test_read_only_account_can_export():
    client = app.test_client()
    register(client, 'ro4')
    _expire(1)
    make_job(1, name='Kept client')
    resp = client.get('/account/export')
    check('export ok', resp.status_code, 200)
    archive = zipfile.ZipFile(io.BytesIO(resp.data))
    names = set(archive.namelist())
    check('has jobs csv', 'jobs.csv' in names, True)
    check('has invoices csv', 'invoices.csv' in names, True)
    check('has expenses csv', 'expenses.csv' in names, True)
    jobs_csv = archive.read('jobs.csv').decode('utf-8-sig')
    check('job data present', 'Kept client' in jobs_csv, True)


def test_export_never_contains_password_hash():
    client = app.test_client()
    register(client, 'ro5')
    resp = client.get('/account/export')
    archive = zipfile.ZipFile(io.BytesIO(resp.data))
    account = archive.read('account.csv').decode('utf-8-sig')
    check('no password column', 'password' in account.splitlines()[0], False)


def test_lifecycle_sends_each_email_once(monkeypatch):
    sent = []
    monkeypatch.setattr(trial_lifecycle, 'send_email',
                        lambda to, subject, body: sent.append(subject) or True)
    _create(username='life1', plan='free', ends_in=-1)
    with app.app_context():
        run_trial_lifecycle()
        run_trial_lifecycle()
    check('one expired email only', len(sent), 1)


def test_lifecycle_marks_only_on_successful_send(monkeypatch):
    monkeypatch.setattr(trial_lifecycle, 'send_email', lambda *a, **k: False)
    _create(username='life2', plan='free', ends_in=-1)
    with app.app_context():
        run_trial_lifecycle()
        check('not marked when send fails', User.query.first().trial_emails_sent, None)


def test_deletion_is_off_by_default():
    os.environ.pop('DATA_RETENTION_DELETE', None)
    _create(username='keep1', plan='free', ends_in=-61)
    with app.app_context():
        deleted = trial_lifecycle.delete_expired_accounts()
        check('nothing deleted', deleted, 0)
        check('account still there', User.query.count(), 1)


def test_deletion_removes_expired_never_subscribed_accounts():
    os.environ['DATA_RETENTION_DELETE'] = '1'
    _create(username='gone1', plan='free', ends_in=-61)
    with app.app_context():
        deleted = trial_lifecycle.delete_expired_accounts()
        check('one deleted', deleted, 1)
        check('no accounts left', User.query.count(), 0)


def test_deletion_keeps_accounts_that_ever_subscribed():
    os.environ['DATA_RETENTION_DELETE'] = '1'
    _create(username='sub1', plan='free', ends_in=-61, subscription='sub_x')
    with app.app_context():
        deleted = trial_lifecycle.delete_expired_accounts()
        check('subscriber kept', deleted, 0)


def test_deletion_keeps_recent_expiries():
    os.environ['DATA_RETENTION_DELETE'] = '1'
    _create(username='recent1', plan='free', ends_in=-10)
    with app.app_context():
        deleted = trial_lifecycle.delete_expired_accounts()
        check('recent kept', deleted, 0)


# ─── helpers ───────────────────────────────────────────

def _job_form(client):
    return {
        'client_name': 'Test client',
        'address': '1 Test Street',
        'date': (datetime.utcnow() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),
        'duration_minutes': '60',
        'price': '100',
        'csrf_token': csrf(client),
    }


def _set(**fields):
    with app.app_context():
        user = User.query.first()
        for key, value in fields.items():
            setattr(user, key, value)
        db.session.commit()


def _expire(days_ago):
    _set(plan='free', trial_ends_at=datetime.utcnow() - timedelta(days=days_ago))


def _create(username, plan, ends_in, subscription=None):
    with app.app_context():
        user = User(username=username, email='%s@t.test' % username, password='x',
                    plan=plan, trial_ends_at=datetime.utcnow() + timedelta(days=ends_in),
                    stripe_subscription_id=subscription)
        db.session.add(user)
        db.session.commit()
