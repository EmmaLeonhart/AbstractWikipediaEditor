"""Debug: what happens when clicking clipboard items with 2 items."""

import io, sys, os, json, time, requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
load_dotenv()

WIKI_URL = "https://abstract.wikipedia.org"
API_URL = f"{WIKI_URL}/w/api.php"

def api_login_cookies():
    session = requests.Session()
    session.headers.update({"User-Agent": "AbstractTestBot/1.0"})
    r = session.get(API_URL, params={"action": "query", "meta": "tokens", "type": "login", "format": "json"})
    lt = r.json()["query"]["tokens"]["logintoken"]
    r = session.post(API_URL, data={"action": "login", "lgname": os.environ["WIKI_USERNAME"].split("@")[0], "lgpassword": os.environ["WIKI_MAIN_PASSWORD"], "lgtoken": lt, "format": "json"})
    print(f"Login: {r.json()['login']['result']}", flush=True)
    return session.cookies.get_dict()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()

    cookies = api_login_cookies()
    for n, v in cookies.items():
        context.add_cookies([{"name": n, "value": v, "domain": ".wikipedia.org", "path": "/"}])

    # Copy both from Enoshima
    page.goto(f"{WIKI_URL}/w/index.php?title=Q11259219&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(6)

    dots = page.locator("button[aria-label*='fragment-actions-menu']")
    dots.nth(0).click(); time.sleep(1)
    page.get_by_role("option", name="Copy to clipboard").click(); time.sleep(2)
    dots.nth(1).click(); time.sleep(1)
    page.get_by_role("option", name="Copy to clipboard").click(); time.sleep(2)
    print("Both copied", flush=True)

    # Go to a new page editor
    page.goto(f"{WIKI_URL}/w/index.php?title=Q11261436&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(5)

    # Add empty fragment
    page.locator("button[aria-label='Menu for selecting and adding a new fragment']").click()
    time.sleep(1)
    page.get_by_role("option", name="Add empty fragment").click()
    time.sleep(2)

    # Open paste dialog
    page.locator("button[aria-label*='fragment-actions-menu']").first.click()
    time.sleep(1)
    page.get_by_role("option", name="Paste from clipboard").click()
    time.sleep(2)

    # Inspect the clipboard dialog
    dialog = page.locator(".cdx-dialog").first
    items = dialog.locator("div.ext-wikilambda-app-clipboard__item")
    print(f"\nClipboard items: {items.count()}", flush=True)

    for i in range(items.count()):
        item = items.nth(i)
        text = item.inner_text()[:150].replace('\n', ' | ')
        html = item.inner_html()[:200]
        print(f"  Item [{i}]: text='{text}'", flush=True)

    page.screenshot(path="debug_clipboard_2items.png")

    # Try clicking item 0 first (deity)
    print("\nClicking item 0 (should be deity)...", flush=True)
    items.nth(0).click()
    time.sleep(3)
    print(f"URL after click 0: {page.url}", flush=True)
    page.screenshot(path="debug_after_click0.png")

    time.sleep(10)
    browser.close()
