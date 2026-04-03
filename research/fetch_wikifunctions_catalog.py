"""
Fetch ALL Wikifunctions Z8 (Function) and Z4 (Type) objects and document them.

Uses two approaches to ensure completeness:
1. wikilambdasearch_labels (search API) - fast but incomplete (~818 results)
2. allpages enumeration + batch wikilambda_fetch - slow but catches everything

Outputs:
- data/wikifunctions_catalog.json (machine-readable)
- WIKIFUNCTIONS_CATALOG.md (human-readable with implementation notes)
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

# Z-IDs we have successfully used in article creation
USED_IN_BOT = {
    "Z6091": "Type used as Wikidata item reference wrapper in both location and deity fragments",
    "Z14396": "Used to wrap monolingual text strings inside article fragments",
    "Z26570": "Core function: generates 'located in [entity], [class]' text for shrine location fragments",
    "Z27868": "Converts a plain string into an HTML fragment for the visual editor clipboard",
    "Z28016": "Core function: generates 'The deity of [shrine] is [deity]' sentences for deity fragments",
    "Z29749": "Wraps monolingual text as an HTML fragment with automatic language code detection",
}


def fetch_all_zids_via_allpages():
    """Get every Z-ID on wikifunctions.org via the allpages API."""
    all_zids = []
    params = {
        "action": "query", "list": "allpages",
        "apnamespace": 0, "aplimit": 500, "format": "json",
    }
    page = 1
    while True:
        print(f"  allpages page {page}...")
        r = SESSION.get(API, params=params)
        r.raise_for_status()
        data = r.json()
        batch = [p["title"] for p in data["query"]["allpages"]]
        all_zids.extend(batch)
        if "continue" not in data:
            break
        params["apcontinue"] = data["continue"]["apcontinue"]
        page += 1
        time.sleep(0.3)
    return all_zids


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
        if "Z9K1" in type_obj:
            return type_obj["Z9K1"]
        if "Z7K1" in type_obj:
            base = resolve_type_ref(type_obj["Z7K1"])
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


def get_object_type(obj):
    """Get the Z-type of a Z2 persistent object's value."""
    z2_value = obj.get("Z2K2", {})
    if isinstance(z2_value, dict):
        t = z2_value.get("Z1K1", "")
        if isinstance(t, str):
            return t
        if isinstance(t, dict):
            return t.get("Z9K1", "")
    return ""


def parse_function_detail(zid, obj):
    """Parse a Z8 function object into a clean descriptor."""
    z2_value = obj.get("Z2K2", {})
    if not isinstance(z2_value, dict):
        return None

    label = extract_multilingual_text(obj.get("Z2K3", {}))
    description = extract_multilingual_text(obj.get("Z2K5", {}))

    args_list = z2_value.get("Z8K1", [])
    arguments = []
    if isinstance(args_list, list):
        for arg in args_list:
            if isinstance(arg, dict) and "Z17K2" in arg:
                arguments.append({
                    "key": arg.get("Z17K2", ""),
                    "type": resolve_type_ref(arg.get("Z17K1", "")),
                    "label": extract_multilingual_text(arg.get("Z17K3", {})),
                })

    return_type = resolve_type_ref(z2_value.get("Z8K2", ""))

    tests = z2_value.get("Z8K3", [])
    impls = z2_value.get("Z8K4", [])
    num_tests = len([t for t in tests if isinstance(t, dict)]) if isinstance(tests, list) else 0
    num_impls = len([i for i in impls if isinstance(i, dict)]) if isinstance(impls, list) else 0

    return {
        "zid": zid,
        "label": label,
        "description": description,
        "arguments": arguments,
        "return_type": return_type,
        "input_types": [a.get("type", "") for a in arguments],
        "num_tests": num_tests,
        "num_implementations": num_impls,
        "used_in_bot": zid in USED_IN_BOT,
        "bot_usage_note": USED_IN_BOT.get(zid, ""),
    }


def parse_type_detail(zid, obj):
    """Parse a Z4 type object into a clean descriptor."""
    label = extract_multilingual_text(obj.get("Z2K3", {}))
    description = extract_multilingual_text(obj.get("Z2K5", {}))

    z2_value = obj.get("Z2K2", {})
    # Z4 types have Z4K2 (keys) and Z4K3 (validator)
    keys = []
    keys_list = z2_value.get("Z4K2", [])
    if isinstance(keys_list, list):
        for k in keys_list:
            if isinstance(k, dict) and "Z3K2" in k:
                keys.append({
                    "key": k.get("Z3K2", ""),
                    "type": resolve_type_ref(k.get("Z3K1", "")),
                    "label": extract_multilingual_text(k.get("Z3K3", {})),
                })

    return {
        "zid": zid,
        "label": label,
        "description": description,
        "keys": keys,
        "used_in_bot": zid in USED_IN_BOT,
        "bot_usage_note": USED_IN_BOT.get(zid, ""),
    }


