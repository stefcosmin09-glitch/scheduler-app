"""Record a high-quality demo video of TradeScheduler using Playwright.

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

The video is saved to tools/out/demo.webm.

Environment:
    DEMO_URL   base URL of the demo server (default http://127.0.0.1:8770)
    DEMO_USER  login email (default demo@example.com)
    DEMO_PASS  login password (default demo-password-123)
    DEMO_DB    path to the demo SQLite db (for looking up the new job id)
"""
import os
import re
import sqlite3
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('Playwright is not installed. Run: pip install playwright && playwright install chromium')
    sys.exit(1)

BASE_URL = os.environ.get('DEMO_URL', 'http://127.0.0.1:8770')
DEMO_USER = os.environ.get('DEMO_USER', 'demo@example.com')
DEMO_PASS = os.environ.get('DEMO_PASS', 'demo-password-123')

OUT_DIR = os.path.join(os.path.dirname(__file__), 'out')
os.makedirs(OUT_DIR, exist_ok=True)
STORAGE_STATE = os.path.join(OUT_DIR, 'storage_state.json')


def pause(page, ms=1500):
    page.wait_for_timeout(ms)


def wait_dashboard(page, timeout=15000):
    page.wait_for_selector('text=My Jobs', timeout=timeout)


def slow_type(page, selector, text, delay=60):
    """Type text character by character for a natural look."""
    page.click(selector)
    page.wait_for_timeout(200)
    for ch in text:
        page.keyboard.type(ch, delay=delay)
    page.wait_for_timeout(300)


def smooth_scroll(page, steps=5, px=120, delay=40):
    """Scroll in small steps with pauses for a fluid feel."""
    for _ in range(steps):
        page.mouse.wheel(0, px)
        page.wait_for_timeout(delay)


def get_latest_job_id():
    db_path = os.environ.get('DEMO_DB') or os.path.join(
        os.environ.get('TEMP', '/tmp'), 'tradescheduler-demo-video.db')
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT id FROM job WHERE client_name='Sarah Whitfield' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def main():
    # --- Step 0: log in (not recorded) and save storage state ---
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 390, 'height': 844})
        context.add_init_script(
            "localStorage.setItem('ts_cookie_consent', JSON.stringify({analytics:true,ads:true,clarity:true}));"
        )
        page = context.new_page()
        page.goto(BASE_URL + '/login')
        page.fill('input[name="email"]', DEMO_USER)
        page.fill('input[name="password"]', DEMO_PASS)
        page.click('button[type="submit"]')
        wait_dashboard(page)
        context.storage_state(path=STORAGE_STATE)
        browser.close()

    # --- Step 1: recorded session starts on the dashboard ---
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 390, 'height': 844},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
            storage_state=STORAGE_STATE,
            record_video_dir=OUT_DIR,
            record_video_size={'width': 780, 'height': 1688},
        )
        context.add_init_script(
            "localStorage.setItem('ts_cookie_consent', JSON.stringify({analytics:true,ads:true,clarity:true}));"
        )
        page = context.new_page()

        # Dashboard — pause on "Money you're owed"
        page.goto(BASE_URL + '/')
        try:
            wait_dashboard(page)
        except Exception as e:
            page.screenshot(path=os.path.join(OUT_DIR, 'debug_dashboard.png'))
            print('DASHBOARD FAILED:', e)
            print('URL:', page.url)
            print('TEXT:', page.inner_text('body')[:300].encode('ascii','replace').decode('ascii'))
            context.close()
            browser.close()
            sys.exit(1)
        pause(page, 6000)  # "Know who owes you"

        # Create job for Sarah Whitfield (type slowly)
        page.goto(BASE_URL + '/job/add')
        pause(page, 3000)  # "Book the job in seconds"
        slow_type(page, 'input[name="client_name"]', 'Sarah Whitfield', delay=60)
        slow_type(page, 'input[name="client_email"]', 'sarah.whitfield@example.com', delay=60)
        slow_type(page, 'input[name="address"]', '14 Elm Close, Reading RG1 4AB', delay=60)
        page.fill('input[name="date"]', '2026-10-20T09:00')
        slow_type(page, 'textarea[name="description"]', 'Consumer unit replacement', delay=60)
        slow_type(page, 'input[name="price"]', '665', delay=60)
        page.select_option('select[name="activity_type"]', 'electric')
        page.wait_for_timeout(500)
        page.click('button[type="submit"]')
        wait_dashboard(page)
        pause(page, 3000)

        # Create invoice for that job (triggers PDF download + email, mocked)
        job_id = get_latest_job_id()
        if job_id:
            page.request.get(BASE_URL + '/job/invoice/%d' % job_id)
            page.goto(BASE_URL + '/invoices')
            pause(page, 4000)  # "Send the invoice"

        # Record payment of 300 on that invoice
        forms = page.locator('form[action*="mark-paid"]')
        if forms.count() > 0:
            form = forms.first
            record_btn = page.locator('button:has-text("Record Payment")').first
            if record_btn.count() > 0:
                record_btn.click()
                page.wait_for_timeout(800)
                amt = form.locator('input[name="amount"]')
                if amt.count() > 0:
                    amt.fill('300')
                meth = form.locator('select[name="payment_method"]')
                if meth.count() > 0:
                    meth.select_option('bank_transfer')
                form.locator('button[type="submit"]').first.click()
                page.wait_for_timeout(3000)  # "Get paid"

        # End on dashboard
        page.goto(BASE_URL + '/')
        wait_dashboard(page)
        pause(page, 2500)  # final: "14-day free trial"

        video_path = page.video.path()
        context.close()
        browser.close()

    print('Video saved to:', video_path)
    print()
    print('Convert to MP4 with:')
    print('  ffmpeg -i "%s" -vf "scale=1080:1920" -c:v libx264 -crf 23 -preset medium -movflags +faststart tools/out/demo.mp4' % video_path)
    print()
    print('Poster image:')
    print('  ffmpeg -i tools/out/demo.mp4 -ss 00:00:01 -vframes 1 tools/out/poster.jpg')


if __name__ == '__main__':
    main()