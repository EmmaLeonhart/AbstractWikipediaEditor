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
WRAPPER_FUNCS = {"Z27868", "Z29749", "Z14396", "Z32123"}

# See convert_article.py for the rationale — the Z26955→Z28016 rewrite is
# role-specific because Z28016's K1 identity (value vs topic) depends on
# what the role (K2) is.
NAMING_ROLE_QIDS = {
    "Q5119", "Q1762010", "Q10444029", "Q23492",
    "Q8142", "Q2285706", "Q48352",
}

# Minor / non-defining roles — render via Z32982 instead of Z28016.
# See convert_article.py for the rationale.
MINOR_ROLE_QIDS = {
    "Q66305721",  # part of
}


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
        # Q6091500 ("it") — not used in articles; render as SUBJECT.
        if qid == "Q6091500":
            return "SUBJECT"
        return qid

    if z1k1 == "Z18":
        arg = obj.get("Z18K1", {})
        if isinstance(arg, dict):
            arg = arg.get("Z6K1", "?")
        if arg == "Z825K1":
            return "SUBJECT"
        if arg == "Z825K2":
            return "$lang"
        return f"${arg}"

    if z1k1 == "Z6":
        return obj.get("Z6K1", "")

    if z1k1 == "Z9":
        return obj.get("Z9K1", "?")

    # Z13518: natural number
    if z1k1 == "Z13518":
        return obj.get("Z13518K1", "?")

    # Z19677: quantity/ratio (numerator/denominator)
    if z1k1 == "Z19677":
        num = extract_value(obj.get("Z19677K2", {}))
        den = extract_value(obj.get("Z19677K3", {}))
        if den == "1":
            return num
        return f"{num}/{den}"

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

    # Z26095 ("A X is a Y") is deprecated. Rewrite as Z26039 ("X is a Y").
    # Same arg shape (K1=class/entity, K2=super-class/class, K3=lang),
    # so a name swap is enough.
    if fid == "Z26095":
        k1 = extract_value(obj.get("Z26095K1", {}))
        k2 = extract_value(obj.get("Z26095K2", {}))
        alias = FUNCTION_NAMES.get("Z26039", "Z26039")
        return "{{" + "|".join([alias, k1, k2]) + "}}"

    # Z26955 is deprecated. Rewrite as Z28016 (or Z32982 for minor roles)
    # with role-specific arg order.
    if fid == "Z26955":
        role_ref = obj.get("Z26955K1", {})
        role_qid = None
        if isinstance(role_ref, dict):
            qid_inner = role_ref.get("Z6091K1", {})
            if isinstance(qid_inner, dict):
                role_qid = qid_inner.get("Z6K1")
            elif isinstance(qid_inner, str):
                role_qid = qid_inner

        k2 = extract_value(obj.get("Z26955K2", {}))
        k3 = extract_value(obj.get("Z26955K3", {}))
        pred = extract_value(obj.get("Z26955K1", {}))

        if role_qid in NAMING_ROLE_QIDS:
            new_k1, new_k2, new_k3 = k3, pred, k2
        else:
            new_k1, new_k2, new_k3 = k2, pred, k3

        target_fid = "Z32982" if role_qid in MINOR_ROLE_QIDS else "Z28016"
        alias = FUNCTION_NAMES.get(target_fid, target_fid)
        return "{{" + "|".join([alias, new_k1, new_k2, new_k3]) + "}}"

    # Z28016 with a minor role -> Z32982 (same arg order).
    if fid == "Z28016":
        role_ref = obj.get("Z28016K2", {})
        role_qid = None
        if isinstance(role_ref, dict):
            qid_inner = role_ref.get("Z6091K1", {})
            if isinstance(qid_inner, dict):
                role_qid = qid_inner.get("Z6K1")
            elif isinstance(qid_inner, str):
                role_qid = qid_inner
        if role_qid in MINOR_ROLE_QIDS:
            k1 = extract_value(obj.get("Z28016K1", {}))
            k2 = extract_value(obj.get("Z28016K2", {}))
            k3 = extract_value(obj.get("Z28016K3", {}))
            alias = FUNCTION_NAMES.get("Z32982", "Z32982")
            return "{{" + "|".join([alias, k1, k2, k3]) + "}}"

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
    inner = "|".join(parts)
    return "{{" + inner + "}}"


