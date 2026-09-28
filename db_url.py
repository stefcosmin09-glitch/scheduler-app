"""One shared way to turn a DATABASE_URL into an engine-ready URL.

Every path that opens the database from the environment applies the same two
rewrites, so they cannot drift apart again:

  - a sqlite path is resolved against the project`s instance directory, and
  - a postgres URL is pinned to the bundled psycopg2 driver.

The pin is load-bearing. SQLAlchemy 2.1 made psycopg (v3) the default driver
for a bare postgres URL, while the project ships psycopg2-binary, so a
create_engine() on the raw URL raises

    ModuleNotFoundError: No module named 'psycopg'

That is exactly what happened at deploy time in migrate.py: the migration
probe could not even build its engine, never read the schema, and the 0003
columns were never created, so every user query 500'd on
`column user.created_at does not exist`. config.py has always pinned the
driver, which is why the app engine connected while the probe silently gave up.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def resolve_url(raw):
    url = raw or 'sqlite:///scheduler.db'
    if url.startswith('sqlite:///'):
        path = url[len('sqlite:///'):]
        if not os.path.isabs(path) and not path.startswith('instance'):
            candidate = os.path.join(BASE_DIR, 'instance', path)
            if os.path.exists(candidate):
                return 'sqlite:///' + candidate.replace('\\', '/')
    if '+' not in url.split('://', 1)[0]:
        for scheme in ('postgres://', 'postgresql://'):
            if url.startswith(scheme):
                return 'postgresql+psycopg2://' + url[len(scheme):]
    return url