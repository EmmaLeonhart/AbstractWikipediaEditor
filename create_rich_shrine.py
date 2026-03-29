"""Create rich shrine article from Enoshima Shrine template.

1. Open Enoshima Shrine (Q11259219), copy both fragments to clipboard
2. Create target page with location fragment (pass 1)
3. Edit target page, swap deity QID in clipboard, paste deity fragment (pass 2)

The swap MUST happen after navigating to the target editor, because
the clipboard is stored in localStorage and reloads on navigation.
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

SOURCE_QID = "Q11259219"       # Enoshima Shrine (has both fragments)
TARGET_QID = "Q11261436"       # Ogami Shrine
OLD_DEITY_QID = "Q10948069"    # Three Goddesses (Enoshima's deity)
NEW_DEITY_QID = "Q644201"     # Kuraokami


def api_login_cookies():
    session = requests.Session()
    session.headers.update({"User-Agent": "AbstractTestBot/1.0"})
    r = session.get(API_URL, params={
        "action": "query", "meta": "tokens", "type": "login", "format": "json"
    })
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


def publish_page(page):
    """Force-enable Publish, click it, fill summary, confirm."""
    page.evaluate("""
        const btn = document.querySelector('button.ext-wikilambda-app-abstract-publish__publish');
        if (btn) { btn.removeAttribute('disabled'); btn.disabled = false; }
    """)
    time.sleep(0.5)
    page.evaluate("""
        document.querySelector('button.ext-wikilambda-app-abstract-publish__publish')?.click();
    """)
    time.sleep(3)

    # Fill summary using native setter to trigger Vue reactivity
    page.evaluate("""
        const inputs = document.querySelectorAll('.cdx-dialog input');
        for (const inp of inputs) {
            if (inp.offsetParent !== null) {
                const nativeSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                nativeSetter.call(inp, 'created page');
                inp.dispatchEvent(new Event('input', { bubbles: true }));
                inp.dispatchEvent(new Event('change', { bubbles: true }));
                break;
            }
        }
    """)
    time.sleep(1)

    # Click the publish button in the dialog
    page.evaluate("""
        const dialogs = document.querySelectorAll('.cdx-dialog');
        for (const d of dialogs) {
            if (d.offsetParent !== null) {
                const btns = d.querySelectorAll('button.cdx-button--action-progressive');
                for (const b of btns) {
                    if (b.offsetParent !== null && !b.disabled) { b.click(); break; }
                }
            }
        }
    """)
    time.sleep(15)


def swap_deity_in_clipboard(page, old_qid, new_qid):
    """Swap deity QID in the clipboard's deity fragment."""
    result = page.evaluate("""([oldQid, newQid]) => {
        const app = document.querySelector('.ext-wikilambda-app')?.__vue_app__
            || document.querySelector('#ext-wikilambda-app')?.__vue_app__;
        const pinia = app.config.globalProperties.$pinia;
        const store = pinia._s.get('main');
        let count = 0;
        function replaceInObj(obj) {
            if (!obj || typeof obj !== 'object') return;
            for (const key of Object.keys(obj)) {
                if (key === 'Z6K1' && obj[key] === oldQid) {
                    obj[key] = newQid;
                    count++;
                } else if (typeof obj[key] === 'object') {
                    replaceInObj(obj[key]);
                }
            }
        }
        for (const item of store.clipboardItems) {
            replaceInObj(item);
        }
        return count;
    }""", [old_qid, new_qid])
    return result


