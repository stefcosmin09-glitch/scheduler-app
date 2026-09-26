"""Throttling for the sign-in form.

A login form with no limit is a free password oracle, so this is the test that
says the form stops answering once a caller runs out of allowance, and, just as
importantly, that it cannot be used to find out which addresses have accounts.

The counters live in the database rather than in a dict in the worker, because
gunicorn runs one worker today but Railway can scale the service out and
--workers is one flag away. An in-process counter would quietly hand every
caller N times the allowance, which is worse than no throttle at all because it
still looks like protection.
"""
import time
from datetime import datetime, timedelta

from flask import request

from app import login_throttle
from app.models import LoginAttempt, User
from _support import app, csrf, db  # noqa: F401
from werkzeug.security import generate_password_hash

HEADERS = {'X-Forwarded-For': '203.0.113.7'}


def _email(username):
    return '%s@t.test' % username


def _register(username, password='correct-horse'):
    """A real user, so the password check passes rather than short-circuit."""
    with app.app_context():
        db.session.add(User(username=username, email=_email(username),
                            password=generate_password_hash(password)))
        db.session.commit()


def _post(client, email, password='wrong', ip=HEADERS['X-Forwarded-For']):
    return client.post('/login',
                       data={'email': email, 'password': password,
                             'csrf_token': csrf(client)},
                       headers={'X-Forwarded-For': ip},
                       follow_redirects=True)


def _body(response):
    """The page as text, so a message can be asserted on as a phrase.

    Filtering it down to the words that look interesting was tried first and
    shredded every message it was meant to check: keeping only the words
    containing "attempt" or "wrong" turns "Too many failed attempts" into
    "attempts.".
    """
    return ' '.join(response.data.decode('utf-8').split())


def _row(scope, key):
    with app.app_context():
        return LoginAttempt.query.filter_by(scope=scope, key=key).first()


def _age_back(scope, key, minutes):
    """Move a counter's window and its lock into the past, so both can be
    tested without sleeping through them.

    Done as a query update rather than by assigning to a fetched row. That row
    comes from its own app context, so it is detached by the time a second one
    is opened, and assigning to it and committing elsewhere silently persists
    nothing, which left two of these tests passing for the wrong reason.

    The lock is aged rather than cleared: clearing it would not test expiry at
    all, it would just remove the thing being expired.
    """
    with app.app_context():
        past = datetime.utcnow() - timedelta(minutes=minutes)
        LoginAttempt.query.filter_by(scope=scope, key=key).update(
            {'window_started_at': past, 'last_attempt_at': past,
             'locked_until': past},
            synchronize_session=False)
        db.session.commit()


def _spray(client, ip, count, prefix='spray'):
    """`count` failures from one address, each against a different account.

    A distinct address per attempt on purpose: reusing one would trip the
    per-email counter after five and the per-address counter would stop being
    fed, so the test would end up measuring the wrong thing.
    """
    for n in range(count):
        _post(client, '%s%d@nowhere.test' % (prefix, n), ip=ip)


# --- the throttle engages --------------------------------------------------

def test_wrong_password_is_still_reported_normally(client):
    _register('u1')
    body = _body(_post(client, _email('u1')))
    assert 'Wrong email or password' in body, body


def test_a_correct_password_still_works(client):
    _register('u2')
    response = _post(client, _email('u2'), password='correct-horse')
    assert 'Wrong email' not in response.data.decode('utf-8')


def test_the_email_is_locked_after_five_failures(client):
    _register('u3')
    for _ in range(login_throttle.EMAIL_LIMIT):
        _post(client, _email('u3'))
    body = _body(_post(client, _email('u3')))
    assert 'Too many failed attempts' in body, body


def test_the_right_password_is_refused_while_locked(client):
    """The point of the whole thing: a locked address cannot simply try the
    correct password until it sticks."""
    _register('u4')
    for _ in range(login_throttle.EMAIL_LIMIT):
        _post(client, _email('u4'))
    response = _post(client, _email('u4'), password='correct-horse')
    assert 'Too many failed attempts' in _body(response)
    assert 'Dashboard' not in response.data.decode('utf-8'), \
        'a locked email got in with the right password'


def test_a_successful_sign_in_clears_the_email_counter(client):
    """Two typos and then the right password must not leave a lock waiting to
    fall on the user later."""
    _register('u5')
    _post(client, _email('u5'))
    _post(client, _email('u5'))
    assert _row('email', _email('u5')) is not None, 'failures were not counted'
    _post(client, _email('u5'), password='correct-horse')
    assert _row('email', _email('u5')) is None, \
        'the counter survived a good password'


def test_the_lock_expires(client):
    _register('u6')
    for _ in range(login_throttle.EMAIL_LIMIT):
        _post(client, _email('u6'))
    row = _row('email', _email('u6'))
    assert row is not None and row.locked_until is not None

    # Two hours on, the lock is history and the window has rolled over.
    _age_back('email', _email('u6'), 120)
    body = _body(_post(client, _email('u6'), password='correct-horse'))
    assert 'Too many failed attempts' not in body, body
    assert 'Wrong email' not in body, body


