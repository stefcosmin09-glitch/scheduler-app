"""AI service abstraction for TradeScheduler.

The provider can be swapped later (OpenAI today, others tomorrow) without
touching routes/templates. API keys only live in environment variables and are
never sent to the browser. Every AI output is parsed and validated here before
it reaches a template or the database.
"""
import os
import json
import base64
import urllib.request
import urllib.error
from datetime import datetime


class AIServiceError(Exception):
    """Raised when AI is unavailable, returns invalid output, or fails."""


def ai_provider():
    return os.getenv('AI_PROVIDER', 'openai').strip().lower()


def ai_api_key():
    return os.getenv('AI_API_KEY') or os.getenv('OPENAI_API_KEY')


def ai_model():
    return os.getenv('AI_MODEL', 'gpt-4o-mini')


def ai_configured():
    return ai_provider() == 'openai' and bool(ai_api_key())


# ── quota & payload guards ─────────────────────────────────────────
# The trial needs no card, so without a cap the AI key is an open expense.
# Buckets are hourly and keyed per user, so a heavy user throttles themselves
# without ever blocking the next tradesperson.

AI_HOURLY_PERIOD = '%Y-%m-%dT%H'
MAX_RECEIPT_BYTES = 8 * 1024 * 1024
FREE_HOURLY_AI_CALLS = 30
PRO_HOURLY_AI_CALLS = 120


def consume_ai_quota(user, feature):
    """Count one AI call against this user's hourly cap and raise if spent.

    Counters live in the ai_usage table rather than in memory, so the limit
    survives a deploy and holds when more than one worker is serving.
    """
    if user is None:
        return
    from app import db
    from app.models import AIUsage

    period = datetime.utcnow().strftime(AI_HOURLY_PERIOD)
    cap = PRO_HOURLY_AI_CALLS if getattr(user, 'plan', 'free') == 'pro' else FREE_HOURLY_AI_CALLS

    row = AIUsage.query.filter_by(user_id=user.id, feature=feature, period=period).first()
    if row is None:
        AIUsage.query.filter(
            AIUsage.user_id == user.id, AIUsage.period < period
        ).delete(synchronize_session=False)
        row = AIUsage(user_id=user.id, feature=feature, period=period, count=0)
        db.session.add(row)

    row.count = (row.count or 0) + 1
    db.session.commit()

    if row.count > cap:
        raise AIServiceError(
            'You have used a lot of AI features in the last hour. Please try again shortly.'
        )


def _post_chat(messages, want_json=True):
    if not ai_configured():
        raise AIServiceError('AI is not configured.')
    payload = {
        'model': ai_model(),
        'messages': messages,
        'temperature': 0.2,
        'response_format': {'type': 'json_object'} if want_json else None,
    }
    if payload['response_format'] is None:
        del payload['response_format']
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        'https://api.openai.com/v1/chat/completions',
        data=data,
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + ai_api_key(),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raise AIServiceError('AI provider error (%s).' % e.code)
    except Exception as e:
        raise AIServiceError('AI request failed: %s' % e)
    try:
        content = body['choices'][0]['message']['content']
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError('not an object')
    except Exception:
        raise AIServiceError('AI response was not valid JSON.')
    return parsed


# ── sanitising helpers ─────────────────────────────────────────────

def _num(value):
    try:
        if value is None or value == '':
            return None
        return float(str(value).replace(',', '').replace('£', '').replace('€', '').strip())
    except (TypeError, ValueError):
        return None


def _text(value, max_len=500):
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ('null', 'unknown', 'n/a', 'none', 'cannot determine'):
        return None
    return s[:max_len]


def _date(value):
    if not value:
        return None
    s = str(value).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _time_str(value):
    s = _text(value, 10)
    if not s:
        return None
    s = s.strip()
    try:
        return datetime.strptime(s, '%H:%M').strftime('%H:%M')
    except ValueError:
        return None


def _sample_jobs(user, limit=8):
    """Recent jobs of this user so the AI can use real context (if any)."""
    from app.models import Job
    jobs = []
    try:
        rows = Job.query.filter_by(user_id=user.id).filter(
            Job.description.isnot(None), Job.description != '',
        ).order_by(Job.created_at.desc()).limit(limit).all()
    except Exception:
        rows = []
    for j in rows:
        price = float(j.quote_price or 0) or float(j.price or 0)
        if price and j.description:
            jobs.append({'description': j.description[:300], 'price': round(price, 2)})
    return jobs


