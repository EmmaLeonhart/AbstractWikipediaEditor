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


def fetch_item_data(qid):
    """Fetch claims, labels and description for a Wikidata item."""
    r = SESSION.get("https://www.wikidata.org/w/api.php", params={
        "action": "wbgetentities", "ids": qid,
        "props": "claims|labels|descriptions",
        "languages": "en", "format": "json",
    }, timeout=30)
    r.raise_for_status()
    entity = r.json()["entities"][qid]
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


def generate_wikitext(qid):
    """Generate a wikitext template for the given QID."""
    mapping = load_mapping()
    entity = fetch_item_data(qid)

    label = entity.get("labels", {}).get("en", {}).get("value", qid)
    description = entity.get("descriptions", {}).get("en", {}).get("value", "")
    claims = entity.get("claims", {})

    # Get P31 value (instance of) - needed by several templates
    p31_value = None
    p31_values = []
    if "P31" in claims:
        for claim in claims["P31"]:
            v = extract_qid_value(claim)
            if v:
                p31_values.append(v)
                if not p31_value:
                    p31_value = v

    # Collect variables we'll need
    variables = {}
    fragments = []
    used_props = set()

    # Determine which location property to use (most specific wins)
    # P131 (admin territory) > P17 (country) > P30 (continent)
    location_props_by_priority = ["P131", "P17", "P30"]
    best_location = None
    for pid in location_props_by_priority:
        if pid in claims and pid in mapping:
            best_location = pid
            break

    # Check if P106 (occupation) exists — if so, skip P31 ("is a human" is useless)
    has_occupation = "P106" in claims and "P106" in mapping

    # Collect all occupation values
    occupation_values = []
    if has_occupation:
        for claim in claims["P106"]:
            v = extract_qid_value(claim)
            if v:
                occupation_values.append(v)

    # When both P106 (occupation) and P27 (citizenship) exist, combine first occupation
    # with citizenship: "X is a tragedy writer of Classical Athens"
    has_citizenship = "P27" in claims and "P27" in mapping
    if occupation_values and has_citizenship:
        citizenship_value = None
        for claim in claims["P27"]:
            v = extract_qid_value(claim)
            if v:
                citizenship_value = v
                break
        if citizenship_value:
            fragments.append(f"{{{{Z26955|{occupation_values[0]}|SUBJECT|{citizenship_value}}}}}")
            # Remaining occupations as standalone "is a" fragments
            for occ in occupation_values[1:]:
                fragments.append(f"{{{{Z26039|SUBJECT|{occ}}}}}")
            used_props.add("P106")
            used_props.add("P27")

    # If P106 exists but P27 doesn't, emit all occupations as standalone
    if occupation_values and "P106" not in used_props:
        for occ in occupation_values:
            fragments.append(f"{{{{Z26039|SUBJECT|{occ}}}}}")
        used_props.add("P106")

    # Include P31 values, but skip Q5 (human) when occupation exists
    if "P31" in mapping and p31_values:
        for v in p31_values:
            if has_occupation and v == "Q5":
                continue
            fragments.append(f"{{{{Z26039|SUBJECT|{v}}}}}")
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

        # Include all QID values for this property, not just the first
        values = []
        for claim in claims[pid]:
            v = extract_qid_value(claim)
            if v:
                values.append(v)
        if not values:
            continue
        value = values[0]

        # Build the template line based on the mapping
        func = pmap["function"]
        template = pmap["template"]

        # Emit a line for each value of this property
        for v in values:
            line = template.replace("SUBJECT", "SUBJECT")
            line = line.replace("$value", v)
            if "$P31_value" in line:
                if p31_value:
                    line = line.replace("$P31_value", p31_value)
                else:
                    continue  # Skip if we need P31 but don't have it
            fragments.append(line)

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

    # Add fragments
    for frag in fragments:
        lines.append(frag)

    return "\n".join(lines), used_props, label


def main():
    parser = argparse.ArgumentParser(description="Generate wikitext from Wikidata item")
    parser.add_argument("qid", type=str, help="Wikidata QID (e.g. Q706499)")
    parser.add_argument("--save", action="store_true", help="Save to data/templates/auto/")
    args = parser.parse_args()

    qid = args.qid.upper()
    print(f"Generating wikitext for {qid}...", flush=True)

    wikitext, used_props, label = generate_wikitext(qid)

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
