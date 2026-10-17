"""Legal pages, cookie consent and the social-proof component."""
from _support import check


def test_legal_pages_render(client):
    for path in ('/privacy', '/terms', '/cookies', '/about'):
        response = client.get(path)
        check('%s returns 200' % path, response.status_code, 200)


def test_legal_pages_carry_the_draft_banner(client):
    body = client.get('/privacy').get_data(as_text=True)
    check('privacy shows the DRAFT banner', 'DRAFT - to be reviewed' in body, True)


def test_consent_gating_hides_tracking_until_consent(client):
    body = client.get('/').get_data(as_text=True)
    # The tracking scripts must not be loaded eagerly: no <script src=...> tag
    # for them in the rendered page (they are injected only after consent).
    check('no eager GA script tag', '<script async src="https://www.googletagmanager.com/gtag/js' in body, False)
    check('no eager Clarity script tag', 'src="https://www.clarity.ms/tag/' in body, False)
    # Consent Mode defaults must be present and denied.
    check('consent default is present', "gtag('consent', 'default'" in body, True)
    check('ad_storage denied by default', "ad_storage: 'denied'" in body, True)
    check('analytics_storage denied by default', "analytics_storage: 'denied'" in body, True)


def test_testimonials_render_nothing_when_empty(client):
    body = client.get('/').get_data(as_text=True)
    check('no testimonial section rendered', 'What tradespeople say' in body, False)


def test_cookie_settings_link_present(client):
    body = client.get('/').get_data(as_text=True)
    check('cookie settings link present', 'cookie-settings-link' in body, True)