def batch_fetch_and_classify(all_zids):
    """Fetch all Z-objects in batches and classify them by type."""
    functions = {}
    types = {}
    other_counts = {}

    for i in range(0, len(all_zids), 50):
        batch = all_zids[i:i+50]
        batch_str = "|".join(batch)
        progress = f"{i+1}-{i+len(batch)}/{len(all_zids)}"
        print(f"  Fetching {progress}...", end="")
        data = None
        for attempt in range(5):
            try:
                r = SESSION.get(API, params={
                    "action": "wikilambda_fetch",
                    "zids": batch_str,
                    "format": "json",
                })
                if r.status_code == 429:
                    wait = 5 * (attempt + 1)
                    print(f" rate limited, waiting {wait}s...", end="")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                data = r.json()
                break
            except Exception as e:
                print(f" ERROR: {e}", end="")
                time.sleep(3 * (attempt + 1))
        if data is None:
            print(" SKIPPED")
            continue

        fn_count = 0
        type_count = 0
        for zid in batch:
            if zid not in data:
                continue
            try:
                obj = json.loads(data[zid].get("wikilambda_fetch", "{}"))
            except (json.JSONDecodeError, TypeError):
                continue

            obj_type = get_object_type(obj)
            if obj_type == "Z8":
                parsed = parse_function_detail(zid, obj)
                if parsed:
                    functions[zid] = parsed
                    fn_count += 1
            elif obj_type == "Z4":
                parsed = parse_type_detail(zid, obj)
                if parsed:
                    types[zid] = parsed
                    type_count += 1
            else:
                other_counts[obj_type] = other_counts.get(obj_type, 0) + 1

        print(f" {fn_count} functions, {type_count} types")
        time.sleep(1.5)

    return functions, types, other_counts


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
        for attempt in range(5):
            try:
                r = SESSION.get(API, params={
                    "action": "wikilambda_fetch",
                    "zids": batch_str,
                    "format": "json",
                })
                if r.status_code == 429:
                    time.sleep(5 * (attempt + 1))
                    continue
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
                break
            except Exception:
                time.sleep(3 * (attempt + 1))
        time.sleep(1.5)


def human_type(type_str):
    """Convert a type reference like Z6 to 'String (Z6)'."""
    if not type_str:
        return "Unknown"
    if "(" in type_str:
        base = type_str.split("(")[0]
        inner = type_str[len(base):]
        base_label = TYPE_LABELS.get(base, base)
        inner_clean = inner.strip("()")
        parts = [TYPE_LABELS.get(p.strip(), p.strip()) for p in inner_clean.split(",")]
        return f"{base_label} ({base})({', '.join(parts)})"
    label = TYPE_LABELS.get(type_str, "")
    if label:
        return f"{label} ({type_str})"
    return type_str


