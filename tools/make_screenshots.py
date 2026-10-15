"""Capture real screenshots of the app for the marketing pages.

Starts the demo server on a spare port, drives the installed Chrome in headless
mode at a fixed window size, and writes the results into
app/static/screenshots/.

    python tools/make_screenshots.py
    python tools/make_screenshots.py --only dashboard invoices

Everything is pinned: same demo data, same window size, same capture settings,
so a re-run produces the same files and a diff only shows what the app itself
changed. That is the point of taking screenshots here rather than cropping them
by hand: when the UI moves, the pictures move with it.
"""
import argparse
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]

# name, path to photograph, viewport width, viewport height
#
# The width is not arbitrary. Each of these is displayed about 660px wide in the
# product tour on the landing page, and the app's text has to stay readable once
# it is scaled down. Around 960px of viewport lands close to 1:1 at that size,
# while still showing the desktop layout rather than the phone one.
SHOTS = [
    ('dashboard', '/', 960, 640),
    ('invoices', '/invoices', 960, 640),
    ('accounting', '/accounting', 960, 640),
    ('time', '/time', 960, 640),
    ('expenses', '/expenses', 960, 640),
    ('new-job', '/job/add', 960, 640),
    ('payments', '/payments', 960, 640),
    ('dashboard-phone', '/', 414, 896),
]

CHROME_CANDIDATES = [
    pathlib.Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe'),
    pathlib.Path(r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'),
    pathlib.Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'),
    pathlib.Path('/usr/bin/google-chrome'),
    pathlib.Path('/usr/bin/chromium'),
    pathlib.Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
]

OUT_DIR = ROOT / 'app' / 'static' / 'screenshots'
TARGET_WIDTH = 1600   # plenty for a 640px-wide landing image on a 2x screen
SCALE = 2             # capture at 2x, then downscale, for crisp text

# A page shorter than its window leaves a flat strip at the bottom. Only trim
# when that strip is unmistakable, so a footer can never be sliced off.
BLANK_RUN = 120


def find_chrome():
    override = os.environ.get('CHROME_PATH')
    if override:
        candidate = pathlib.Path(override)
        if candidate.exists():
            return candidate
        raise SystemExit('CHROME_PATH is set but does not exist: %s' % override)
    for candidate in CHROME_CANDIDATES:
        if candidate.exists():
            return candidate
    raise SystemExit('Could not find Chrome or Edge; set CHROME_PATH to point at it.')


def wait_for(url, seconds=60):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def capture(chrome, profile, url, out_path, width, height):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    result = subprocess.run(
        [
            str(chrome),
            '--headless',
            '--disable-gpu',
            '--hide-scrollbars',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-extensions',
            '--force-device-scale-factor=%d' % SCALE,
            '--user-data-dir=%s' % profile,
            '--window-size=%d,%d' % (width, height),
            '--virtual-time-budget=8000',
            '--screenshot=%s' % out_path,
            url,
        ],
        capture_output=True,
        timeout=120,
    )
    if not out_path.exists():
        raise SystemExit(
            'no screenshot for %s (chrome exit %s)\n%s\n%s' % (
                url, result.returncode,
                result.stdout.decode(errors='replace')[-500:],
                result.stderr.decode(errors='replace')[-1500:],
            )
        )


def trim_blank_bottom(image):
    """Drop an obviously empty strip under the content.

    Returns (image, pixels_removed). The strip has to be at least BLANK_RUN tall
    before anything is cut, so a page that simply ends never loses its footer.
    """
    width, height = image.size
    pixels = image.load()
    step = max(1, width // 60)
    background = pixels[0, height - 1]

    def is_background(y):
        for x in range(0, width, step):
            pixel = pixels[x, y]
            if (abs(pixel[0] - background[0]) + abs(pixel[1] - background[1])
                    + abs(pixel[2] - background[2])) > 6:
                return False
        return True

    y = height - 1
    while y >= 0 and is_background(y):
        y -= 1
    content_end = min(height, y + 1 + BLANK_RUN)
    if height - content_end < BLANK_RUN:
        return image, 0
    return image.crop((0, 0, width, content_end)), height - content_end


def tidy(path):
    from PIL import Image

    with Image.open(path) as raw:
        image = raw.convert('RGB')

    image, removed = trim_blank_bottom(image)

    if image.width > TARGET_WIDTH:
        height = round(image.height * TARGET_WIDTH / image.width)
        image = image.resize((TARGET_WIDTH, height), Image.LANCZOS)

    image.save(path, 'PNG', optimize=True)
    return image.size, removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', nargs='*', default=None,
                        help='capture just these shots, by name')
    parser.add_argument('--port', type=int, default=8770,
                        help='loopback port for the demo server. Avoid the ports '
                             'Chrome refuses to reach (5060, 5061, 6000, '
                             '6665-6669 ...): there it reports ERR_UNSAFE_PORT '
                             'and quietly writes no screenshot at all')
    args = parser.parse_args()

    shots = SHOTS
    if args.only:
        wanted = set(args.only)
        shots = [shot for shot in SHOTS if shot[0] in wanted]
        missing = wanted - {shot[0] for shot in shots}
        if missing:
            raise SystemExit('unknown shot(s): %s' % ', '.join(sorted(missing)))

    chrome = find_chrome()
    base = 'http://127.0.0.1:%d' % args.port

    server = subprocess.Popen(
        [sys.executable, str(ROOT / 'tools' / 'demo_server.py'),
         '--port', str(args.port)],
        cwd=str(ROOT),
    )
    try:
        if not wait_for(base + '/login'):
            raise SystemExit('demo server did not come up on %s' % base)

        with tempfile.TemporaryDirectory(prefix='ts-shots-') as profile:
            for name, path, width, height in shots:
                out_path = OUT_DIR / ('%s.png' % name)
                url = '%s/__demo_login__?next=%s' % (base, urllib.parse.quote(path))
                capture(chrome, profile, url, out_path, width, height)
                size, removed = tidy(out_path)
                print('%-18s %sx%s  %5.0f KB%s' % (
                    name, size[0], size[1],
                    out_path.stat().st_size / 1024,
                    '  (trimmed %dpx)' % removed if removed else ''))
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == '__main__':
    main()
