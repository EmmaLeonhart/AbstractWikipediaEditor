"""Single-pass rich shrine creation via direct clipboard injection.

Pastes both location and deity fragments in one editor session,
publishing only once. This is the most efficient approach:
- No Enoshima visit
- No QID swap
- One navigate, one publish per shrine

Usage:
    python create_rich_onepass.py                        # Dry run
    python create_rich_onepass.py --apply                # Create articles
    python create_rich_onepass.py --apply --max-edits 5  # Limit to 5
    python create_rich_onepass.py --apply --headed       # See the browser
"""

import io
import sys
import os
import json
import time
import copy
import argparse
import requests
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
load_dotenv()

WIKI_URL = "https://abstract.wikipedia.org"
API_URL = f"{WIKI_URL}/w/api.php"
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

# Clipboard template: [0] = deity fragment, [1] = location fragment
CLIPBOARD_TEMPLATE = [
    {
        "itemId": "Q8776414.2#1",
        "originKey": "Q8776414.2",
        "originSlotType": "Z89",
        "value": {
            "Z1K1": {"Z1K1": "Z9", "Z9K1": "Z7"},
            "Z7K1": {"Z1K1": "Z9", "Z9K1": "Z29749"},
            "Z29749K1": {
                "Z1K1": {"Z1K1": "Z9", "Z9K1": "Z7"},
                "Z7K1": {"Z1K1": "Z9", "Z9K1": "Z28016"},
                "Z28016K1": {
                    "Z1K1": {"Z1K1": "Z9", "Z9K1": "Z6091"},
                    "Z6091K1": {"Z1K1": "Z6", "Z6K1": "DEITY_QID_PLACEHOLDER"}
                },
                "Z28016K2": {
                    "Z1K1": {"Z1K1": "Z9", "Z9K1": "Z6091"},
                    "Z6091K1": {"Z1K1": "Z6", "Z6K1": "Q11591100"}
                },
                "Z28016K3": {
                    "Z1K1": {"Z1K1": "Z9", "Z9K1": "Z18"},
                    "Z18K1": {"Z1K1": "Z6", "Z6K1": "Z825K1"}
                },
                "Z28016K4": {
                    "Z1K1": {"Z1K1": "Z9", "Z9K1": "Z18"},
                    "Z18K1": {"Z1K1": "Z6", "Z6K1": "Z825K2"}
                }
            },
            "Z29749K2": {
                "Z1K1": {"Z1K1": "Z9", "Z9K1": "Z18"},
                "Z18K1": {"Z1K1": "Z6", "Z6K1": "Z825K2"}
            }
        },
        "objectType": "Z7",
        "resolvingType": "Z89"
    },
    {
        "itemId": "Q8776414.1#1",
        "originKey": "Q8776414.1",
        "originSlotType": "Z89",
        "value": {
            "Z1K1": {"Z1K1": "Z9", "Z9K1": "Z7"},
            "Z7K1": {"Z1K1": "Z9", "Z9K1": "Z27868"},
            "Z27868K1": {
                "Z1K1": {"Z1K1": "Z9", "Z9K1": "Z7"},
                "Z7K1": {"Z1K1": "Z9", "Z9K1": "Z14396"},
                "Z14396K1": {
                    "Z1K1": {"Z1K1": "Z9", "Z9K1": "Z7"},
                    "Z7K1": {"Z1K1": "Z9", "Z9K1": "Z26570"},
                    "Z26570K1": {
                        "Z1K1": {"Z1K1": "Z9", "Z9K1": "Z18"},
                        "Z18K1": {"Z1K1": "Z6", "Z6K1": "Z825K1"}
                    },
                    "Z26570K2": {
                        "Z1K1": {"Z1K1": "Z9", "Z9K1": "Z6091"},
                        "Z6091K1": {"Z1K1": "Z6", "Z6K1": "Q845945"}
                    },
                    "Z26570K3": {
                        "Z1K1": {"Z1K1": "Z9", "Z9K1": "Z6091"},
                        "Z6091K1": {"Z1K1": "Z6", "Z6K1": "Q17"}
                    },
                    "Z26570K4": {
                        "Z1K1": {"Z1K1": "Z9", "Z9K1": "Z18"},
                        "Z18K1": {"Z1K1": "Z6", "Z6K1": "Z825K2"}
                    }
                }
            }
        },
        "objectType": "Z7",
        "resolvingType": "Z89"
    }
]

