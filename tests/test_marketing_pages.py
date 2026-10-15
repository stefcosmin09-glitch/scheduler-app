"""The public marketing pages used as Google Ads sitelink destinations.

They exist as real URLs because Google rejects fragment destinations such as
/#pricing, so these tests pin down that each page renders, has its own title
and canonical URL, and stays linked from the landing page.
"""
from _support import check

# path -> a phrase unique to that page
PAGES = {
    '/why': 'Why UK tradespeople move their business',
    '/how-it-works': 'from the first call to getting paid',
    '/pricing': 'Simple pricing, no surprises',
    '/faq': 'Frequently asked questions',
}

CANONICALS = {
    '/why': 'https://thetradescheduler.com/why',
    '/how-it-works': 'https://thetradescheduler.com/how-it-works',
    '/pricing': 'https://thetradescheduler.com/pricing',
    '/faq': 'https://thetradescheduler.com/faq',
}


def test_marketing_pages_render(client):
    for path, marker in PAGES.items():
        response = client.get(path)
        check('%s returns 200' % path, response.status_code, 200)
        body = response.get_data(as_text=True)
        check('%s has its own heading' % path, marker in body, True)
        check('%s links its canonical URL' % path, CANONICALS[path] in body, True)


def test_landing_links_to_the_new_pages(client):
    body = client.get('/').get_data(as_text=True)
    for path in PAGES:
        check('landing links to %s' % path, 'href="%s"' % path in body, True)


def test_pricing_page_keeps_the_published_numbers(client):
    body = client.get('/pricing').get_data(as_text=True)
    check('Starter price is shown', '£12.99' in body, True)
    check('Starter AI quote allowance is shown', '25 / month' in body, True)
    check('Pro receipt allowance is shown', 'up to 300 / month' in body, True)
    check('trial length is stated', '14 days' in body, True)


def test_faq_page_carries_the_retention_wording(client):
    body = client.get('/faq').get_data(as_text=True)
    check('60-day retention is stated', '60 days' in body, True)
    check('the seven-day warning is stated', 'seven days before' in body, True)
    check('the backup caveat is stated', 'backup copy' in body, True)


def test_landing_shows_the_product_mockups(client):
    body = client.get('/').get_data(as_text=True)
    for marker in ('ts-window', 'ts-app-sidebar', 'ts-phone', 'ts-phone-static'):
        check('landing renders the %s mockup' % marker, marker in body, True)


def test_marketing_assets_are_linked(client):
    body = client.get('/').get_data(as_text=True)
    check('marketing.css is linked', 'marketing.css' in body, True)
    check('marketing.js is linked', 'marketing.js' in body, True)


def test_marketing_css_declares_the_utilities_the_build_is_missing(client):
    # The committed Tailwind file predates some templates, so these live in
    # marketing.css. If they ever disappear the mocked-up UI collapses again.
    css = client.get('/static/marketing.css').get_data(as_text=True)
    for rule in (r'.sm\:flex', r'.lg\:block', '.h-7', '.rounded-md', '.bg-white\\/10'):
        check('marketing.css defines %s' % rule, rule in css, True)


def test_trust_band_and_trial_reassurance_are_shown(client):
    # Honest, checkable claims only: the six trust markers plus the plain
    # explanation of what happens if the visitor never subscribes.
    for path in ('/', '/pricing'):
        body = client.get(path).get_data(as_text=True)
        check('%s shows the trust band' % path, 'Export your data' in body, True)
        check('%s shows the no-card marker' % path, 'No credit card' in body, True)
        check('%s explains the post-trial state' % path,
              'becomes read-only' in body, True)


def test_mobile_cta_is_on_every_marketing_page(client):
    # One tap away from the trial on a phone, on every page a visitor can land
    # on from an ad or a sitelink.
    for path in ('/', '/why', '/how-it-works', '/pricing', '/faq'):
        body = client.get(path).get_data(as_text=True)
        check('%s shows the sticky mobile CTA' % path,
              'id="ts-mobile-cta"' in body, True)
        check('%s can dismiss the CTA' % path,
              'ts-mobile-cta-close' in body, True)
