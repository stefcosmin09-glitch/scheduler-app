"""The app must refuse to start rather than run without a signing key.

The old Config carried a fallback, 'dev-key-schimba-in-productie'. It looked
like a safety net and was the opposite of one: it was committed, so anyone who
deployed without setting SECRET_KEY would have had every session and CSRF token
signed with a key published on GitHub.

Worse, it never actually worked. create_app() overwrote it with
os.getenv('SECRET_KEY'), which is None when the variable is unset, so a fresh
checkout without a .env ran with no key at all and every login died on
"Session backend did not open a session". That is how these tests were found:
cloning the repository and running the suite, which 22 tests failed.
"""
import os
import subprocess
import sys

import pytest

from config import _require_secret_key

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = (
    "import os, sys\n"
    "os.environ['DATABASE_URL'] = 'sqlite:///' + os.environ['PROBE_DB']\n"
    "from app import create_app\n"
    "try:\n"
    "    app = create_app()\n"
    "except RuntimeError as exc:\n"
    "    print('REFUSED:', exc)\n"
    "    sys.exit(3)\n"
    "print('STARTED:', app.secret_key)\n"
)


def _run(with_key, tmp_path):
    env = dict(os.environ,
               DATABASE_URL='sqlite:///' + str(tmp_path / 'probe.db'),
               PROBE_DB=str(tmp_path / 'probe.db').replace('\\', '/'))
    env.pop('SECRET_KEY', None)
    if with_key:
        env['SECRET_KEY'] = 'a-key-only-this-subprocess-sees'
    return subprocess.run([sys.executable, '-c', PROBE], cwd=ROOT, env=env,
                          capture_output=True, text=True)


def test_missing_key_is_refused(tmp_path):
    result = _run(False, tmp_path)
    assert result.returncode == 3, (
        'the app started without SECRET_KEY, which means sessions are being '
        'signed with something guessable: %s %s'
        % (result.stdout, result.stderr[-1500:]))
    assert 'SECRET_KEY is not set' in result.stdout, result.stdout
    assert 'python -c' in result.stdout, \
        'the error should say how to fix it, not just that it is broken'


def test_present_key_starts_the_app(tmp_path):
    result = _run(True, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr[-1500:]
    assert 'STARTED: a-key-only-this-subprocess-sees' in result.stdout


def test_no_committed_fallback():
    """The old default, and anything shaped like it, must not come back.

    Checks the assignment rather than the string, because the comment
    explaining the history quotes the old value on purpose.
    """
    with open(os.path.join(ROOT, 'config.py'), encoding='utf-8') as handle:
        lines = handle.read().splitlines()
    assignments = [line.split('#')[0].strip() for line in lines
                   if line.strip().startswith('SECRET_KEY')]
    assert len(assignments) == 1, \
        'expected one SECRET_KEY assignment, found %r' % assignments
    assert assignments[0] == "SECRET_KEY = os.environ.get('SECRET_KEY')", (
        'SECRET_KEY should be read straight from the environment, with no '
        '"or some-default" fallback: %r' % assignments[0])


def test_create_app_does_not_overwrite_the_key():
    """The line that nulled the key looked redundant, because Config had
    already read the same variable. It was not redundant, it was the bug.
    """
    with open(os.path.join(ROOT, 'app', '__init__.py'), encoding='utf-8') as handle:
        source = handle.read()
    body = source.split('def create_app', 1)[1]
    assert "app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')" not in body, \
        'create_app() must not assign SECRET_KEY over the config value'


def test_require_helper_rejects_empty_and_none():
    for value in (None, ''):
        with pytest.raises(RuntimeError, match='SECRET_KEY is not set'):
            _require_secret_key(value)


def test_require_helper_passes_a_real_key_through():
    assert _require_secret_key('abc') == 'abc'
