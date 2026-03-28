"""Create Abstract Wikipedia articles via browser automation.

Workflow:
1. Log in and go to Q11581011 (source article) in edit mode
2. Copy the fragment to Abstract Wikipedia's internal clipboard
3. For each target QID:
   a. Open editor, add empty fragment
   b. Paste from clipboard
   c. Publish (no edit summary)

Usage:
    python create_via_browser.py                          # Dry run
    python create_via_browser.py --apply                  # Create articles
    python create_via_browser.py --apply --max-edits 10   # Limit
    python create_via_browser.py --apply --headed         # See the browser
"""

import io
import sys
import os
import json
import time
import argparse
import requests
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
load_dotenv()

WIKI_URL = "https://abstract.wikipedia.org"
API_URL = f"{WIKI_URL}/w/api.php"
EDIT_DELAY = 3
SOURCE_QID = "Q11581011"


def api_login_cookies():
    """Log in via API and return cookies dict."""
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


def copy_source_fragment(page):
    """Go to the source article and copy the fragment to wiki clipboard."""
    print(f"Copying fragment from {SOURCE_QID}...", flush=True)
    page.goto(f"{WIKI_URL}/w/index.php?title={SOURCE_QID}&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(5)

    # Open fragment actions menu and copy
    page.locator("button[aria-label*='fragment-actions-menu']").first.click()
    time.sleep(1)
    page.get_by_role("option", name="Copy to clipboard").click()
    time.sleep(2)
    print("Fragment copied to wiki clipboard", flush=True)


def create_article(page, qid):
    """Create an article for a single QID. Returns 'created', 'skip', or 'error'."""
    # Check if page exists
    page.goto(f"{WIKI_URL}/wiki/{qid}")
    page.wait_for_load_state("networkidle")
    body_text = page.locator("body").inner_text()

    if "There is currently no text in this page" not in body_text:
        return "skip"

    # Open editor
    page.goto(f"{WIKI_URL}/w/index.php?title={qid}&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(4)

    # Add empty fragment
    page.locator("button[aria-label='Menu for selecting and adding a new fragment']").click()
    time.sleep(1)
    page.get_by_role("option", name="Add empty fragment").click()
    time.sleep(2)

    # Open fragment menu and paste
    page.locator("button[aria-label*='fragment-actions-menu']").first.click()
    time.sleep(1)
    page.get_by_role("option", name="Paste from clipboard").click()
    time.sleep(2)

    # Click the clipboard item in the dialog
    dialog = page.locator(".cdx-dialog, [role='dialog']").first
    clipboard_item = dialog.locator("div.ext-wikilambda-app-clipboard__item").first
    clipboard_item.click()
    time.sleep(2)

    # Force-enable Publish if needed and click
    page.evaluate("""
        const btn = document.querySelector('button.ext-wikilambda-app-abstract-publish__publish');
        if (btn) { btn.removeAttribute('disabled'); btn.disabled = false; }
    """)
    time.sleep(0.5)

    pub = page.locator("button.ext-wikilambda-app-abstract-publish__publish").first
    pub.click()
    time.sleep(2)

    # Handle publish dialog
    pub_dialog = page.locator(".cdx-dialog, [role='dialog']")
    if pub_dialog.count() > 0 and pub_dialog.first.is_visible():
        # Click Publish in the dialog (no summary)
        pub_dialog.locator("button:has-text('Publish')").last.click()

        try:
            page.wait_for_url(f"**/wiki/{qid}**", timeout=20000)
            return "created"
        except Exception:
            if "action=edit" not in page.url:
                return "created"
            return "error"

    return "error"


def main():
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description="Create Abstract Wikipedia articles via browser")
    parser.add_argument("--apply", action="store_true", help="Actually create articles")
    parser.add_argument("--max-edits", type=int, default=100, help="Max articles to create")
    parser.add_argument("--run-tag", type=str, default="", help="Run tag (for workflow compat)")
    parser.add_argument("--qids-file", type=str, default="shrine_qids.json", help="JSON file with QIDs")
    parser.add_argument("--headed", action="store_true", help="Show the browser window")
    args = parser.parse_args()

    if not os.path.exists(args.qids_file):
        print(f"QIDs file not found: {args.qids_file}")
        sys.exit(1)

    with open(args.qids_file, "r", encoding="utf-8") as f:
        qids = json.load(f)

    print(f"Loaded {len(qids)} QIDs", flush=True)
    if not args.apply:
        print("DRY RUN mode (use --apply to create articles)\n", flush=True)
        for i, qid in enumerate(qids[:args.max_edits]):
            print(f"  [{i+1}] Would create {qid}", flush=True)
        print(f"\nDone! {min(len(qids), args.max_edits)} articles would be created.", flush=True)
        return

    password = os.environ.get("WIKI_MAIN_PASSWORD", "")
    if not password:
        print("ERROR: Set WIKI_MAIN_PASSWORD in .env")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        # Inject login cookies
        cookies = api_login_cookies()
        for name, value in cookies.items():
            context.add_cookies([{
                "name": name, "value": value,
                "domain": ".wikipedia.org", "path": "/",
            }])

        # Copy the source fragment once
        copy_source_fragment(page)

        stats = {"created": 0, "skip": 0, "error": 0}

        for i, qid in enumerate(qids):
            if stats["created"] >= args.max_edits:
                print(f"\nReached max edits ({args.max_edits}), stopping.", flush=True)
                break

            print(f"[{i+1}/{len(qids)}] {qid}...", flush=True, end=" ")

            try:
                result = create_article(page, qid)
                stats[result] = stats.get(result, 0) + 1
                print(result.upper(), flush=True)

                if result == "created":
                    time.sleep(EDIT_DELAY)

            except Exception as e:
                print(f"ERROR: {e}", flush=True)
                stats["error"] += 1

        browser.close()
        print(f"\nDone! {json.dumps(stats)}", flush=True)


if __name__ == "__main__":
    main()
