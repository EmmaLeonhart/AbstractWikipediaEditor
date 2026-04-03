"""Three-fragment shrine creation: location + deity + admin territory.

Extends create_rich_onepass.py by adding a third fragment using Z26570
(State location using entity and class) with the administrative territory
from Wikidata P131.

Result: articles with three sentences like:
  1. "[Shrine] is a Shinto shrine in Japan."
  2. "The deity of [Shrine] is [Deity]."
  3. "[Shrine] is a Shinto shrine in [Prefecture/City]."

Usage:
    python create_rich_threepass.py                        # Dry run
    python create_rich_threepass.py --apply --max-edits 10 # Create 10
    python create_rich_threepass.py --apply --headed        # See browser
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

# Helper to build a Z9 reference
def z9(zid):
    return {"Z1K1": {"Z1K1": "Z9", "Z9K1": "Z9"}, "Z9K1": zid}

def z9s(zid):
    """Short Z9 reference used in the clipboard format."""
    return {"Z1K1": "Z9", "Z9K1": zid}

# ============================================================
# Fragment templates
# ============================================================

def make_deity_fragment(deity_qid):
    """Fragment: 'The deity of [shrine] is [deity].' using Z28016 (defining role sentence)."""
    return {
        "itemId": "Q8776414.2#1",
        "originKey": "Q8776414.2",
        "originSlotType": "Z89",
        "value": {
            "Z1K1": z9s("Z7"),
            "Z7K1": z9s("Z29749"),
            "Z29749K1": {
                "Z1K1": z9s("Z7"),
                "Z7K1": z9s("Z28016"),
                "Z28016K1": {
                    "Z1K1": z9s("Z6091"),
                    "Z6091K1": {"Z1K1": "Z6", "Z6K1": deity_qid}
                },
                "Z28016K2": {
                    "Z1K1": z9s("Z6091"),
                    "Z6091K1": {"Z1K1": "Z6", "Z6K1": "Q11591100"}
                },
                "Z28016K3": {
                    "Z1K1": z9s("Z18"),
                    "Z18K1": {"Z1K1": "Z6", "Z6K1": "Z825K1"}
                },
                "Z28016K4": {
                    "Z1K1": z9s("Z18"),
                    "Z18K1": {"Z1K1": "Z6", "Z6K1": "Z825K2"}
                }
            },
            "Z29749K2": {
                "Z1K1": z9s("Z18"),
                "Z18K1": {"Z1K1": "Z6", "Z6K1": "Z825K2"}
            }
        },
        "objectType": "Z7",
        "resolvingType": "Z89"
    }

def make_location_fragment(location_qid):
    """Fragment: '[Shrine] is a Shinto shrine in [location].' using Z26570."""
    return {
        "itemId": "Q8776414.1#1",
        "originKey": "Q8776414.1",
        "originSlotType": "Z89",
        "value": {
            "Z1K1": z9s("Z7"),
            "Z7K1": z9s("Z27868"),
            "Z27868K1": {
                "Z1K1": z9s("Z7"),
                "Z7K1": z9s("Z14396"),
                "Z14396K1": {
                    "Z1K1": z9s("Z7"),
                    "Z7K1": z9s("Z26570"),
                    "Z26570K1": {
                        "Z1K1": z9s("Z18"),
                        "Z18K1": {"Z1K1": "Z6", "Z6K1": "Z825K1"}
                    },
                    "Z26570K2": {
                        "Z1K1": z9s("Z6091"),
                        "Z6091K1": {"Z1K1": "Z6", "Z6K1": "Q845945"}
                    },
                    "Z26570K3": {
                        "Z1K1": z9s("Z6091"),
                        "Z6091K1": {"Z1K1": "Z6", "Z6K1": location_qid}
                    },
                    "Z26570K4": {
                        "Z1K1": z9s("Z18"),
                        "Z18K1": {"Z1K1": "Z6", "Z6K1": "Z825K2"}
                    }
                }
            }
        },
        "objectType": "Z7",
        "resolvingType": "Z89"
    }


def build_clipboard(deity_qid, admin_qid):
    """Build clipboard with 3 fragments: location-Japan, deity, location-admin."""
    return [
        make_deity_fragment(deity_qid),
        make_location_fragment("Q17"),       # "X is a shrine in Japan"
        make_location_fragment(admin_qid),   # "X is a shrine in [admin territory]"
    ]


# ============================================================
# SPARQL: fetch deity AND admin territory in one query
# ============================================================

SPARQL_QUERY = """
SELECT ?shrine ?deity ?admin WHERE {
  ?shrine wdt:P31 wd:Q845945 .
  ?shrine wdt:P825 ?deity .
  ?shrine wdt:P131 ?admin .
}
LIMIT 200
"""


def fetch_shrines():
    print("Querying Wikidata for shrines with deity + admin territory...", flush=True)
    for attempt in range(5):
        try:
            r = requests.get(
                SPARQL_ENDPOINT,
                params={"query": SPARQL_QUERY, "format": "json"},
                headers={"User-Agent": "AbstractTestBot/1.0"},
                timeout=30,
            )
            r.raise_for_status()
            break
        except Exception as e:
            wait = 5 * (attempt + 1)
            print(f"  SPARQL attempt {attempt+1} failed ({e}), retrying in {wait}s...", flush=True)
            time.sleep(wait)
    else:
        raise RuntimeError("SPARQL endpoint unavailable after 5 attempts")
    data = r.json()
    seen = set()
    shrines = []
    for result in data["results"]["bindings"]:
        shrine_qid = result["shrine"]["value"].split("/")[-1]
        deity_qid = result["deity"]["value"].split("/")[-1]
        admin_qid = result["admin"]["value"].split("/")[-1]
        if shrine_qid not in seen:
            seen.add(shrine_qid)
            shrines.append({
                "shrine": shrine_qid,
                "deity": deity_qid,
                "admin": admin_qid,
            })
    print(f"Found {len(shrines)} unique shrines with deity + admin", flush=True)
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
    print(f"    Clipboard items: {count}", flush=True)
    if count <= clipboard_index:
        print(f"    ERROR: Need index {clipboard_index} but only {count} items", flush=True)
        return False
    items.nth(clipboard_index).click()
    time.sleep(3)
    return True


def create_article(page, shrine_qid, deity_qid, admin_qid):
    """Create a rich article with three fragments in a single editor session."""
    print(f"\n{'='*50}", flush=True)
    print(f"Creating {shrine_qid} (deity={deity_qid}, admin={admin_qid})", flush=True)

    clipboard = build_clipboard(deity_qid, admin_qid)

    page.goto(f"{WIKI_URL}/w/index.php?title={shrine_qid}&action=edit")
    page.wait_for_load_state("networkidle")
    time.sleep(5)

    inject_clipboard(page, clipboard)
    time.sleep(1)

    # Fragment 1: Location (Japan) — clipboard index 1
    print("  Pasting location (Japan) fragment...", flush=True)
    if not paste_fragment(page, 1, is_first=True):
        return "error"

    # Fragment 2: Deity — clipboard index 0
    print("  Pasting deity fragment...", flush=True)
    if not paste_fragment(page, 0):
        return "error"

    # Fragment 3: Location (admin territory) — clipboard index 2
    print("  Pasting admin territory fragment...", flush=True)
    if not paste_fragment(page, 2):
        return "error"

    # Dismiss any lingering dialogs
    page.evaluate("""
        document.querySelectorAll('.cdx-dialog-backdrop').forEach(b => b.remove());
        document.querySelectorAll('.cdx-dialog button[aria-label="Close dialog"]').forEach(b => b.click());
    """)
    time.sleep(2)

    # Publish
    print("  Publishing...", flush=True)
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

    parser = argparse.ArgumentParser(description="Three-fragment shrine creation")
    parser.add_argument("--apply", action="store_true", help="Actually create articles")
    parser.add_argument("--max-edits", type=int, default=10, help="Max articles to create")
    parser.add_argument("--run-tag", type=str, default="", help="Run tag (for workflow compat)")
    parser.add_argument("--headed", action="store_true", help="Show the browser window")
    parser.add_argument("--delay", type=int, default=5, help="Seconds between articles")
    parser.add_argument("--shrine", type=str, default="", help="Specific shrine QID to create")
    parser.add_argument("--deity", type=str, default="", help="Deity QID (with --shrine)")
    parser.add_argument("--admin", type=str, default="", help="Admin QID (with --shrine)")
    args = parser.parse_args()

    if args.shrine:
        shrines = [{"shrine": args.shrine, "deity": args.deity, "admin": args.admin}]
        print(f"Using specified shrine: {args.shrine} (deity={args.deity}, admin={args.admin})", flush=True)
    else:
        shrines = fetch_shrines()

    print("Checking which shrines need articles...", flush=True)
    todo = []
    for s in shrines:
        if len(todo) >= args.max_edits * 3:
            break
        if not check_article_exists(s["shrine"]):
            todo.append(s)
            print(f"  {s['shrine']} (deity: {s['deity']}, admin: {s['admin']}) — needs article", flush=True)
        if len(todo) >= args.max_edits:
            break

    print(f"\n{len(todo)} shrines to create", flush=True)

    if not args.apply:
        print("DRY RUN mode (use --apply to create articles)\n", flush=True)
        for i, s in enumerate(todo):
            print(f"  [{i+1}] {s['shrine']} — deity={s['deity']}, admin={s['admin']}", flush=True)
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
                result = create_article(page, s["shrine"], s["deity"], s["admin"])
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