def main():
    print(f"Target: {TARGET_QID}", flush=True)
    print(f"Deity: {OLD_DEITY_QID} -> {NEW_DEITY_QID}\n", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        cookies = api_login_cookies()
        for name, value in cookies.items():
            context.add_cookies([{
                "name": name, "value": value,
                "domain": ".wikipedia.org", "path": "/",
            }])

        # =============================================
        # Copy both fragments from Enoshima
        # =============================================
        print(f"Copying both fragments from {SOURCE_QID}...", flush=True)
        page.goto(f"{WIKI_URL}/w/index.php?title={SOURCE_QID}&action=edit")
        page.wait_for_load_state("networkidle")
        time.sleep(6)

        dots = page.locator("button[aria-label*='fragment-actions-menu']")
        print(f"  Enoshima fragments: {dots.count()}", flush=True)

        # Copy location (fragment 0)
        dots.nth(0).click()
        time.sleep(1)
        page.get_by_role("option", name="Copy to clipboard").click()
        time.sleep(2)
        print("  Location copied (clipboard index will be 1)", flush=True)

        # Copy deity (fragment 1)
        dots.nth(1).click()
        time.sleep(1)
        page.get_by_role("option", name="Copy to clipboard").click()
        time.sleep(2)
        print("  Deity copied (clipboard index will be 0)", flush=True)

        # =============================================
        # Pass 1: Create page with location fragment
        # =============================================
        print(f"\nPass 1: Creating {TARGET_QID} with location sentence...", flush=True)

        page.goto(f"{WIKI_URL}/w/index.php?title={TARGET_QID}&action=edit")
        page.wait_for_load_state("networkidle")
        time.sleep(5)

        # Add empty fragment, paste location
        page.locator("button[aria-label='Menu for selecting and adding a new fragment']").click()
        time.sleep(1)
        page.get_by_role("option", name="Add empty fragment").click()
        time.sleep(2)
        page.locator("button[aria-label*='fragment-actions-menu']").first.click()
        time.sleep(1)
        page.get_by_role("option", name="Paste from clipboard").click()
        time.sleep(2)

        # Clipboard: [deity(0), location(1)] — paste location
        dialog = page.locator(".cdx-dialog").first
        items = dialog.locator("div.ext-wikilambda-app-clipboard__item-head")
        print(f"  Clipboard items: {items.count()}", flush=True)
        # Location = last copied first = index 1. But if only 2 items, let's be safe
        # and click the one that has "Z26570" (location) not "Z28016" (deity)
        # For now just use index 1
        items.nth(1).click()
        time.sleep(2)

        print("  Location pasted, publishing...", flush=True)
        publish_page(page)
        print(f"  After publish URL: {page.url}", flush=True)

        # Verify
        page.goto(f"{WIKI_URL}/wiki/{TARGET_QID}")
        page.wait_for_load_state("networkidle")
        if "There is currently no text in this page" in page.locator("body").inner_text():
            print("  ERROR: Pass 1 failed", flush=True)
            browser.close()
            return
        print("  Pass 1 done — page created", flush=True)

        # =============================================
        # Pass 2: Edit to add deity fragment with swapped QID
        # =============================================
        print(f"\nPass 2: Adding deity sentence...", flush=True)
        page.goto(f"{WIKI_URL}/w/index.php?title={TARGET_QID}&action=edit")
        page.wait_for_load_state("networkidle")
        time.sleep(6)

        # Swap deity QID NOW (after navigation, clipboard is loaded)
        swaps = swap_deity_in_clipboard(page, OLD_DEITY_QID, NEW_DEITY_QID)
        print(f"  Swapped {swaps} QID occurrences in clipboard", flush=True)

        dots2 = page.locator("button[aria-label*='fragment-actions-menu']")
        print(f"  Existing fragments: {dots2.count()}", flush=True)

        # Delete the existing deity fragment (fragment 1, the broken one)
        if dots2.count() >= 2:
            print("  Deleting old deity fragment...", flush=True)
            dots2.nth(1).click()
            time.sleep(1)
            page.get_by_role("option", name="Delete fragment").click()
            time.sleep(2)
            print("  Deleted", flush=True)

        # Add empty fragment for new deity
        page.locator("button[aria-label='Menu for selecting and adding a new fragment']").click()
        time.sleep(1)
        page.get_by_role("option", name="Add empty fragment").click()
        time.sleep(2)

        # Paste deity from clipboard (index 0 = most recently copied = deity)
        dots3 = page.locator("button[aria-label*='fragment-actions-menu']")
        dots3.last.click()
        time.sleep(1)
        page.get_by_role("option", name="Paste from clipboard").click()
        time.sleep(2)

        dialog = page.locator(".cdx-dialog").first
        items = dialog.locator("div.ext-wikilambda-app-clipboard__item-head")
        print(f"  Clipboard items: {items.count()}", flush=True)
        # Deity should be index 0 (last copied)
        items.nth(0).click()
        time.sleep(3)
        print("  Deity pasted with swapped QID", flush=True)

        # Check preview
        page.evaluate("""
            document.querySelectorAll('.cdx-dialog-backdrop').forEach(b => b.remove());
            document.querySelectorAll('.cdx-dialog button[aria-label="Close dialog"]').forEach(b => b.click());
        """)
        time.sleep(2)

        preview = page.locator(".ext-wikilambda-app-abstract-preview__body")
        if preview.count() > 0:
            print(f"  Preview: {preview.first.inner_text()[:400]}", flush=True)

        page.screenshot(path="rich_final_editor.png")

        # Publish
        print("\nPublishing...", flush=True)
        publish_page(page)
        print(f"Final URL: {page.url}", flush=True)
        page.screenshot(path="rich_final_result.png")

        if "action=edit" not in page.url:
            print("\nSUCCESS!", flush=True)
        else:
            print("\nMay have failed — still on edit page", flush=True)

        time.sleep(10)
        browser.close()


if __name__ == "__main__":
    main()
