"""Which currencies and languages the app offers.

The app is UK-only for now, so only GBP and English are switched on. The other
currencies (RON, EUR, USD, AUD) and Romanian are kept in the code and switched
off here. To bring one back, add its code to the matching tuple.

A user's saved choice is never rewritten. While a market is off, the app just
uses the default instead, so turning it back on restores what they chose.
"""

ENABLED_CURRENCIES = ('GBP',)
ENABLED_LANGUAGES = ('en',)

# Tax systems the app knows how to invoice for. UK only at launch; the others
# are kept in the code for when a market is opened. Add a code to turn it on.
ENABLED_TAX_COUNTRIES = ('UK',)

DEFAULT_CURRENCY = 'GBP'
DEFAULT_LANGUAGE = 'en'
DEFAULT_TAX_COUNTRY = 'UK'


def active_currency(code):
    return code if code in ENABLED_CURRENCIES else DEFAULT_CURRENCY


def active_language(code):
    return code if code in ENABLED_LANGUAGES else DEFAULT_LANGUAGE


def active_tax_country(code):
    return code if code in ENABLED_TAX_COUNTRIES else DEFAULT_TAX_COUNTRY
