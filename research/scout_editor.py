"""Scout the Abstract Wikipedia editor UI step by step."""

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


with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # headed so user can see
    context = browser.new_context()
    page = context.new_page()

    # Inject API cookies
    cookies = api_login_cookies()
    for name, value in cookies.items():
        context.add_cookies([{"name": name, "value": value, "domain": ".wikipedia.org", "path": "/"}])

    # Go to the edit page
    page.goto(f"{WIKI_URL}/w/index.php?title=Q29682&action=edit")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#ext-wikilambda-app", timeout=15000)
    time.sleep(3)

    # Screenshot: initial editor state
    page.screenshot(path="scout_01_initial.png")
    print("Screenshot 1: Initial editor state", flush=True)

    # Find and click the + button
    plus_btn = page.locator("button:has-text('+'), .ext-wikilambda-app-abstract-add-fragment")
    if plus_btn.count() == 0:
        # Try other selectors for the + button
        plus_btn = page.locator("button").filter(has_text="+")

    # Actually let's just dump all buttons on the page
    buttons = page.locator("button")
    print(f"\nAll buttons on page ({buttons.count()}):", flush=True)
    for i in range(buttons.count()):
        btn = buttons.nth(i)
        try:
            text = btn.inner_text().strip()
            classes = btn.get_attribute("class") or ""
            disabled = btn.get_attribute("disabled")
            visible = btn.is_visible()
            print(f"  [{i}] text='{text}' class='{classes[:80]}' disabled={disabled} visible={visible}", flush=True)
        except:
            pass

    # Also dump all interactive elements
    print(f"\nLooking for the + add button...", flush=True)

    # Try clicking the area that has the + symbol
    add_btns = page.locator("[class*='add'], [aria-label*='add'], [aria-label*='Add']")
    print(f"Elements with 'add' in class/aria: {add_btns.count()}", flush=True)
    for i in range(min(add_btns.count(), 10)):
        el = add_btns.nth(i)
        try:
            tag = el.evaluate("el => el.tagName")
            text = el.inner_text().strip()[:50]
            classes = el.get_attribute("class") or ""
            print(f"  [{i}] <{tag}> text='{text}' class='{classes[:80]}'", flush=True)
        except:
            pass

    # Keep browser open for a moment so user can see
    print("\nBrowser will stay open for 30 seconds so you can inspect...", flush=True)
    time.sleep(30)
    browser.close()
