"""
Fetch all Wikifunctions (Z8) functions and their documentation.
Outputs a comprehensive catalog to data/wikifunctions_catalog.json
and a human-readable markdown to WIKIFUNCTIONS_CATALOG.md
"""
import requests
import json
import time
import sys
import io
import os

# Windows Unicode fix
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

API = "https://wikifunctions.org/w/api.php"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "AbstractTestBot/1.0 (Shinto shrine article creator)"})

def fetch_all_function_ids():
    """Enumerate all Z8 (Function) objects via wikilambdasearch_labels."""
    functions = []
    params = {
        "action": "query",
        "list": "wikilambdasearch_labels",
        "wikilambdasearch_search": "",
        "wikilambdasearch_type": "Z8",
        "wikilambdasearch_language": "en",
        "wikilambdasearch_limit": 500,
        "format": "json",
    }
    page = 1
    while True:
        print(f"  Fetching function list page {page}...")
        r = SESSION.get(API, params=params)
        r.raise_for_status()
        data = r.json()
        batch = data.get("query", {}).get("wikilambdasearch_labels", [])
        functions.extend(batch)
        print(f"    Got {len(batch)} functions (total: {len(functions)})")
        if "continue" not in data:
            break
        params["wikilambdasearch_continue"] = data["continue"]["wikilambdasearch_continue"]
        params["continue"] = data["continue"]["continue"]
        page += 1
        time.sleep(0.5)
    return functions


def extract_multilingual_text(z12_obj):
    """Extract English text from a Z12 (Multilingual Text) object, fallback to first available."""
    if not z12_obj or not isinstance(z12_obj, dict):
        return ""
    texts = z12_obj.get("Z12K1", [])
    if isinstance(texts, list):
        for item in texts:
            if isinstance(item, dict):
                lang = item.get("Z11K1", "")
                if isinstance(lang, dict):
                    lang = lang.get("Z9K1", "")
                if lang == "Z1002":
                    return item.get("Z11K2", "")
        # Fallback: first text
        for item in texts:
            if isinstance(item, dict) and "Z11K2" in item:
                return item.get("Z11K2", "")
    return ""


def resolve_type_ref(type_obj):
    """Resolve a type reference to a readable string."""
    if isinstance(type_obj, str):
        return type_obj
    if isinstance(type_obj, dict):
        # Could be a Z9 (Reference) or a Z7 (Function call / generic type)
        if "Z9K1" in type_obj:
            return type_obj["Z9K1"]
        if "Z7K1" in type_obj:
            # Generic type like Z881(Z6) = Typed list of strings
            base = resolve_type_ref(type_obj["Z7K1"])
            # Collect generic args
            args = []
            for key, val in sorted(type_obj.items()):
                if key.startswith("Z") and key != "Z7K1" and key != "Z1K1":
                    args.append(resolve_type_ref(val))
            if args:
                return f"{base}({', '.join(args)})"
            return base
        if "Z1K1" in type_obj:
            t = type_obj["Z1K1"]
            if isinstance(t, str):
                return t
            if isinstance(t, dict) and "Z9K1" in t:
                return t["Z9K1"]
    return str(type_obj)


