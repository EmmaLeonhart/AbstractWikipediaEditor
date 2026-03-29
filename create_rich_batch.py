"""Batch-create rich shrine articles with location + deity sentences.

Queries Wikidata for Shinto shrines that have a worshipped deity (P1049),
checks which ones lack an Abstract Wikipedia article, then creates them
using the two-pass browser automation approach from create_rich_shrine.py.

Usage:
    python create_rich_batch.py                        # Dry run
    python create_rich_batch.py --apply                # Create articles
    python create_rich_batch.py --apply --max-edits 10 # Limit to 10
    python create_rich_batch.py --apply --headed       # See the browser
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
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

SOURCE_QID = "Q11259219"       # Enoshima Shrine (template with both fragments)
OLD_DEITY_QID = "Q10948069"    # Three Goddesses (Enoshima's deity)

# Query for Shinto shrines with a dedicated deity (P825)
SPARQL_QUERY = """
SELECT ?shrine ?deity WHERE {
  ?shrine wdt:P31 wd:Q845945 .
  ?shrine wdt:P825 ?deity .
}
LIMIT 200
"""


def fetch_shrines_with_deity():
    """Fetch Shinto shrines that have a worshipped deity from Wikidata."""
    print("Querying Wikidata for shrines with worshipped deity...", flush=True)
    r = requests.get(
        SPARQL_ENDPOINT,
        params={"query": SPARQL_QUERY, "format": "json"},
        headers={"User-Agent": "AbstractTestBot/1.0"},
    )
    r.raise_for_status()
    data = r.json()

    seen = set()
    shrines = []
    for result in data["results"]["bindings"]:
        shrine_qid = result["shrine"]["value"].split("/")[-1]
        deity_qid = result["deity"]["value"].split("/")[-1]
        if shrine_qid not in seen:
            seen.add(shrine_qid)
            shrines.append({"shrine": shrine_qid, "deity": deity_qid})

    print(f"Found {len(shrines)} unique shrines with deity", flush=True)
    return shrines


def check_article_exists(qid):
    """Check if an Abstract Wikipedia article already exists for this QID."""
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


def publish_page(page):
    """Force-enable Publish, click it, confirm dialog."""
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


def copy_both_fragments(page):
    """Copy both fragments (location + deity) from Enoshima Shrine."""
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
    print("  Location copied", flush=True)

    # Copy deity (fragment 1)
    dots.nth(1).click()
    time.sleep(1)
    page.get_by_role("option", name="Copy to clipboard").click()
    time.sleep(2)
    print("  Deity copied", flush=True)


def create_rich_article(page, shrine_qid, deity_qid):
    """Create a rich article with location + deity for one shrine. Returns 'created' or 'error'."""
    print(f"\n{'='*50}", flush=True)
    print(f"Creating {shrine_qid} with deity {deity_qid}", flush=True)

    # === Pass 1: Create page with location fragment ===
    print(f"  Pass 1: location sentence...", flush=True)
    page.goto(f"{WIKI_URL}/w/index.php?title={shrine_qid}&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(5)

    page.locator("button[aria-label='Menu for selecting and adding a new fragment']").click()
    time.sleep(1)
    page.get_by_role("option", name="Add empty fragment").click()
    time.sleep(2)
    page.locator("button[aria-label*='fragment-actions-menu']").first.click()
    time.sleep(1)
    page.get_by_role("option", name="Paste from clipboard").click()
    time.sleep(2)

    dialog = page.locator(".cdx-dialog").first
    items = dialog.locator("div.ext-wikilambda-app-clipboard__item-head")
    print(f"  Clipboard items: {items.count()}", flush=True)
    items.nth(1).click()  # Location = index 1
    time.sleep(2)

    print("  Publishing pass 1...", flush=True)
    publish_page(page)

    # Verify pass 1
    page.goto(f"{WIKI_URL}/wiki/{shrine_qid}")
    page.wait_for_load_state("networkidle")
    if "There is currently no text in this page" in page.locator("body").inner_text():
        print("  ERROR: Pass 1 failed", flush=True)
        return "error"
    print("  Pass 1 done", flush=True)

    # === Pass 2: Edit to add deity fragment with swapped QID ===
    print(f"  Pass 2: deity sentence...", flush=True)
    page.goto(f"{WIKI_URL}/w/index.php?title={shrine_qid}&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(6)

    swaps = swap_deity_in_clipboard(page, OLD_DEITY_QID, deity_qid)
    print(f"  Swapped {swaps} QID occurrences", flush=True)

    dots2 = page.locator("button[aria-label*='fragment-actions-menu']")
    if dots2.count() >= 2:
        dots2.nth(1).click()
        time.sleep(1)
        page.get_by_role("option", name="Delete fragment").click()
        time.sleep(2)

    page.locator("button[aria-label='Menu for selecting and adding a new fragment']").click()
    time.sleep(1)
    page.get_by_role("option", name="Add empty fragment").click()
    time.sleep(2)

    dots3 = page.locator("button[aria-label*='fragment-actions-menu']")
    dots3.last.click()
    time.sleep(1)
    page.get_by_role("option", name="Paste from clipboard").click()
    time.sleep(2)

    dialog = page.locator(".cdx-dialog").first
    items = dialog.locator("div.ext-wikilambda-app-clipboard__item-head")
    items.nth(0).click()  # Deity = index 0
    time.sleep(3)

    page.evaluate("""
        document.querySelectorAll('.cdx-dialog-backdrop').forEach(b => b.remove());
        document.querySelectorAll('.cdx-dialog button[aria-label="Close dialog"]').forEach(b => b.click());
    """)
    time.sleep(2)

    page.screenshot(path="screenshots/rich_batch_editor.png")

    print("  Publishing pass 2...", flush=True)
    publish_page(page)

    page.screenshot(path="screenshots/rich_batch_result.png")

    if "action=edit" not in page.url:
        print(f"  SUCCESS: {page.url}", flush=True)
        # Reset deity QID in clipboard back to original for next shrine
        page.goto(f"{WIKI_URL}/w/index.php?title={shrine_qid}&action=edit")
        page.wait_for_load_state("networkidle")
        time.sleep(4)
        swap_deity_in_clipboard(page, deity_qid, OLD_DEITY_QID)
        return "created"
    else:
        print("  May have failed — still on edit page", flush=True)
        # Still reset
        swap_deity_in_clipboard(page, deity_qid, OLD_DEITY_QID)
        return "error"


def main():
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description="Batch-create rich shrine articles")
    parser.add_argument("--apply", action="store_true", help="Actually create articles")
    parser.add_argument("--max-edits", type=int, default=10, help="Max articles to create")
    parser.add_argument("--run-tag", type=str, default="", help="Run tag (for workflow compat)")
    parser.add_argument("--headed", action="store_true", help="Show the browser window")
    parser.add_argument("--delay", type=int, default=5, help="Seconds between articles")
    args = parser.parse_args()

    shrines = fetch_shrines_with_deity()

    # Filter out ones that already have articles
    print("Checking which shrines need articles...", flush=True)
    todo = []
    for s in shrines:
        if len(todo) >= args.max_edits * 3:  # Check more than we need
            break
        if not check_article_exists(s["shrine"]):
            todo.append(s)
            print(f"  {s['shrine']} (deity: {s['deity']}) — needs article", flush=True)
        if len(todo) >= args.max_edits:
            break

    print(f"\n{len(todo)} shrines to create", flush=True)

    if not args.apply:
        print("DRY RUN mode (use --apply to create articles)\n", flush=True)
        for i, s in enumerate(todo):
            print(f"  [{i+1}] {s['shrine']} with deity {s['deity']}", flush=True)
        return

    password = os.environ.get("WIKI_MAIN_PASSWORD", "")
    if not password:
        print("ERROR: Set WIKI_MAIN_PASSWORD in .env")
        sys.exit(1)

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

        copy_both_fragments(page)

        stats = {"created": 0, "error": 0}

        for i, s in enumerate(todo):
            if stats["created"] >= args.max_edits:
                break

            try:
                result = create_rich_article(page, s["shrine"], s["deity"])
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
