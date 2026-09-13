import os
import datetime
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, text, inspect

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def resolve_url(url):
    if url.startswith('sqlite:///'):
        path = url[len('sqlite:///'):]
        if not os.path.isabs(path) and not path.startswith('instance'):
            p = os.path.join(BASE_DIR, 'instance', path)
            if os.path.exists(p):
                return 'sqlite:///' + p.replace('\\', '/')
    return url


BACKUP_URL = resolve_url(os.getenv('BACKUP_DATABASE_URL') or os.getenv('DATABASE_URL') or 'sqlite:///scheduler.db')


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
    s = str(v).replace("'", "''")
    return "'" + s + "'"


def tables_in_order(conn, insp):
    names = insp.get_table_names()
    preferred = ['user', 'business_profile', 'job', 'invoice', 'payment']
    ordered = [n for n in preferred if n in names]
    for n in names:
        if n not in ordered:
            ordered.append(n)
    return ordered


def main():
    engine = create_engine(BACKUP_URL)
    insp = inspect(engine)
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f'backup_{stamp}.sql')

    with engine.connect() as conn, open(out_path, 'w', encoding='utf-8') as f:
        f.write(f"-- TradeScheduler backup {stamp}\n-- source: {BACKUP_URL.split('//')[0]}//...\n")
        for table in tables_in_order(conn, insp):
            rows = conn.execute(text(f'SELECT * FROM "{table}"')).mappings().all()
            f.write(f'\n-- TABLE {table}: {len(rows)} rows\n')
            for r in rows:
                cols = [c for c in r.keys()]
                vals = [sql_literal(r[c]) for c in cols]
                f.write(f'INSERT INTO "{table}" ({", ".join(cols)}) VALUES ({", ".join(vals)});\n')

    print(f'Backup salvat: {out_path}')


if __name__ == '__main__':
    main()