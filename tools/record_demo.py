"""Record a demo video of TradeScheduler using Playwright.

Prerequisites:
    pip install playwright
    playwright install chromium

Usage:
    1. Start the demo server in another terminal:
       DEMO_DB=/tmp/tradescheduler-demo-video.db python tools/demo_server.py --port 8770
       (or set DEMO_DB to the file seeded by tools/seed_demo.py)
    2. Seed the demo database:
       python tools/seed_demo.py --reset
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
import time

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


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 390, 'height': 844},
            record_video_dir=OUT_DIR,
            record_video_size={'width': 390, 'height': 844},
        )
        page = context.new_page()

        # --- Login ---
        page.goto(BASE_URL + '/login')
        pause(page, 1200)
        page.fill('input[name="email"]', DEMO_USER)
        page.fill('input[name="password"]', DEMO_PASS)
        page.click('button[type="submit"]')
        page.wait_for_url('**/', timeout=10000)
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
        page.wait_for_url('**/', timeout=10000)
        pause(page, 1500)

        # --- Generate quote (skip if no AI key) ---
        # The demo server has no OpenAI key, so we skip AI generation.
        # If a key is available, uncomment the block below.
        # page.goto(BASE_URL + '/job/quote/1')
        # pause(page, 1000)  # "Quote in a minute"
        # page.click('button:has-text("Generate with AI")')
        # page.wait_for_timeout(5000)

        # --- Create and send invoice ---
        # Download invoice for the first job (creates invoice + sends email, mocked by MAIL_SUPPRESS_SEND)
        page.goto(BASE_URL + '/job/invoice/1')
        pause(page, 2000)  # "Send the invoice"

        # --- Record payment of 300 by bank transfer ---
        page.goto(BASE_URL + '/invoices')
        pause(page, 1500)
        # Find the first unpaid invoice and mark 300 paid
        first_pay = page.locator('form[action*="mark-paid"] button, button:has-text("Record payment")').first
        if first_pay.count() > 0:
            first_pay.click()
            page.wait_for_timeout(500)
            page.fill('input[name="amount"]', '300')
            page.select_option('select[name="payment_method"]', 'bank_transfer')
            page.click('button[type="submit"]')
            page.wait_for_timeout(1500)

        # --- Back to dashboard ---
        page.goto(BASE_URL + '/')
        pause(page, 2500)  # "Get paid" + "14-day free trial · No card needed"

        context.close()
        browser.close()

    print('Video saved to:', OUT_DIR)
    print('Convert to MP4 with:')
    print('  ffmpeg -i %s/demo.webm -vf "scale=1080:1920" -c:v libx264 -crf 23 -preset medium %s/demo.mp4' % (OUT_DIR, OUT_DIR))


if __name__ == '__main__':
    main()