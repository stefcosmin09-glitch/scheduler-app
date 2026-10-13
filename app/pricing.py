"""Landing-page currency localisation.

PRO_MONTHLY drives every displayed/charged price.
PREFERRED_CURRENCIES reflects the displayed, localised order on the landing page.
"""
from decimal import Decimal

PRO_MONTHLY = {
    'GBP': Decimal('22.99'),
    'USD': Decimal('25.99'),
    'RON': Decimal('99'),
    'AUD': Decimal('34.99'),
}

# GBP only at launch. Other currencies come back when there is real demand.
PREFERRED_CURRENCIES = ['GBP']

_SYMBOL = {'GBP': '\u00a3', 'USD': '$', 'RON': 'lei', 'EUR': '\u20ac', 'AUD': 'AU$'}


def price_text(currency='GBP'):
    currency = (currency or 'GBP').upper()
    amount = PRO_MONTHLY.get(currency)
    if currency == 'RON':
        return format(amount) + ' lei'
    if amount is not None:
        symbol = _SYMBOL.get(currency, '\u00a3')
        return '%s%.2f' % (symbol, float(amount))
    return '%.2f GBP' % float(PRO_MONTHLY['GBP'])
