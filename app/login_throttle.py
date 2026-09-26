"""Throttling for the sign-in form.

An unthrottled login form hands an attacker a free password oracle, so this
counts failures and refuses to keep checking passwords once a caller has run
out of allowance. Two counters, and both have to be under their limit:

  per email   stops one account being sprayed from many addresses
  per address stops one address spraying many accounts

The per-address limit is deliberately much looser than the per-email one.
Offices, mobile carriers and coffee shops put a lot of unrelated people behind
one address, and a tight limit there locks out honest users over somebody
else's typos. That trade is worth making in this direction: an over-tight
per-address limit is a support problem, an over-loose one still leaves the
per-email limit, which is the one that protects an individual account.

Not in app/limits.py, which is about what a plan is allowed to use rather than
about how hard someone may hit a form.
"""
from datetime import datetime, timedelta

from app import db
from app.models import LoginAttempt

# Failures allowed inside the window before the email is refused. Five is the
# usual compromise: a person fat-fingering a password gets a few tries, and
# nobody needs more.
EMAIL_LIMIT = 5

# Much higher on purpose, see the module docstring. Shared addresses are real.
IP_LIMIT = 20

# How long failures accumulate before the count is forgotten. Long enough that
# a scripted run cannot trickle, short enough that a genuine mistake is not
# remembered for a day.
WINDOW = timedelta(minutes=15)

# First lockout, doubled per extra failure up to MAX_BACKOFF, so a caller who
# keeps going waits longer and longer. Without the growth a five-minute lock is
# just an inconvenience to wait out between bursts.
FIRST_BACKOFF = timedelta(minutes=1)
MAX_BACKOFF = timedelta(hours=4)

# Rows older than the window are dead weight. Pruned on write, because a
# scheduled job would mean another moving part in the deploy.
PRUNE_AFTER = timedelta(days=1)

EMAIL = 'email'
IP = 'ip'


def _now():
    return datetime.utcnow()


def email_key(email):
    """Casefolded so casing variants cannot buy a fresh allowance.

    Only used for the counter, never for finding the user, because the register
    route stores the address exactly as typed and normalising there would lock
    out anyone who signed up with capitals in their email.
    """
    return (email or '').strip().lower()[:255]


def address_key():
    """The caller's address, or a bucket for when it is not usable.

    ProxyFix in create_app() is what makes this the real client rather than the
    proxy in front of the app. Returning a constant rather than '' keeps an
    unknown address counted under one shared key, which is the safe direction:
    it can throttle, it cannot be used to slip past a limit.
    """
    from flask import request
    return (request.remote_addr or 'unknown')[:255]


def _row(scope, key):
    return LoginAttempt.query.filter_by(scope=scope, key=key).first()


def _prune(now):
    try:
        LoginAttempt.query.filter(
            LoginAttempt.last_attempt_at < now - PRUNE_AFTER).delete(
                synchronize_session=False)
        db.session.commit()
    except Exception:
        # Housekeeping must never be the reason a sign-in fails.
        db.session.rollback()


def locked_until(email, address):
    """When the email is refused again, or None if it is not locked.

    Checks both counters and reports the later of the two, because that is how
    long the caller actually has to wait.
    """
    now = _now()
    limit_for = {EMAIL: EMAIL_LIMIT, IP: IP_LIMIT}
    keys = {EMAIL: email_key(email), IP: address}
    waits = []
    for scope, key in keys.items():
        row = _row(scope, key)
        if row is None or row.locked_until is None:
            continue
        if row.locked_until <= now:
            continue
        waits.append(row.locked_until)
    if not waits:
        return None
    return max(waits)


def seconds_remaining(email, address):
    until = locked_until(email, address)
    if until is None:
        return 0
    return max(0, int((until - _now()).total_seconds()))


def record_failure(email, address):
    """Count one failed attempt against both the email and the address."""
    now = _now()
    _prune(now)
    for scope, key, limit in ((EMAIL, email_key(email), EMAIL_LIMIT),
                              (IP, address, IP_LIMIT)):
        if not key:
            continue
        row = _row(scope, key)
        if row is None:
            row = LoginAttempt(scope=scope, key=key, failed_count=0,
                               window_started_at=now)
            db.session.add(row)
        elif row.window_started_at is None or now - row.window_started_at > WINDOW:
            # The window closed, so this is a fresh start rather than an
            # extension of an old count.
            row.failed_count = 0
            row.window_started_at = now
            row.locked_until = None
        row.failed_count = (row.failed_count or 0) + 1
        row.last_attempt_at = now
        if row.failed_count >= limit:
            row.locked_until = now + _backoff_for(row.failed_count, limit)
    db.session.commit()


def _backoff_for(failures, limit):
    if failures <= limit:
        return FIRST_BACKOFF
    steps = failures - limit
    return min(FIRST_BACKOFF * (2 ** min(steps - 1, 16)), MAX_BACKOFF)


def clear(email):
    """Forget the failures for this address' owner after a good password.

    Only the email counter is reset. Clearing the address counter too would
    hand out a bypass: hold one valid account, fail a lot, sign in cleanly and
    the per-address allowance is back. The address counter is left to age out
    of its window, which is the whole point of having one.
    """
    try:
        LoginAttempt.query.filter_by(scope=EMAIL, key=email_key(email)).delete(
            synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()


def waiting_message(seconds):
    """What to tell someone who is genuinely locked out.

    Deliberately does not say whether the address is known, and the counters
    are kept for addresses that do not exist, so this cannot be used to find
    out which emails are registered.
    """
    if seconds < 60:
        return 'Too many failed attempts. Try again in a moment.'
    minutes = max(1, round(seconds / 60))
    if minutes == 1:
        return 'Too many failed attempts. Try again in about a minute.'
    if minutes < 60:
        return 'Too many failed attempts. Try again in about %d minutes.' % minutes
    hours = max(1, round(minutes / 60))
    return 'Too many failed attempts. Try again in about %d hour%s.' % (
        hours, '' if hours == 1 else 's')
