"""Create an Abstract Wikipedia article for any Wikidata item.

Combines the full pipeline:
1. generate_wikitext.py: QID -> wikitext template
2. wikitext_parser.py: wikitext -> clipboard JSON
3. Playwright: inject clipboard + publish

Usage:
    python create_from_qid.py Q1490                     # Dry run for Tokyo
    python create_from_qid.py Q1490 --apply --headed    # Create article
    python create_from_qid.py --batch Q1,Q2,Q3 --apply  # Multiple items
"""

import io
import sys
import os
import json
import time
import argparse
import requests
import base64

if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

from generate_wikitext import generate_wikitext
from wikitext_parser import compile_template

WIKI_URL = "https://abstract.wikipedia.org"
API_URL = f"{WIKI_URL}/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"


def check_article_exists(qid):
    r = requests.get(f"{WIKI_URL}/wiki/{qid}", allow_redirects=True,
                     headers={"User-Agent": "AbstractTestBot/1.0"})
    return "There is currently no text in this page" not in r.text


def add_wikidata_sitelink(qid):
    """Add an Abstract Wikipedia sitelink to the Wikidata item using bot credentials."""
    username = base64.b64decode(os.environ.get("WIKI_USERNAME_B64", "")).decode('utf-8')
    password = base64.b64decode(os.environ.get("WIKI_PASSWORD_B64", "")).decode('utf-8')
    if not username or not password:
        print(f"  SITELINK: Skipped (no bot credentials in .env)", flush=True)
        return False

    session = requests.Session()
    session.headers.update({"User-Agent": "AbstractTestBot/1.0"})

    # Step 1: Get login token
    r = session.get(WIKIDATA_API, params={
        "action": "query", "meta": "tokens", "type": "login", "format": "json",
    })
    login_token = r.json()["query"]["tokens"]["logintoken"]

    # Step 2: Log in with bot credentials
    r = session.post(WIKIDATA_API, data={
        "action": "login",
        "lgname": username,
        "lgpassword": password,
        "lgtoken": login_token,
        "format": "json",
    })
    login_result = r.json().get("login", {})
    if login_result.get("result") != "Success":
        print(f"  SITELINK: Login failed: {login_result}", flush=True)
        return False
    print(f"  SITELINK: Logged in to Wikidata as {login_result.get('lgusername')}", flush=True)

    # Step 3: Get CSRF token
    r = session.get(WIKIDATA_API, params={
        "action": "query", "meta": "tokens", "format": "json",
    })
    csrf_token = r.json()["query"]["tokens"]["csrftoken"]

    # Step 4: Set the sitelink
    r = session.post(WIKIDATA_API, data={
        "action": "wbsetsitelink",
        "id": qid,
        "linksite": "abstractwiki",
        "linktitle": qid,
        "summary": "Adding Abstract Wikipedia sitelink",
        "token": csrf_token,
        "format": "json",
    })
    result = r.json()
    if "error" in result:
        print(f"  SITELINK: Error: {result['error'].get('info', result['error'])}", flush=True)
        return False

    print(f"  SITELINK: Added abstractwikipedia sitelink for {qid}", flush=True)
    return True


def browser_login(page):
    """Log in via the browser UI. VPN usage may trigger email verification (not 2FA)."""
    username = base64.b64decode(os.environ.get("WIKI_USERNAME_B64", "")).decode('utf-8').split("@")[0]
    password = base64.b64decode(os.environ.get("WIKI_MAIN_PASSWORD_B64", "")).decode('utf-8')

    page.goto(f"{WIKI_URL}/w/index.php?title=Special:UserLogin")
    page.wait_for_load_state("networkidle")

    # Fill login form
    page.locator("#wpName1").fill(username)
    page.locator("#wpPassword1").fill(password)
    page.locator("#wpLoginAttempt").click()
    print(f"Submitted login for {username}, waiting for redirect...", flush=True)

    # Wait for redirect. VPN usage may trigger email verification (not 2FA).
    # Give the user up to 5 minutes to handle any verification prompt.
    page.wait_for_url(
        lambda url: "Special:UserLogin" not in url,
        timeout=300000,
    )
    print("Login successful!", flush=True)