# ── Phase 2 · Quote generation ────────────────────────────────────

def generate_quote(user, description):
    if not description or not description.strip():
        raise AIServiceError('Please describe the job first.')
    consume_ai_quota(user, 'quote')
    samples = _sample_jobs(user)
    sample_txt = ''
    if samples:
        sample_txt = '\n'.join(
            '- "%s" → £%.2f' % (s['description'][:200], s['price']) for s in samples
        )
    prompt = (
        "You help UK tradespeople build quotes. The user describes a job and you "
        "produce a draft quote STRUCTURE to be reviewed and edited by them.\n\n"
        "Job description: %s\n" % description.strip()[:1500]
    )
    if sample_txt:
        prompt += (
            "\nThe user's OWN recent jobs and quote prices (use only as indication "
            "of how they price work, never copy blindly):\n%s\n" % sample_txt
        )
    prompt += (
        "\nReturn strict JSON only, with this exact shape:\n"
        "{\"summary\": \"a short client-friendly rephrasing of the work, a few lines, "
        "no prices\", \"currency\": \"GBP\", \"labour\": number|null, "
        "\"materials\": number|null, \"total\": number|null, "
        "\"items\": [{\"label\": string, \"quantity\": number|null, "
        "\"unit_price\": number|null, \"amount\": number|null, "
        "\"kind\": \"labour\"|\"material\"}], "
        "\"needs_review\": true, \"notes\": \"short note in English about anything "
        "the tradesperson must check\"}\n"
        "Rules:\n"
        "- Use conservative, realistic UK guide prices. Make a clear estimate.\n"
        "- If a price (labour or materials) cannot be estimated, set it to null.\n"
        "- Never invent quantities that are not implied (e.g. 'a tap' = 1).\n"
        "- total = labour + materials when both are known, else null.\n"
        "- needs_review must always be true.\n"
        "- Do not add VAT. Currency is GBP."
    )
    raw = _post_chat([{'role': 'user', 'content': prompt}])
    try:
        items = []
        for it in raw.get('items') or []:
            if not isinstance(it, dict):
                continue
            items.append({
                'label': _text(it.get('label'), 200) or 'Item',
                'quantity': int(it['quantity']) if _num(it.get('quantity')) is not None else None,
                'unit_price': _num(it.get('unit_price')),
                'amount': _num(it.get('amount')),
                'kind': it.get('kind') if it.get('kind') in ('labour', 'material') else 'material',
            })
        labour = _num(raw.get('labour'))
        materials = _num(raw.get('materials'))
        total = _num(raw.get('total'))
        if total is None and labour is not None and materials is not None:
            total = round(labour + materials, 2)
        summary = _text(raw.get('summary'), 1000) or description.strip()[:1000]
        return {
            'summary': summary,
            'currency': (str(raw.get('currency', 'GBP')).upper()[:3] if raw.get('currency') else 'GBP'),
            'labour': labour,
            'materials': materials,
            'total': total,
            'items': items,
            'needs_review': True,
            'notes': _text(raw.get('notes'), 500) or 'Review the prices before sending.',
        }
    except Exception:
        raise AIServiceError('Could not parse the generated quote.')


# ── Phase 3 · Receipt extraction ──────────────────────────────────

