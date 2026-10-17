"""Legal pages, cookie consent and the social-proof component."""
import os

from _support import app, check, reset_db


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


def test_homepage_has_no_tracking_scripts_before_consent(client):
    body = client.get('/').get_data(as_text=True)
    check('no GA script tag', '<script async src="https://www.googletagmanager.com/gtag/js' in body, False)
    check('no Clarity script tag', 'src="https://www.clarity.ms/tag/' in body, False)
    check('consent default present', "gtag('consent', 'default'" in body, True)


def test_legal_pages_404_when_config_missing(client, monkeypatch):
    # Temporarily blank the config to simulate an unconfigured deploy.
    monkeypatch.setitem(app.config, 'SUPPORT_EMAIL', '')
    monkeypatch.setitem(app.config, 'LEGAL_ENTITY_NAME', '')
    for path in ('/privacy', '/terms', '/cookies', '/about', '/compare'):
        check('%s 404 when unconfigured' % path, client.get(path).status_code, 404)


def test_legal_pages_200_when_config_set(client, monkeypatch):
    monkeypatch.setitem(app.config, 'SUPPORT_EMAIL', 'help@example.com')
    monkeypatch.setitem(app.config, 'LEGAL_ENTITY_NAME', 'Jane Doe')
    for path in ('/privacy', '/terms', '/cookies', '/about', '/compare'):
        check('%s 200 when configured' % path, client.get(path).status_code, 200)


def test_no_todo_text_when_configured(client, monkeypatch):
    monkeypatch.setitem(app.config, 'SUPPORT_EMAIL', 'help@example.com')
    monkeypatch.setitem(app.config, 'LEGAL_ENTITY_NAME', 'Jane Doe')
    for path in ('/privacy', '/terms', '/cookies'):
        body = client.get(path).get_data(as_text=True)
        check('%s has no TODO text' % path, 'TODO(owner)' in body or 'TODO(owner):' in body, False)


def test_company_number_omitted_when_empty(client, monkeypatch):
    monkeypatch.setitem(app.config, 'SUPPORT_EMAIL', 'help@example.com')
    monkeypatch.setitem(app.config, 'LEGAL_ENTITY_NAME', 'Jane Doe')
    monkeypatch.setitem(app.config, 'COMPANY_NUMBER', '')
    body = client.get('/privacy').get_data(as_text=True)
    check('no company number line', 'company number' in body, False)


def test_privacy_lists_real_processors(client, monkeypatch):
    monkeypatch.setitem(app.config, 'SUPPORT_EMAIL', 'help@example.com')
    monkeypatch.setitem(app.config, 'LEGAL_ENTITY_NAME', 'Jane Doe')
    body = client.get('/privacy').get_data(as_text=True)
    for name in ('Stripe', 'Railway', 'Resend', 'SendGrid', 'Google', 'Microsoft', 'OpenAI'):
        check('privacy mentions %s' % name, name in body, True)