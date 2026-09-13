import os
import sys
import re
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import IntegrityError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def resolve_url(url):
    if url.startswith('sqlite:///'):
        path = url[len('sqlite:///'):]
        if not os.path.isabs(path) and not path.startswith('instance'):
            p = os.path.join(BASE_DIR, 'instance', path)
            if os.path.exists(p):
                return 'sqlite:///' + p.replace('\\', '/')
    return url


RESTORE_URL = resolve_url(os.getenv('RESTORE_DATABASE_URL') or os.getenv('DATABASE_URL') or 'sqlite:///scheduler.db')


def split_statements(sql):
    statements = []
    i, n = 0, len(sql)
    while i < n:
        if sql[i:i + 2] == '--':
            while i < n and sql[i] != '\n':
                i += 1
            continue
        if sql[i] in ' \t\r\n':
            i += 1
            continue
        start = i
        in_str = False
        while i < n:
            c = sql[i]
            if in_str:
                if c == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        i += 2
                        continue
                    in_str = False
                i += 1
            else:
                if c == "'":
                    in_str = True
                    i += 1
                elif c == ';':
                    i += 1
                    break
                else:
                    i += 1
        stmt = sql[start:i].strip()
        if stmt and stmt.startswith('INSERT'):
            statements.append(stmt)
    return statements


def bump_sequences(conn, engine):
    insp = inspect(engine)
    for table in insp.get_table_names():
        cols = insp.get_columns(table)
        if any(c['name'] == 'id' for c in cols):
            conn.execute(text(
                f"SELECT setval(pg_get_serial_sequence('\"{table}\"', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM \"{table}\"), 1), true)"))

def main(backup_file):
    if not os.path.exists(backup_file):
        print(f'Fisierul nu exista: {backup_file}')
        sys.exit(1)

    sql = open(backup_file, encoding='utf-8').read()
    statements = split_statements(sql)
    if not statements:
        print('Nicio comanda INSERT in fisier.')
        sys.exit(1)

    engine = create_engine(RESTORE_URL)
    dialect = engine.dialect.name
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            if dialect == 'postgresql':
                conn.execute(text('SET session_replication_role = replica'))
            else:
                conn.execute(text('PRAGMA foreign_keys = OFF'))

            insp = inspect(engine)
            tables = insp.get_table_names()
            tables.reverse()
            for table in tables:
                conn.execute(text(f'DELETE FROM "{table}"'))

            # for sqlite, the FK check is per-connection; keep it off during inserts
            for stmt in statements:
                conn.execute(text(stmt))
            conn.execute(text('PRAGMA foreign_keys = ON')) if dialect != 'postgresql' else None
            if dialect == 'postgresql':
                conn.execute(text('SET session_replication_role = DEFAULT'))
                bump_sequences(conn, engine)
            trans.commit()
        except IntegrityError as e:
            trans.rollback()
            print('EROARE la import:', e)
            sys.exit(1)

    print('Restaurare reusita.')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Folosire: python restore.py backups/backup_XXXXXXXX.sql')
        sys.exit(1)
    main(sys.argv[1])