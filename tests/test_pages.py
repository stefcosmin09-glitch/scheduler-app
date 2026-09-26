"""Pages touched by time tracking must keep rendering, with CSRF intact.

Each page is requested the way a signed-in user reaches it, so a template
that loses a token or a route that starts raising shows up here.
"""
from datetime import datetime

from werkzeug.security import generate_password_hash

from _support import app, check, db, login
from app.models import Job, User

PAGES = ['/', '/time', '/business-settings', '/job/add', '/invoices', '/expenses']


def _seed(client):
    with app.app_context():
        db.drop_all()
        db.create_all()
        user = User(username='reg1', email='reg1@t.test',
                    password=generate_password_hash('pw'), plan='pro')
        db.session.add(user)
        db.session.flush()
        job = Job(user_id=user.id, client_name='C', address='A',
                  date=datetime.utcnow(), status='pending')
        db.session.add(job)
        db.session.commit()
    login(client, 'reg1')


def test_feature_pages_render(client):
    _seed(client)
    for path in PAGES:
        check('%s returns 200' % path, client.get(path).status_code, 200)


def test_navigation_links_to_time(client):
    _seed(client)
    body = client.get('/').get_data(as_text=True)
    check('nav links to /time', 'href="/time"' in body, True)
    check('nav links to settings', 'href="/business-settings"' in body, True)


def test_forms_carry_a_csrf_token(client):
    _seed(client)
    for path in ('/time', '/job/add'):
        body = client.get(path).get_data(as_text=True)
        check('%s has a csrf_token' % path,
              body.count('name="csrf_token"') >= 1, True)


def test_calendar_feed_served_over_http(client):
    _seed(client)
    with app.app_context():
        user = User.query.get(1)
        user.calendar_token = 'tok-reg'
        db.session.commit()

    response = client.get('/calendar/tok-reg.ics')
    check('feed returns 200', response.status_code, 200)
    check('content type is text/calendar',
          'text/calendar' in response.headers.get('Content-Type', ''), True)
    check('uses CRLF line endings',
          '\r\n' in response.get_data(as_text=True), True)
