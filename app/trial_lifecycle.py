"""What happens to an account as its 14-day trial runs out.

Timeline for an account that never subscribes:

  day 10   email: four days left
  day 13   email: one day left
  day 14   trial ends; the account becomes read-only
           email: trial ended, here is how to keep going
  day 53   email: your data is deleted in seven days, export it now
  day 60   account and data deleted, only if DATA_RETENTION_DELETE=1

Each email goes out once, recorded in user.trial_emails_sent. Accounts that have
ever held a Stripe subscription are never deleted automatically: a cancelled
subscriber's clock would otherwise start from the trial, not from cancellation.
"""
import os
import threading
from datetime import datetime, timedelta

from app import db
from app.email_service import send_email
from app.models import LoginAttempt, User

# One run at a time. The dashboard fallback and the daily scheduler job can fire
# together; serialising them means the second sees the marks the first just
# wrote instead of sending the same email twice.
_LOCK = threading.Lock()

RETENTION_DAYS = 60
WARNING_DAYS_BEFORE_DELETE = 7
PAID_PLANS = ('pro', 'starter')


def _sent(user):
    return {k for k in (user.trial_emails_sent or '').split(',') if k}


def _mark(user, key):
    sent = _sent(user)
    sent.add(key)
    user.trial_emails_sent = ','.join(sorted(sent))


def next_stage(user, now=None):
    """The one lifecycle email this user is due, or None."""
    now = now or datetime.utcnow()
    if user.plan in PAID_PLANS or not user.trial_ends_at:
        return None
    sent = _sent(user)
    left = user.trial_ends_at - now
    if left > timedelta(0):
        if left <= timedelta(days=1) and 'd13' not in sent:
            return 'd13'
        if left <= timedelta(days=4) and 'd10' not in sent:
            return 'd10'
        return None
    if 'expired' not in sent:
        return 'expired'
    expired_for = now - user.trial_ends_at
    if (expired_for >= timedelta(days=RETENTION_DAYS - WARNING_DAYS_BEFORE_DELETE)
            and 'deletion_warning' not in sent):
        return 'deletion_warning'
    return None


_SUBJECTS = {
    'en': {
        'd10': 'Your TradeScheduler trial: 4 days left',
        'd13': 'Your TradeScheduler trial ends tomorrow',
        'expired': 'Your TradeScheduler trial has ended',
        'deletion_warning': 'Your TradeScheduler data will be deleted in 7 days',
    },
    'ro': {
        'd10': 'Trialul tău TradeScheduler: au mai rămas 4 zile',
        'd13': 'Trialul tău TradeScheduler expiră mâine',
        'expired': 'Trialul tău TradeScheduler s-a încheiat',
        'deletion_warning': 'Datele tale TradeScheduler vor fi șterse în 7 zile',
    },
}

_BODIES = {
    'en': {
        'd10': 'Hi {name},\n\nYour trial ends on {date}. Until then you have every feature unlocked.\n\nChoose a plan before then to keep going: Starter at £12.99 a month, or Pro at £22.99 a month. Cancel anytime.\n\n{url}\n\n— TradeScheduler',
        'd13': 'Hi {name},\n\nYour trial ends tomorrow ({date}). Choose a plan now so you do not lose access to adding jobs and invoices.\n\n{url}\n\n— TradeScheduler',
        'expired': 'Hi {name},\n\nYour trial has ended, so your account is now read-only. Nothing is deleted: you can still see and download all your jobs, invoices and expenses.\n\nTo start adding jobs and invoices again, choose a plan: {url}\n\nYour data is kept for {days} days after the trial ends. Download a copy any time: {export_url}\n\n— TradeScheduler',
        'deletion_warning': 'Hi {name},\n\nYour TradeScheduler account has been read-only for {warn_days} days. In {warn_left} days, your data will be deleted.\n\nTo keep your data, choose a plan: {url}\n\nTo take a copy with you before then: {export_url}\n\n— TradeScheduler',
    },
    'ro': {
        'd10': 'Bună ziua {name},\n\nTrialul tău se încheie pe {date}. Până atunci ai acces la toate funcțiile.\n\nAlege un plan înainte de această dată: Starter la £12.99 pe lună sau Pro la £22.99 pe lună. Anulezi oricând.\n\n{url}\n\n— TradeScheduler',
        'd13': 'Bună ziua {name},\n\nTrialul tău se încheie mâine ({date}). Alege un plan acum ca să nu pierzi accesul la adăugarea de joburi și facturi.\n\n{url}\n\n— TradeScheduler',
        'expired': 'Bună ziua {name},\n\nTrialul tău s-a încheiat, deci contul este acum doar în citire. Nu s-a șters nimic: poți vedea și descărca joburile, facturile și cheltuielile.\n\nCa să adaugi din nou joburi și facturi, alege un plan: {url}\n\nDatele tale sunt păstrate {days} zile după încheierea trialului. Poți descărca o copie oricând: {export_url}\n\n— TradeScheduler',
        'deletion_warning': 'Bună ziua {name},\n\nContul tău TradeScheduler este în modul doar citire de {warn_days} zile. Peste {warn_left} zile, datele tale vor fi șterse.\n\nCa să le păstrezi, alege un plan: {url}\n\nCa să iei o copie înainte: {export_url}\n\n— TradeScheduler',
    },
}


