"""Source files must stay valid UTF-8.

The app is full of Romanian diacritics, and Windows tooling has a habit of
round-tripping them through a local codepage. A lossy conversion leaves
U+FFFD replacement characters that render as "?" in the UI, and the damage is
invisible until someone opens the file in a browser.
"""
import glob
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FILES = [
    'app/templates/time.html',
    'app/templates/base.html',
    'app/templates/dashboard.html',
    'app/templates/business_settings.html',
    'app/templates/add_job.html',
    'app/routes.py',
    'app/models.py',
    'app/ics.py',
]


def _read(relative):
    with open(os.path.join(ROOT, relative), 'rb') as handle:
        return handle.read().decode('utf-8')


def _scanned():
    """The app files plus this suite, so the check covers itself too."""
    own = ['tests/' + os.path.relpath(path, ROOT).replace('\\', '/')
           for path in sorted(glob.glob(os.path.join(ROOT, 'tests', '*.py')))]
    return [relative for relative in FILES + own
            if os.path.isfile(os.path.join(ROOT, relative))]


def test_every_file_decodes_as_utf8():
    for relative in _scanned():
        try:
            _read(relative)
        except UnicodeDecodeError as error:
            raise AssertionError('%s is not valid UTF-8: %s' % (relative, error))


def test_no_replacement_characters():
    """Characters that are not valid printable text survive a lossy round trip
    as U+FFFD, which is the tell that a file was re-saved in the wrong codepage.
    """
    offenders = ['%s has %d replacement character(s)' % (relative, count)
                 for relative in _scanned()
                 for count in [_read(relative).count('\ufffd')] if count]
    assert not offenders, '; '.join(offenders)
