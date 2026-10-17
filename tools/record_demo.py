"""Record a demo video of TradeScheduler using Playwright.

Prerequisites:
    pip install playwright
    playwright install chromium

Usage:
    1. Seed the demo database:
       python tools/seed_demo.py --reset
    2. Start the demo server in another terminal (same DEMO_DB):
       set DEMO_DB=%TEMP%\\tradescheduler-demo-video.db
       python tools/demo_server.py --port 8770
    3. Run this script:
       python tools/record_demo.py

The video is saved to tools/demo_output/demo.webm. Convert to MP4 with ffmpeg
(see the printed instructions at the end of this script).

Environment:
    DEMO_URL   base URL of the demo server (default http://127.0.0.1:8770)
    DEMO_USER  login email (default demo@example.com)
    DEMO_PASS  login password (default demo-password-123)
"""
import os
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('Playwright is not installed. Run: pip install playwright && playwright install chromium')
    sys.exit(1)

BASE_URL = os.environ.get('DEMO_URL', 'http://127.0.0.1:8770')
DEMO_USER = os.environ.get('DEMO_USER', 'demo@example.com')
DEMO_PASS = os.environ.get('DEMO_PASS', 'demo-password-123')

OUT_DIR = os.path.join(os.path.dirname(__file__), 'demo_output')
os.makedirs(OUT_DIR, exist_ok=True)


def pause(page, ms=1500):
    page.wait_for_timeout(ms)


def wait_dashboard(page, timeout=15000):
    page.wait_for_selector('text=My Jobs', timeout=timeout)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 390, 'height': 844},
            record_video_dir=OUT_DIR,
            record_video_size={'width': 390, 'height': 844},
        )
        # Grant cookie consent before any page loads so the banner never blocks.
        context.add_init_script(
            "localStorage.setItem('ts_cookie_consent', JSON.stringify({analytics:true,ads:true,clarity:true}));"
        )
        page = context.new_page()

        # --- Login ---
        page.goto(BASE_URL + '/login')
        pause(page, 1200)
        page.fill('input[name="email"]', DEMO_USER)
        page.fill('input[name="password"]', DEMO_PASS)
        page.click('button[type="submit"]')
        wait_dashboard(page)
        pause(page, 2000)  # dashboard: "Know who owes you"

        # --- Create job ---
        page.goto(BASE_URL + '/job/add')
        pause(page, 1200)  # "Book the job in seconds"
        page.fill('input[name="client_name"]', 'Sarah Whitfield')
        page.fill('input[name="client_email"]', 'sarah.whitfield@example.com')
        page.fill('input[name="address"]', '14 Elm Close, Reading RG1 4AB')
        page.fill('input[name="date"]', '2026-10-20T09:00')
        page.fill('textarea[name="description"]', 'Consumer unit replacement')
        page.fill('input[name="price"]', '665')
        page.select_option('select[name="activity_type"]', 'electric')
        page.click('button[type="submit"]')
        wait_dashboard(page)
        pause(page, 1500)

        # --- Generate quote (skipped: no AI key in demo) ---
        # If a key is available, uncomment:
        # page.goto(BASE_URL + '/job/quote/1')
        # pause(page, 1000)  # "Quote in a minute"

        # --- Create and send invoice ---
        page.goto(BASE_URL + '/job/invoice/1')
        pause(page, 2000)  # "Send the invoice"

        # --- Record payment of 300 by bank transfer ---
        page.goto(BASE_URL + '/invoices')
        pause(page, 1500)
        # The payment form is hidden until "Record Payment" is clicked.
        record_btn = page.locator('button:has-text("Record Payment")').first
        if record_btn.count() > 0:
            record_btn.click()
            page.wait_for_timeout(800)
            form = page.locator('form[action*="mark-paid"]').first
            amt = form.locator('input[name="amount"]')
            if amt.count() > 0:
                amt.fill('300')
            meth = form.locator('select[name="payment_method"]')
            if meth.count() > 0:
                meth.select_option('bank_transfer')
            form.locator('button[type="submit"]').first.click()
            page.wait_for_timeout(1500)

        # --- Back to dashboard ---
        page.goto(BASE_URL + '/')
        wait_dashboard(page)
        pause(page, 2500)  # "Get paid" + "14-day free trial · No card needed"

        video_path = page.video.path()
        context.close()
        browser.close()

    print('Video saved to:', video_path)
    print()
    print('Convert to MP4 with:')
    print('  ffmpeg -i "%s" -vf "scale=1080:1920" -c:v libx264 -crf 23 -preset medium -movflags +faststart tools/demo_output/demo.mp4' % video_path)
    print()
    print('Poster image:')
    print('  ffmpeg -i tools/demo_output/demo.mp4 -ss 00:00:01 -vframes 1 tools/demo_output/poster.jpg')


if __name__ == '__main__':
    main()