"""Copy fragment from Q11581011 first, then paste into new article."""

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


SOURCE_QID = "Q11581011"  # Your existing article to copy from
TARGET_QID = "Q48744"     # New article to create

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()

    cookies = api_login_cookies()
    for name, value in cookies.items():
        context.add_cookies([{"name": name, "value": value, "domain": ".wikipedia.org", "path": "/"}])

    # ============================================
    # PHASE 1: Go to Q11581011 edit page and COPY the fragment
    # ============================================
    print(f"Phase 1: Opening {SOURCE_QID} to copy fragment...", flush=True)
    page.goto(f"{WIKI_URL}/w/index.php?title={SOURCE_QID}&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(5)
    page.screenshot(path="copypaste_01_source.png")

    # Find the three-dots menu on the existing fragment
    dots_btns = page.locator("button[aria-label*='fragment-actions-menu']")
    print(f"Found {dots_btns.count()} fragment action buttons", flush=True)

    if dots_btns.count() == 0:
        print("No fragment actions found. Looking for other menus...", flush=True)
        buttons = page.locator("button")
        for i in range(buttons.count()):
            btn = buttons.nth(i)
            try:
                if btn.is_visible():
                    aria = btn.get_attribute("aria-label") or ""
                    text = btn.inner_text().strip()
                    if aria or text:
                        print(f"  [{i}] aria='{aria}' text='{text}'", flush=True)
            except:
                pass

    # Click the three-dots on the SECOND fragment (index 1 = the function call, not Z89)
    # Or just the first visible one
    dots_btn = dots_btns.first
    dots_btn.click()
    time.sleep(1)
    page.screenshot(path="copypaste_02_menu.png")

    # List menu items
    lis = page.locator("li.cdx-menu-item--enabled")
    print("Menu items:", flush=True)
    for i in range(lis.count()):
        li = lis.nth(i)
        try:
            if li.is_visible():
                print(f"  [{i}] '{li.inner_text().strip()}'", flush=True)
        except:
            pass

    # Click "Copy to clipboard"
    copy_opt = page.get_by_role("option", name="Copy to clipboard")
    print(f"Found 'Copy to clipboard': {copy_opt.count()}", flush=True)
    copy_opt.click()
    time.sleep(2)
    print("Fragment copied to wiki clipboard!", flush=True)
    page.screenshot(path="copypaste_03_copied.png")

    # ============================================
    # PHASE 2: Go to target article and PASTE
    # ============================================
    print(f"\nPhase 2: Opening {TARGET_QID} to paste...", flush=True)
    page.goto(f"{WIKI_URL}/w/index.php?title={TARGET_QID}&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(5)

    # Add empty fragment first
    page.locator("button[aria-label='Menu for selecting and adding a new fragment']").click()
    time.sleep(1)
    page.get_by_role("option", name="Add empty fragment").click()
    time.sleep(2)
    print("Empty fragment added", flush=True)

    # Open three-dots on the new fragment
    page.locator("button[aria-label*='fragment-actions-menu']").first.click()
    time.sleep(1)

    # Click "Paste from clipboard"
    paste_opt = page.get_by_role("option", name="Paste from clipboard")
    paste_opt.click()
    time.sleep(2)
    page.screenshot(path="copypaste_04_paste_dialog.png")
    print("Paste from clipboard clicked", flush=True)

    # Check for clipboard dialog
    dialog = page.locator(".cdx-dialog, [role='dialog']")
    if dialog.count() > 0 and dialog.first.is_visible():
        dialog_text = dialog.first.inner_text()[:500]
        print(f"Dialog text: {dialog_text}", flush=True)
        page.screenshot(path="copypaste_05_clipboard_dialog.png")

        # Look for the copied item in the clipboard and click it
        clipboard_items = dialog.locator("li, [role='option'], .cdx-menu-item")
        print(f"Clipboard items: {clipboard_items.count()}", flush=True)
        for i in range(clipboard_items.count()):
            try:
                text = clipboard_items.nth(i).inner_text().strip()
                print(f"  [{i}] '{text[:100]}'", flush=True)
            except:
                pass

        # Try clicking the first item
        if clipboard_items.count() > 0:
            clipboard_items.first.click()
            time.sleep(2)
            print("Clicked clipboard item", flush=True)

        # Look for a confirm/paste button
        paste_btn = dialog.locator("button:has-text('Paste'), button:has-text('Select'), button:has-text('OK'), button.cdx-button--action-progressive")
        if paste_btn.count() > 0:
            print(f"Found confirm button: {paste_btn.first.inner_text()}", flush=True)
            paste_btn.first.click()
            time.sleep(2)

    page.screenshot(path="copypaste_06_after_paste.png")

    # Check preview
    preview = page.locator(".ext-wikilambda-app-abstract-preview__body")
    if preview.count() > 0:
        print(f"Preview: {preview.first.inner_text()[:200]}", flush=True)

    # Check Publish state
    pub = page.locator("button.ext-wikilambda-app-abstract-publish__publish").first
    pub_disabled = pub.get_attribute("disabled")
    print(f"Publish disabled: {pub_disabled}", flush=True)

    print("\nBrowser open for 30 seconds...", flush=True)
    time.sleep(30)
    browser.close()
