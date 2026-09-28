"""The admin view is read-only and confined to accounts that were promoted in
the database, never by the register route.

Three gates are tested, in the order a visitor meets them: anonymous is bounced
to login, a signed-in user without the flag gets 404 so the area does not even
confirm itself, and an admin gets the page. Everything else is about what the
page shows and keeps quiet about.
"""
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from _support import app, db, login, make_user
from app.models import User


def _make_admin(username='owner'):
    with app.app_context():
        user = User(username=username, email='%s@t.test' % username,
                    password=generate_password_hash('pw'), is_admin=True)
        db.session.add(user)
        db.session.commit()
    return username


def _regular(username='regular'):
    """A signed-in, non-admin account whose password matches login()."""
    with app.app_context():
        user = User(username=username, email='%s@t.test' % username,
                    password=generate_password_hash('pw'))
        db.session.add(user)
        db.session.commit()
    return username


def test_anonymous_is_sent_to_login(client):
    response = client.get('/admin/users')
    location = response.headers.get('Location', '')
    assert response.status_code == 302, response.status_code
    assert '/login' in location, \
        'an anonymous visitor was not bounced to login'


def test_a_normal_user_gets_404(client):
    _regular()
    login(client, 'regular')
    assert client.get('/admin/users').status_code == 404


def test_an_admin_gets_the_page(client):
    _make_admin()
    login(client, 'owner')
    assert client.get('/admin/users').status_code == 200


def test_the_list_is_ordered_newest_first(client):
    with app.app_context():
        db.session.add(User(username='owner', email='owner@t.test',
                            password=generate_password_hash('pw'),
                            is_admin=True))
        base = datetime.utcnow()
        for days in (3, 1, 2):
            db.session.add(User(username='u%d' % days,
                                email='u%d@t.test' % days, password='x',
                                created_at=base - timedelta(days=days)))
        db.session.commit()
    login(client, 'owner')

    body = client.get('/admin/users').get_data(as_text=True)
    first = body.index('u1@t.test')
    second = body.index('u2@t.test')
    last = body.index('u3@t.test')
    assert first < second < last, \
        'the list is not newest first: expected u1, u2, u3'


def test_the_search_filters_email(client):
    _make_admin()
    login(client, 'owner')
    make_user('ana')
    make_user('ion')

    body = client.get('/admin/users?q=ana').get_data(as_text=True)
    assert 'ana@t.test' in body
    assert 'ion@t.test' not in body, \
        'the other account leaked through the filter'


def test_search_ignores_lower_and_upper_case(client):
    _make_admin()
    login(client, 'owner')
    make_user('mihai')

    body = client.get('/admin/users?q=MIHAI').get_data(as_text=True)
    assert 'mihai@t.test' in body, \
        'search is case-sensitive, so a capital query misses an email'


def test_missing_date_is_shown_as_unknown(client):
    _make_admin()
    login(client, 'owner')
    with app.app_context():
        user = User.query.get(make_user('ghost'))
        user.created_at = None
        db.session.commit()

    body = client.get('/admin/users').get_data(as_text=True)
    assert 'ghost@t.test' in body
    assert 'unknown' in body


def test_the_detail_page_reads_one_account(client):
    _make_admin()
    login(client, 'owner')
    uid = make_user('viz')

    response = client.get('/admin/users/%d' % uid)
    assert response.status_code == 200
    assert 'viz@t.test' in response.get_data(as_text=True)


def test_a_non_admin_cannot_read_a_detail_page(client):
    _regular()
    login(client, 'regular')
    uid = make_user('target')
    assert client.get('/admin/users/%d' % uid).status_code == 404


def test_the_nav_link_only_shows_for_admins(client):
    _make_admin()
    login(client, 'owner')
    assert '/admin/users' in client.get('/').get_data(as_text=True)

    with app.app_context():
        owner = User.query.filter_by(username='owner').one()
        owner.is_admin = False
        plain = User(username='plain', email='plain@t.test',
                     password=generate_password_hash('pw'))
        db.session.add_all([owner, plain])
        db.session.commit()
    login(client, 'plain')
    plain_nav = client.get('/').get_data(as_text=True)
    assert '/admin/users' not in plain_nav, \
        'the admin link leaks to users who cannot use it'


def test_the_pages_are_read_only(client):
    """Nothing on any admin route may mutate, whatever method it is asked
    for."""
    _make_admin()
    login(client, 'owner')
    uid = make_user('frozen')
    for route in ('/admin/users', '/admin/users/%d' % uid):
        assert client.post(route).status_code == 405, \
            'an admin route accepted a POST (%s)' % route