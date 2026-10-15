"""The real product screenshots in the landing page's product tour.

They replaced hand-built HTML mockups, and the whole point of the swap is that
they are real: the files are committed, the page points at them, and each one
carries alt text and intrinsic dimensions. A screenshot that goes missing
renders as an empty window frame, which on a landing page is worse than a
broken image icon, so it is worth a test.

The files are captured at twice the size they are declared at, because the app
text has to stay sharp on a retina screen. That is why the declared width and
the file width are not the same number.
"""
import pathlib
import re

from _support import check

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHOT_DIR = ROOT / 'app' / 'static' / 'screenshots'

# file -> the size declared on the page, which is half the captured size
EXPECTED = {
    'dashboard.png': (960, 640),
    'invoices.png': (960, 640),
    'accounting.png': (960, 640),
    'dashboard-phone.png': (390, 844),
}

IMG_TAG = re.compile(r'<img[^>]*>')


def _png_size(path):
    header = path.read_bytes()[:24]
    return (int.from_bytes(header[16:20], 'big'), int.from_bytes(header[20:24], 'big'))


def _attribute(tag, name):
    match = re.search(r'\b%s="([^"]*)"' % name, tag)
    return match.group(1) if match else None


def _tour_images(client):
    body = client.get('/').get_data(as_text=True)
    return [tag for tag in IMG_TAG.findall(body) if 'screenshots/' in tag]


def test_the_tour_shows_every_screenshot(client):
    tags = _tour_images(client)
    check('the tour uses images, not mockup markup',
          len(tags), len(EXPECTED))
    for name in EXPECTED:
        check('the landing shows %s' % name,
              any(name in tag for tag in tags), True)


def test_every_screenshot_file_is_committed(client):
    for name, (width, height) in EXPECTED.items():
        path = SHOT_DIR / name
        check('%s exists' % name, path.exists(), True)
        if not path.exists():
            continue
        check('%s is a png' % name, path.read_bytes()[:8], b'\x89PNG\r\n\x1a\n')
        file_width, file_height = _png_size(path)
        check('%s is at least as wide as it is declared' % name,
              file_width >= width, True)
        check('%s keeps roughly the declared shape' % name,
              abs(file_width / file_height - width / height) < 0.02, True)


def test_every_screenshot_carries_alt_text_and_a_size(client):
    for tag in _tour_images(client):
        source = _attribute(tag, 'src')
        alt = _attribute(tag, 'alt') or ''
        check('%s has alt text' % source, len(alt.strip()) > 25, True)
        check('%s declares a width' % source,
              _attribute(tag, 'width') is not None, True)
        check('%s declares a height' % source,
              _attribute(tag, 'height') is not None, True)


def test_the_declared_size_matches_the_file(client):
    for tag in _tour_images(client):
        source = _attribute(tag, 'src')
        name = source.rsplit('/', 1)[-1]
        if name not in EXPECTED:
            continue
        declared = (int(_attribute(tag, 'width')), int(_attribute(tag, 'height')))
        check('%s is declared at the size it was captured for' % name,
              declared, EXPECTED[name])
