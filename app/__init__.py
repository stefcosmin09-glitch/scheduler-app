from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_mail import Mail
from flask_migrate import Migrate
from flask_babel import Babel
from flask_wtf.csrf import CSRFProtect
from apscheduler.schedulers.background import BackgroundScheduler
from config import Config
import os
from dotenv import load_dotenv

load_dotenv()

def get_locale():
    if current_user.is_authenticated and current_user.language in ('en', 'ro'):
        return current_user.language
    return 'en'

from decimal import Decimal, ROUND_HALF_UP

CURRENCY_SYMBOLS = {
    'GBP': ('£', False),
    'RON': ('lei', True),
    'EUR': ('€', True),
    'USD': ('$', False),
}

def format_money(amount, currency=None):
    from app.currency import convert
    if currency is None:
        currency = current_user.currency if current_user.is_authenticated else 'GBP'
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

    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

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
        currency = None
        if current_user.is_authenticated and current_user.currency:
            currency = current_user.currency
        else:
            c = request.cookies.get('ts_currency')
            if c and c in PRO_MONTHLY:
                currency = c
        if currency not in PRO_MONTHLY:
            currency = 'GBP'
        return {
            'display_currency': currency,
            'pro_price_text': price_text(currency),
            'PRO_PRICES': {k: price_text(k) for k in PRO_MONTHLY},
            'PREFERRED_CURRENCIES': PREFERRED_CURRENCIES,
        }

    from app.routes import auth, main
    app.register_blueprint(auth)
    app.register_blueprint(main)

    return app