from decimal import Decimal

PRO_MONTHLY = {
    'GBP': Decimal('22.99'),
    'USD': Decimal('25.99'),
    'RON': Decimal('99'),
}

# PREFERRED_CURRENCIES reflects the displayed, localised order on the landing page
PREFERRED_CURRENCIES = ['GBP', 'USD', 'RON']

_SYMBOL = {'GBP': '\u00a3', 'USD': '$', 'RON': 'lei', 'EUR': '\u20ac'}


def price_text(currency='GBP'):
    currency = (currency or 'GBP').upper()
    amount = PRO_MONTHLY.get(currency)
    if currency == 'RON':
        return format(amount) + ' lei'
    if amount is not None:
        symbol = _SYMBOL.get(currency, '\u00a3')
        return '%s%.2f' % (symbol, float(amount))
    return '%.2f GBP' % float(PRO_MONTHLY['GBP'])