def extract_paragraph_calls(obj):
    """Extract inner function calls from a paragraph combiner.

    Handles both Z33068 (new — typed list ['Z1', {call}, {call}, ...] of
    sentences) and legacy Z32234 (typed list ['Z1', {call}, ' ', {call},
    ...] interleaved with whitespace strings). Returns the inner Z-object
    calls (unwrapped); plain strings in the list are skipped.
    """
    for key in sorted(obj.keys()):
        if key in ("Z1K1", "Z7K1"):
            continue
        val = obj[key]
        if isinstance(val, list):
            calls = []
            for item in val:
                if isinstance(item, dict):
                    core = unwrap_fragment(item)
                    calls.append(core)
            return calls
    return []


def _extract_section_qid_bp(obj):
    """Extract QID from a Z31465 section title object."""
    try:
        inner = obj.get("Z31465K1", {})
        fid = get_func_id(inner)
        z10771 = inner if fid == "Z10771" else {}
        z24766 = z10771.get("Z10771K1", {})
        if get_func_id(z24766) == "Z24766":
            z6091 = z24766.get("Z24766K1", {})
            z1k1 = z6091.get("Z1K1", "")
            if isinstance(z1k1, dict):
                z1k1 = z1k1.get("Z9K1", "")
            if "Z6091" in str(z1k1):
                val = z6091.get("Z6091K1", {})
                return val.get("Z6K1") if isinstance(val, dict) else val
    except (AttributeError, KeyError):
        pass
    return None


def format_fragment_neutral(fragment):
    """Format a Z-object fragment as wikitext template syntax.

    Z33068 (paragraph from sentences, new) and legacy Z32234 (join text
    to html) are decomposed into their inner calls so that each sentence
    gets its own wikitext line within a paragraph group. Z31465 section
    titles become ==QID== headers. Returns a tuple (type, text) where
    type is 'paragraph', 'header', or None.
    """
    if isinstance(fragment, str):
        return fragment

    core = unwrap_fragment(fragment)
    fid = get_func_id(core)

    # Z31465 section title -> ==QID==
    if fid == "Z31465":
        qid = _extract_section_qid_bp(core)
        if qid:
            return f"=={qid}=="
        return None

    # Z33068 / Z32234 paragraph combiner - decompose into inner sentences
    if fid in ("Z33068", "Z32234"):
        inner_calls = extract_paragraph_calls(core)
        lines = []
        for call in inner_calls:
            wt = format_as_wikitext(call)
            if wt and wt != "Z89":
                lines.append(wt)
        return "\n".join(lines) if lines else None

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
    if qid == "SUBJECT" and article_qid:
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
        if val == "SUBJECT":
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
        elif fid == "Z32229" and len(a) >= 4:
            return f"{a[0]} has a {a[2]} {a[3]} times that of {a[1]}."
        else:
            return " ".join(a)
    except (IndexError, KeyError):
        return None


