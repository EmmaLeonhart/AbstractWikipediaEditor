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

    # Always start with P31 (instance of) if available
    if "P31" in mapping and p31_value:
        fragments.append(f"{{{{Z26039 | $subject | {p31_value}}}}}")
        used_props.add("P31")

    # Process other mapped properties
    for pid, pmap in mapping.items():
        if pid in used_props:
            continue
        if pid not in claims:
            continue

        # Get first QID value for this property
        value = None
        for claim in claims[pid]:
            v = extract_qid_value(claim)
            if v:
                value = v
                break
        if not value:
            continue

        # Build the template line based on the mapping
        func = pmap["function"]
        template = pmap["template"]

        # Replace template variables
        line = template.replace("$subject", "$subject")
        line = line.replace("$value", value)
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
