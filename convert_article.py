"""Convert an Abstract Wikipedia article's Z-objects to wikitext.

Fetches the article content from Abstract Wikipedia and converts
each fragment to human-readable wikitext using function aliases.

Usage:
    python convert_article.py Q191
"""

import io
import sys
import os
import json
import requests

if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")

API_URL = "https://abstract.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "AbstractTestBot/1.0"})

# Load function aliases
FUNCTION_NAMES = {}
aliases_path = os.path.join(DATA_DIR, "function_aliases.json")
try:
    with open(aliases_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for zid, names in data.get("reverse", {}).items():
        FUNCTION_NAMES[zid] = names[0]
except (FileNotFoundError, json.JSONDecodeError):
    pass

WRAPPER_FUNCS = {"Z27868", "Z29749", "Z14396", "Z32123"}


def get_func_id(obj):
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
    if not isinstance(obj, dict):
        return obj
    fid = get_func_id(obj)
    if fid in WRAPPER_FUNCS:
        for key, val in sorted(obj.items()):
            if key in ("Z1K1", "Z7K1"):
                continue
            if isinstance(val, dict) and get_func_id(val):
                return unwrap_fragment(val)
    return obj


def extract_value(obj):
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
        # Q6091500 is the deliberate exception to literal round-tripping:
        # pull it as the wikitext alias "it" so the source reads naturally,
        # and let compile_template resolve "it" back to the Q6091500 entity
        # on push. This closes the loop — "it" is the only token that ever
        # appears in source wikitext for the pronoun, whether the author
        # typed it themselves or it came in from a round-tripped article.
        if qid == "Q6091500":
            return "it"
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

    # Z20420: date — inverse of wikitext_parser.z20420_date(). Emit as
    # YYYY-MM-DD so compile_template's parse_date_string accepts it on push.
    if z1k1 == "Z20420":
        try:
            year = obj["Z20420K1"]["Z20159K2"]["Z13518K1"]
            month_ref = obj["Z20420K2"]["Z20342K1"]["Z16098K1"]
            day = obj["Z20420K2"]["Z20342K2"]["Z13518K1"]
            month = int(month_ref.replace("Z", "")) - 16100
            return f"{int(year):04d}-{month:02d}-{int(day):02d}"
        except (KeyError, TypeError, ValueError, AttributeError):
            return "?"

    fid = get_func_id(obj)
    if fid:
        return FUNCTION_NAMES.get(fid, fid)

    return "?"


def format_as_wikitext(obj):
    if isinstance(obj, str):
        return obj if obj != "Z89" else None

    fid = get_func_id(obj)
    if not fid:
        return None

    alias = FUNCTION_NAMES.get(fid, fid)
    args = []
    for key in sorted(obj.keys()):
        if key in ("Z1K1", "Z7K1"):
            continue
        val = obj[key]
        extracted = extract_value(val)
        if extracted == "$lang":
            continue
        args.append(extracted)

    parts = [alias] + args
    return "{{" + "|".join(parts) + "}}"


def _extract_section_qid(obj):
    """Extract the QID from a Z31465 section title object.

    Expected structure: Z31465(Z10771(Z24766(Z6091(QID), ...)))
    """
    try:
        inner = obj.get("Z31465K1", {})
        z10771 = inner if get_func_id(inner) == "Z10771" else {}
        z24766 = z10771.get("Z10771K1", {})
        if get_func_id(z24766) == "Z24766":
            z6091 = z24766.get("Z24766K1", {})
            z1k1 = z6091.get("Z1K1", "")
            if isinstance(z1k1, dict):
                z1k1 = z1k1.get("Z9K1", "")
            if z1k1 == "Z6091" or (isinstance(z1k1, str) and "Z6091" in z1k1):
                return z6091.get("Z6091K1", {}).get("Z6K1", None) if isinstance(z6091.get("Z6091K1"), dict) else z6091.get("Z6091K1", None)
    except (AttributeError, KeyError):
        pass
    return None


def convert_article_to_wikitext(qid, oldid=None):
    """Fetch an Abstract Wikipedia article and return its wikitext, or None.

    This is the data-only version of the CLI. The CLI wrapper below prints
    the result; other scripts call this directly to round-trip articles
    (e.g. roundtrip_broken_it_articles.py).
    """
    # Fetch from Abstract Wikipedia
    params = {
        "action": "query",
        "prop": "revisions", "rvprop": "content",
        "rvslots": "main", "format": "json",
    }
    if oldid:
        params["revids"] = oldid
    else:
        params["titles"] = qid
    r = SESSION.get(API_URL, params=params, timeout=30)
    r.raise_for_status()
    pages = r.json()["query"]["pages"]

    content = None
    for page in pages.values():
        revisions = page.get("revisions", [])
        if revisions:
            raw = revisions[0].get("slots", {}).get("main", {}).get("*", "")
            if raw:
                content = json.loads(raw)

    if not content:
        return None

    # Get label
    lr = SESSION.get(WIKIDATA_API, params={
        "action": "wbgetentities", "ids": qid,
        "props": "labels|descriptions", "languages": "en", "format": "json",
    }, timeout=15)
    lr.raise_for_status()
    entity = lr.json()["entities"].get(qid, {})
    label = entity.get("labels", {}).get("en", {}).get("value", qid)
    description = entity.get("descriptions", {}).get("en", {}).get("value", "")

    # Output wikitext
    lines = [
        "---",
        f"title: {label}",
    ]
    if description:
        lines.append(f'description: "{description}"')
    lines.append(f"# From Abstract Wikipedia {qid}")
    lines.append("variables: {}")
    lines.append("---")
    lines.append("")

    sections = content.get("sections", {})
    paragraph_count = 0
    for section in sections.values():
        for frag in section.get("fragments", []):
            if isinstance(frag, str):
                continue
            core = unwrap_fragment(frag)
            fid = get_func_id(core)

            # Z31465 (section title) — extract QID and emit ==QID==
            if fid == "Z31465":
                section_qid = _extract_section_qid(core)
                if section_qid:
                    lines.append(f"=={section_qid}==")
                    paragraph_count += 1
                continue

            # Z32234 (join text to html) is a paragraph combiner -
            # decompose into individual sentences
            if fid == "Z32234":
                if paragraph_count > 0:
                    lines.append("{{p}}")
                for key in sorted(core.keys()):
                    if key in ("Z1K1", "Z7K1"):
                        continue
                    val = core[key]
                    if isinstance(val, list):
                        for item in val:
                            if isinstance(item, dict):
                                inner = unwrap_fragment(item)
                                wt = format_as_wikitext(inner)
                                if wt:
                                    lines.append(wt)
                paragraph_count += 1
                continue

            wt = format_as_wikitext(core)
            if wt:
                if paragraph_count > 0:
                    lines.append("{{p}}")
                lines.append(wt)
                paragraph_count += 1

    return "\n".join(lines)


def convert_article(qid, oldid=None):
    """CLI entry point: fetch and print wikitext (or exit on failure)."""
    wikitext = convert_article_to_wikitext(qid, oldid=oldid)
    if wikitext is None:
        print(f"# No article found for {qid}", flush=True)
        sys.exit(1)
    print(wikitext, flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Convert Abstract Wikipedia article to wikitext")
    parser.add_argument("qid", type=str, help="Wikidata QID")
    parser.add_argument("--oldid", type=str, default=None, help="Specific revision ID to fetch")
    args = parser.parse_args()
    convert_article(args.qid.upper(), oldid=args.oldid)
