"""Closer look at the editor: why is Publish disabled?"""

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
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()

    cookies = api_login_cookies()
    for name, value in cookies.items():
        context.add_cookies([{"name": name, "value": value, "domain": ".wikipedia.org", "path": "/"}])

    page.goto(f"{WIKI_URL}/w/index.php?title=Q29682&action=edit")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#ext-wikilambda-app", timeout=15000)
    time.sleep(5)  # Let Vue app fully render

    # Take a full-size screenshot
    page.screenshot(path="scout_02_fullsize.png", full_page=True)
    print("Screenshot: full editor", flush=True)

    # Get the full text content of the editor app
    app = page.locator("#ext-wikilambda-app")
    app_text = app.inner_text()
    print(f"\nEditor app text:\n{app_text}", flush=True)

    # Check the Publish button state
    pub = page.locator("button:has-text('Publish')")
    pub_disabled = pub.get_attribute("disabled")
    pub_classes = pub.get_attribute("class")
    print(f"\nPublish button: disabled={pub_disabled} class={pub_classes}", flush=True)

    # Get the HTML structure of the editor for analysis
    app_html = app.inner_html()
    # Save to file since it could be large
    with open("editor_html.txt", "w", encoding="utf-8") as f:
        f.write(app_html)
    print(f"Editor HTML saved to editor_html.txt ({len(app_html)} chars)", flush=True)

    # Check for any error/warning messages
    errors = page.locator(".cdx-message--error, .cdx-message--warning, .error, .warning")
    if errors.count() > 0:
        for i in range(errors.count()):
            print(f"Error/Warning [{i}]: {errors.nth(i).inner_text()[:200]}", flush=True)
    else:
        print("No error/warning messages found", flush=True)

    print("\nBrowser open for 20 seconds...", flush=True)
    time.sleep(20)
    browser.close()
