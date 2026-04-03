"""Copy from Q11581011, paste into new article - with proper clipboard item click."""

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
    print(f"API login: {result['lgusername']}", flush=True)
    return session.cookies.get_dict()


SOURCE_QID = "Q11581011"
TARGET_QID = "Q48744"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()

    cookies = api_login_cookies()
    for name, value in cookies.items():
        context.add_cookies([{"name": name, "value": value, "domain": ".wikipedia.org", "path": "/"}])

    # PHASE 1: Copy fragment from Q11581011
    print(f"Phase 1: Copying fragment from {SOURCE_QID}...", flush=True)
    page.goto(f"{WIKI_URL}/w/index.php?title={SOURCE_QID}&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(5)

    page.locator("button[aria-label*='fragment-actions-menu']").first.click()
    time.sleep(1)
    page.get_by_role("option", name="Copy to clipboard").click()
    time.sleep(2)
    print("Fragment copied!", flush=True)

    # PHASE 2: Create new article with paste
    print(f"\nPhase 2: Creating {TARGET_QID}...", flush=True)
    page.goto(f"{WIKI_URL}/w/index.php?title={TARGET_QID}&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(5)

    # Add empty fragment
    page.locator("button[aria-label='Menu for selecting and adding a new fragment']").click()
    time.sleep(1)
    page.get_by_role("option", name="Add empty fragment").click()
    time.sleep(2)
    print("Empty fragment added", flush=True)

    # Open three-dots, click Paste
    page.locator("button[aria-label*='fragment-actions-menu']").first.click()
    time.sleep(1)
    page.get_by_role("option", name="Paste from clipboard").click()
    time.sleep(2)
    print("Paste dialog opened", flush=True)

    # Now find and click the clipboard item
    dialog = page.locator(".cdx-dialog, [role='dialog']").first

    # Get the dialog HTML to find clickable elements
    dialog_html = dialog.inner_html()
    with open("clipboard_dialog.html", "w", encoding="utf-8") as f:
        f.write(dialog_html)
    print(f"Dialog HTML saved ({len(dialog_html)} chars)", flush=True)

    # Try various selectors for the clipboard item
    # It's a card/item showing the fragment info
    selectors_to_try = [
        "div[class*='clipboard-item']",
        "div[class*='clipboard'] div[class*='item']",
        "[class*='clipboard-entry']",
        "[class*='fragment-clipboard']",
        "div[class*='ext-wikilambda']",
        ".ext-wikilambda-app-abstract-clipboard-item",
        "[data-testid*='clipboard']",
    ]

    for sel in selectors_to_try:
        items = dialog.locator(sel)
        if items.count() > 0:
            print(f"Found with '{sel}': {items.count()} items", flush=True)
            items.first.click()
            time.sleep(1)
            break
    else:
        # Brute force: find all clickable divs inside the dialog
        print("Trying all divs in dialog...", flush=True)
        all_divs = dialog.locator("div")
        print(f"Total divs in dialog: {all_divs.count()}", flush=True)
        for i in range(all_divs.count()):
            div = all_divs.nth(i)
            try:
                classes = div.get_attribute("class") or ""
                if classes and div.is_visible():
                    text = div.inner_text()[:60].replace('\n', ' ')
                    print(f"  [{i}] class='{classes[:80]}' text='{text}'", flush=True)
            except:
                pass

    page.screenshot(path="copypaste2_after_click.png")

    print("\nBrowser open for 30 seconds...", flush=True)
    time.sleep(30)
    browser.close()
