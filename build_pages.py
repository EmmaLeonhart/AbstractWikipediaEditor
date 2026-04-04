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


def format_fragment_english(fragment, labels):
    """Format a Z-object fragment with English labels replacing QIDs."""
    if isinstance(fragment, str):
        return fragment

    core = unwrap_fragment(fragment)
    wikitext = format_as_wikitext(core)

    # Replace QIDs with labels
    def replace_qid(match):
        qid = match.group(0)
        label = labels.get(qid, qid)
        return f"**{label}** ({qid})"

    return re.sub(r'Q\d+', replace_qid, wikitext)


def build_article_page(article, content):
    """Generate markdown for a single article page."""
    title = article["title"]
    timestamp = article["timestamp"]

    # Get label for the article's QID
    label = get_label(title) if title.startswith("Q") else title

    # Extract all QIDs and fetch labels
    qids = extract_qids_from_zobject(content)
    qids.add(title)
    labels = get_wikidata_labels(list(qids))

    # Extract function IDs
    func_ids = extract_function_ids(content)

    # Parse sections and fragments
    sections = content.get("sections", {})

    lines = [
        "---",
        f"title: \"{label}\"",
        "render_with_liquid: false",
        "---",
        "",
        f"# {label}",
        "",
        f"**Wikidata:** [{title}](https://www.wikidata.org/wiki/{title})",
        f" | **Abstract Wikipedia:** [{title}]({ABSTRACT_WIKI_BASE}{title})",
        f" | **Created:** {timestamp[:10]}",
        "",
    ]

    # Functions used
    if func_ids:
        func_list = ", ".join(
            f"`{fid}` ({FUNCTION_NAMES.get(fid, '?')})" for fid in sorted(func_ids)
            if fid not in ("Z29749", "Z27868", "Z14396")  # skip wrappers
        )
        if func_list:
            lines.append(f"**Functions used:** {func_list}")
            lines.append("")

    # Language-neutral view
    lines.append("## Language-neutral representation")
    lines.append("")
    lines.append("```")
    frag_num = 0
    for section_id, section in sections.items():
        fragments = section.get("fragments", [])
        for frag in fragments:
            frag_num += 1
            wt = format_fragment_neutral(frag)
            if wt and wt != "Z89":  # skip bare Z89 placeholder
                lines.append(wt)
    lines.append("```")
    lines.append("")

    # English aliases view
    lines.append("## English aliases")
    lines.append("")
    en_num = 0
    for section_id, section in sections.items():
        fragments = section.get("fragments", [])
        for frag in fragments:
            english = format_fragment_english(frag, labels)
            if english and english != "Z89":
                en_num += 1
                lines.append(f"{en_num}. {english}")
    lines.append("")

    # QID reference table
    article_qids = {q for q in qids if q.startswith("Q") and q != title}
    if article_qids:
        lines.append("## Referenced items")
        lines.append("")
        lines.append("| QID | Label |")
        lines.append("|-----|-------|")
        for qid in sorted(article_qids):
            lines.append(f"| [{qid}](https://www.wikidata.org/wiki/{qid}) | {labels.get(qid, '?')} |")
        lines.append("")

    lines.append(f"---")
    lines.append(f"[Back to index](../index.html)")

    return "\n".join(lines)


def build_index(articles, labels):
    """Generate the index page."""
    lines = [
        "# Abstract Wikipedia Article Catalog",
        "",
        f"**{len(articles)} articles** created on [Abstract Wikipedia](https://abstract.wikipedia.org/)",
        "",
        "Each page shows the language-neutral Z-function representation and English alias view.",
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
    lines.append("Generated by [AbstractTestBot](https://github.com/EmmaLeonhart/AbstractEditing)")

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

    # Build index
    all_labels = {a["title"]: _label_cache.get(a["title"], a["title"]) for a in articles}
    index_md = build_index(articles, all_labels)
    with open(os.path.join(SITE_DIR, "index.md"), "w", encoding="utf-8") as f:
        f.write(index_md + "\n")

    # Save failures for next retry
    save_failures(new_failures)
    print(f"\nDone! {total} pages generated in site/", flush=True)
    if new_failures:
        print(f"  {len(new_failures)} archiving failures saved for retry", flush=True)


if __name__ == "__main__":
    main()