SPARQL_QUERY = """
SELECT ?shrine ?deity WHERE {
  ?shrine wdt:P31 wd:Q845945 .
  ?shrine wdt:P825 ?deity .
}
LIMIT 200
"""


def fetch_shrines_with_deity():
    print("Querying Wikidata for shrines with deity...", flush=True)
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


def build_clipboard(deity_qid):
    clipboard = copy.deepcopy(CLIPBOARD_TEMPLATE)
    clipboard[0]["value"]["Z29749K1"]["Z28016K1"]["Z6091K1"]["Z6K1"] = deity_qid
    return clipboard


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


def create_article_onepass(page, shrine_qid, deity_qid):
    """Create a rich article with both fragments in a single editor session."""
    print(f"\n{'='*50}", flush=True)
    print(f"Creating {shrine_qid} with deity {deity_qid}", flush=True)

    clipboard = build_clipboard(deity_qid)

    page.goto(f"{WIKI_URL}/w/index.php?title={shrine_qid}&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(5)

    inject_clipboard(page, clipboard)
    time.sleep(1)

    # --- Fragment 1: Location ---
    print("  Pasting location fragment...", flush=True)
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
    if items.count() < 2:
        print("  ERROR: Clipboard injection failed — not enough items", flush=True)
        return "error"
    items.nth(1).click()  # Location = index 1
    time.sleep(3)

    # --- Fragment 2: Deity ---
    print("  Pasting deity fragment...", flush=True)
    page.locator("button[aria-label='Menu for selecting and adding a new fragment']").click()
    time.sleep(1)
    page.get_by_role("option", name="Add empty fragment").click()
    time.sleep(2)

    dots = page.locator("button[aria-label*='fragment-actions-menu']")
    dots.last.click()
    time.sleep(1)
    page.get_by_role("option", name="Paste from clipboard").click()
    time.sleep(2)

    dialog = page.locator(".cdx-dialog").first
    items = dialog.locator("div.ext-wikilambda-app-clipboard__item-head")
    items.nth(0).click()  # Deity = index 0
    time.sleep(3)

    # Dismiss any lingering dialogs
    page.evaluate("""
        document.querySelectorAll('.cdx-dialog-backdrop').forEach(b => b.remove());
        document.querySelectorAll('.cdx-dialog button[aria-label="Close dialog"]').forEach(b => b.click());
    """)
    time.sleep(2)

    # --- Single publish ---
    print("  Publishing (single pass)...", flush=True)
    publish_page(page)

    # Verify
    page.goto(f"{WIKI_URL}/wiki/{shrine_qid}")
    page.wait_for_load_state("networkidle")
    body = page.locator("body").inner_text()
    if "There is currently no text in this page" not in body:
        print(f"  SUCCESS: {page.url}", flush=True)
        return "created"
    else:
        print("  ERROR: Page has no content after publish", flush=True)
        return "error"


def main():
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description="Single-pass rich shrine creation via clipboard injection")
    parser.add_argument("--apply", action="store_true", help="Actually create articles")
    parser.add_argument("--max-edits", type=int, default=5, help="Max articles to create")
    parser.add_argument("--run-tag", type=str, default="", help="Run tag (for workflow compat)")
    parser.add_argument("--headed", action="store_true", help="Show the browser window")
    parser.add_argument("--delay", type=int, default=5, help="Seconds between articles")
    args = parser.parse_args()

    shrines = fetch_shrines_with_deity()

    print("Checking which shrines need articles...", flush=True)
    todo = []
    for s in shrines:
        if len(todo) >= args.max_edits * 3:
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

        stats = {"created": 0, "error": 0}

        for i, s in enumerate(todo):
            if stats["created"] >= args.max_edits:
                break
            try:
                result = create_article_onepass(page, s["shrine"], s["deity"])
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
