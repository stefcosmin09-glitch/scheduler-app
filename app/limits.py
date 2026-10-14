"""Free-plan allowances and usage counting.

A free account is permanent and capped, so a tradesperson can try the product
for real without a card. Pro is unmetered.

Jobs and customers are derived from the job table, so nothing has to be
counted for them. The AI features share the ai_usage table with the hourly rate
limit in ai_service: monthly buckets are 'YYYY-MM', hourly ones 'YYYY-MM-DDTHH'.
"""
from datetime import datetime

from sqlalchemy import distinct, func

from app import db
from app.models import AIUsage, Job

MONTH_PERIOD = '%Y-%m'

# feature -> free plan allowance. Everything here resets at the start of each
# month. 'customers' counts only customers introduced this month, so an account
# can grow over time while repeat work for known customers stays unlimited.
FREE_LIMITS = {
    'jobs': 20,
    'customers': 5,
    'ai_quote': 25,
    'ai_receipt': 10,
    'ai_message': 25,
}

AI_FEATURES = ('ai_quote', 'ai_receipt', 'ai_message')

# Starter (£12.99): jobs and customers are unlimited, AI has a small monthly cap
# so the user can try it and want Pro. Pro gets a generous fair-use cap.
STARTER_AI_LIMITS = {
    'ai_quote': 25,
    'ai_receipt': 10,
    'ai_message': 25,
}

PRO_AI_LIMITS = {
    'ai_quote': 500,
    'ai_receipt': 300,
    'ai_message': 500,
}

# English labels for the dashboard counters; templates run them through _().
FEATURE_LABELS = {
    'jobs': 'jobs this month',
    'customers': 'new customers this month',
    'ai_quote': 'AI quotes this month',
    'ai_receipt': 'receipt scans this month',
}


def is_pro(user):
    return getattr(user, 'plan', 'free') == 'pro'


def is_starter(user):
    return getattr(user, 'plan', 'free') == 'starter'


def trial_active(user):
    """True while the 14-day trial is still running."""
    if is_pro(user) or is_starter(user):
        return False
    ends = getattr(user, 'trial_ends_at', None)
    return bool(ends) and ends > datetime.utcnow()


def is_unmetered(user):
    """True where the free allowances must not apply to jobs and customers.

    Paid plans are unmetered, and so is a live trial: the landing page sells the
    trial as full access, so letting the free caps touch it would contradict what
    was promised at signup. Only once the trial lapses do the caps start counting.
    """
    return is_pro(user) or is_starter(user) or trial_active(user)


def is_read_only(user):
    """True once the trial has ended without a paid plan.

    Such an account keeps its data and can still view and export it, but cannot
    add or change anything until it subscribes.
    """
    return not is_unmetered(user)


def limit_for(user, feature):
    """Allowance for this user, or None when unmetered."""
    if feature in AI_FEATURES:
        if is_pro(user) or trial_active(user):
            return PRO_AI_LIMITS[feature]
        if is_starter(user):
            return STARTER_AI_LIMITS[feature]
        return FREE_LIMITS.get(feature)
    if is_unmetered(user):
        return None
    return FREE_LIMITS.get(feature)


def month_period(now=None):
    return (now or datetime.utcnow()).strftime(MONTH_PERIOD)


def month_start(now=None):
    now = now or datetime.utcnow()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def usage(user, feature):
    """How much of this feature the user has used in the current period."""
    if feature == 'jobs':
        return Job.query.filter(
            Job.user_id == user.id, Job.created_at >= month_start()).count()
    if feature == 'customers':
        # Customers genuinely introduced this month: a name that appears in a
        # job from this month but never in an earlier one. Names are compared
        # lowercased so "Acme" and "acme" cannot both consume an allowance.
        earlier = (db.session.query(func.lower(Job.client_name))
                   .filter(Job.user_id == user.id, Job.created_at < month_start()))
        return (db.session.query(func.count(distinct(func.lower(Job.client_name))))
                .filter(Job.user_id == user.id,
                        Job.created_at >= month_start(),
                        func.lower(Job.client_name).notin_(earlier)).scalar() or 0)
    if feature in AI_FEATURES:
        row = AIUsage.query.filter_by(
            user_id=user.id, feature=feature, period=month_period()).first()
        return int(row.count) if row and row.count else 0
    return 0


def state(user, feature):
    """(limit, used, remaining); limit and remaining are None when unmetered."""
    limit = limit_for(user, feature)
    used = usage(user, feature)
    if limit is None:
        return None, used, None
    return limit, used, max(0, limit - used)


def reached(user, feature):
    limit, used, _ = state(user, feature)
    return limit is not None and used >= limit


def message(user, feature):
    """The message shown when a feature has run out.

    In practice this fires on Starter's AI allowances, so it points at Pro's
    much larger fair-use allowance rather than promising "unlimited", which Pro
    is not.
    """
    limit, _, _ = state(user, feature)
    if feature == 'jobs':
        return ('You have used all %d jobs included this month.'
                % limit)
    if feature == 'customers':
        return ('You have added all %d new customers included this month. '
                'Keep working with the customers you already have, or upgrade '
                'for more.' % limit)
    if feature == 'ai_quote':
        return ('You have used all %d AI quotes included this month. '
                'Upgrade to Pro for a much larger monthly allowance.' % limit)
    if feature == 'ai_receipt':
        return ('You have used all %d receipt scans included this month. '
                'Upgrade to Pro for a much larger monthly allowance.' % limit)
    return ('You have used all %d AI message reads included this month. '
            'Upgrade to Pro for a much larger monthly allowance.' % limit)


def _bump_ai(user, feature):
    period = month_period()
    row = AIUsage.query.filter_by(user_id=user.id, feature=feature, period=period).first()
    if row is None:
        row = AIUsage(user_id=user.id, feature=feature, period=period, count=0)
        db.session.add(row)
    row.count = (row.count or 0) + 1
    db.session.commit()


def consume(user, feature):
    """Check the allowance and count this use.

    Returns None when allowed, otherwise the message to show. Jobs and
    customers are derived from the job table, so they are only checked here;
    only the AI features need a counter bumped.
    """
    if reached(user, feature):
        return message(user, feature)
    if feature in AI_FEATURES:
        _bump_ai(user, feature)
    return None


def new_customer_block(user, client_name):
    """Message if saving this client would push the free plan past its cap.

    Repeat work for a customer you already have is always allowed, so this only
    bites on a genuinely new name, and only once this month's new-customer
    allowance is used up.
    """
    name = (client_name or '').strip()
    if not name or is_unmetered(user):
        return None
    if Job.query.filter(
        func.lower(Job.client_name) == name.lower(), Job.user_id == user.id
    ).first():
        return None
    limit, used, _ = state(user, 'customers')
    if used >= limit:
        return message(user, 'customers')
    return None


def dashboard_state(user):
    """Limit usage for the dashboard banners, as a list of dicts.

    Only Starter has allowances to show: Pro, a live trial and a read-only
    account have none.
    """
    if not is_starter(user):
        return []
    out = []
    for feature in ('jobs', 'customers', 'ai_quote', 'ai_receipt'):
        limit, used, remaining = state(user, feature)
        if limit is None:
            continue
        out.append({
            'feature': feature,
            'label': FEATURE_LABELS.get(feature, feature),
            'limit': limit,
            'used': used,
            'remaining': remaining,
            'exhausted': remaining == 0,
            # warn once the user is within two of the wall
            'warn': remaining <= 2,
        })
    return out
