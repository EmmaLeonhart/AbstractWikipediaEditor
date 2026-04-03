"""Try to understand why Publish is disabled and find a workaround."""

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
    time.sleep(5)

    # Check publish button state
    pub = page.locator("button:has-text('Publish')").first
    pub_disabled = pub.get_attribute("disabled")
    print(f"Publish disabled: {pub_disabled}", flush=True)

    # Try to intercept the internal API calls the editor makes
    # Let's check what happens when we force-enable and click publish
    print("\nForce-enabling Publish button via JS...", flush=True)
    page.evaluate("""
        const btn = document.querySelector('button.ext-wikilambda-app-abstract-publish__publish');
        if (btn) {
            btn.removeAttribute('disabled');
            btn.disabled = false;
            console.log('Button enabled');
        }
    """)

    time.sleep(1)
    pub_disabled_after = pub.get_attribute("disabled")
    print(f"Publish disabled after JS: {pub_disabled_after}", flush=True)

    page.screenshot(path="scout_03_enabled.png")

    if pub_disabled_after is None:
        print("Button enabled! Clicking Publish...", flush=True)

        # Set up network listener to capture API calls
        api_calls = []
        def on_request(request):
            if "api.php" in request.url:
                api_calls.append({
                    "url": request.url,
                    "method": request.method,
                    "post_data": request.post_data[:500] if request.post_data else None,
                })
        page.on("request", on_request)

        pub.click()
        time.sleep(5)

        print(f"\nAPI calls after clicking Publish ({len(api_calls)}):", flush=True)
        for call in api_calls:
            print(f"  {call['method']} {call['url']}", flush=True)
            if call['post_data']:
                print(f"    POST data: {call['post_data']}", flush=True)

        page.screenshot(path="scout_04_after_publish.png")

        # Check for dialog
        dialog = page.locator(".cdx-dialog, [role='dialog']")
        if dialog.count() > 0:
            print(f"\nDialog appeared! Text: {dialog.first.inner_text()[:500]}", flush=True)
            page.screenshot(path="scout_05_dialog.png")

    print("\nBrowser open for 15 seconds...", flush=True)
    time.sleep(15)
    browser.close()
