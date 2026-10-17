"""Google Ads conversion label is wired up correctly."""
import os

from _support import check

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _all_text_files():
    out = []
    for dirpath, _, filenames in os.walk(ROOT):
        # skip caches and venv
        if any(part in dirpath for part in ('.git', '__pycache__', 'venv', '.pytest_cache')):
            continue
        for name in filenames:
            if name.endswith(('.py', '.html', '.js', '.css', '.md', '.txt', '.json', '.cfg', '.ini')):
                out.append(os.path.join(dirpath, name))
    return out


def test_no_placeholder_remains():
    for path in _all_text_files():
        if os.path.basename(path).startswith('test_'):
            continue
        text = open(path, encoding='utf-8', errors='replace').read()
        check('no TODO_LABEL in %s' % path, 'TODO_LABEL' in text, False)
        check('no XXXXXXXXX in %s' % path, 'XXXXXXXXX' in text, False)


def test_new_send_to_present_only_in_login_template():
    needle = "AW-18339646944/M1qlCPWn158dEOCbg6lE"
    found = []
    for path in _all_text_files():
        if os.path.basename(path).startswith('test_'):
            continue
        text = open(path, encoding='utf-8', errors='replace').read()
        if needle in text:
            found.append(os.path.relpath(path, ROOT).replace(os.sep, '/'))
    check('send_to present in exactly one file', found, ['app/templates/login.html'])