def _email_for(user, stage, base_url):
    lang = 'ro' if (user.language or 'en') == 'ro' else 'en'
    ends = user.trial_ends_at
    expired_for = max(0, (datetime.utcnow() - ends).days) if ends else 0
    fields = {
        'name': user.username,
        'date': ends.strftime('%d/%m/%Y') if ends else '',
        'url': base_url + '/business-settings',
        'export_url': base_url + '/account/export',
        'days': RETENTION_DAYS,
        'warn_days': expired_for,
        'warn_left': max(1, RETENTION_DAYS - expired_for),
    }
    return _SUBJECTS[lang][stage], _BODIES[lang][stage].format(**fields)


def run_trial_lifecycle(now=None):
    """Send each due lifecycle email once, then apply the retention rule."""
    with _LOCK:
        base_url = os.getenv('APP_URL') or 'https://thetradescheduler.com'
        now = now or datetime.utcnow()
        sent_count = 0
        candidates = User.query.filter(
            User.plan.notin_(PAID_PLANS), User.trial_ends_at.isnot(None)).all()
        for user in candidates:
            stage = next_stage(user, now)
            if stage is None:
                continue
            subject, body = _email_for(user, stage, base_url)
            if send_email(user.email, subject, body):
                _mark(user, stage)
                sent_count += 1
        db.session.commit()
        deleted = delete_expired_accounts(now)
        return sent_count, deleted


def _deletion_enabled():
    """True when DATA_RETENTION_DELETE=1, tolerating a stray space in the name.

    Railway keeps a trailing space when a variable name was pasted with one,
    and os.getenv('DATA_RETENTION_DELETE') then returns None even though the
    variable looks perfectly present in the dashboard. A retention rule that
    silently never runs is worse than an unusual lookup, so names are compared
    with surrounding whitespace stripped.
    """
    for key, value in os.environ.items():
        if key.strip() == 'DATA_RETENTION_DELETE':
            return (value or '').strip() == '1'
    return False


def delete_expired_accounts(now=None):
    """Delete never-subscribed accounts 60 days after their trial ended.

    Does nothing unless DATA_RETENTION_DELETE=1, so turning deletion on is a
    deliberate step in the environment, not a side effect of deploying this code.
    """
    if not _deletion_enabled():
        return 0
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=RETENTION_DAYS)
    doomed = User.query.filter(
        User.plan.notin_(PAID_PLANS),
        User.trial_ends_at.isnot(None),
        User.trial_ends_at < cutoff,
        User.stripe_subscription_id.is_(None),
    ).all()
    for user in doomed:
        # The sign-in throttle is keyed by email, not by user id, so the
        # account cascade never reaches it. Left alone it would outlive the
        # data we promised to delete.
        LoginAttempt.query.filter_by(scope='email', key=user.email).delete(
            synchronize_session=False)
        db.session.delete(user)
    db.session.commit()
    return len(doomed)