def parse_function_detail(zid, raw_json):
    """Parse the full Z-object JSON into a clean function descriptor."""
    try:
        obj = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except (json.JSONDecodeError, TypeError):
        return None

    z2_value = obj.get("Z2K2", {})
    if not isinstance(z2_value, dict):
        return None

    # Labels
    labels_obj = obj.get("Z2K3", {})
    label = extract_multilingual_text(labels_obj)

    # Description
    desc_obj = obj.get("Z2K5", {})
    description = extract_multilingual_text(desc_obj)

    # Arguments
    args_list = z2_value.get("Z8K1", [])
    arguments = []
    if isinstance(args_list, list):
        for arg in args_list:
            if not isinstance(arg, dict) or arg.get("Z1K1") == "Z17":
                pass  # valid
            if isinstance(arg, dict) and "Z17K2" in arg:
                arg_info = {
                    "key": arg.get("Z17K2", ""),
                    "type": resolve_type_ref(arg.get("Z17K1", "")),
                    "label": extract_multilingual_text(arg.get("Z17K3", {})),
                }
                arguments.append(arg_info)

    # Return type
    return_type = resolve_type_ref(z2_value.get("Z8K2", ""))

    # Count tests and implementations
    tests = z2_value.get("Z8K3", [])
    impls = z2_value.get("Z8K4", [])
    num_tests = len([t for t in tests if isinstance(t, dict)]) if isinstance(tests, list) else 0
    num_impls = len([i for i in impls if isinstance(i, dict)]) if isinstance(impls, list) else 0

    # Input types (collect unique arg types for the Z7 composition signature)
    input_types = [a.get("type", "") for a in arguments]

    return {
        "zid": zid,
        "label": label,
        "description": description,
        "arguments": arguments,
        "return_type": return_type,
        "input_types": input_types,
        "num_tests": num_tests,
        "num_implementations": num_impls,
    }


def fetch_function_details(zids):
    """Fetch full Z-object data for a batch of ZIDs (max 50 at a time)."""
    results = {}
    for i in range(0, len(zids), 50):
        batch = zids[i:i+50]
        batch_str = "|".join(batch)
        print(f"  Fetching details {i+1}-{i+len(batch)} of {len(zids)}...")
        r = SESSION.get(API, params={
            "action": "wikilambda_fetch",
            "zids": batch_str,
            "format": "json",
        })
        r.raise_for_status()
        data = r.json()
        for zid in batch:
            if zid in data:
                raw = data[zid].get("wikilambda_fetch", "{}")
                parsed = parse_function_detail(zid, raw)
                if parsed:
                    results[zid] = parsed
        time.sleep(1.0)
    return results


# Known Z-type labels for human-readable output
TYPE_LABELS = {}

def fetch_type_labels(type_zids):
    """Fetch labels for type Z-IDs so we can display human-readable type names."""
    global TYPE_LABELS
    unique = list(set(z for z in type_zids if z.startswith("Z") and z not in TYPE_LABELS))
    if not unique:
        return
    for i in range(0, len(unique), 50):
        batch = unique[i:i+50]
        batch_str = "|".join(batch)
        print(f"  Fetching type labels {i+1}-{i+len(batch)}...")
        r = SESSION.get(API, params={
            "action": "wikilambda_fetch",
            "zids": batch_str,
            "format": "json",
        })
        r.raise_for_status()
        data = r.json()
        for zid in batch:
            if zid in data:
                try:
                    obj = json.loads(data[zid].get("wikilambda_fetch", "{}"))
                    label = extract_multilingual_text(obj.get("Z2K3", {}))
                    if label:
                        TYPE_LABELS[zid] = label
                except Exception:
                    pass
        time.sleep(0.5)


def human_type(type_str):
    """Convert a type reference like Z6 to 'String (Z6)'."""
    if not type_str:
        return "Unknown"
    # Handle generic types like Z881(Z6)
    if "(" in type_str:
        base = type_str.split("(")[0]
        inner = type_str[len(base):]
        base_label = TYPE_LABELS.get(base, base)
        # Resolve inner types too
        inner_clean = inner.strip("()")
        parts = [TYPE_LABELS.get(p.strip(), p.strip()) for p in inner_clean.split(",")]
        return f"{base_label} ({base})({', '.join(parts)})"
    label = TYPE_LABELS.get(type_str, "")
    if label:
        return f"{label} ({type_str})"
    return type_str


