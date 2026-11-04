"""Whether the app charges for access.

The app is free at launch: payments are switched off and every account has
full access. The billing code stays in place (Stripe, plans, trials) so it
can be turned back on by setting PAYMENTS_ENABLED=1 without a rewrite.
"""
import os
from flask import current_app


def payments_enabled():
    try:
        return bool(current_app.config.get('PAYMENTS_ENABLED', False))
    except RuntimeError:
        # Outside an application context (e.g. unit tests calling limit_for
        # directly). Fall back to the environment variable.
        return os.environ.get('PAYMENTS_ENABLED', '0') == '1'