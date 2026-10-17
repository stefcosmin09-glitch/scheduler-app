"""Trade landing pages, /health and /compare."""
from _support import check


def test_trade_pages_render(client):
    for path in ('/electricians', '/plumbers', '/builders', '/roofers'):
        response = client.get(path)
        check('%s returns 200' % path, response.status_code, 200)


def test_trade_pages_have_noindex(client):
    for path in ('/electricians', '/plumbers', '/builders', '/roofers'):
        body = client.get(path).get_data(as_text=True)
        check('%s has noindex' % path, '<meta name="robots" content="noindex">' in body, True)


def test_trade_pages_have_no_nav(client):
    for path in ('/electricians', '/plumbers', '/builders', '/roofers'):
        body = client.get(path).get_data(as_text=True)
        check('%s has no nav menu' % path, 'id="menu-toggle"' in body, False)
        check('%s has one CTA' % path, body.count('Start your 14-day free trial') >= 1, True)


def test_trade_pages_have_per_trade_h1(client):
    for path in ('/electricians', '/plumbers', '/builders', '/roofers'):
        body = client.get(path).get_data(as_text=True)
        trade = path.strip('/')
        check('%s h1 matches intent' % path, 'for UK %s' % trade in body, True)


def test_health_returns_ok(client):
    response = client.get('/health')
    check('health returns 200', response.status_code, 200)
    check('health body', response.get_json(), {'status': 'ok'})


def test_compare_page_renders(client):
    response = client.get('/compare')
    check('compare returns 200', response.status_code, 200)