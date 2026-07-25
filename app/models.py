from app import db, login_manager
from flask_login import UserMixin
from datetime import datetime

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    jobs = db.relationship('Job', backref='owner', lazy=True)

ACTIVITY_TYPES = [
    ('electric', '⚡ Instalare electrică'),
    ('sanitar', '🔧 Instalare sanitară'),
    ('constructii', '🏗️ Construcții'),
    ('tamplarie', '🪟 Tâmplărie'),
    ('zugraveli', '🎨 Zugrăveli'),
    ('reparatii', '🔩 Reparații generale'),
    ('altele', '➕ Altele'),
]

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(100), nullable=False)
    client_email = db.Column(db.String(120))
    address = db.Column(db.String(200), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    description = db.Column(db.Text)
    activity_type = db.Column(db.String(50), default='altele')
    price = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='pending')
    quote_status = db.Column(db.String(20), default='none')
    quote_price = db.Column(db.Float, default=0.0)
    quote_description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)