def test_the_window_rolls_over():
    """More failures than the limit allows, each one further back than the
    window is long, must never add up to a lock.

    Driven through record_failure rather than through the form. Ageing a
    counter through HTTP cannot separate the two effects at work here: the
    first lock lasts a minute and the window is fifteen, so anything moved far
    enough back to matter has already expired the lock as well, and the count
    is never seen to climb.
    """
    address = '198.51.100.60'
    email = 'window@t.test'
    headers = {'X-Forwarded-For': address}

    for _ in range(login_throttle.EMAIL_LIMIT + 2):
        with app.test_request_context('/login', headers=headers):
            LoginAttempt.query.filter_by(scope='email', key=email).update(
                {'window_started_at': (datetime.utcnow()
                                      - timedelta(minutes=20)),
                 'locked_until': None},
                synchronize_session=False)
            db.session.commit()
            login_throttle.record_failure(email, address)

    with app.app_context():
        row = LoginAttempt.query.filter_by(scope='email', key=email).first()
        assert row is not None
        assert row.failed_count == 1, \
            'the count reached %d, so the window is not being honoured' % (
                row.failed_count)
        assert login_throttle.locked_until(email, address) is None, \
            'failures spread further apart than the window still added up'


def test_backoff_grows_with_repeated_failures():
    first = login_throttle._backoff_for(login_throttle.EMAIL_LIMIT, 5)
    later = login_throttle._backoff_for(login_throttle.EMAIL_LIMIT + 3, 5)
    assert later > first, 'a caller who keeps going is not made to wait longer'
    assert login_throttle._backoff_for(50, 5) == login_throttle.MAX_BACKOFF, \
        'the wait is not capped'


# --- two counters, two jobs ------------------------------------------------

def test_one_address_spraying_many_accounts_is_throttled(client):
    """The per-address counter is the one that catches this, and it is checked
    separately from the per-email one."""
    for name in ('s1', 's2', 's3', 's4', 's5'):
        _register(name)
    _spray(client, '198.51.100.9', login_throttle.IP_LIMIT)
    body = _body(_post(client, _email('s2'), ip='198.51.100.9'))
    assert 'Too many failed attempts' in body, \
        'one address got %d tries across %d accounts with no complaint' % (
            login_throttle.IP_LIMIT, 5)


def test_the_address_limit_is_looser_than_the_email_limit():
    """Offices and mobile carriers put many unrelated people behind one
    address, so a tight per-address limit would lock out honest users over
    somebody else's typos."""
    assert login_throttle.IP_LIMIT > login_throttle.EMAIL_LIMIT * 2, \
        'the per-address limit is tight enough to punish a shared office'


def test_one_account_sprayed_from_many_addresses_is_throttled(client):
    """...and the reverse, which the per-email counter catches."""
    _register('u8')
    for n in range(login_throttle.EMAIL_LIMIT):
        _post(client, _email('u8'), ip='198.51.100.%d' % (10 + n))
    row = _row('email', _email('u8'))
    assert row is not None and row.locked_until is not None, \
        'changing address bought a fresh allowance'


def test_casing_variants_do_not_buy_a_fresh_allowance(client):
    """The counter is casefolded, so this does not reset at 'U9@T.TEST'."""
    _register('u9')
    for _ in range(login_throttle.EMAIL_LIMIT - 1):
        _post(client, _email('u9'))
    _post(client, 'U9@T.TEST')
    body = _body(_post(client, '  u9@T.Test  '))
    assert 'Too many failed attempts' in body, body


def test_a_locked_address_cannot_sign_in_at_all(client):
    """A locked address is refused before the password is even looked at, so
    there is no way in from it, not even with the right password."""
    _register('u10')
    _register('victim')
    _spray(client, '198.51.100.20', login_throttle.IP_LIMIT)
    body = _body(_post(client, _email('u10'), password='correct-horse',
                       ip='198.51.100.20'))
    assert 'Too many failed attempts' in body, \
        'a locked address got in with a correct password'


def test_a_successful_sign_in_does_not_clear_the_address_counter(client):
    """Otherwise one valid account is a key that hands out a fresh per-address
    allowance at will, and a spray can be interleaved with a good login.

    Kept below the limit on purpose: a locked address cannot sign in at all, so
    the sign-in would never reach the reset. Nothing in clear() can reach the
    address counter either, since it is only handed an email, and this is here
    to keep it that way rather than to catch a change that is currently
    impossible to make.
    """
    _register('u10b')
    _spray(client, '198.51.100.21', login_throttle.EMAIL_LIMIT, prefix='pre')
    before = _row('ip', '198.51.100.21')
    assert before is not None and before.failed_count > 0

    _post(client, _email('u10b'), password='correct-horse', ip='198.51.100.21')

    after = _row('ip', '198.51.100.21')
    assert after is not None, 'the address counter was deleted by a good login'
    assert after.failed_count == before.failed_count, \
        'the address counter was reset by a good login'


