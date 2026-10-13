"""Starter and Pro plans: allowances, checkout selection and webhook plan mapping."""
from datetime import datetime, timedelta
from unittest import mock

import os

import pytest

from _support import app, check, csrf, db, login, make_job, make_user, register
from app.limits import (FREE_LIMITS, PRO_AI_LIMITS, STARTER_AI_LIMITS,
                        limit_for, is_pro, is_starter)
from app.models import User

_STRIPE_VARS = ('STRIPE_API_KEY', 'STRIPE_STARTER_PRICE_ID', 'STRIPE_WEBHOOK_SECRET')


@pytest.fixture(autouse=True)
def restore_stripe_env():
    """Each test sets its own Stripe variables; none may leak into the next."""
    saved = {k: os.environ.get(k) for k in _STRIPE_VARS}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _user(uid):
    with app.app_context():
        user = User.query.get(uid)
        db.session.expunge_all()
        return user


def test_starter_allowances():
    uid = make_user('starter1', plan='starter')
    user = _user(uid)
    check('starter is starter', is_starter(user), True)
    check('starter is not pro', is_pro(user), False)
    check('starter jobs unlimited', limit_for(user, 'jobs'), None)
    check('starter customers unlimited', limit_for(user, 'customers'), None)
    check('starter AI quotes', limit_for(user, 'ai_quote'), STARTER_AI_LIMITS['ai_quote'])
    check('starter receipts', limit_for(user, 'ai_receipt'), STARTER_AI_LIMITS['ai_receipt'])
    check('starter messages', limit_for(user, 'ai_message'), STARTER_AI_LIMITS['ai_message'])


def test_pro_allowances_are_fair_use():
    uid = make_user('pro1', plan='pro')
    user = _user(uid)
    check('pro jobs unlimited', limit_for(user, 'jobs'), None)
    check('pro AI quotes fair use', limit_for(user, 'ai_quote'), PRO_AI_LIMITS['ai_quote'])
    check('pro AI is larger than starter', PRO_AI_LIMITS['ai_quote'] > STARTER_AI_LIMITS['ai_quote'], True)


def test_expired_account_falls_back_to_free_caps():
    uid = make_user('expired1', plan='free')
    with app.app_context():
        user = User.query.get(uid)
        user.trial_ends_at = datetime.utcnow() - timedelta(days=1)
        db.session.commit()
        db.session.expunge_all()
    user = _user(uid)
    check('expired jobs capped', limit_for(user, 'jobs'), FREE_LIMITS['jobs'])
    check('expired AI capped', limit_for(user, 'ai_quote'), FREE_LIMITS['ai_quote'])


def test_live_trial_is_unmetered_jobs_and_fair_use_ai():
    uid = make_user('trial1', plan='trial')
    with app.app_context():
        user = User.query.get(uid)
        user.trial_ends_at = datetime.utcnow() + timedelta(days=10)
        db.session.commit()
        db.session.expunge_all()
    user = _user(uid)
    check('trial jobs unlimited', limit_for(user, 'jobs'), None)
    check('trial AI uses pro fair use', limit_for(user, 'ai_quote'), PRO_AI_LIMITS['ai_quote'])


def test_starter_job_count_is_not_blocked():
    uid = make_user('starter2', plan='starter')
    for i in range(FREE_LIMITS['jobs'] + 3):
        make_job(uid, name='Client %d' % i)
    from app.limits import state
    user = _user(uid)
    with app.app_context():
        limit, used, remaining = state(User.query.get(uid), 'jobs')
    check('starter has no job cap', limit, None)
    check('starter counted jobs', used, FREE_LIMITS['jobs'] + 3)


def _post_webhook(event):
    import os
    os.environ['STRIPE_WEBHOOK_SECRET'] = 'whsec_test'
    with mock.patch('stripe.Webhook.construct_event', return_value=event):
        return app.test_client().post('/stripe/webhook', data=b'{}',
                                      headers={'Stripe-Signature': 'x'})


def test_checkout_completed_sets_starter_from_metadata():
    uid = make_user('hook1', plan='free')
    event = {'type': 'checkout.session.completed', 'data': {'object': {
        'id': 'cs_test_1', 'subscription': 'sub_test_1',
        'metadata': {'user_id': str(uid), 'plan': 'starter'},
        'client_reference_id': str(uid)}}}
    resp = _post_webhook(event)
    check('webhook ok', resp.status_code, 200)
    check('plan is starter', _user(uid).plan, 'starter')


def test_checkout_completed_defaults_to_pro_without_plan_metadata():
    uid = make_user('hook2', plan='free')
    event = {'type': 'checkout.session.completed', 'data': {'object': {
        'id': 'cs_test_2', 'subscription': 'sub_test_2',
        'metadata': {'user_id': str(uid)}}}}
    _post_webhook(event)
    check('plan defaults to pro', _user(uid).plan, 'pro')


def test_subscription_active_on_starter_price_is_starter():
    import os
    os.environ['STRIPE_STARTER_PRICE_ID'] = 'price_starter_test'
    uid = make_user('hook3', plan='starter')
    with app.app_context():
        user = User.query.get(uid)
        user.stripe_subscription_id = 'sub_hook3'
        db.session.commit()
    event = {'type': 'customer.subscription.updated', 'data': {'object': {
        'id': 'sub_hook3', 'status': 'active',
        'items': {'data': [{'price': {'id': 'price_starter_test'}}]}}}}
    _post_webhook(event)
    check('stays starter', _user(uid).plan, 'starter')


def test_subscription_active_on_other_price_is_pro():
    import os
    os.environ['STRIPE_STARTER_PRICE_ID'] = 'price_starter_test'
    uid = make_user('hook4', plan='starter')
    with app.app_context():
        user = User.query.get(uid)
        user.stripe_subscription_id = 'sub_hook4'
        db.session.commit()
    event = {'type': 'customer.subscription.updated', 'data': {'object': {
        'id': 'sub_hook4', 'status': 'active',
        'items': {'data': [{'price': {'id': 'price_pro_test'}}]}}}}
    _post_webhook(event)
    check('upgrades to pro', _user(uid).plan, 'pro')


def test_checkout_starter_without_price_is_refused():
    import os
    register(app.test_client(), 'nochk')
    os.environ.pop('STRIPE_STARTER_PRICE_ID', None)
    os.environ['STRIPE_API_KEY'] = 'sk_test_dummy'
    client = app.test_client()
    login(client, 'nochk')
    with mock.patch('stripe.checkout.Session.create') as create:
        resp = client.post('/billing/checkout', data={'plan': 'starter', 'csrf_token': csrf(client)})
    check('no stripe call without price', create.called, False)
    check('redirected to settings', resp.status_code, 302)


def test_checkout_starter_uses_starter_price_and_metadata():
    import os
    os.environ['STRIPE_API_KEY'] = 'sk_test_dummy'
    os.environ['STRIPE_STARTER_PRICE_ID'] = 'price_starter_test'
    client = app.test_client()
    register(client, 'chk1')
    login(client, 'chk1')
    fake_session = mock.Mock(url='https://checkout.stripe.test/session')
    with mock.patch('stripe.Customer.create', return_value=mock.Mock(id='cus_test')), \
         mock.patch('stripe.checkout.Session.create', return_value=fake_session) as create:
        client.post('/billing/checkout', data={'plan': 'starter', 'csrf_token': csrf(client)})
    kwargs = create.call_args.kwargs
    check('starter price used', kwargs['line_items'][0]['price'], 'price_starter_test')
    check('plan metadata', kwargs['metadata']['plan'], 'starter')
