"""Edit an existing Abstract Wikipedia article, replacing all fragments with fresh Wikidata-generated ones.

Pipeline:
1. Find articles that already exist on Abstract Wikipedia
2. Generate fresh wikitext from Wikidata properties
3. Use Playwright to open the editor, delete all existing fragments, paste new ones, publish

Usage:
    python edit_from_qid.py Q1490                     # Dry run for Tokyo
    python edit_from_qid.py Q1490 --apply --headed    # Edit article
    python edit_from_qid.py --batch Q1,Q2,Q3 --apply  # Multiple items
    python edit_from_qid.py --random 5 --apply        # Pick 5 random existing articles
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
SCREENSHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "AbstractTestBot/1.0"})


def check_article_exists(qid):
    r = SESSION.get(f"{WIKI_URL}/wiki/{qid}", allow_redirects=True)
    return "There is currently no text in this page" not in r.text


def find_existing_articles(limit=50):
    """Find QIDs that already have articles on Abstract Wikipedia using the API."""
    r = SESSION.get(API_URL, params={
        "action": "query",
        "list": "allpages",
        "apnamespace": 0,
        "aplimit": limit,
        "format": "json",
    })
    r.raise_for_status()
    pages = r.json().get("query", {}).get("allpages", [])
    # Filter to QID-shaped titles
    qids = [p["title"] for p in pages if p["title"].startswith("Q") and p["title"][1:].isdigit()]
    return qids


def browser_login(page):
    """Log in via the browser UI. VPN usage may trigger email verification (not 2FA)."""
    username = os.environ.get("WIKI_USERNAME", "").split("@")[0]
    password = os.environ.get("WIKI_MAIN_PASSWORD", "")

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


def count_fragments(page):
    """Count how many fragment action menu buttons exist (= number of fragments)."""
    return page.locator("button[aria-label*='fragment-actions-menu']").count()


def remove_all_fragments(page):
    """Remove every existing fragment from the editor by clicking Remove on each one."""
    removed = 0
    max_attempts = 50  # safety limit

    while max_attempts > 0:
        max_attempts -= 1
        dots = page.locator("button[aria-label*='fragment-actions-menu']")
        n = dots.count()
        if n == 0:
            break

        print(f"    {n} fragment(s) remaining, removing first...", flush=True)

        # Always click the FIRST fragment's menu
        dots.first.click()
        time.sleep(1)

        # Click "Delete fragment" - the destructive menu item
        delete_opt = page.locator(".cdx-menu-item--destructive")
        if delete_opt.count() > 0 and delete_opt.first.is_visible():
            delete_opt.first.click()
            time.sleep(2)

            # Handle confirmation dialog if one appears
            confirm_btn = page.locator(".cdx-dialog button.cdx-button--action-destructive")
            if confirm_btn.count() > 0 and confirm_btn.first.is_visible():
                confirm_btn.first.click()
                time.sleep(1)

            removed += 1
        else:
            # Fallback: try by text
            fallback = page.locator(".cdx-menu-item:has-text('Delete fragment')")
            if fallback.count() > 0:
                fallback.first.click()
                time.sleep(2)
                removed += 1
            else:
                menu_items = page.locator(".cdx-menu-item")
                options = [menu_items.nth(i).inner_text() for i in range(menu_items.count())]
                print(f"    WARNING: No delete option found. Available: {options}", flush=True)
                page.keyboard.press("Escape")
                time.sleep(1)
                break

    print(f"    Removed {removed} fragment(s)", flush=True)
    return removed


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


EDIT_SUMMARY_CREATE = "Created page with [[User:Immanuelle/Abstract Wikipedia Editor|Abstract Wikipedia Editor]] (https://emmaleonhart.github.io/AbstractEditing/)"
EDIT_SUMMARY_EDIT = "Edited with [[User:Immanuelle/Abstract Wikipedia Editor|Abstract Wikipedia Editor]] (https://emmaleonhart.github.io/AbstractEditing/)"


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


def shot(page, name):
    os.makedirs(SCREENSHOTS, exist_ok=True)
    path = os.path.join(SCREENSHOTS, f"edit_{name}.png")
    page.screenshot(path=path)
    print(f"  Screenshot: {path}", flush=True)


def edit_article_from_qid(page, qid, wikitext_override=None):
    """Full pipeline: open existing article, delete fragments, paste new ones, publish."""
    print(f"\n{'='*50}", flush=True)
    print(f"Editing article for {qid}", flush=True)

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

    # Step 4: Count and remove existing fragments
    existing = count_fragments(page)
    print(f"  Found {existing} existing fragment(s)", flush=True)
    shot(page, f"{qid}_01_editor_loaded")

    if existing > 0:
        print("  Removing existing fragments...", flush=True)
        remove_all_fragments(page)
        time.sleep(2)
        shot(page, f"{qid}_02_after_removal")

    remaining = count_fragments(page)
    if remaining > 0:
        print(f"  WARNING: {remaining} fragment(s) still remain after removal", flush=True)

    # Step 5: Paste new fragments one at a time
    for i, item in enumerate(clipboard):
        print(f"  Pasting fragment {i+1}/{len(clipboard)}...", flush=True)
        if not paste_fragment(page, item, is_first=(i == 0)):
            return "error"

    # Dismiss any leftover dialogs
    page.evaluate("""
        document.querySelectorAll('.cdx-dialog-backdrop').forEach(b => b.remove());
        document.querySelectorAll('.cdx-dialog button[aria-label="Close dialog"]').forEach(b => b.click());
    """)
    time.sleep(2)

    shot(page, f"{qid}_03_after_paste")

    # Step 6: Publish
    print("  Publishing...", flush=True)
    publish_page(page, EDIT_SUMMARY_EDIT)

    # Verify
    page.goto(f"{WIKI_URL}/wiki/{qid}")
    page.wait_for_load_state("networkidle")
    body = page.locator("body").inner_text()
    if "There is currently no text in this page" not in body:
        print(f"  SUCCESS: {WIKI_URL}/wiki/{qid}", flush=True)
        return "edited"
    else:
        print("  ERROR: Page has no content after publish", flush=True)
        return "error"


def main():
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description="Edit existing Abstract Wikipedia articles with fresh Wikidata content")
    parser.add_argument("qid", nargs="?", type=str, help="Wikidata QID")
    parser.add_argument("--batch", type=str, help="Comma-separated QIDs")
    parser.add_argument("--wikitext", type=str, help="Path to wikitext file (use instead of generating from Wikidata)")
    parser.add_argument("--random", type=int, help="Pick N random existing articles to edit")
    parser.add_argument("--apply", action="store_true", help="Actually edit articles")
    parser.add_argument("--headed", action="store_true", help="Show browser")
    parser.add_argument("--delay", type=int, default=5, help="Seconds between articles")
    args = parser.parse_args()

    # Load wikitext from file if provided
    wikitext_override = None
    if args.wikitext:
        with open(args.wikitext, "r", encoding="utf-8") as f:
            wikitext_override = f.read()
        print(f"Loaded wikitext from {args.wikitext}", flush=True)

    if args.random:
        print(f"Finding existing articles...", flush=True)
        all_qids = find_existing_articles(limit=200)
        print(f"  Found {len(all_qids)} articles on Abstract Wikipedia", flush=True)

        import random
        qids = random.sample(all_qids, min(args.random, len(all_qids)))
        print(f"  Selected: {', '.join(qids)}", flush=True)
    elif args.batch:
        qids = [q.strip().upper() for q in args.batch.split(",")]
    elif args.qid:
        qids = [args.qid.upper()]
    else:
        print("ERROR: Provide a QID, --batch, or --random")
        sys.exit(1)

    # Verify articles exist
    verified = []
    for qid in qids:
        if check_article_exists(qid):
            verified.append(qid)
        else:
            print(f"  {qid}: no article exists, skipping", flush=True)

    if not verified:
        print("No existing articles to edit!")
        return

    # Dry run: just show what would change
    if not args.apply:
        print(f"DRY RUN mode (use --apply to edit articles)\n", flush=True)
        for qid in verified:
            wikitext, props, label = generate_wikitext(qid)
            print(f"\n--- {label} ({qid}) ---", flush=True)
            print(f"Properties: {', '.join(sorted(props))}", flush=True)
            print(wikitext, flush=True)
        return

    password = os.environ.get("WIKI_MAIN_PASSWORD", "")
    if not password:
        print("ERROR: Set WIKI_MAIN_PASSWORD in .env")
        sys.exit(1)

    print(f"\n{len(verified)} articles to edit", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        browser_login(page)

        stats = {"edited": 0, "error": 0, "skipped": 0}

        for i, qid in enumerate(verified):
            try:
                result = edit_article_from_qid(page, qid, wikitext_override)
                stats[result] = stats.get(result, 0) + 1
                if result == "edited" and i < len(verified) - 1:
                    time.sleep(args.delay)
            except Exception as e:
                print(f"  ERROR: {e}", flush=True)
                stats["error"] += 1

        browser.close()
        print(f"\nDone! {json.dumps(stats)}", flush=True)


if __name__ == "__main__":
    main()