# --- not telling an attacker who has an account ----------------------------

def test_unknown_and_known_addresses_are_throttled_identically(client):
    """Counters are kept for addresses that match nobody, so the lockout cannot
    be used to enumerate who is registered."""
    for _ in range(login_throttle.EMAIL_LIMIT):
        _post(client, 'nobody@nowhere.test', ip='198.51.100.30')
    body = _body(_post(client, 'nobody@nowhere.test', ip='198.51.100.30'))
    assert 'Too many failed attempts' in body, body


def test_the_lockout_message_does_not_distinguish_the_two_cases(client):
    _register('u11')
    for _ in range(login_throttle.EMAIL_LIMIT):
        _post(client, _email('u11'))
    body = _body(_post(client, _email('u11')))
    assert 'Wrong email or password' not in body, \
        'the locked message still distinguishes the two cases'


def test_a_missing_account_takes_as_long_as_a_wrong_password(client):
    """check_password_hash is slow on purpose. Returning early for an unknown
    address answered in a fraction of the time, which made the form a way to
    list the users."""
    _register('u12')
    with app.test_request_context():
        started = time.perf_counter()
        for _ in range(3):
            _post(client, 'ghost@nowhere.test', ip='198.51.100.40')
        unknown = time.perf_counter() - started

        started = time.perf_counter()
        for _ in range(3):
            _post(client, _email('u12'), ip='198.51.100.40')
        known = time.perf_counter() - started

    # Generous on purpose: this runs on a shared machine and the point is to
    # catch an early return, not to measure a hash.
    assert unknown > known * 0.6, \
        'an unknown address was answered in %.3fs against %.3fs for a known ' \
        'one, which is enough to enumerate accounts' % (unknown, known)


# --- the address behind the proxy -----------------------------------------

def test_the_client_address_survives_the_proxy(client):
    """Without ProxyFix the app sees the address of the proxy in front of it,
    so every caller on the internet counts as one and a single attacker would
    lock out everybody.

    Driven through the test client because ProxyFix wraps the WSGI app, and a
    bare request context never reaches it.
    """
    _post(client, 'pf@nowhere.test', ip='198.51.100.77')
    assert _row('ip', '198.51.100.77') is not None, \
        'the forwarded address is not what is being counted'
    assert _row('ip', '127.0.0.1') is None, \
        'the proxy or loopback address is being counted instead'


def test_two_callers_behind_one_proxy_are_counted_apart(client):
    """The failure mode of a missing ProxyFix, stated as a test."""
    _post(client, 'pf1@nowhere.test', ip='198.51.100.78')
    _post(client, 'pf2@nowhere.test', ip='198.51.100.79')
    assert _row('ip', '198.51.100.78') is not None
    assert _row('ip', '198.51.100.79') is not None


def test_a_request_without_a_forwarded_address_is_still_counted():
    """Local development has no proxy and must not be broken by the fix."""
    with app.test_request_context('/login', environ_base={'REMOTE_ADDR': '10.0.0.9'}):
        assert login_throttle.address_key() == '10.0.0.9'


def test_a_missing_address_falls_back_to_a_shared_bucket():
    """A constant is the safe direction: it can still be throttled, and it
    cannot be used to slip past a limit."""
    with app.test_request_context('/login', environ_base={'REMOTE_ADDR': ''}):
        assert login_throttle.address_key() == 'unknown'


# --- housekeeping ----------------------------------------------------------

def test_old_rows_are_pruned(client):
    """The table would otherwise grow one row per address ever seen."""
    for n in range(login_throttle.EMAIL_LIMIT):
        _post(client, 'stale%d@nowhere.test' % n, ip='198.51.100.50')
    with app.app_context():
        LoginAttempt.query.filter(
            LoginAttempt.last_attempt_at
            < datetime.utcnow() - timedelta(days=3)).update(
                {'last_attempt_at': datetime.utcnow() - timedelta(days=3)},
                synchronize_session=False)
        db.session.commit()
        stale = LoginAttempt.query.count()

    # One more failure is enough to trigger the sweep.
    _post(client, 'fresh@nowhere.test', ip='198.51.100.51')

    with app.app_context():
        survivors = LoginAttempt.query.filter(
            LoginAttempt.last_attempt_at
            < datetime.utcnow() - login_throttle.PRUNE_AFTER).count()
        assert stale > 0, 'nothing was old enough to be worth pruning'
        assert survivors == 0, \
            '%d rows older than the prune window survived' % survivors


def test_a_locked_address_still_serves_the_form(client):
    """A refusal that is not a 500 and does not lock the person out of their
    own account page once the wait is over."""
    _register('u13')
    for _ in range(login_throttle.EMAIL_LIMIT):
        _post(client, _email('u13'))
    response = client.get('/login')
    assert response.status_code == 200