def inject_clipboard(page, clipboard_data):
    page.evaluate("""(data) => {
        localStorage.setItem('ext-wikilambda-app-clipboard', JSON.stringify(data));
        const app = document.querySelector('.ext-wikilambda-app')?.__vue_app__
            || document.querySelector('#ext-wikilambda-app')?.__vue_app__;
        if (app) {
            const pinia = app.config.globalProperties.$pinia;
            const store = pinia._s.get('main');
            store.clipboardItems = data;
        }
    }""", clipboard_data)


TOOL_CREDIT = "([[User:Immanuelle/Abstract Wikipedia Editor|AWE]])"
EDIT_SUMMARY_CREATE = f"Created page {TOOL_CREDIT}"
EDIT_SUMMARY_EDIT = f"Edited {TOOL_CREDIT}"


def publish_page(page, summary=""):
    page.evaluate("""
        const btn = document.querySelector('button.ext-wikilambda-app-abstract-publish__publish');
        if (btn) { btn.removeAttribute('disabled'); btn.disabled = false; }
    """)
    time.sleep(0.5)
    page.evaluate("""
        document.querySelector('button.ext-wikilambda-app-abstract-publish__publish')?.click();
    """)
    time.sleep(3)

    # Fill edit summary if there's an input in the dialog
    if summary:
        page.evaluate("""(summary) => {
            const dialogs = document.querySelectorAll('.cdx-dialog');
            for (const d of dialogs) {
                if (d.offsetParent !== null) {
                    const input = d.querySelector('input[type="text"], textarea, .cdx-text-input__input');
                    if (input) {
                        input.value = summary;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                }
            }
        }""", summary)
        time.sleep(1)

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


def paste_fragment(page, single_item, is_first=False):
    """Add an empty fragment and paste a single clipboard item into it.

    Instead of injecting all items at once and selecting by index, we inject
    only the one item we need right before pasting.  This avoids issues with
    clipboard items being consumed or re-indexed after each paste.
    """
    # Inject just this one item so index 0 is always the right one
    inject_clipboard(page, [single_item])
    time.sleep(0.5)

    page.locator("button[aria-label='Menu for selecting and adding a new fragment']").click()
    time.sleep(1)
    page.get_by_role("option", name="Add empty fragment").click()
    time.sleep(2)

    dots = page.locator("button[aria-label*='fragment-actions-menu']")
    if is_first:
        dots.first.click()
    else:
        dots.last.click()
    time.sleep(1)
    page.get_by_role("option", name="Paste from clipboard").click()
    time.sleep(2)

    dialog = page.locator(".cdx-dialog").first
    items = dialog.locator("div.ext-wikilambda-app-clipboard__item-head")
    count = items.count()
    if count == 0:
        print(f"    ERROR: No clipboard items found in dialog", flush=True)
        return False
    items.first.click()
    time.sleep(3)
    return True


