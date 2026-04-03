"""Full test: add fragment, paste content from clipboard, publish."""

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

    # Put the fragment JSON into the clipboard BEFORE opening the menu
    page.evaluate(f"navigator.clipboard.writeText({json.dumps(FRAGMENT_JSON)})")
    print("Clipboard set with fragment JSON", flush=True)

    # Step 1: Click + to open fragment menu
    page.locator("button[aria-label='Menu for selecting and adding a new fragment']").click()
    time.sleep(1)
    print("Step 1: + menu opened", flush=True)

    # Step 2: Click "Add empty fragment"
    page.get_by_role("option", name="Add empty fragment").click()
    time.sleep(2)
    print("Step 2: Empty fragment added", flush=True)

    # Step 3: Click the three-dots menu
    page.locator("button[aria-label*='fragment-actions-menu']").first.click()
    time.sleep(1)
    print("Step 3: Three-dots menu opened", flush=True)

    # Step 4: Click "Paste from clipboard"
    paste_opt = page.get_by_role("option", name="Paste from clipboard")
    print(f"Step 4: Found paste option: {paste_opt.count()}", flush=True)
    paste_opt.click()
    time.sleep(3)
    page.screenshot(path="paste_05_after_paste.png")
    print("Step 4: Paste from clipboard clicked", flush=True)

    # Check what happened - did a dialog appear?
    dialog = page.locator(".cdx-dialog, [role='dialog']")
    if dialog.count() > 0 and dialog.first.is_visible():
        print(f"Dialog appeared: {dialog.first.inner_text()[:300]}", flush=True)
        page.screenshot(path="paste_06_dialog.png")

    # Check if the editor content changed
    preview = page.locator(".ext-wikilambda-app-abstract-preview__body")
    if preview.count() > 0:
        preview_text = preview.first.inner_text()
        print(f"Preview text: {preview_text[:200]}", flush=True)

    # Check Publish button state
    pub = page.locator("button.ext-wikilambda-app-abstract-publish__publish").first
    pub_disabled = pub.get_attribute("disabled")
    print(f"Publish button disabled: {pub_disabled}", flush=True)

    if pub_disabled is None or pub_disabled == "":
        print("Publish is enabled! Clicking...", flush=True)
        pub.click()
        time.sleep(2)

        # Handle publish dialog - NO edit summary per user request
        dialog = page.locator(".cdx-dialog, [role='dialog']")
        if dialog.count() > 0 and dialog.first.is_visible():
            print("Publish dialog appeared", flush=True)
            dialog_pub = dialog.locator("button:has-text('Publish')").last
            dialog_pub.click()
            print("Clicked Publish in dialog", flush=True)

            try:
                page.wait_for_url(f"**/wiki/{TEST_QID}**", timeout=20000)
                print(f"SUCCESS! Page created: {page.url}", flush=True)
            except:
                print(f"Timed out. Current URL: {page.url}", flush=True)
                page.screenshot(path="paste_07_timeout.png")
    else:
        print("Publish still disabled. Trying force-enable...", flush=True)
        page.evaluate("""
            const btn = document.querySelector('button.ext-wikilambda-app-abstract-publish__publish');
            if (btn) { btn.removeAttribute('disabled'); btn.disabled = false; }
        """)
        time.sleep(1)
        pub.click()
        time.sleep(2)
        dialog = page.locator(".cdx-dialog, [role='dialog']")
        if dialog.count() > 0 and dialog.first.is_visible():
            dialog.locator("button:has-text('Publish')").last.click()
            try:
                page.wait_for_url(f"**/wiki/{TEST_QID}**", timeout=20000)
                print(f"SUCCESS! Page created: {page.url}", flush=True)
            except:
                print(f"Timed out. URL: {page.url}", flush=True)
                page.screenshot(path="paste_07_timeout.png")

    print("\nBrowser open for 15 seconds...", flush=True)
    time.sleep(15)
    browser.close()
