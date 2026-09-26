import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-schimba-in-productie'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///scheduler.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Receipt photos are base64-encoded before reaching the AI, so cap the whole
    # request body. 10 MB leaves room for a modern phone photo plus form fields.
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024

    # Email
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.sendgrid.net'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 465)
    MAIL_USE_TLS = False
    MAIL_USE_SSL = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or 'apikey'
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'stef.cosmin09@gmail.com'