def build_article_page(article, content):
    """Generate an HTML page that uses renderer.js (same as the Electron app) to render the article."""
    title = article["title"]
    timestamp = article["timestamp"]

    label = get_label(title) if title.startswith("Q") else title

    # Extract wikitext fragments from the Z-object. New-shape paragraphs
    # are Z33068 holding a list of sentences directly; legacy paragraphs
    # are Z32123(Z32234(...)) (the Z32123 wrapper is stripped by
    # unwrap_fragment, leaving the Z32234). Either way, emit the inner
    # calls on consecutive lines with a blank line between successive
    # paragraphs so the source-form parser re-bundles them correctly.
    # Section headers (==QID==) act as their own paragraph breaks.
    sections = content.get("sections", {})
    wikitext_parts = []
    last_was_paragraph = False
    for section_id, section in sections.items():
        fragments = section.get("fragments", [])
        for frag in fragments:
            if isinstance(frag, str):
                continue
            core = unwrap_fragment(frag)
            fid = get_func_id(core)

            if fid == "Z31465":
                qid = _extract_section_qid_bp(core)
                if qid:
                    wikitext_parts.append(f"=={qid}==")
                last_was_paragraph = False
                continue

            if fid in ("Z33068", "Z32234"):
                paragraph_lines = []
                for call in extract_paragraph_calls(core):
                    wt = format_as_wikitext(call)
                    if wt and wt != "Z89":
                        paragraph_lines.append(wt)
                if paragraph_lines:
                    if last_was_paragraph:
                        wikitext_parts.append("")
                    wikitext_parts.extend(paragraph_lines)
                    last_was_paragraph = True
                continue

            wt = format_as_wikitext(core)
            if wt and wt != "Z89":
                if last_was_paragraph:
                    wikitext_parts.append("")
                wikitext_parts.append(wt)
                last_was_paragraph = True
    wikitext = "\n".join(wikitext_parts)

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
<nav><a href="../index.html">Home</a> | <a href="../catalog.html">Article Catalog</a> | <a href="../quickstatements.html">QuickStatements</a></nav>
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
        "[Home](index.html) | Article Catalog | [QuickStatements](quickstatements.html)",
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
    lines.append("[Back to home](index.html) | [Abstract Wikipedia Editor](https://github.com/EmmaLeonhart/AbstractWikipediaEditor)")

    return "\n".join(lines)


def fetch_connected_qids():
    """Query WDQS for all Wikidata items that already have an Abstract Wikipedia sitelink."""
    sparql = """SELECT ?item WHERE {
  ?sitelink schema:about ?item ;
            schema:isPartOf <https://abstract.wikipedia.org/> .
}"""
    try:
        resp = SESSION.get(
            "https://query.wikidata.org/sparql",
            params={"query": sparql, "format": "json"},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        connected = set()
        for row in data["results"]["bindings"]:
            uri = row["item"]["value"]
            qid = uri.rsplit("/", 1)[-1]
            connected.add(qid)
        return connected
    except Exception as e:
        print(f"  SPARQL query failed: {e}", flush=True)
        return set()


def build_quickstatements(articles):
    """Generate a QuickStatements page for Abstract Wikipedia articles missing sitelinks on Wikidata."""
    all_qids = [a["title"] for a in articles if a["title"].startswith("Q")]

    print(f"Checking sitelinks for {len(all_qids)} articles via WDQS...", flush=True)
    connected = fetch_connected_qids()
    print(f"  {len(connected)} already connected", flush=True)

    unconnected = [qid for qid in all_qids if qid not in connected]
    print(f"  {len(unconnected)} need sitelinks", flush=True)

    lines = [
        "[Home](index.html) | [Article Catalog](catalog.html) | QuickStatements",
        "",
        "# QuickStatements",
        "",
        f"**{len(unconnected)}** of {len(all_qids)} Abstract Wikipedia articles need sitelinks on Wikidata.",
        "",
    ]

    if unconnected:
        lines.append("Copy the block below and paste it into [QuickStatements v1](https://quickstatements.toolforge.org/#/batch).")
        lines.append("")
        lines.append("```")
        for qid in unconnected:
            lines.append(f'{qid}|Sabstractwiki|"{qid}"')
        lines.append("```")
    else:
        lines.append("All articles are already connected!")

    lines.append("")
    lines.append("---")
    lines.append("[Back to home](index.html) | [Abstract Wikipedia Editor](https://github.com/EmmaLeonhart/AbstractWikipediaEditor)")

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
        f.write("description: Abstract Wikipedia articles with rendered English previews\n")
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

    # Build QuickStatements page
    qs_md = build_quickstatements(articles)
    with open(os.path.join(SITE_DIR, "quickstatements.md"), "w", encoding="utf-8") as f:
        f.write(qs_md + "\n")

    # Save failures for next retry
    save_failures(new_failures)
    print(f"\nDone! {total} pages generated in site/", flush=True)
    if new_failures:
        print(f"  {len(new_failures)} archiving failures saved for retry", flush=True)


if __name__ == "__main__":
    main()
