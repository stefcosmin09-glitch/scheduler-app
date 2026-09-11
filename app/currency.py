import json 
import threading
import time
from decimal import Decimal
from urllib.request import urlopen

BASE_CURRENCY = 'GBP'
API_URL = 'https://open.er-api.com/v6/latest/GBP'
CACHE_TTL_SECONDS = 6 * 3600

_rates_cache = {}
_lock = threading.Lock()


def get_rates():
    now = time.time()
    with _lock:
        cached = _rates_cache.get('rates')
        if cached and now - cached['ts'] < CACHE_TTL_SECONDS:
            return cached['data']
    try:
        with urlopen(API_URL, timeout=10) as resp:
            data = json.load(resp)
        rates = data.get('rates', {})
        rates[BASE_CURRENCY] = Decimal('1.0')
        with _lock:
            _rates_cache['rates'] = {'ts': now, 'data': rates}
        return rates
    except Exception as e:
        print(f">>> FX rate fetch error: {e}")
        with _lock:
            cached = _rates_cache.get('rates')
        return cached['data'] if cached else {BASE_CURRENCY: Decimal('1.0')}

def convert(amount, to_currency):
    if to_currency == BASE_CURRENCY:
        return amount
    rates = get_rates()
    rate = rates.get(to_currency)
    if rate is None:
        print(f">>>No rate for {to_currency}, using 1.0")
        return amount
    return Decimal(str(amount)) * Decimal(str(rate))

def convert_to_base(amount, from_currency):
    if from_currency == BASE_CURRENCY:
        return amount
    rates = get_rates()
    rate = rates.get(from_currency)
    if rate is None:
        print(f">>>No rate for {from_currency}, using 1.0")
        return amount
    return Decimal(str(amount)) / Decimal(str(rate))