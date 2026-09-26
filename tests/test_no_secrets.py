"""Nothing that looks like a credential may be committed.

Scans the tracked files rather than the working diff, so it also catches a key
that was committed earlier and would otherwise sit in history unnoticed.

A line that reads the value from the environment is the shape we want to see,
so those are skipped: the point is to find literals, not variable names.
"""
import os
import re
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOOKUP = re.compile(r'os\.(?:environ\.get|getenv)\(')
TEXT_SUFFIXES = {'.py', '.html', '.txt', '.cfg', '.ini', '.json', '.yml', '.yaml'}

# Catching "something assigned to a variable called token or password" is a
# blunt instrument, and the test suite is full of deliberate fakes like
# calendar_token = 'tokenul-owner'. A vendor key would never be legitimate in a
# test either, so those patterns still run everywhere; only the blunt one backs
# off inside tests/.
PATTERNS = [
    ('stripe live key', r'sk_live_\w+', False),
    ('stripe secret', r'sk_(?:test|live)_\w{10,}', False),
    ('webhook secret', r'whsec_\w+', False),
    ('aws key', r'AKIA[0-9A-Z]{16}', False),
    ('private key block', r'-----BEGIN [A-Z ]*PRIVATE KEY-----', False),
    ('google api key', r'AIza[0-9A-Za-z_\-]{35}', False),
    ('slack token', r'xox[baprs]-[0-9A-Za-z-]+', False),
    ('github token', r'gh[pousr]_[0-9A-Za-z]{20,}', False),
    ('resend key', r're_[0-9A-Za-z]{20,}', False),
    ('postgres url with password', r'postgres(?:ql)?://[^:\s\'"]+:[^@\s\'"]+@', False),
    ('assigned secret literal',
     r'(?:api_?key|secret|password|token)\s*=\s*[\'"][^\'"]{8,}[\'"]', True),
]


def _tracked_text_files():
    result = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True,
                            text=True, encoding='utf-8', errors='replace')
    if result.returncode != 0:
        pytest.skip('not a git checkout')
    files = [line.strip() for line in result.stdout.splitlines()]
    return [f for f in files
            if os.path.splitext(f)[1] in TEXT_SUFFIXES
            and os.path.isfile(os.path.join(ROOT, f))]


@pytest.mark.parametrize('name,pattern,lenient_in_tests',
                         PATTERNS, ids=[p[0] for p in PATTERNS])
def test_no_credential_shaped_literals(name, pattern, lenient_in_tests):
    offenders = []
    for relative in _tracked_text_files():
        in_tests = relative.replace('\\', '/').startswith('tests/')
        if in_tests and lenient_in_tests:
            continue
        with open(os.path.join(ROOT, relative), encoding='utf-8',
                  errors='replace') as handle:
            for number, line in enumerate(handle.read().splitlines(), 1):
                if LOOKUP.search(line):
                    continue
                if re.search(pattern, line, re.IGNORECASE):
                    offenders.append('%s:%d  %s'
                                     % (relative, number, line.strip()[:70]))
    assert not offenders, '%s found:\n  %s' % (name, '\n  '.join(offenders))
