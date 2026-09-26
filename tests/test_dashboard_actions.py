"""The dashboard's job actions must render as forms, not links.

The POST-only routes in test_time_tracking.py are only reachable through this
markup, so a template edit that turned the buttons back into <a href> would
405 the moment somebody clicked. These assert the shape rather than the
behaviour.
"""
import re
from datetime import datetime

from werkzeug.security import generate_password_hash

from _support import app, check, db, login
from app.models import Job, User

ACTION = re.compile(
    r'<form method="POST" action="/job/(?:delete|done)/\d+".*?</form>', re.S)


def _dashboard(client):
    with app.app_context():
        user = User(username='lay', email='lay@t.test',
                    password=generate_password_hash('pw'), plan='pro')
        db.session.add(user)
        db.session.flush()
        for i in range(3):
            db.session.add(Job(user_id=user.id, client_name='Client %d' % i,
                               address='Adresa %d' % i,
                               date=datetime.utcnow(), status='pending'))
        db.session.commit()
    login(client, 'lay')
    return client.get('/').get_data(as_text=True)


def test_both_actions_render_per_job(client):
    body = _dashboard(client)
    check('three delete forms', body.count('action="/job/delete/'), 3)
    check('three done forms', body.count('action="/job/done/'), 3)
    check('at least one job is listed', 'Client 0' in body, True)


def test_every_action_form_carries_a_token(client):
    forms = ACTION.findall(_dashboard(client))
    check('found the action forms', len(forms) >= 2, True)
    for form in forms:
        check('form has a button', '<button' in form, True)
        check('form has a token', 'csrf_token' in form, True)
        check('form is closed', form.strip().endswith('</form>'), True)


def test_no_get_links_survive(client):
    body = _dashboard(client)
    check('no GET link to delete', 'href="/job/delete/' in body, False)
    check('no GET link to done', 'href="/job/done/' in body, False)


def test_buttons_keep_their_look(client):
    body = _dashboard(client)
    check('delete keeps its icon', '\U0001F5D1' in body, True)
    check('done keeps its icon', '✅' in body, True)
    check('delete still confirms', 'confirm(' in body, True)


def test_tags_balance(client):
    """A form left unclosed would swallow the rest of the card."""
    body = _dashboard(client)
    check('every form is closed', body.count('<form') == body.count('</form>'), True)