def extract_receipt(user, image_bytes, mime):
    if not image_bytes:
        raise AIServiceError('No image provided.')
    if len(image_bytes) > MAX_RECEIPT_BYTES:
        raise AIServiceError('That photo is too large. Please use an image under 8 MB.')
    consume_ai_quota(user, 'receipt')
    b64 = base64.b64encode(image_bytes).decode('ascii')
    allowed = ["Materials", "Tools", "Fuel / Vehicle", "Subcontractors",
               "Insurance", "Accountancy", "Marketing", "Rent / Office",
               "Phone / Internet", "Trade body / Courses", "Other"]
    prompt = (
        "You read a photo of a receipt/invoice from a UK trade business. "
        "Return strict JSON only with this shape:\n"
        "{\"merchant\": string|null, \"date\": \"YYYY-MM-DD\"|null, "
        "\"total\": number|null, \"vat_amount\": number|null, "
        "\"currency\": \"GBP\"|null, \"category\": one of %r|null, "
        "\"description\": string|null, "
        "\"uncertain_fields\": [string...], \"notes\": string|null}\n"
        "Rules: only fill a field if you are reasonably sure. If unsure, set it to "
        "null AND list its name in uncertain_fields. "
        "Categories allowed: %s." % (allowed, ", ".join(allowed))
    )
    raw = _post_chat([
        {'role': 'user', 'content': [
            {'type': 'text', 'text': prompt},
            {'type': 'image_url', 'image_url': {'url': 'data:%s;base64,%s' % (mime, b64)}},
        ]},
    ])
    total = _num(raw.get('total'))
    date = _date(raw.get('date'))
    uncertain = set()
    if isinstance(raw.get('uncertain_fields'), list):
        for f in raw['uncertain_fields']:
            if isinstance(f, str):
                uncertain.add(f[:30])
    if total is None:
        uncertain.add('total')
    if date is None:
        uncertain.add('date')
    category = _text(raw.get('category'), 40)
    if category and category not in allowed:
        category = 'Other'
        uncertain.add('category')
    currency = _text(raw.get('currency'), 4)
    from app.markets import ENABLED_CURRENCIES
    if currency and currency.upper() in ENABLED_CURRENCIES:
        currency = currency.upper()
    else:
        currency = 'GBP'
    return {
        'merchant': _text(raw.get('merchant'), 200),
        'date': date.isoformat() if date else None,
        'total': round(total, 2) if total is not None else None,
        'vat_amount': round(_num(raw.get('vat_amount')), 2) if _num(raw.get('vat_amount')) is not None else None,
        'currency': currency,
        'category': category or 'Other',
        'description': _text(raw.get('description'), 500),
        'uncertain_fields': sorted(uncertain),
        'notes': _text(raw.get('notes'), 500),
    }


# ── Phase 5 · Message → Job extraction ────────────────────────────

def extract_job_from_message(user, text):
    if not text or not text.strip():
        raise AIServiceError('Please paste the client message first.')
    consume_ai_quota(user, 'message')
    types = "electric, plumbing, construction, carpentry, decorating, general, other"
    prompt = (
        "A UK tradesperson received a message from a client about a job. "
        "Extract useful details. Message:\n\n%s\n\n" % text.strip()[:1500]
    )
    prompt += (
        "Return strict JSON only with shape:\n"
        "{\"customer_name\": string|null, \"customer_email\": string|null, "
        "\"address\": string|null, \"date\": \"YYYY-MM-DD\"|null, "
        "\"time\": \"HH:MM\"|null, \"description\": string, "
        "\"activity_type\": one of [%s], \"uncertain_fields\": [string...], "
        "\"notes\": string|null}\n"
        "Rules:\n"
        "- Fill email/address/date/time ONLY if present in the message; never invent.\n"
        "- A weekday like 'Friday' means the next upcoming such day — resolve it to "
        "YYYY-MM-DD.\n"
        "- If the date is missing or ambiguous (e.g. 'asap', 'this week', 'whenever') "
        "set date to null and add 'date' to uncertain_fields.\n"
        "- If the address looks incomplete (missing postcode/street number) add "
        "'address' to uncertain_fields.\n"
        "- If the customer name cannot be clearly identified from the message, set it "
        "null and add to uncertain_fields.\n"
        "- description: one clear sentence about the work.\n"
        "- activity_type must be one of [%s]."
    ) % (types, types)
    raw = _post_chat([{'role': 'user', 'content': prompt}])
    uncertain = set()
    if isinstance(raw.get('uncertain_fields'), list):
        for f in raw['uncertain_fields']:
            if isinstance(f, str):
                uncertain.add(f[:30])
    date = _date(raw.get('date'))
    if date is None:
        uncertain.add('date')
    customer = _text(raw.get('customer_name'), 100)
    if not customer:
        uncertain.add('customer_name')
    address = _text(raw.get('address'), 200)
    if not address:
        uncertain.add('address')
    activity = _text(raw.get('activity_type'), 30)
    if activity and activity in ('electric', 'plumbing', 'construction', 'carpentry', 'decorating', 'general'):
        pass
    else:
        activity = 'other'
    return {
        'customer_name': customer,
        'customer_email': _text(raw.get('customer_email'), 120),
        'address': address,
        'date': date.isoformat() if date else None,
        'time': _time_str(raw.get('time')),
        'description': _text(raw.get('description'), 500) or 'General work',
        'activity_type': activity,
        'uncertain_fields': sorted(uncertain),
        'notes': _text(raw.get('notes'), 500),
    }