def generate_markdown(functions_by_id):
    """Generate a comprehensive markdown catalog."""
    sorted_funcs = sorted(functions_by_id.values(), key=lambda f: int(f["zid"][1:]))

    # Group by return type for a summary section
    by_return = {}
    for f in sorted_funcs:
        rt = human_type(f["return_type"])
        by_return.setdefault(rt, []).append(f)

    lines = []
    lines.append("# Wikifunctions Catalog")
    lines.append("")
    lines.append(f"Complete catalog of all **{len(sorted_funcs)}** functions available on")
    lines.append("[Wikifunctions](https://www.wikifunctions.org/) as used by Abstract Wikipedia.")
    lines.append("")
    lines.append(f"*Auto-generated by `research/fetch_wikifunctions_catalog.py`*")
    lines.append("")

    # Table of contents by return type
    lines.append("## Summary by Return Type")
    lines.append("")
    lines.append("| Return Type | Count |")
    lines.append("|-------------|-------|")
    for rt in sorted(by_return.keys()):
        lines.append(f"| {rt} | {len(by_return[rt])} |")
    lines.append("")

    # Full catalog
    lines.append("## Full Catalog")
    lines.append("")

    for f in sorted_funcs:
        zid = f["zid"]
        label = f["label"] or "(unnamed)"
        desc = f["description"] or ""
        rt = human_type(f["return_type"])

        lines.append(f"### {zid}: {label}")
        lines.append("")
        if desc:
            lines.append(f"> {desc}")
            lines.append("")

        # Signature
        arg_strs = []
        for a in f["arguments"]:
            atype = human_type(a["type"])
            alabel = a["label"] or a["key"]
            arg_strs.append(f"{alabel}: {atype}")
        sig = ", ".join(arg_strs) if arg_strs else "(no arguments)"
        lines.append(f"**Signature:** `{label}({sig})` -> `{rt}`")
        lines.append("")

        if f["arguments"]:
            lines.append("| Argument | Key | Type |")
            lines.append("|----------|-----|------|")
            for a in f["arguments"]:
                lines.append(f"| {a['label'] or '—'} | `{a['key']}` | {human_type(a['type'])} |")
            lines.append("")

        lines.append(f"**Returns:** {rt}  ")
        lines.append(f"**Implementations:** {f['num_implementations']} | **Tests:** {f['num_tests']}")
        lines.append(f"**Link:** [View on Wikifunctions](https://www.wikifunctions.org/view/en/{zid})")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)

    print("=== Wikifunctions Catalog Builder ===")
    print()

    # Step 1: Get all function IDs
    print("[1/4] Fetching function list...")
    func_list = fetch_all_function_ids()
    print(f"  Found {len(func_list)} functions")
    print()

    # Step 2: Fetch full details
    print("[2/4] Fetching function details...")
    zids = [f["page_title"] for f in func_list]
    functions = fetch_function_details(zids)
    print(f"  Successfully parsed {len(functions)} functions")
    print()

    # Step 3: Resolve type labels
    print("[3/4] Resolving type labels...")
    all_types = set()
    for f in functions.values():
        all_types.add(f["return_type"].split("(")[0] if "(" in f["return_type"] else f["return_type"])
        for a in f["arguments"]:
            t = a["type"]
            all_types.add(t.split("(")[0] if "(" in t else t)
    fetch_type_labels(list(all_types))
    print(f"  Resolved {len(TYPE_LABELS)} type labels")
    print()

    # Step 4: Write outputs
    print("[4/4] Writing output files...")

    # JSON catalog
    json_path = os.path.join(repo_root, "data", "wikifunctions_catalog.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_functions": len(functions),
            "type_labels": TYPE_LABELS,
            "functions": {k: v for k, v in sorted(functions.items(), key=lambda x: int(x[0][1:]))},
        }, f, indent=2, ensure_ascii=False)
    print(f"  Wrote {json_path}")

    # Markdown catalog
    md_path = os.path.join(repo_root, "WIKIFUNCTIONS_CATALOG.md")
    md = generate_markdown(functions)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"  Wrote {md_path}")

    print()
    print(f"Done! {len(functions)} functions documented.")


if __name__ == "__main__":
    main()
