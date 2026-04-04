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

if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

from generate_wikitext import generate_wikitext
from wikitext_parser import compile_template

WIKI_URL = "https://abstract.wikipedia.org"
API_URL = f"{WIKI_URL}/w/api.php"


def check_article_exists(qid):
    r = requests.get(f"{WIKI_URL}/wiki/{qid}", allow_redirects=True,
                     headers={"User-Agent": "AbstractTestBot/1.0"})
    return "There is currently no text in this page" not in r.text


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


def publish_page(page):
    page.evaluate("""
        const btn = document.querySelector('button.ext-wikilambda-app-abstract-publish__publish');
        if (btn) { btn.removeAttribute('disabled'); btn.disabled = false; }
    """)
    time.sleep(0.5)
    page.evaluate("""
        document.querySelector('button.ext-wikilambda-app-abstract-publish__publish')?.click();
    """)
    time.sleep(3)
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


def paste_fragment(page, clipboard_index, is_first=False):
    """Add an empty fragment and paste from clipboard at the given index."""
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
    if count <= clipboard_index:
        print(f"    ERROR: Need index {clipboard_index} but only {count} items", flush=True)
        return False
    items.nth(clipboard_index).click()
    time.sleep(3)
    return True


def create_article_from_qid(page, qid):
    """Full pipeline: QID -> wikitext -> clipboard -> article."""
    print(f"\n{'='*50}", flush=True)
    print(f"Creating article for {qid}", flush=True)

    # Step 1: Generate wikitext
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

    # Step 4: Inject and paste fragments
    inject_clipboard(page, clipboard)
    time.sleep(1)

    for i in range(len(clipboard)):
        print(f"  Pasting fragment {i+1}/{len(clipboard)}...", flush=True)
        if not paste_fragment(page, i, is_first=(i == 0)):
            return "error"

    # Dismiss dialogs
    page.evaluate("""
        document.querySelectorAll('.cdx-dialog-backdrop').forEach(b => b.remove());
        document.querySelectorAll('.cdx-dialog button[aria-label="Close dialog"]').forEach(b => b.click());
    """)
    time.sleep(2)

    # Step 5: Publish
    print("  Publishing...", flush=True)
    publish_page(page)

    # Verify
    page.goto(f"{WIKI_URL}/wiki/{qid}")
    page.wait_for_load_state("networkidle")
    body = page.locator("body").inner_text()
    if "There is currently no text in this page" not in body:
        print(f"  SUCCESS: {WIKI_URL}/wiki/{qid}", flush=True)
        return "created"
    else:
        print("  ERROR: Page has no content after publish", flush=True)
        return "error"


def main():
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description="Create Abstract Wikipedia article from any QID")
    parser.add_argument("qid", nargs="?", type=str, help="Wikidata QID")
    parser.add_argument("--batch", type=str, help="Comma-separated QIDs")
    parser.add_argument("--apply", action="store_true", help="Actually create articles")
    parser.add_argument("--headed", action="store_true", help="Show browser")
    parser.add_argument("--delay", type=int, default=5, help="Seconds between articles")
    args = parser.parse_args()

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

    password = os.environ.get("WIKI_MAIN_PASSWORD", "")
    if not password:
        print("ERROR: Set WIKI_MAIN_PASSWORD in .env")
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

        cookies = api_login_cookies()
        for name, value in cookies.items():
            context.add_cookies([{
                "name": name, "value": value,
                "domain": ".wikipedia.org", "path": "/",
            }])

        stats = {"created": 0, "error": 0, "skipped": 0}

        for i, qid in enumerate(todo):
            try:
                result = create_article_from_qid(page, qid)
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
