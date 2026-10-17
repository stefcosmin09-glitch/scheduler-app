from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_mail import Mail
from flask_migrate import Migrate
from flask_babel import Babel
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from apscheduler.schedulers.background import BackgroundScheduler
from config import Config, _require_secret_key
import os
from dotenv import load_dotenv

load_dotenv()

from app.markets import active_currency, active_language, ENABLED_CURRENCIES, ENABLED_LANGUAGES

def get_locale():
    if current_user.is_authenticated:
        return active_language(current_user.language)
    return 'en'

from decimal import Decimal, ROUND_HALF_UP

CURRENCY_SYMBOLS = {
    'GBP': ('£', False),
    'RON': ('lei', True),
    'EUR': ('€', True),
    'USD': ('$', False),
    'AUD': ('AU$', False),
}

def format_money(amount, currency=None):
    from app.currency import convert
    if currency is None:
        currency = current_user.currency if current_user.is_authenticated else 'GBP'
    currency = active_currency(currency)
    symbol, european = CURRENCY_SYMBOLS.get(currency, ('£', False))
    try:
        amount = Decimal(str(convert(amount, currency))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except Exception:
        amount = Decimal('0.00')
    if european:
        s = f"{amount:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        return f"{s} {symbol}"
    return f"{symbol}{amount:,.2f}"

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
mail = Mail() 
scheduler = BackgroundScheduler()
migrate = Migrate()
babel = Babel()
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    _require_secret_key(app.config.get('SECRET_KEY'))

    # Railway terminates TLS and forwards the connection, so without this every
    # request arrives with remote_addr set to the proxy and any per-address
    # limit counts the whole internet as one caller. x_for=1 trusts exactly
    # one hop, which matches a single proxy in front of the app. It also fixes
    # request.scheme, so externally generated links stop saying http.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)
    babel.init_app(app, default_locale='en', locale_selector=get_locale)
    csrf.init_app(app)
    app.jinja_env.filters['money'] = format_money

    @app.context_processor
    def inject_pricing():
        from flask import request
        from app.pricing import PRO_MONTHLY, price_text, PREFERRED_CURRENCIES
        # GBP only at launch: every price is charged and shown in pounds.
        currency = 'GBP'
        return {
            'display_currency': currency,
            'pro_price_text': price_text(currency),
            'PRO_PRICES': {k: price_text(k) for k in PRO_MONTHLY},
            'PREFERRED_CURRENCIES': PREFERRED_CURRENCIES,
            'ENABLED_CURRENCIES': ENABLED_CURRENCIES,
            'ENABLED_LANGUAGES': ENABLED_LANGUAGES,
        }

    from app.routes import auth, main
    from app.admin import admin
    app.register_blueprint(auth)
    app.register_blueprint(main)
    app.register_blueprint(admin)

    @app.cli.command('trial-lifecycle')
    def trial_lifecycle_command():
        """Send due trial emails and apply the retention rule. Run daily."""
        from app.trial_lifecycle import run_trial_lifecycle
        sent, deleted = run_trial_lifecycle()
        print('trial lifecycle: %d emails sent, %d accounts deleted' % (sent, deleted))

    return app