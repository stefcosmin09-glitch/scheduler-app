from app import create_app, db, scheduler
from flask_migrate import upgrade
from dotenv import load_dotenv

load_dotenv()

app = create_app()

with app.app_context():
    upgrade()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    scheduler.start()

    try:
        app.run(debug=True, use_reloader=False)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()