def create_article_from_qid(page, qid, wikitext_override=None, extra_summary=None):
    """Full pipeline: QID -> wikitext -> clipboard -> article."""
    print(f"\n{'='*50}", flush=True)
    print(f"Creating article for {qid}", flush=True)

    # Step 1: Get wikitext (from file override or generate from Wikidata)
    if wikitext_override:
        wikitext = wikitext_override
        print(f"  Using provided wikitext ({len(wikitext)} chars)", flush=True)
    else:
        wikitext, used_props, label = generate_wikitext(qid)
        print(f"  {label}: {len(used_props)} properties -> wikitext", flush=True)
        if not used_props:
            print("  SKIP: No mappable properties found", flush=True)
            return "skipped"

    # Save wikitext for tracking
    auto_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "templates", "auto")
    os.makedirs(auto_dir, exist_ok=True)
    wt_path = os.path.join(auto_dir, f"{qid}.wikitext")
    with open(wt_path, "w", encoding="utf-8") as f:
        f.write(wikitext + "\n")
    print(f"  Saved wikitext to {wt_path}", flush=True)

    # Step 2: Compile to clipboard JSON
    clipboard = compile_template(wikitext, {"subject": qid})
    print(f"  Compiled to {len(clipboard)} clipboard fragments", flush=True)

    if not clipboard:
        print("  SKIP: No fragments generated", flush=True)
        return "skipped"

    # Step 3: Navigate to editor
    page.goto(f"{WIKI_URL}/w/index.php?title={qid}&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(5)

    # Step 4: Paste fragments one at a time
    for i, item in enumerate(clipboard):
        print(f"  Pasting fragment {i+1}/{len(clipboard)}...", flush=True)
        if not paste_fragment(page, item, is_first=(i == 0)):
            return "error"

    # Dismiss dialogs
    page.evaluate("""
        document.querySelectorAll('.cdx-dialog-backdrop').forEach(b => b.remove());
        document.querySelectorAll('.cdx-dialog button[aria-label="Close dialog"]').forEach(b => b.click());
    """)
    time.sleep(2)

    # Step 5: Publish
    if extra_summary:
        summary = f"{extra_summary} {TOOL_CREDIT}"
    else:
        summary = EDIT_SUMMARY_CREATE
    print(f"  Publishing with summary: {summary}", flush=True)
    publish_page(page, summary)

    # Verify
    page.goto(f"{WIKI_URL}/wiki/{qid}")
    page.wait_for_load_state("networkidle")
    body = page.locator("body").inner_text()
    if "There is currently no text in this page" not in body:
        print(f"  SUCCESS: {WIKI_URL}/wiki/{qid}", flush=True)
        # Add Wikidata sitelink now that the page exists
        try:
            add_wikidata_sitelink(qid)
        except Exception as e:
            print(f"  SITELINK: Exception: {e}", flush=True)
        return "created"
    else:
        print("  ERROR: Page has no content after publish", flush=True)
        return "error"


def main():
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description="Create Abstract Wikipedia article from any QID")
    parser.add_argument("qid", nargs="?", type=str, help="Wikidata QID")
    parser.add_argument("--batch", type=str, help="Comma-separated QIDs")
    parser.add_argument("--wikitext", type=str, help="Path to wikitext file (use instead of generating from Wikidata)")
    parser.add_argument("--apply", action="store_true", help="Actually create articles")
    parser.add_argument("--headed", action="store_true", help="Show browser")
    parser.add_argument("--summary", type=str, default=None, help="Extra text appended to the edit summary")
    parser.add_argument("--delay", type=int, default=5, help="Seconds between articles")
    args = parser.parse_args()

    # Load wikitext from file if provided
    wikitext_override = None
    if args.wikitext:
        with open(args.wikitext, "r", encoding="utf-8") as f:
            wikitext_override = f.read()
        print(f"Loaded wikitext from {args.wikitext}", flush=True)

    if args.batch:
        qids = [q.strip().upper() for q in args.batch.split(",")]
    elif args.qid:
        qids = [args.qid.upper()]
    else:
        print("ERROR: Provide a QID or --batch")
        sys.exit(1)

    # Dry run: just generate wikitext
    if not args.apply:
        print("DRY RUN mode (use --apply to create articles)\n", flush=True)
        for qid in qids:
            if check_article_exists(qid):
                print(f"  {qid}: article already exists, skipping", flush=True)
                continue
            wikitext, props, label = generate_wikitext(qid)
            print(f"\n--- {label} ({qid}) ---", flush=True)
            print(f"Properties: {', '.join(sorted(props))}", flush=True)
            print(wikitext, flush=True)
        return

    password = os.environ.get("WIKI_MAIN_PASSWORD_B64", "")
    if not password:
        print("ERROR: Set WIKI_MAIN_PASSWORD_B64 in .env")
        sys.exit(1)

    # Filter out existing articles
    todo = []
    for qid in qids:
        if check_article_exists(qid):
            print(f"  {qid}: article already exists, skipping", flush=True)
        else:
            todo.append(qid)

    if not todo:
        print("No articles to create!")
        return

    print(f"\n{len(todo)} articles to create", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        browser_login(page)

        stats = {"created": 0, "error": 0, "skipped": 0}

        for i, qid in enumerate(todo):
            try:
                result = create_article_from_qid(page, qid, wikitext_override, extra_summary=args.summary)
                stats[result] = stats.get(result, 0) + 1
                if result == "created" and i < len(todo) - 1:
                    time.sleep(args.delay)
            except Exception as e:
                print(f"  ERROR: {e}", flush=True)
                stats["error"] += 1

        browser.close()
        print(f"\nDone! {json.dumps(stats)}", flush=True)


if __name__ == "__main__":
    main()