def generate_markdown(functions_by_id, types_by_id, other_counts):
    """Generate a comprehensive markdown catalog."""
    sorted_funcs = sorted(functions_by_id.values(), key=lambda f: int(f["zid"][1:]))
    sorted_types = sorted(types_by_id.values(), key=lambda t: int(t["zid"][1:]))

    used_funcs = [f for f in sorted_funcs if f["used_in_bot"]]
    used_types = [t for t in sorted_types if t["used_in_bot"]]

    # Group functions by return type
    by_return = {}
    for f in sorted_funcs:
        rt = human_type(f["return_type"])
        by_return.setdefault(rt, []).append(f)

    lines = []
    lines.append("# Wikifunctions Catalog")
    lines.append("")
    lines.append(f"Complete catalog of all **{len(sorted_funcs)}** functions and **{len(sorted_types)}** types on")
    lines.append("[Wikifunctions](https://www.wikifunctions.org/) as used by Abstract Wikipedia.")
    lines.append("")
    lines.append(f"*Auto-generated by `research/fetch_wikifunctions_catalog.py`*")
    lines.append("")

    # ============================================================
    # USED IN BOT section - the most important part
    # ============================================================
    lines.append("## Currently Used in AbstractTestBot")
    lines.append("")
    lines.append("These are the functions and types we have **successfully implemented** in our shrine article")
    lines.append("creation workflow (`create_rich_onepass.py`). They are injected into the Abstract Wikipedia")
    lines.append("visual editor clipboard as nested Z-object JSON.")
    lines.append("")

    if used_funcs:
        lines.append("### Functions We Use")
        lines.append("")
        for f in used_funcs:
            zid = f["zid"]
            label = f["label"] or "(unnamed)"
            rt = human_type(f["return_type"])
            lines.append(f"#### {zid}: {label} ✅ IMPLEMENTED")
            lines.append("")
            lines.append(f"**Bot usage:** {f['bot_usage_note']}")
            lines.append("")
            if f["description"]:
                lines.append(f"> {f['description']}")
                lines.append("")
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
            lines.append(f"**Link:** [View on Wikifunctions](https://www.wikifunctions.org/view/en/{zid})")
            lines.append("")
            lines.append("---")
            lines.append("")

    if used_types:
        lines.append("### Types We Use")
        lines.append("")
        for t in used_types:
            zid = t["zid"]
            label = t["label"] or "(unnamed)"
            lines.append(f"#### {zid}: {label} ✅ IMPLEMENTED")
            lines.append("")
            lines.append(f"**Bot usage:** {t['bot_usage_note']}")
            lines.append("")
            if t["description"]:
                lines.append(f"> {t['description']}")
                lines.append("")
            if t["keys"]:
                lines.append("| Key | ID | Type |")
                lines.append("|-----|-----|------|")
                for k in t["keys"]:
                    lines.append(f"| {k['label'] or '—'} | `{k['key']}` | {human_type(k['type'])} |")
                lines.append("")
            lines.append(f"**Link:** [View on Wikifunctions](https://www.wikifunctions.org/view/en/{zid})")
            lines.append("")
            lines.append("---")
            lines.append("")

    # Nesting diagram
    lines.append("### How They Nest Together")
    lines.append("")
    lines.append("Each article has two clipboard fragments. Here's how the functions compose:")
    lines.append("")
    lines.append("```")
    lines.append("Fragment 1: Location")
    lines.append("  Z27868 (string to HTML fragment)")
    lines.append("    └─ Z14396 (string of monolingual text)")
    lines.append("         └─ Z26570 (State location using entity and class)")
    lines.append("              ├─ Z26570K1: argument key reference")
    lines.append("              ├─ Z26570K2: Z6091 (Wikidata item ref) → Q845945 (shrine QID)")
    lines.append("              ├─ Z26570K3: Z6091 (Wikidata item ref) → Q17 (country: Japan)")
    lines.append("              └─ Z26570K4: argument key reference")
    lines.append("")
    lines.append("Fragment 2: Deity")
    lines.append("  Z29749 (monolingual text as HTML fragment w/ auto-langcode)")
    lines.append("    ├─ Z29749K1:")
    lines.append("    │   └─ Z28016 (defining role sentence)")
    lines.append("    │        ├─ Z28016K1: Z6091 (Wikidata item ref) → deity QID")
    lines.append("    │        ├─ Z28016K2: Z6091 (Wikidata item ref) → Q11591100 (Shinto shrine)")
    lines.append("    │        ├─ Z28016K3: argument key reference")
    lines.append("    │        └─ Z28016K4: argument key reference")
    lines.append("    └─ Z29749K2: argument key reference")
    lines.append("```")
    lines.append("")

    # ============================================================
    # Summary tables
    # ============================================================
    lines.append("## Summary")
    lines.append("")
    lines.append("### Z-Object Type Breakdown")
    lines.append("")
    lines.append("| Object Type | Count |")
    lines.append("|-------------|-------|")
    lines.append(f"| Z8 (Function) | {len(sorted_funcs)} |")
    lines.append(f"| Z4 (Type) | {len(sorted_types)} |")
    for otype, count in sorted(other_counts.items(), key=lambda x: -x[1]):
        label = TYPE_LABELS.get(otype, otype)
        lines.append(f"| {label} ({otype}) | {count} |")
    lines.append("")

    lines.append("### Functions by Return Type")
    lines.append("")
    lines.append("| Return Type | Count |")
    lines.append("|-------------|-------|")
    for rt in sorted(by_return.keys()):
        lines.append(f"| {rt} | {len(by_return[rt])} |")
    lines.append("")

    # ============================================================
    # Types catalog
    # ============================================================
    lines.append("## Types Catalog")
    lines.append("")
    lines.append(f"All **{len(sorted_types)}** types available on Wikifunctions.")
    lines.append("")

    for t in sorted_types:
        zid = t["zid"]
        label = t["label"] or "(unnamed)"
        used_marker = " ✅ USED IN BOT" if t["used_in_bot"] else ""
        lines.append(f"### {zid}: {label}{used_marker}")
        lines.append("")
        if t["used_in_bot"]:
            lines.append(f"**Bot usage:** {t['bot_usage_note']}")
            lines.append("")
        if t["description"]:
            lines.append(f"> {t['description']}")
            lines.append("")
        if t["keys"]:
            lines.append("| Key | ID | Type |")
            lines.append("|-----|-----|------|")
            for k in t["keys"]:
                lines.append(f"| {k['label'] or '—'} | `{k['key']}` | {human_type(k['type'])} |")
            lines.append("")
        lines.append(f"**Link:** [View on Wikifunctions](https://www.wikifunctions.org/view/en/{zid})")
        lines.append("")
        lines.append("---")
        lines.append("")

    # ============================================================
    # Full functions catalog
    # ============================================================
    lines.append("## Functions Catalog")
    lines.append("")
    lines.append(f"All **{len(sorted_funcs)}** functions available on Wikifunctions.")
    lines.append("")

    for f in sorted_funcs:
        zid = f["zid"]
        label = f["label"] or "(unnamed)"
        desc = f["description"] or ""
        rt = human_type(f["return_type"])
        used_marker = " ✅ USED IN BOT" if f["used_in_bot"] else ""

        lines.append(f"### {zid}: {label}{used_marker}")
        lines.append("")
        if f["used_in_bot"]:
            lines.append(f"**Bot usage:** {f['bot_usage_note']}")
            lines.append("")
        if desc:
            lines.append(f"> {desc}")
            lines.append("")

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

    print("=== Wikifunctions Complete Catalog Builder ===")
    print()

    # Step 1: Enumerate ALL Z-objects
    print("[1/4] Enumerating all Z-objects via allpages...")
    all_zids = fetch_all_zids_via_allpages()
    print(f"  Found {len(all_zids)} total Z-objects")
    print()

    # Step 2: Fetch and classify everything
    print("[2/4] Fetching and classifying all Z-objects...")
    functions, types, other_counts = batch_fetch_and_classify(all_zids)
    print(f"  Found {len(functions)} functions, {len(types)} types")
    used = [z for z in USED_IN_BOT if z in functions or z in types]
    print(f"  {len(used)}/{len(USED_IN_BOT)} bot-used Z-objects found in catalog")
    print()

    # Step 3: Resolve type labels
    print("[3/4] Resolving type labels...")
    all_type_refs = set()
    for f in functions.values():
        rt = f["return_type"]
        all_type_refs.add(rt.split("(")[0] if "(" in rt else rt)
        for a in f["arguments"]:
            t = a["type"]
            all_type_refs.add(t.split("(")[0] if "(" in t else t)
    for t in types.values():
        for k in t["keys"]:
            kt = k["type"]
            all_type_refs.add(kt.split("(")[0] if "(" in kt else kt)
    for otype in other_counts:
        all_type_refs.add(otype)
    fetch_type_labels(list(all_type_refs))
    print(f"  Resolved {len(TYPE_LABELS)} type labels")
    print()

    # Step 4: Write outputs
    print("[4/4] Writing output files...")

    json_path = os.path.join(repo_root, "data", "wikifunctions_catalog.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_functions": len(functions),
            "total_types": len(types),
            "used_in_bot": USED_IN_BOT,
            "type_labels": TYPE_LABELS,
            "functions": {k: v for k, v in sorted(functions.items(), key=lambda x: int(x[0][1:]))},
            "types": {k: v for k, v in sorted(types.items(), key=lambda x: int(x[0][1:]))},
        }, f, indent=2, ensure_ascii=False)
    print(f"  Wrote {json_path}")

    md_path = os.path.join(repo_root, "WIKIFUNCTIONS_CATALOG.md")
    md = generate_markdown(functions, types, other_counts)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"  Wrote {md_path}")

    print()
    print(f"Done! {len(functions)} functions + {len(types)} types documented.")
    print(f"Bot-used objects annotated: {', '.join(sorted(used))}")


if __name__ == "__main__":
    main()
