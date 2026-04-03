"""Full paste workflow: add fragment, open three-dots, paste content, publish."""

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

    # Step 1: Click + to open fragment menu
    add_btn = page.locator("button[aria-label='Menu for selecting and adding a new fragment']")
    add_btn.click()
    time.sleep(1)
    print("Step 1: + menu opened", flush=True)

    # Step 2: Click "Add empty fragment"
    page.get_by_role("option", name="Add empty fragment").click()
    time.sleep(2)
    print("Step 2: Empty fragment added", flush=True)

    # Step 3: Click the three-dots (fragment actions) menu
    dots_btn = page.locator("button[aria-label*='fragment-actions-menu']")
    print(f"Step 3: Found three-dots button: {dots_btn.count()}", flush=True)
    dots_btn.first.click()
    time.sleep(1)
    page.screenshot(path="paste_04_dots_menu.png")

    # Dump what's in the dropdown
    menu_items = page.locator("[role='option'], [role='menuitem'], .cdx-menu-item")
    print(f"Menu items visible: {menu_items.count()}", flush=True)
    for i in range(menu_items.count()):
        item = menu_items.nth(i)
        try:
            text = item.inner_text().strip()
            visible = item.is_visible()
            if visible:
                print(f"  [{i}] '{text}'", flush=True)
        except:
            pass

    # Look for paste option
    paste_option = page.locator("[role='option']:has-text('Paste'), [role='option']:has-text('paste'), [role='menuitem']:has-text('Paste'), [role='menuitem']:has-text('paste')")
    print(f"\nPaste options found: {paste_option.count()}", flush=True)

    # Also try getting all visible list items
    lis = page.locator("li.cdx-menu-item--enabled")
    print(f"Enabled menu items: {lis.count()}", flush=True)
    for i in range(lis.count()):
        li = lis.nth(i)
        try:
            if li.is_visible():
                print(f"  [{i}] '{li.inner_text().strip()}'", flush=True)
        except:
            pass

    print("\nBrowser open for 30 seconds...", flush=True)
    time.sleep(30)
    browser.close()
