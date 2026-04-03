"""Inspect exactly what the clipboard contains after copying fragments."""

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
SOURCE_QID = "Q11259219"


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


with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()

    cookies = api_login_cookies()
    for name, value in cookies.items():
        context.add_cookies([{"name": name, "value": value, "domain": ".wikipedia.org", "path": "/"}])

    # Open Enoshima Shrine editor
    page.goto(f"{WIKI_URL}/w/index.php?title={SOURCE_QID}&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(6)

    dots = page.locator("button[aria-label*='fragment-actions-menu']")
    print(f"Fragments: {dots.count()}", flush=True)

    # Copy fragment 0
    dots.nth(0).click()
    time.sleep(1)
    page.get_by_role("option", name="Copy to clipboard").click()
    time.sleep(2)
    print("Copied fragment 0", flush=True)

    # Copy fragment 1
    if dots.count() >= 2:
        dots.nth(1).click()
        time.sleep(1)
        page.get_by_role("option", name="Copy to clipboard").click()
        time.sleep(2)
        print("Copied fragment 1", flush=True)

    # NOW: dump the FULL clipboard contents
    clipboard_dump = page.evaluate("""() => {
        const app = document.querySelector('.ext-wikilambda-app')?.__vue_app__
            || document.querySelector('#ext-wikilambda-app')?.__vue_app__;
        const pinia = app.config.globalProperties.$pinia;
        const store = pinia._s.get('main');
        return JSON.stringify(store.clipboardItems, null, 2);
    }""")

    print(f"\n=== FULL CLIPBOARD CONTENTS ===\n{clipboard_dump}", flush=True)

    # Also save to file for easier reading
    with open("clipboard_dump.json", "w", encoding="utf-8") as f:
        f.write(clipboard_dump)
    print("\nSaved to clipboard_dump.json", flush=True)

    time.sleep(5)
    browser.close()
