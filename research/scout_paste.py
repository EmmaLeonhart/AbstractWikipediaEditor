"""Scout: try the paste-from-clipboard workflow in the editor.

The goal is to replicate the manual steps:
1. Click + to add a fragment
2. Click "add empty fragment"
3. Click the three dots menu
4. Click "paste from clipboard"
5. Paste the function call JSON
"""

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

# The function call content from Q11581011 (the part inside fragments[1])
FRAGMENT_JSON = json.dumps({
    "Z1K1": "Z7",
    "Z7K1": "Z27868",
    "Z27868K1": {
        "Z1K1": "Z7",
        "Z7K1": "Z14396",
        "Z14396K1": {
            "Z1K1": "Z7",
            "Z7K1": "Z26570",
            "Z26570K1": {
                "Z1K1": "Z18",
                "Z18K1": "Z825K1"
            },
            "Z26570K2": {
                "Z1K1": "Z6091",
                "Z6091K1": "Q845945"
            },
            "Z26570K3": {
                "Z1K1": "Z6091",
                "Z6091K1": "Q17"
            },
            "Z26570K4": {
                "Z1K1": "Z18",
                "Z18K1": "Z825K2"
            }
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


# Use a QID that doesn't have a page yet
TEST_QID = "Q48744"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()

    cookies = api_login_cookies()
    for name, value in cookies.items():
        context.add_cookies([{"name": name, "value": value, "domain": ".wikipedia.org", "path": "/"}])

    page.goto(f"{WIKI_URL}/w/index.php?title={TEST_QID}&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(5)

    page.screenshot(path="paste_01_initial.png")
    print("Step 0: Initial editor", flush=True)

    # Find all buttons and clickable elements
    # We need to find the + button to add a fragment
    buttons = page.locator("button")
    print(f"\nAll visible buttons:", flush=True)
    for i in range(buttons.count()):
        btn = buttons.nth(i)
        try:
            if btn.is_visible():
                text = btn.inner_text().strip()
                classes = btn.get_attribute("class") or ""
                aria = btn.get_attribute("aria-label") or ""
                print(f"  [{i}] text='{text}' aria='{aria}' class='{classes[:100]}'", flush=True)
        except:
            pass

    # Look for the + button - it's the one that adds fragments
    # From the earlier recon, it was button[10] with "add" in its class
    add_btn = page.locator("button[class*='add-fragment'], button[aria-label*='Add'], button[aria-label*='add']")
    print(f"\nAdd-fragment buttons: {add_btn.count()}", flush=True)

    # If none found, try the icon-only button that looks like +
    if add_btn.count() == 0:
        # Try locating by the visual + icon
        icon_btns = page.locator("button .cdx-icon--add, button[class*='quiet'][class*='normal']")
        print(f"Icon buttons: {icon_btns.count()}", flush=True)

        # Let's try the specific button from the editor
        all_quiet = page.locator("button.cdx-button--weight-normal")
        print(f"Normal weight buttons: {all_quiet.count()}", flush=True)
        for i in range(all_quiet.count()):
            btn = all_quiet.nth(i)
            try:
                if btn.is_visible():
                    html = btn.inner_html()
                    print(f"  [{i}] inner_html='{html[:200]}'", flush=True)
            except:
                pass

    # Also look for any menu items that might be relevant
    print("\n--- Trying to find and click the + button ---", flush=True)

    # The + button from the screenshot is inside the lead paragraph section
    # Let's find elements inside the abstract article section
    section = page.locator(".ext-wikilambda-app-abstract-section, [class*='abstract-section'], [class*='fragment']")
    print(f"Section elements: {section.count()}", flush=True)
    for i in range(min(section.count(), 5)):
        el = section.nth(i)
        try:
            classes = el.get_attribute("class") or ""
            text = el.inner_text()[:100]
            print(f"  [{i}] class='{classes}' text='{text}'", flush=True)
        except:
            pass

    # Let's just get the full HTML structure of the editor area
    editor_html = page.locator("#ext-wikilambda-app").first.inner_html()
    with open("editor_structure.html", "w", encoding="utf-8") as f:
        f.write(editor_html)
    print(f"\nFull editor HTML saved to editor_structure.html ({len(editor_html)} chars)", flush=True)

    print("\nBrowser open for 30 seconds - please inspect the + button...", flush=True)
    time.sleep(30)
    browser.close()
