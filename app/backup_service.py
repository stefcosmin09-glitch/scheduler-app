import os
import io
import glob
import base64
import datetime
from sqlalchemy import create_engine, text, inspect
from db_url import resolve_url

BACKUPS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backups', 'auto')
KEEP_COUNT = 14
MAX_ATTACHMENT_SIZE = 30 * 1024 * 1024


def sql_literal(v):
    if v is None:
        return 'NULL'
    if isinstance(v, bool):
        return 'TRUE' if v else 'FALSE'
    if isinstance(v, (int, float)):
        return str(v)
    from decimal import Decimal
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return "'" + v.isoformat() + "'"
    return "'" + str(v).replace("'", "''") + "'"


def build_backup_sql(url):
    resolved = resolve_url(url)
    if resolved.startswith('sqlite:///'):
        engine = create_engine(resolved, connect_args={'timeout': 30})
    else:
        engine = create_engine(resolved)
    insp = inspect(engine)
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    out = io.StringIO()
    preferred = ['user', 'business_profile', 'job', 'invoice', 'payment']
    names = insp.get_table_names()
    ordered = [n for n in preferred if n in names] + [n for n in names if n not in preferred]

    with engine.connect() as conn:
        out.write(f"-- TradeScheduler backup {stamp}\n")
        out.write(f"-- source: {url.split('//')[0]}//...\n")
        for table in ordered:
            rows = conn.execute(text(f'SELECT * FROM "{table}"')).mappings().all()
            out.write(f'\n-- TABLE {table}: {len(rows)} rows\n')
            for r in rows:
                cols = list(r.keys())
                vals = [sql_literal(r[c]) for c in cols]
                out.write(f'INSERT INTO "{table}" ({", ".join(cols)}) VALUES ({", ".join(vals)});\n')
    return stamp, out.getvalue(), len(ordered)


def run_auto_backup(app):
    try:
        url = os.getenv('BACKUP_DATABASE_URL') or os.getenv('DATABASE_URL') or 'sqlite:///scheduler.db'
        stamp, sql, _ = build_backup_sql(url)

        os.makedirs(BACKUPS_DIR, exist_ok=True)
        path = os.path.join(BACKUPS_DIR, f'backup_{stamp}.sql')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(sql)
        print(f'>>> Auto backup salvat: {path}')

        for old in sorted(glob.glob(os.path.join(BACKUPS_DIR, 'backup_*.sql')))[:-KEEP_COUNT]:
            os.remove(old)
            print(f'>>> Șters backup vechi: {old}')

        _email_backup(app, path)
        return path
    except Exception as e:
        print(f'>>> Auto backup EROARE: {e}')
        return None


def _email_backup(app, path, max_size=MAX_ATTACHMENT_SIZE):
    try:
        from app.models import User, BusinessProfile
        if not os.getenv('RESEND_API_KEY'):
            return
        if os.path.getsize(path) > max_size:
            print('>>> Backup prea mare pentru email, trimis doar fișier.')
            return

        owner = User.query.order_by(User.id.asc()).first()
        if not owner:
            return
        to = owner.email
        biz = BusinessProfile.query.filter_by(user_id=owner.id).first()
        if biz and biz.business_email:
            to = biz.business_email

        stamp = os.path.basename(path).replace('backup_', '').replace('.sql', '')
        with open(path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')

        from app.email_service import send_email_with_attachment
        subject = f'TradeScheduler backup {stamp}'
        body = f'Automat backup TradeScheduler - {stamp}\nFișier ataș: {os.path.basename(path)}'
        send_email_with_attachment(to, subject, body, b64, os.path.basename(path))
        print(f'>>> Backup trimis pe email: {to}')
    except Exception as e:
        print(f'>>> Backup email EROARE: {e}')