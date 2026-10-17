"""The app is UK-only for now: GBP and English are the only live options.

Other currencies and Romanian are switched off in app/markets.py, not deleted.
These tests pin that down: a user who saved a switched-off choice gets the
default, the switched-off options are not offered, and the saved value itself
is left alone so it comes back if the market is switched on again.
"""
from werkzeug.security import generate_password_hash

from _support import app, check, db, login, reset_db
from app.markets import ENABLED_CURRENCIES, ENABLED_LANGUAGES, active_currency, active_language
from app.models import User


def test_only_uk_markets_are_enabled():
    check('currencies', ENABLED_CURRENCIES, ('GBP',))
    check('languages', ENABLED_LANGUAGES, ('en',))


def test_switched_off_values_fall_back_to_defaults():
    check('EUR -> GBP', active_currency('EUR'), 'GBP')
    check('RON -> GBP', active_currency('RON'), 'GBP')
    check('None -> GBP', active_currency(None), 'GBP')
    check('ro -> en', active_language('ro'), 'en')
    check('None -> en', active_language(None), 'en')


def test_saved_choices_are_kept_in_the_database():
    reset_db()
    with app.app_context():
        user = User(username='rou', email='rou@t.test',
                    password=generate_password_hash('pw'), plan='trial',
                    language='ro', currency='EUR')
        db.session.add(user)
        db.session.commit()
        uid = user.id
    client = app.test_client()
    login(client, 'rou', 'pw')
    with app.app_context():
        user = db.session.get(User, uid)
        check('saved language untouched', user.language, 'ro')
        check('saved currency untouched', user.currency, 'EUR')


def test_page_shows_english_and_pounds_only():
    reset_db()
    with app.app_context():
        user = User(username='rou', email='rou@t.test',
                    password=generate_password_hash('pw'), plan='trial',
                    language='ro', currency='EUR')
        db.session.add(user)
        db.session.commit()
    client = app.test_client()
    response = login(client, 'rou', 'pw')
    html = response.get_data(as_text=True)
    check('no RO option', 'RO</option>' in html, False)
    check('no Romanian option', 'Română' in html, False)
    check('no EUR option', 'EUR</option>' in html, False)
    check('no RON option', 'lei RON' in html, False)
    check('no USD option', 'USD</option>' in html, False)
    check('no AUD option', 'AUD</option>' in html, False)


def test_settings_page_hides_currency_and_language_choice():
    reset_db()
    with app.app_context():
        user = User(username='uk', email='uk@t.test',
                    password=generate_password_hash('pw'), plan='trial')
        db.session.add(user)
        db.session.commit()
    client = app.test_client()
    login(client, 'uk', 'pw')
    html = client.get('/business-settings').get_data(as_text=True)
    check('no language select', 'name="language"' in html, False)
    check('no currency select', 'name="currency"' in html, False)


def test_set_currency_ignores_switched_off_currency():
    reset_db()
    with app.app_context():
        user = User(username='uk', email='uk@t.test',
                    password=generate_password_hash('pw'), plan='trial')
        db.session.add(user)
        db.session.commit()
        uid = user.id
    client = app.test_client()
    login(client, 'uk', 'pw')
    from _support import csrf
    client.post('/set-currency', data={'currency': 'EUR', 'csrf_token': csrf(client)})
    with app.app_context():
        check('currency still GBP', db.session.get(User, uid).currency in (None, 'GBP'), True)
