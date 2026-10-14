"""Check the Starter price in Stripe test mode and create a sandbox checkout link.

Reads the key from STRIPE_API_KEY in the current terminal session only. Refuses
anything that is not a test key, and never prints the key.

Usage (PowerShell, in the project folder):
    $env:STRIPE_API_KEY = "<your sk_test key>"
    $env:STRIPE_STARTER_PRICE_ID = "price_..."
    python scripts/stripe_sandbox_check.py
"""
import os
import sys

import stripe


def main():
    key = os.getenv('STRIPE_API_KEY', '')
    price_id = os.getenv('STRIPE_STARTER_PRICE_ID', '')
    if not key.startswith('sk_test_'):
        print('STRIPE_API_KEY is missing or is not a test key (sk_test_...). Stopping.')
        return 1
    if not price_id.startswith('price_'):
        print('STRIPE_STARTER_PRICE_ID is missing. Stopping.')
        return 1

    stripe.api_key = key
    price = stripe.Price.retrieve(price_id)
    print('price found: livemode=%s, amount=%s %s, interval=%s, active=%s' % (
        price.livemode, price.unit_amount, price.currency,
        price.recurring.interval if price.recurring else None, price.active))
    if price.livemode:
        print('This price is a LIVE price. Stopping.')
        return 1
    if price.unit_amount != 1299 or price.currency != 'gbp':
        print('Expected 1299 gbp. Check the price in Stripe.')
        return 1

    session = stripe.checkout.Session.create(
        mode='subscription',
        line_items=[{'price': price_id, 'quantity': 1}],
        success_url='https://thetradescheduler.com/business-settings',
        cancel_url='https://thetradescheduler.com/business-settings',
        metadata={'plan': 'starter', 'user_id': '0'},
    )
    print('checkout session created: %s' % session.id)
    print('open this link and pay with card 4242 4242 4242 4242:')
    print(session.url)
    return 0


if __name__ == '__main__':
    sys.exit(main())
