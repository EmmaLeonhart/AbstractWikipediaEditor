"""Automate the full paste workflow step by step."""

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

FRAGMENT_JSON = json.dumps({
    "Z1K1": "Z7",
    "Z7K1": "Z27868",
    "Z27868K1": {
        "Z1K1": "Z7",
        "Z7K1": "Z14396",
        "Z14396K1": {
            "Z1K1": "Z7",
            "Z7K1": "Z26570",
            "Z26570K1": {"Z1K1": "Z18", "Z18K1": "Z825K1"},
            "Z26570K2": {"Z1K1": "Z6091", "Z6091K1": "Q845945"},
            "Z26570K3": {"Z1K1": "Z6091", "Z6091K1": "Q17"},
            "Z26570K4": {"Z1K1": "Z18", "Z18K1": "Z825K2"}
        }
    }
}, ensure_ascii=False)


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


TEST_QID = "Q48744"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(
        viewport={"width": 1400, "height": 900},
        permissions=["clipboard-read", "clipboard-write"],
    )
    page = context.new_page()

    cookies = api_login_cookies()
    for name, value in cookies.items():
        context.add_cookies([{"name": name, "value": value, "domain": ".wikipedia.org", "path": "/"}])

    page.goto(f"{WIKI_URL}/w/index.php?title={TEST_QID}&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(5)
    print("Editor loaded", flush=True)

    # Step 1: Click the + button to open the fragment menu
    add_btn = page.locator("button[aria-label='Menu for selecting and adding a new fragment']")
    print(f"Step 1: Found + button: {add_btn.count()}", flush=True)
    add_btn.click()
    time.sleep(1)
    page.screenshot(path="paste_02_menu_open.png")
    print("Step 1: Menu opened", flush=True)

    # Step 2: Click "Add empty fragment"
    add_empty = page.get_by_role("option", name="Add empty fragment")
    print(f"Step 2: Found 'Add empty fragment': {add_empty.count()}", flush=True)
    add_empty.click()
    time.sleep(2)
    page.screenshot(path="paste_03_empty_fragment.png")
    print("Step 2: Empty fragment added", flush=True)

    # Step 3: Look for the three-dots menu on the new fragment
    # Dump all buttons again to find the three-dots menu
    buttons = page.locator("button")
    print(f"\nAll visible buttons after adding fragment:", flush=True)
    for i in range(buttons.count()):
        btn = buttons.nth(i)
        try:
            if btn.is_visible():
                text = btn.inner_text().strip()
                classes = btn.get_attribute("class") or ""
                aria = btn.get_attribute("aria-label") or ""
                if text or aria:
                    print(f"  [{i}] text='{text}' aria='{aria}' class='{classes[:80]}'", flush=True)
        except:
            pass

    # Look for three-dots/more/options menu button
    dots_btn = page.locator("button[aria-label*='menu'], button[aria-label*='Menu'], button[aria-label*='options'], button[aria-label*='more']")
    print(f"\nMenu/options buttons: {dots_btn.count()}", flush=True)
    for i in range(dots_btn.count()):
        btn = dots_btn.nth(i)
        try:
            if btn.is_visible():
                aria = btn.get_attribute("aria-label") or ""
                classes = btn.get_attribute("class") or ""
                print(f"  [{i}] aria='{aria}' class='{classes[:80]}'", flush=True)
        except:
            pass

    # Also get the updated editor HTML
    editor_html = page.locator("#ext-wikilambda-app").first.inner_html()
    with open("editor_after_add.html", "w", encoding="utf-8") as f:
        f.write(editor_html)
    print(f"\nEditor HTML saved ({len(editor_html)} chars)", flush=True)

    print("\nBrowser open for 30 seconds...", flush=True)
    time.sleep(30)
    browser.close()
