"""Build GitHub Pages site from Abstract Wikipedia articles.

Fetches all articles from Abstract Wikipedia, generates markdown pages
with both language-neutral (raw Z-function calls) and English alias
views, and attempts to archive each page on the Wayback Machine.

Failed archiving attempts are saved to data/archive_failures.json
and retried on the next run.

Usage:
    python build_pages.py              # Build site + archive
    python build_pages.py --no-archive # Build site only (skip archiving)
"""

import io
import sys
import os
import json
import re
import time
import argparse
import requests

if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.join(SCRIPT_DIR, "site")
PAGES_DIR = os.path.join(SITE_DIR, "pages")
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
FAILURES_PATH = os.path.join(DATA_DIR, "archive_failures.json")

API_URL = "https://abstract.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WAYBACK_SAVE = "https://web.archive.org/save/"
ABSTRACT_WIKI_BASE = "https://abstract.wikipedia.org/wiki/"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "AbstractTestBot/1.0"})

# Cache for Wikidata labels
_label_cache = {}

# Reverse alias lookup: Z-ID -> human name
FUNCTION_NAMES = {}


def load_function_names():
    """Load reverse aliases from function_aliases.json."""
    aliases_path = os.path.join(DATA_DIR, "function_aliases.json")
    try:
        with open(aliases_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for zid, names in data.get("reverse", {}).items():
            FUNCTION_NAMES[zid] = names[0]
    except (FileNotFoundError, json.JSONDecodeError):
        pass


def get_wikidata_labels(qids):
    """Fetch English labels for a batch of QIDs (up to 50)."""
    missing = [q for q in qids if q not in _label_cache]
    if not missing:
        return {q: _label_cache[q] for q in qids}

    for i in range(0, len(missing), 50):
        batch = missing[i:i+50]
        try:
            r = SESSION.get(WIKIDATA_API, params={
                "action": "wbgetentities", "ids": "|".join(batch),
                "props": "labels", "languages": "en", "format": "json",
            }, timeout=15)
            r.raise_for_status()
            entities = r.json().get("entities", {})
            for qid in batch:
                label = entities.get(qid, {}).get("labels", {}).get("en", {}).get("value")
                _label_cache[qid] = label or qid
        except Exception:
            for qid in batch:
                _label_cache[qid] = qid

    return {q: _label_cache.get(q, q) for q in qids}


def get_label(qid):
    """Get English label for a single QID."""
    return get_wikidata_labels([qid])[qid]


def fetch_all_articles():
    """Fetch all articles from Abstract Wikipedia via allpages API, newest first."""
    articles = []
    params = {
        "action": "query", "list": "recentchanges",
        "rctype": "new", "rcnamespace": 0,
        "rclimit": 500, "rcprop": "title|timestamp|sizes|user",
        "format": "json",
    }

    while True:
        r = SESSION.get(API_URL, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        for rc in data["query"]["recentchanges"]:
            articles.append({
                "title": rc["title"],
                "timestamp": rc["timestamp"],
                "size": rc.get("newlen", 0),
                "user": rc.get("user", ""),
            })
        if "continue" not in data:
            break
        params["rccontinue"] = data["continue"]["rccontinue"]

    print(f"Found {len(articles)} articles (newest first)", flush=True)
    return articles


def fetch_articles_batch(titles):
    """Fetch raw Z-object content for a batch of articles (up to 50).
    Returns dict mapping title -> parsed JSON content."""
    results = {}
    for attempt in range(3):
        try:
            r = SESSION.get(API_URL, params={
                "action": "query", "titles": "|".join(titles),
                "prop": "revisions", "rvprop": "content",
                "rvslots": "main", "format": "json",
            }, timeout=60)
            if r.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"rate-limited, waiting {wait}s... ", end="", flush=True)
                time.sleep(wait)
                continue
            r.raise_for_status()
            pages = r.json()["query"]["pages"]
            for page in pages.values():
                page_title = page.get("title", "")
                revisions = page.get("revisions", [])
                if revisions:
                    content = revisions[0].get("slots", {}).get("main", {}).get("*", "")
                    if content:
                        try:
                            results[page_title] = json.loads(content)
                        except json.JSONDecodeError:
                            pass
            return results
        except requests.exceptions.HTTPError as e:
            if "429" in str(e) and attempt < 2:
                time.sleep(30 * (attempt + 1))
                continue
            raise
    return results


def extract_qids_from_zobject(obj, qids=None):
    """Recursively extract all QIDs referenced in a Z-object."""
    if qids is None:
        qids = set()
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key == "Z6091K1" and isinstance(val, str) and val.startswith("Q"):
                qids.add(val)
            elif key == "Z6K1" and isinstance(val, str) and val.startswith("Q"):
                qids.add(val)
            else:
                extract_qids_from_zobject(val, qids)
    elif isinstance(obj, list):
        for item in obj:
            extract_qids_from_zobject(item, qids)
    return qids


def extract_function_ids(obj, funcs=None):
    """Recursively extract all Z-function IDs from a Z-object."""
    if funcs is None:
        funcs = set()
    if isinstance(obj, dict):
        if obj.get("Z1K1") == "Z7" or (isinstance(obj.get("Z1K1"), dict) and obj["Z1K1"].get("Z9K1") == "Z7"):
            fid = obj.get("Z7K1", {})
            if isinstance(fid, dict):
                zid = fid.get("Z9K1")
                if zid:
                    funcs.add(zid)
            elif isinstance(fid, str):
                funcs.add(fid)
        for val in obj.values():
            extract_function_ids(val, funcs)
    elif isinstance(obj, list):
        for item in obj:
            extract_function_ids(item, funcs)
    return funcs


# Wrapper functions that should be stripped to show the inner call
WRAPPER_FUNCS = {"Z27868", "Z29749", "Z14396"}


def get_func_id(obj):
    """Extract function ID from a Z7 call."""
    if not isinstance(obj, dict):
        return None
    z1k1 = obj.get("Z1K1", "")
    if isinstance(z1k1, dict):
        z1k1 = z1k1.get("Z9K1", "")
    if z1k1 != "Z7":
        return None
    func_ref = obj.get("Z7K1", {})
    if isinstance(func_ref, dict):
        return func_ref.get("Z9K1")
    return func_ref if isinstance(func_ref, str) else None


def unwrap_fragment(obj):
    """Strip wrapper functions (Z27868, Z29749, Z14396) to get the core call."""
    if not isinstance(obj, dict):
        return obj
    fid = get_func_id(obj)
    if fid in WRAPPER_FUNCS:
        # Find the first argument that's itself a function call
        for key, val in sorted(obj.items()):
            if key in ("Z1K1", "Z7K1"):
                continue
            if isinstance(val, dict) and get_func_id(val):
                return unwrap_fragment(val)
    return obj


def extract_value(obj):
    """Extract a clean value string from a Z-object node."""
    if isinstance(obj, str):
        return obj
    if not isinstance(obj, dict):
        return str(obj)

    z1k1 = obj.get("Z1K1", "")
    if isinstance(z1k1, dict):
        z1k1 = z1k1.get("Z9K1", "")

    if z1k1 == "Z6091":
        qid = obj.get("Z6091K1", {})
        if isinstance(qid, dict):
            qid = qid.get("Z6K1", "?")
        return qid

    if z1k1 == "Z18":
        arg = obj.get("Z18K1", {})
        if isinstance(arg, dict):
            arg = arg.get("Z6K1", "?")
        if arg == "Z825K1":
            return "$subject"
        if arg == "Z825K2":
            return "$lang"
        return f"${arg}"

    if z1k1 == "Z6":
        return obj.get("Z6K1", "")

    if z1k1 == "Z9":
        return obj.get("Z9K1", "?")

    # Nested function call - show just the function name
    fid = get_func_id(obj)
    if fid:
        alias = FUNCTION_NAMES.get(fid, fid)
        return alias

    # Unknown structure - just show type
    return "?"


def format_as_wikitext(obj):
    """Format a Z-object as wikitext template syntax.

    Uses raw tags to prevent Jekyll/Liquid from interpreting the braces.
    """
    if isinstance(obj, str):
        if obj == "Z89":
            return "Z89"
        return obj

    fid = get_func_id(obj)
    if not fid:
        return str(obj)[:100]

    alias = FUNCTION_NAMES.get(fid, fid)

    args = []
    for key in sorted(obj.keys()):
        if key in ("Z1K1", "Z7K1"):
            continue
        val = obj[key]
        extracted = extract_value(val)
        # Skip $lang args (auto-filled)
        if extracted == "$lang":
            continue
        args.append(extracted)

    parts = [alias] + args
    inner = " | ".join(parts)
    return "{{" + inner + "}}"


def format_fragment_neutral(fragment):
    """Format a Z-object fragment as wikitext template syntax."""
    if isinstance(fragment, str):
        return fragment

    core = unwrap_fragment(fragment)
    return format_as_wikitext(core)


def format_fragment_linked(fragment):
    """Format a Z-object fragment with QIDs as clickable links."""
    if isinstance(fragment, str):
        return fragment

    core = unwrap_fragment(fragment)
    wikitext = format_as_wikitext(core)

    # Make QIDs clickable with HTML links
    def link_qid(match):
        qid = match.group(0)
        return f'<a href="https://www.wikidata.org/wiki/{qid}">{qid}</a>'

    return re.sub(r'Q\d+', link_qid, wikitext)


def qid_link_label(qid, article_qid=None):
    """Return an HTML link with the QID's English label."""
    if qid == "$subject" and article_qid:
        label = get_label(article_qid)
        return f'<a href="https://www.wikidata.org/wiki/{article_qid}">{label}</a>'
    if qid.startswith("Q"):
        label = get_label(qid)
        return f'<a href="https://www.wikidata.org/wiki/{qid}">{label}</a>'
    return qid


def render_english_preview(fragment, article_qid):
    """Render a Z-object fragment as an approximate English sentence with linked labels."""
    if isinstance(fragment, str):
        return None

    core = unwrap_fragment(fragment)
    fid = get_func_id(core)
    if not fid:
        return None

    # Extract positional args (skip Z1K1, Z7K1)
    args = []
    for key in sorted(core.keys()):
        if key in ("Z1K1", "Z7K1"):
            continue
        val = core[key]
        extracted = extract_value(val)
        if extracted == "$lang":
            continue
        args.append(extracted)

    # Resolve args to linked labels
    def r(val):
        if val == "$subject":
            return qid_link_label(val, article_qid)
        return qid_link_label(val)

    a = [r(v) for v in args]

    # Render sentence based on function
    try:
        if fid == "Z26570" and len(a) >= 3:
            return f"{a[0]} is a {a[1]} in {a[2]}."
        elif fid == "Z26039" and len(a) >= 2:
            return f"{a[0]} is a {a[1]}."
        elif fid == "Z26095" and len(a) >= 2:
            return f"A {a[0]} is a {a[1]}."
        elif fid == "Z28016" and len(a) >= 3:
            return f"{a[0]} is the {a[1]} of {a[2]}."
        elif fid == "Z26955" and len(a) >= 3:
            return f"{a[1]} is {a[0]} of {a[2]}."
        elif fid == "Z29591" and len(a) >= 3:
            return f"{a[0]} is a {a[1]} {a[2]}."
        elif fid == "Z26627" and len(a) >= 2:
            return f"{a[0]} are {a[1]}."
        elif fid == "Z27243" and len(a) >= 4:
            return f"{a[0]} is the {a[1]} {a[2]} in {a[3]}."
        elif fid == "Z27173" and len(a) >= 3:
            return f"{a[0]} is {a[1]} {a[2]}."
        elif fid == "Z29743" and len(a) >= 3:
            return f"A {a[0]} is a {a[1]} {a[2]}."
        else:
            return " ".join(a)
    except (IndexError, KeyError):
        return None


def build_article_page(article, content):
    """Generate an HTML page that uses renderer.js (same as the Electron app) to render the article."""
    title = article["title"]
    timestamp = article["timestamp"]

    label = get_label(title) if title.startswith("Q") else title

    # Extract wikitext fragments from the Z-object
    sections = content.get("sections", {})
    wikitext_lines = []
    for section_id, section in sections.items():
        fragments = section.get("fragments", [])
        for frag in fragments:
            wt = format_fragment_neutral(frag)
            if wt and wt != "Z89":
                wikitext_lines.append(wt)
    wikitext = "\n".join(wikitext_lines)

    # Escape for embedding in JS
    wikitext_escaped = wikitext.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")

    return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{label}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 900px; margin: 2em auto; padding: 0 1em; line-height: 1.6; color: #333; }}
h1 {{ border-bottom: 2px solid #3366cc; padding-bottom: .3em; }}
h2 {{ color: #3366cc; margin-top: 1.5em; }}
a {{ color: #3366cc; }}
.meta {{ font-size: 14px; color: #555; margin-bottom: 1.5em; }}
.meta a {{ margin-right: 12px; }}
#rendered {{ background: #f8f9fa; border: 1px solid #ddd; border-radius: 6px; padding: 20px; margin-bottom: 1.5em; font-size: 16px; line-height: 1.8; }}
#rendered .sentence {{ margin-bottom: 8px; }}
#rendered a {{ color: #3366cc; text-decoration: underline; text-decoration-style: dotted; }}
#rendered a:hover {{ color: #2a4b8d; }}
pre {{ background: #f5f5f5; padding: 1em; border-radius: 4px; overflow-x: auto; font-size: 13px; }}
nav {{ background: #f5f5f5; padding: 10px 16px; border-radius: 4px; margin-bottom: 1.5em; font-size: 14px; }}
nav a {{ margin-right: 8px; }}
.back {{ margin-top: 2em; border-top: 1px solid #ddd; padding-top: 1em; }}
</style>
</head>
<body>
<nav><a href="../index.html">Home</a> | <a href="../catalog.html">Article Catalog</a></nav>
<h1>{label}</h1>
<div class="meta">
  <a href="https://www.wikidata.org/wiki/{title}">Wikidata: {title}</a>
  <a href="{ABSTRACT_WIKI_BASE}{title}">Abstract Wikipedia</a>
  <span>Created: {timestamp[:10]}</span>
</div>

<h2>Rendered</h2>
<div id="rendered"><em>Loading...</em></div>

<h2>Wikitext</h2>
<pre>{wikitext}</pre>

<div class="back"><a href="../catalog.html">Back to catalog</a> | <a href="../index.html">Home</a></div>

<script src="../renderer.js"></script>
<script>
renderWikitext(`{wikitext_escaped}`, "{title}", document.getElementById("rendered"));
</script>
</body>
</html>'''


def build_index(articles, labels):
    """Generate the index page."""
    lines = [
        "[Home](index.html) | Article Catalog",
        "",
        "# Abstract Wikipedia Article Catalog",
        "",
        f"**{len(articles)} articles** on [Abstract Wikipedia](https://abstract.wikipedia.org/) with rendered English previews.",
        "",
        "Abstract Wikipedia articles often fail to render in the browser. Click any article below to see a live-rendered English preview.",
        "",
        "| # | Article | QID | Created | Fragments |",
        "|---|---------|-----|---------|-----------|",
    ]

    for i, a in enumerate(articles, 1):
        title = a["title"]
        label = labels.get(title, title)
        ts = a["timestamp"][:10]
        frag_count = a.get("fragment_count", "?")
        lines.append(f"| {i} | [{label}](pages/{title}.html) | [{title}]({ABSTRACT_WIKI_BASE}{title}) | {ts} | {frag_count} |")

    lines.append("")
    lines.append("---")
    lines.append("[Back to home](index.html) | Generated by [AbstractTestBot](https://github.com/EmmaLeonhart/AbstractEditing)")

    return "\n".join(lines)


def try_archive(title):
    """Try to archive a page on the Wayback Machine. Returns True on success."""
    page_url = ABSTRACT_WIKI_BASE + title
    try:
        resp = SESSION.post(
            WAYBACK_SAVE,
            data={"url": page_url, "capture_all": "on"},
            timeout=120,
        )
        if resp.status_code == 429:
            print("rate-limited", end="", flush=True)
            time.sleep(30)
            return False
        if resp.status_code >= 500:
            print(f"{resp.status_code}", end="", flush=True)
            return False
        return resp.status_code in (200, 302)
    except Exception as e:
        print(f"err", end="", flush=True)
        return False


def load_failures():
    """Load list of QIDs that failed archiving on previous runs."""
    try:
        with open(FAILURES_PATH, "r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_failures(failures):
    """Save list of QIDs that failed archiving."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(FAILURES_PATH, "w") as f:
        json.dump(sorted(failures), f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Build GitHub Pages site from Abstract Wikipedia")
    parser.add_argument("--no-archive", action="store_true", help="Skip Wayback Machine archiving")
    args = parser.parse_args()

    load_function_names()

    # Fetch all articles (newest first from recentchanges)
    articles = fetch_all_articles()
    if not articles:
        print("No articles found!")
        return

    # Reverse to process oldest first
    articles.reverse()

    # Prepare output directories
    os.makedirs(PAGES_DIR, exist_ok=True)

    # Write Jekyll config
    with open(os.path.join(SITE_DIR, "_config.yml"), "w") as f:
        f.write("title: Abstract Wikipedia Article Catalog\n")
        f.write("description: All articles created by AbstractTestBot on Abstract Wikipedia\n")
        f.write("theme: jekyll-theme-cayman\n")
        f.write("baseurl: /AbstractEditing\n")

    # Load previous archive failures for retry
    prev_failures = load_failures()
    new_failures = set()

    # Collect all QIDs for batch label fetching
    all_qids = [a["title"] for a in articles if a["title"].startswith("Q")]
    # Batch fetch labels (50 at a time)
    for i in range(0, len(all_qids), 50):
        get_wikidata_labels(all_qids[i:i+50])
        time.sleep(0.5)

    total = len(articles)
    print(f"\nProcessing {total} articles...", flush=True)

    # Batch fetch content (50 at a time to reduce API calls)
    content_cache = {}
    for batch_start in range(0, total, 50):
        batch = articles[batch_start:batch_start + 50]
        batch_titles = [a["title"] for a in batch]
        print(f"  Fetching content batch {batch_start//50 + 1} ({len(batch_titles)} pages)...", flush=True)
        batch_content = fetch_articles_batch(batch_titles)
        content_cache.update(batch_content)
        time.sleep(3)

    print(f"  Fetched content for {len(content_cache)}/{total} articles\n", flush=True)

    for i, article in enumerate(articles):
        title = article["title"]
        label = _label_cache.get(title, title)
        print(f"[{i+1}/{total}] {title} ({label}) ... ", end="", flush=True)

        content = content_cache.get(title)
        if not content:
            print("no content, skipping", flush=True)
            continue

        # Count fragments
        frag_count = 0
        for section in content.get("sections", {}).values():
            frag_count += len(section.get("fragments", []))
        article["fragment_count"] = frag_count

        # Generate page markdown
        page_md = build_article_page(article, content)
        page_path = os.path.join(PAGES_DIR, f"{title}.md")
        with open(page_path, "w", encoding="utf-8") as f:
            f.write(page_md + "\n")
        print("page ", end="", flush=True)

        # Archive
        if not args.no_archive:
            print("archive:", end="", flush=True)
            if try_archive(title):
                print("ok ", end="", flush=True)
            else:
                new_failures.add(title)
                print("fail ", end="", flush=True)
            time.sleep(8)

        print("done", flush=True)

    # Re-reverse to newest first for the index
    articles.reverse()

    # Build catalog (separate from landing page)
    all_labels = {a["title"]: _label_cache.get(a["title"], a["title"]) for a in articles}
    catalog_md = build_index(articles, all_labels)
    with open(os.path.join(SITE_DIR, "catalog.md"), "w", encoding="utf-8") as f:
        f.write(catalog_md + "\n")

    # Save failures for next retry
    save_failures(new_failures)
    print(f"\nDone! {total} pages generated in site/", flush=True)
    if new_failures:
        print(f"  {len(new_failures)} archiving failures saved for retry", flush=True)


if __name__ == "__main__":
    main()
