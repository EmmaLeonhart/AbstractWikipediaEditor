"""Scout the fragment actions menu on an existing article to find the removal option."""

import io
import sys
import os
import json
import time
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
load_dotenv()

WIKI_URL = "https://abstract.wikipedia.org"
API_URL = f"{WIKI_URL}/w/api.php"

SCREENSHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "screenshots")
os.makedirs(SCREENSHOTS, exist_ok=True)


def api_login_cookies():
    session = requests.Session()
    session.headers.update({"User-Agent": "AbstractTestBot/1.0"})
    r = session.get(API_URL, params={"action": "query", "meta": "tokens", "type": "login", "format": "json"})
    login_token = r.json()["query"]["tokens"]["logintoken"]
    username = os.environ.get("WIKI_USERNAME", "").split("@")[0]
    password = os.environ.get("WIKI_MAIN_PASSWORD", "")
    r = session.post(API_URL, data={
        "action": "login", "lgname": username, "lgpassword": password,
        "lgtoken": login_token, "format": "json",
    })
    result = r.json()["login"]
    if result["result"] != "Success":
        raise RuntimeError(f"Login failed: {result}")
    print(f"Logged in as {result['lgusername']}", flush=True)
    return session.cookies.get_dict()


def shot(page, name):
    path = os.path.join(SCREENSHOTS, f"scout_frag_{name}.png")
    page.screenshot(path=path)
    print(f"  Screenshot: {path}", flush=True)


# Pick an article we know exists - use the API to find one
r = requests.get(API_URL, params={
    "action": "query", "list": "allpages", "apnamespace": 0,
    "aplimit": 10, "format": "json",
}, headers={"User-Agent": "AbstractTestBot/1.0"})
pages = r.json()["query"]["allpages"]
qids = [p["title"] for p in pages if p["title"].startswith("Q") and p["title"][1:].isdigit()]
target = qids[0] if qids else "Q1490"
print(f"Target article: {target}", flush=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()

    cookies = api_login_cookies()
    for name, value in cookies.items():
        context.add_cookies([{"name": name, "value": value, "domain": ".wikipedia.org", "path": "/"}])

    # Load the editor
    print(f"Opening editor for {target}...", flush=True)
    page.goto(f"{WIKI_URL}/w/index.php?title={target}&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(6)
    shot(page, "01_editor_loaded")

    # Count fragments
    dots = page.locator("button[aria-label*='fragment-actions-menu']")
    n = dots.count()
    print(f"Found {n} fragment action buttons", flush=True)

    if n == 0:
        # Try other selectors
        print("Trying alternative selectors...", flush=True)
        for selector in [
            "button[aria-label*='fragment']",
            "button[aria-label*='Fragment']",
            ".ext-wikilambda-app-abstract-fragment button",
            "[data-testid*='fragment'] button",
            "button.cdx-button--icon-only",
        ]:
            count = page.locator(selector).count()
            print(f"  {selector}: {count} matches", flush=True)

        # Also dump the full page structure around fragments
        html = page.evaluate("""
            const el = document.querySelector('.ext-wikilambda-app-abstract-page')
                || document.querySelector('.ext-wikilambda-app');
            return el ? el.innerHTML.slice(0, 3000) : 'NOT FOUND';
        """)
        print(f"\nPage HTML (first 3000 chars):\n{html}", flush=True)
    else:
        # Click the first fragment's menu
        print(f"Clicking first fragment menu...", flush=True)
        dots.first.click()
        time.sleep(2)
        shot(page, "02_menu_open")

        # Dump all menu options
        menu_items = page.locator("[role='option'], [role='menuitem'], .cdx-menu-item")
        count = menu_items.count()
        print(f"Menu has {count} options:", flush=True)
        for i in range(count):
            item = menu_items.nth(i)
            text = item.inner_text()
            aria = item.get_attribute("aria-label") or ""
            classes = item.get_attribute("class") or ""
            print(f"  [{i}] text='{text}' aria='{aria}' class='{classes}'", flush=True)

        # Also dump the raw HTML of the dropdown
        dropdown_html = page.evaluate("""
            const menus = document.querySelectorAll('.cdx-menu, [role="listbox"], [role="menu"]');
            return Array.from(menus).map(m => m.outerHTML.slice(0, 1000)).join('\\n---\\n');
        """)
        print(f"\nDropdown HTML:\n{dropdown_html}", flush=True)

        # Close menu
        page.keyboard.press("Escape")
        time.sleep(1)

    # Also check the Pinia store to understand fragment structure
    store_info = page.evaluate("""
        (() => {
            const app = document.querySelector('.ext-wikilambda-app')?.__vue_app__
                || document.querySelector('#ext-wikilambda-app')?.__vue_app__;
            if (!app) return 'No app found';
            const pinia = app.config.globalProperties.$pinia;
            const store = pinia._s.get('main');
            return JSON.stringify({
                storeKeys: Object.keys(store.$state || store).filter(k => !k.startsWith('_')).slice(0, 50),
                fragmentCount: store.fragments?.length || 'N/A',
                createNewPage: store.createNewPage,
            }, null, 2);
        })()
    """)
    print(f"\nStore info:\n{store_info}", flush=True)

    print("\nBrowser open for 30 seconds...", flush=True)
    time.sleep(30)
    browser.close()
