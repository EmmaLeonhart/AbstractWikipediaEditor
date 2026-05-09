"""Generate wikitext templates from Wikidata items automatically.

Takes a Wikidata QID, fetches its properties, and produces a wikitext
template using the property-to-function mapping.

Usage:
    python generate_wikitext.py Q706499          # Print wikitext for Kashima Jingu
    python generate_wikitext.py Q706499 --save   # Save to data/templates/auto/Q706499.wikitext
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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAPPING_PATH = os.path.join(SCRIPT_DIR, "data", "property_function_mapping.json")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "AbstractTestBot/1.0"})


def load_mapping():
    with open(MAPPING_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["mappings"]


class WikidataItemNotFound(Exception):
    """Raised when a Wikidata QID has no item (malformed or nonexistent)."""


def fetch_item_data(qid):
    """Fetch claims, labels and description for a Wikidata item.

    Raises WikidataItemNotFound if the QID is malformed or the item doesn't
    exist. The Wikidata API has two ways of saying "no such item": for a
    malformed ID (e.g. "Q51241231241" — out-of-range), the response has no
    "entities" key and instead returns an "error" object; for a valid-shape
    but nonexistent ID, the entity is returned with a "missing" key.
    """
    r = SESSION.get("https://www.wikidata.org/w/api.php", params={
        "action": "wbgetentities", "ids": qid,
        "props": "claims|labels|descriptions",
        "languages": "en", "format": "json",
    }, timeout=30)
    r.raise_for_status()
    body = r.json()
    entities = body.get("entities")
    if not entities or qid not in entities:
        raise WikidataItemNotFound(qid)
    entity = entities[qid]
    if "missing" in entity:
        raise WikidataItemNotFound(qid)
    return entity


def get_label(qid):
    """Get English label for a QID."""
    r = SESSION.get("https://www.wikidata.org/w/api.php", params={
        "action": "wbgetentities", "ids": qid,
        "props": "labels", "languages": "en", "format": "json",
    }, timeout=15)
    r.raise_for_status()
    return r.json()["entities"][qid].get("labels", {}).get("en", {}).get("value", qid)


def extract_qid_value(claim):
    """Extract QID from a claim's mainsnak if it's a wikibase-entityid."""
    snak = claim.get("mainsnak", {})
    if snak.get("snaktype") != "value":
        return None
    dv = snak.get("datavalue", {})
    if dv.get("type") == "wikibase-entityid":
        return dv["value"].get("id")
    return None


def extract_date_value(claim):
    """Extract a YYYY-MM-DD date string from a claim's mainsnak.

    Returns None unless the claim has full year/month/day precision
    (Wikidata "precision" 11). Z32473 produces a "born on <date>"
    sentence and a year-only date would render as "born on year 1966"
    or worse — better to fall back to plain P31/P19 sentences than
    to emit a malformed date.
    """
    snak = claim.get("mainsnak", {})
    if snak.get("snaktype") != "value":
        return None
    dv = snak.get("datavalue", {})
    if dv.get("type") != "time":
        return None
    val = dv.get("value", {})
    if val.get("precision", 0) < 11:  # 11 = day precision
        return None
    raw = val.get("time", "")  # "+1966-08-08T00:00:00Z"
    if raw.startswith("+"):
        raw = raw[1:]
    if "T" in raw:
        raw = raw.split("T", 1)[0]
    parts = raw.split("-")
    if len(parts) < 3 or not all(parts):
        return None
    return raw  # "1966-08-08"


# Wikidata reference properties that hold URLs
URL_REFERENCE_PROPS = [
    "P854",   # reference URL
    "P4656",  # Wikimedia import URL
    "P953",   # full work available at URL
    "P973",   # described at URL
]


def cite_fragments_for_claim(claim, seen_urls):
    """Return cite-web fragments for any new reference URLs on this claim.

    Walks the claim's references, pulls URLs from URL_REFERENCE_PROPS,
    skips URLs already in seen_urls (mutating it in place), and skips
    URLs containing '|' since that character would break wikitext
    template parsing.
    """
    out = []
    for ref in claim.get("references", []):
        snaks = ref.get("snaks", {})
        for url_prop in URL_REFERENCE_PROPS:
            if url_prop not in snaks:
                continue
            for snak in snaks[url_prop]:
                val = snak.get("datavalue", {}).get("value")
                if isinstance(val, str) and "|" not in val and val not in seen_urls:
                    seen_urls.add(val)
                    out.append(f"{{{{cite web|{val}}}}}")
    return out


def generate_wikitext(qid):
    """Generate a wikitext template for the given QID."""
    mapping = load_mapping()
    entity = fetch_item_data(qid)

    label = entity.get("labels", {}).get("en", {}).get("value", qid)
    description = entity.get("descriptions", {}).get("en", {}).get("value", "")
    claims = entity.get("claims", {})

    # Get P31 value (instance of) - needed by several templates.
    # Also track the source claim for each value so we can cite it later.
    p31_value = None
    p31_value_claims = []  # list of (qid, claim) tuples
    if "P31" in claims:
        for claim in claims["P31"]:
            v = extract_qid_value(claim)
            if v:
                p31_value_claims.append((v, claim))
                if not p31_value:
                    p31_value = v
    p31_values = [v for v, _ in p31_value_claims]

    # Collect variables we'll need
    variables = {}
    # paragraphs is a list of paragraphs, where each paragraph is a list
    # of fragment strings (sentence call followed by any cite-web calls
    # for that claim). Auto-generation puts every sentence in a single
    # paragraph so they bundle into one Z33068 — JJP's three points on
    # User_talk:Immanuelle (2026-04-28) and the Project chat thread on
    # spaces between sentences (2026-05-02) both pushed back on the
    # earlier one-paragraph-per-sentence layout. The user can still
    # insert {{p}} or a blank line in the editor to force a break.
    paragraphs = [[]]
    used_props = set()
    seen_urls = set()  # global dedupe for cite-web URLs

    def emit(frag, claim=None):
        """Append `frag` (and that claim's citations) to the current
        paragraph. Auto-generation never opens a new paragraph; section
        headers and explicit user-inserted breaks are the only ways
        to split paragraphs in the round-tripped wikitext."""
        paragraphs[-1].append(frag)
        if claim is not None:
            paragraphs[-1].extend(cite_fragments_for_claim(claim, seen_urls))

    def append_to_last(frag):
        """Tack a fragment onto the current paragraph (e.g. an extra
        citation that belongs with the preceding sentence)."""
        paragraphs[-1].append(frag)

    # Determine which location property to use (most specific wins)
    # P131 (admin territory) > P17 (country) > P30 (continent)
    location_props_by_priority = ["P131", "P17", "P30"]
    best_location = None
    for pid in location_props_by_priority:
        if pid in claims and pid in mapping:
            best_location = pid
            break

    # Check if P569 (date of birth) and P19 (place of birth) both exist
    # with day-precision dates — if so, emit a single Z32473 born sentence
    # instead of two separate P569/P19 fragments. Year-only dates fall
    # through to the regular per-property path.
    if "P569" in claims and "P19" in claims:
        birth_date = None
        birth_date_claim = None
        for c in claims["P569"]:
            d = extract_date_value(c)
            if d:
                birth_date = d
                birth_date_claim = c
                break
        birth_place = None
        birth_place_claim = None
        for c in claims["P19"]:
            v = extract_qid_value(c)
            if v:
                birth_place = v
                birth_place_claim = c
                break
        if birth_date and birth_place:
            emit(
                f"{{{{Z32473|SUBJECT|{birth_date}|{birth_place}}}}}",
                birth_date_claim,
            )
            for cite in cite_fragments_for_claim(birth_place_claim, seen_urls):
                append_to_last(cite)
            used_props.add("P569")
            used_props.add("P19")

    # Check if P106 (occupation) exists — if so, skip P31 ("is a human" is useless)
    has_occupation = "P106" in claims and "P106" in mapping

    # Collect all occupation values with their source claims
    occupation_value_claims = []  # list of (qid, claim) tuples
    if has_occupation:
        for claim in claims["P106"]:
            v = extract_qid_value(claim)
            if v:
                occupation_value_claims.append((v, claim))
    occupation_values = [v for v, _ in occupation_value_claims]

    # When both P106 (occupation) and P27 (citizenship) exist, combine first occupation
    # with citizenship: "X is a tragedy writer of Classical Athens"
    has_citizenship = "P27" in claims and "P27" in mapping
    if occupation_value_claims and has_citizenship:
        citizenship_value = None
        citizenship_claim = None
        for claim in claims["P27"]:
            v = extract_qid_value(claim)
            if v:
                citizenship_value = v
                citizenship_claim = claim
                break
        if citizenship_value:
            first_occ, first_occ_claim = occupation_value_claims[0]
            emit(
                f"{{{{Z28016|SUBJECT|{first_occ}|{citizenship_value}}}}}",
                first_occ_claim,
            )
            # Cite the citizenship claim too — append to the same paragraph.
            for cite in cite_fragments_for_claim(citizenship_claim, seen_urls):
                append_to_last(cite)
            # Remaining occupations as standalone "is a" fragments
            for occ_v, occ_claim in occupation_value_claims[1:]:
                emit(f"{{{{Z26039|SUBJECT|{occ_v}}}}}", occ_claim)
            used_props.add("P106")
            used_props.add("P27")

    # If P106 exists but P27 doesn't, emit all occupations as standalone
    if occupation_value_claims and "P106" not in used_props:
        for occ_v, occ_claim in occupation_value_claims:
            emit(f"{{{{Z26039|SUBJECT|{occ_v}}}}}", occ_claim)
        used_props.add("P106")

    # Include P31 values, but skip Q5 (human) when occupation exists
    if "P31" in mapping and p31_value_claims:
        for v, claim in p31_value_claims:
            if has_occupation and v == "Q5":
                continue
            emit(f"{{{{Z26039|SUBJECT|{v}}}}}", claim)
        used_props.add("P31")

    # Process other mapped properties
    for pid, pmap in mapping.items():
        if pid in used_props:
            continue
        if pid not in claims:
            continue

        # Skip properties marked as skipped
        if pmap.get("skip"):
            continue

        # Skip non-best location properties (dedup)
        if pmap.get("location_priority") and pid != best_location:
            continue

        # Skip properties that conflict with others present
        skip_if = pmap.get("skip_if", [])
        if any(other in claims for other in skip_if):
            continue

        # Walk claims directly so we can attach refs to each fragment
        emitted_any = False
        template = pmap["template"]
        for claim in claims[pid]:
            v = extract_qid_value(claim)
            if not v:
                continue
            line = template.replace("$value", v)
            if "$P31_value" in line:
                if p31_value:
                    line = line.replace("$P31_value", p31_value)
                else:
                    continue  # Skip if we need P31 but don't have it
            emit(line, claim)
            emitted_any = True

        if emitted_any:
            used_props.add(pid)

    # Build the frontmatter
    lines = ["---"]
    lines.append(f"title: {label}")
    if description:
        lines.append(f"description: \"{description}\"")
    lines.append(f"# Auto-generated from Wikidata {qid}")
    lines.append(f"# Properties used: {', '.join(sorted(used_props))}")
    lines.append(f"# NOTE: All available values are included below. You probably don't want")
    lines.append(f"# to use all of them — review and remove the ones that aren't relevant.")
    lines.append("variables: {}")
    lines.append("---")
    lines.append("")

    # Emit each paragraph's fragments on consecutive lines, with a blank
    # line between paragraphs so compile_template re-bundles them. Skip
    # empty paragraphs (the initial `[[]]` is empty when no claims map).
    non_empty = [p for p in paragraphs if p]
    for i, para in enumerate(non_empty):
        if i > 0:
            lines.append("")
        for frag in para:
            lines.append(frag)

    return "\n".join(lines), used_props, label


def main():
    parser = argparse.ArgumentParser(description="Generate wikitext from Wikidata item")
    parser.add_argument("qid", type=str, help="Wikidata QID (e.g. Q706499)")
    parser.add_argument("--save", action="store_true", help="Save to data/templates/auto/")
    args = parser.parse_args()

    qid = args.qid.upper()
    print(f"Generating wikitext for {qid}...", flush=True)

    try:
        wikitext, used_props, label = generate_wikitext(qid)
    except WikidataItemNotFound:
        # Stderr text becomes the Electron app's error toast verbatim
        # (the renderer already prefixes "Error: ", so we don't repeat it).
        print(f"No Wikidata item exists for {qid}", file=sys.stderr, flush=True)
        sys.exit(1)

    print(f"\n=== {label} ({qid}) ===", flush=True)
    print(f"Properties mapped: {len(used_props)} ({', '.join(sorted(used_props))})", flush=True)
    print(flush=True)
    print(wikitext, flush=True)

    if args.save:
        out_dir = os.path.join(SCRIPT_DIR, "data", "templates", "auto")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{qid}.wikitext")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(wikitext + "\n")
        print(f"\nSaved to {out_path}", flush=True)


if __name__ == "__main__":
    main()
