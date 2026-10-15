"""robots.txt, sitemap.xml and the social sharing image.

These are the machine-readable parts of the site: the files Google reads to
decide what to crawl, and the image Facebook, LinkedIn and WhatsApp show when
someone shares a link. A broken sitemap or a missing image is invisible on the
page but shows up in Search Console and in every shared link preview.
"""
import pathlib

from _support import check

PUBLIC_PAGES = ['/', '/why', '/how-it-works', '/pricing', '/faq']
ROOT = pathlib.Path(__file__).resolve().parents[1]


def _png_size(path):
    """Width and height straight from the PNG header, no image library needed."""
    header = path.read_bytes()[:24]
    return (int.from_bytes(header[16:20], 'big'), int.from_bytes(header[20:24], 'big'))


def test_robots_txt_points_at_the_sitemap(client):
    response = client.get('/robots.txt')
    check('robots.txt returns 200', response.status_code, 200)
    check('robots.txt is served as plain text', response.mimetype, 'text/plain')
    body = response.get_data(as_text=True)
    check('robots.txt talks to every crawler', 'User-agent: *' in body, True)
    check('robots.txt allows the marketing pages', 'Allow: /' in body, True)
    check('robots.txt advertises the sitemap',
          'https://thetradescheduler.com/sitemap.xml' in body, True)


def test_sitemap_lists_every_public_page_and_nothing_else(client):
    response = client.get('/sitemap.xml')
    check('sitemap.xml returns 200', response.status_code, 200)
    body = response.get_data(as_text=True)
    check('sitemap.xml is a urlset', '<urlset' in body, True)
    check('sitemap.xml has one entry per public page',
          body.count('<url>'), len(PUBLIC_PAGES))
    for path in PUBLIC_PAGES:
        loc = 'https://thetradescheduler.com%s<' % path
        check('sitemap.xml lists %s' % path, loc in body, True)
    for path in ('/login', '/register', '/accounting', '/invoices', '/billing/checkout'):
        check('sitemap.xml leaves out %s' % path,
              'https://thetradescheduler.com%s<' % path not in body, True)


def test_share_image_exists_and_is_the_right_size(client):
    image = ROOT / 'app' / 'static' / 'og-image.png'
    check('og-image.png is committed', image.exists(), True)
    check('og-image.png is 1200x630', _png_size(image), (1200, 630))


def test_every_public_page_points_at_the_share_image(client):
    for path in PUBLIC_PAGES:
        body = client.get(path).get_data(as_text=True)
        check('%s references the share image' % path, 'og-image.png' in body, True)
        check('%s declares the image size' % path, 'og:image:width' in body, True)
        check('%s asks for the large card' % path,
              'summary_large_image' in body, True)
