"""Wiki text template parser for Abstract Wikipedia pages.

Converts a human-readable template syntax into the nested Z-object clipboard
JSON that Abstract Wikipedia's visual editor expects. Templates use a
MediaWiki-inspired syntax:

    {{Z26570 | $subject | Q845945 | Q17}}

Each {{...}} block becomes one clipboard fragment. The parser handles:
- Z-function calls with positional or named arguments
- $subject / $lang as implicit article entity/language references
- Q-items automatically wrapped as Wikidata item references (Z6091)
- $variables filled in at render time
- Auto-wrapping: Z11-returning functions get Z29749, Z6-returning get Z27868

Template format:
    ---
    title: My Template
    variables:
      deity: Q-item
    ---
    {{Z26570 | $subject | Q845945 | Q17}}
    {{Z28016 | $deity | Q11591100 | $subject}}

Usage:
    from wikitext_parser import compile_template

    clipboard = compile_template(template_text, {
        "deity": "Q12345",
        "subject": "Q67890",
    })
"""

import re
import copy
import yaml


# ============================================================
# Z-object helpers (same patterns as create_rich_threepass.py)
# ============================================================

def z9(zid):
    """Build a Z9 reference: {"Z1K1": {"Z1K1": "Z9", "Z9K1": "Z9"}, "Z9K1": zid}."""
    return {"Z1K1": {"Z1K1": "Z9", "Z9K1": "Z9"}, "Z9K1": zid}


def z9s(zid):
    """Short Z9 reference used in clipboard format."""
    return {"Z1K1": "Z9", "Z9K1": zid}


def z6(value):
    """Build a Z6 string literal."""
    return {"Z1K1": "Z6", "Z6K1": value}


def z6091(qid):
    """Build a Wikidata item reference (Z6091) wrapping a QID string."""
    return {
        "Z1K1": z9s("Z6091"),
        "Z6091K1": z6(qid),
    }


def z18(arg_key):
    """Build an argument reference (Z18) for keys like Z825K1, Z825K2."""
    return {
        "Z1K1": z9s("Z18"),
        "Z18K1": z6(arg_key),
    }


def z7_call(func_id, args_dict):
    """Build a Z7 function call with named arguments.

    func_id: e.g. "Z26570"
    args_dict: e.g. {"Z26570K1": <z-obj>, "Z26570K2": <z-obj>}
    """
    result = {
        "Z1K1": z9s("Z7"),
        "Z7K1": z9s(func_id),
    }
    result.update(args_dict)
    return result


# ============================================================
# Function registry: maps Z-function IDs to parameter metadata
# ============================================================

# Each entry: {
#   "params": [{"key": "K1", "name": "human name", "type": "Z6091|Z60|Z18|..."}],
#   "returns": "Z11" or "Z6" or "Z89",
# }
# The "type" field indicates what kind of value the parameter typically takes.
# This is used for auto-wrapping arguments.

FUNCTION_REGISTRY = {
    "Z26570": {
        "name": "State location using entity and class",
        "example": "Seoul is a city in South Korea.",
        "params": [
            {"key": "K1", "name": "entity", "type": "entity_ref"},
            {"key": "K2", "name": "class", "type": "Q-item"},
            {"key": "K3", "name": "location", "type": "Q-item"},
            {"key": "K4", "name": "language", "type": "language"},
        ],
        "returns": "Z11",
    },
    "Z28016": {
        "name": "defining role sentence",
        "example": "Paris is the capital of France.",
        "params": [
            {"key": "K1", "name": "subject", "type": "Q-item"},
            {"key": "K2", "name": "role", "type": "Q-item"},
            {"key": "K3", "name": "dependency", "type": "entity_ref"},
            {"key": "K4", "name": "language", "type": "language"},
        ],
        "returns": "Z11",
    },
    "Z26039": {
        "name": "Article-less instantiating fragment",
        "example": "Nairobi is a city.",
        "params": [
            {"key": "K1", "name": "entity", "type": "entity_ref"},
            {"key": "K2", "name": "class", "type": "Q-item"},
            {"key": "K3", "name": "language", "type": "language"},
        ],
        "returns": "Z6",
    },
    "Z26095": {
        "name": "Article-ful instantiating fragment",
        "example": "An antelope is a mammal.",
        "params": [
            {"key": "K1", "name": "class", "type": "Q-item"},
            {"key": "K2", "name": "super-class", "type": "Q-item"},
            {"key": "K3", "name": "language", "type": "language"},
        ],
        "returns": "Z11",
    },
    "Z26627": {
        "name": "Classifying a class of nouns",
        "example": "Antelopes are mammals.",
        "params": [
            {"key": "K1", "name": "class", "type": "Q-item"},
            {"key": "K2", "name": "class2", "type": "Q-item"},
            {"key": "K3", "name": "language", "type": "language"},
        ],
        "returns": "Z11",
    },
    "Z29591": {
        "name": "describing entity with adjective / class",
        "example": "Venus is a rocky planet.",
        "params": [
            {"key": "K1", "name": "entity", "type": "entity_ref"},
            {"key": "K2", "name": "adjective", "type": "Q-item"},
            {"key": "K3", "name": "class", "type": "Q-item"},
            {"key": "K4", "name": "language", "type": "language"},
        ],
        "returns": "Z11",
    },
    "Z27173": {
        "name": "Describe the class of a class",
        "example": "Ice is frozen water.",
        "params": [
            {"key": "K1", "name": "class_described", "type": "Q-item"},
            {"key": "K2", "name": "adjective", "type": "Q-item"},
            {"key": "K3", "name": "class_describing", "type": "Q-item"},
            {"key": "K4", "name": "language", "type": "language"},
        ],
        "returns": "Z6",
    },
    "Z29743": {
        "name": "description of class with adjective and superclass",
        "example": "A sheep is a domesticated animal.",
        "params": [
            {"key": "K1", "name": "described_class", "type": "Q-item"},
            {"key": "K2", "name": "adjective", "type": "Q-item"},
            {"key": "K3", "name": "superclass", "type": "Q-item"},
            {"key": "K4", "name": "language", "type": "language"},
        ],
        "returns": "Z11",
    },
    "Z27243": {
        "name": "Superlative definition",
        "example": "Mount Everest is the tallest mountain in Asia.",
        "params": [
            {"key": "K1", "name": "entity", "type": "entity_ref"},
            {"key": "K2", "name": "adjective", "type": "Q-item"},
            {"key": "K3", "name": "class", "type": "Q-item"},
            {"key": "K4", "name": "location", "type": "Q-item"},
            {"key": "K5", "name": "language", "type": "language"},
        ],
        "returns": "Z11",
    },
    "Z26955": {
        "name": "SPO sentence, S without and O with article",
        "example": "English is a language.",
        "params": [
            {"key": "K1", "name": "predicate", "type": "Q-item"},
            {"key": "K2", "name": "subject_item", "type": "Q-item"},
            {"key": "K3", "name": "object_item", "type": "Q-item"},
            {"key": "K4", "name": "language", "type": "language"},
        ],
        "returns": "Z6",
    },
    "Z28803": {
        "name": "short description for album",
        "example": "1968 album by The Beatles",
        "params": [
            {"key": "K1", "name": "album", "type": "Q-item"},
            {"key": "K2", "name": "language", "type": "language"},
        ],
        "returns": "Z11",
    },
    "Z30000": {
        "name": "Sunset sentence for location on date",
        "example": "The sun set in Tokyo at 5:23 PM on March 28.",
        "params": [
            {"key": "K1", "name": "location", "type": "Q-item"},
            {"key": "K2", "name": "date_of_sunset", "type": "date"},
            {"key": "K3", "name": "todays_date", "type": "date"},
            {"key": "K4", "name": "language", "type": "language"},
        ],
        "returns": "Z11",
    },
    "Z31405": {
        "name": "Sentence that something begins",
        "example": "The beginning of X",
        "params": [
            {"key": "K1", "name": "subject", "type": "Q-item"},
            {"key": "K2", "name": "language", "type": "language"},
        ],
        "returns": "Z11",
    },
    # Structural / rendering functions (return Z89 directly)
    "Z29822": {
        "name": "ArticlePlaceholder render article",
        "example": "Full auto-generated article from QID",
        "params": [
            {"key": "K1", "name": "display_language", "type": "language"},
            {"key": "K2", "name": "item", "type": "Q-item"},
            {"key": "K3", "name": "include_empty", "type": "boolean"},
        ],
        "returns": "Z89",
    },
}

# Lookup by parameter name -> key for each function
_PARAM_NAME_INDEX = {}
for _fid, _finfo in FUNCTION_REGISTRY.items():
    _PARAM_NAME_INDEX[_fid] = {}
    for _p in _finfo["params"]:
        _PARAM_NAME_INDEX[_fid][_p["name"]] = _p


# ============================================================
# Argument value resolution
# ============================================================

# Special variables that map to argument references (Z18)
IMPLICIT_REFS = {
    "$subject": "Z825K1",   # article entity
    "$lang": "Z825K2",      # language
}


def resolve_value(raw_value, variables=None):
    """Convert a raw template value into a Z-object.

    Resolution rules:
    - "$subject" / "$lang" -> Z18 argument reference
    - "$varname" -> look up in variables dict, then treat result as a value
    - "Q..." (Wikidata QID) -> Z6091 Wikidata item reference
    - "Z..." that looks like a Z-ID -> Z9 reference
    - Anything else -> Z6 string literal
    """
    variables = variables or {}
    raw_value = raw_value.strip()

    # Implicit argument references
    if raw_value in IMPLICIT_REFS:
        return z18(IMPLICIT_REFS[raw_value])

    # Template variables ($deity, $admin, etc.)
    if raw_value.startswith("$"):
        var_name = raw_value[1:]
        if var_name not in variables:
            raise ValueError(f"Undefined variable: {raw_value}")
        resolved = variables[var_name]
        # Recurse: the resolved value might be a QID, Z-ID, etc.
        return resolve_value(resolved, variables)

    # Wikidata QID (Q followed by digits)
    if re.match(r'^Q\d+$', raw_value):
        return z6091(raw_value)

    # Z-object reference (Z followed by digits, no K suffix)
    if re.match(r'^Z\d+$', raw_value):
        return z9s(raw_value)

    # Boolean values for Abstract Wikipedia
    if raw_value.lower() in ("true", "yes"):
        return z9s("Z41")  # Z41 = true
    if raw_value.lower() in ("false", "no"):
        return z9s("Z42")  # Z42 = false

    # Plain string
    return z6(raw_value)


# ============================================================
# Wrapping: convert function output to clipboard-ready Z89
# ============================================================

def wrap_as_fragment(func_id, func_call, return_type):
    """Wrap a function call in the appropriate outer layers to produce Z89.

    The clipboard requires Z89 (HTML fragment) items. Different wrapping
    strategies depending on what the inner function returns:

    - Z11 (monolingual text) -> Z29749(func_call, Z825K2)
      Wraps monolingual text into HTML fragment with auto language code.

    - Z6 (string) -> Z27868(func_call)
      Converts plain string to HTML fragment.

    - Z89 (already HTML) -> no wrapping needed, return as-is.
    """
    if return_type == "Z11":
        # Z29749: monolingual text as HTML fragment w/ auto-langcode
        return z7_call("Z29749", {
            "Z29749K1": func_call,
            "Z29749K2": z18("Z825K2"),
        })
    elif return_type == "Z6":
        # Z27868: string to HTML fragment
        return z7_call("Z27868", {
            "Z27868K1": func_call,
        })
    elif return_type == "Z89":
        return func_call
    else:
        # Unknown return type — try Z29749 as a reasonable default
        return z7_call("Z29749", {
            "Z29749K1": func_call,
            "Z29749K2": z18("Z825K2"),
        })


# ============================================================
# Template parsing
# ============================================================

def parse_frontmatter(text):
    """Split template into YAML frontmatter and body.

    Returns (metadata_dict, body_string).
    """
    text = text.strip()
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            frontmatter_str = parts[1].strip()
            body = parts[2].strip()
            if frontmatter_str:
                metadata = yaml.safe_load(frontmatter_str)
            else:
                metadata = {}
            return metadata or {}, body
    return {}, text


def parse_template_calls(body):
    """Extract all {{...}} template calls from the body text.

    Returns a list of dicts:
        {"func_id": "Z26570", "args": [...], "named_args": {...}, "line": N}

    Supports both positional and named arguments:
        {{Z26570 | $subject | Q845945 | Q17}}
        {{Z26570 | entity=$subject | class=Q845945 | location=Q17}}
    """
    fragments = []
    # Match {{ ... }} allowing newlines inside
    pattern = re.compile(r'\{\{(.+?)\}\}', re.DOTALL)

    for match in pattern.finditer(body):
        inner = match.group(1).strip()
        # Calculate line number
        line_num = body[:match.start()].count('\n') + 1

        parts = [p.strip() for p in inner.split('|')]
        if not parts:
            continue

        func_id = parts[0].strip()
        positional_args = []
        named_args = {}

        for part in parts[1:]:
            if '=' in part and not part.startswith('$'):
                key, _, value = part.partition('=')
                named_args[key.strip()] = value.strip()
            else:
                positional_args.append(part)

        fragments.append({
            "func_id": func_id,
            "args": positional_args,
            "named_args": named_args,
            "line": line_num,
        })

    return fragments


def build_func_call(fragment_def, variables=None):
    """Build a Z7 function call from a parsed fragment definition.

    Resolves positional and named arguments using the function registry.
    Language parameters are auto-filled with $lang if not provided.
    """
    func_id = fragment_def["func_id"]
    positional = fragment_def["args"]
    named = fragment_def["named_args"]
    variables = variables or {}

    # Look up function in registry
    if func_id not in FUNCTION_REGISTRY:
        # Unknown function: build a best-effort call using positional args
        args_dict = {}
        for i, val in enumerate(positional):
            key = f"{func_id}K{i + 1}"
            args_dict[key] = resolve_value(val, variables)
        return z7_call(func_id, args_dict), "Z11"  # assume Z11 by default

    func_info = FUNCTION_REGISTRY[func_id]
    params = func_info["params"]
    args_dict = {}

    # Resolve named arguments first
    used_positions = set()
    for param_name, raw_value in named.items():
        # Find the parameter by name
        if func_id in _PARAM_NAME_INDEX and param_name in _PARAM_NAME_INDEX[func_id]:
            param = _PARAM_NAME_INDEX[func_id][param_name]
            full_key = f"{func_id}{param['key']}"
            args_dict[full_key] = resolve_value(raw_value, variables)
            # Mark this position as used
            idx = next(i for i, p in enumerate(params) if p["name"] == param_name)
            used_positions.add(idx)
        else:
            raise ValueError(
                f"Unknown parameter '{param_name}' for function {func_id}. "
                f"Available: {[p['name'] for p in params]}"
            )

    # Fill positional arguments into remaining slots
    pos_iter = iter(positional)
    for i, param in enumerate(params):
        if i in used_positions:
            continue
        full_key = f"{func_id}{param['key']}"
        if full_key in args_dict:
            continue

        # Auto-fill language parameter if not provided
        if param["type"] == "language":
            if full_key not in args_dict:
                args_dict[full_key] = z18("Z825K2")
            continue

        try:
            raw_value = next(pos_iter)
        except StopIteration:
            raise ValueError(
                f"Not enough arguments for {func_id} ({func_info['name']}). "
                f"Missing: {param['name']} ({param['key']})"
            )

        args_dict[full_key] = resolve_value(raw_value, variables)

    return z7_call(func_id, args_dict), func_info["returns"]


def build_clipboard_item(fragment_value, index=0, origin_qid="Q0"):
    """Wrap a Z89-producing value in the clipboard item envelope."""
    return {
        "itemId": f"{origin_qid}.{index + 1}#1",
        "originKey": f"{origin_qid}.{index + 1}",
        "originSlotType": "Z89",
        "value": fragment_value,
        "objectType": "Z7",
        "resolvingType": "Z89",
    }


# ============================================================
# Public API
# ============================================================

def parse_template(text):
    """Parse a wikitext template into metadata and fragment definitions.

    Returns:
        {
            "metadata": {...frontmatter...},
            "fragments": [...parsed fragment defs...],
        }
    """
    metadata, body = parse_frontmatter(text)
    fragments = parse_template_calls(body)
    return {
        "metadata": metadata,
        "fragments": fragments,
    }


def compile_template(text, variables=None):
    """Compile a wikitext template into clipboard-ready JSON.

    This is the main entry point. Takes a template string and variable
    values, returns a list of clipboard items ready for injection.

    Args:
        text: Template string in wikitext format.
        variables: Dict mapping variable names to values (e.g. {"deity": "Q12345"}).

    Returns:
        List of clipboard item dicts, ready for inject_clipboard().
    """
    variables = variables or {}
    parsed = parse_template(text)

    # Merge frontmatter defaults with provided variables
    meta_vars = parsed["metadata"].get("variables", {})
    # meta_vars defines expected variables; actual values come from `variables` arg

    # Validate: warn about undefined variables
    for var_name in meta_vars:
        if var_name not in variables and var_name != "subject":
            # Not an error — might be optional or have defaults later
            pass

    origin_qid = variables.get("subject", "Q0")
    clipboard_items = []

    for i, frag_def in enumerate(parsed["fragments"]):
        func_call, return_type = build_func_call(frag_def, variables)
        wrapped = wrap_as_fragment(frag_def["func_id"], func_call, return_type)
        item = build_clipboard_item(wrapped, index=i, origin_qid=origin_qid)
        clipboard_items.append(item)

    return clipboard_items


def template_from_file(filepath, variables=None):
    """Load and compile a template from a file path."""
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
    return compile_template(text, variables)


def list_functions():
    """Return a formatted string listing all registered functions."""
    lines = []
    for fid, info in sorted(FUNCTION_REGISTRY.items()):
        params_str = ", ".join(
            f"{p['name']}: {p['type']}" for p in info["params"]
        )
        lines.append(f"  {fid}: {info['name']}")
        lines.append(f"    Example: \"{info['example']}\"")
        lines.append(f"    Args: ({params_str}) -> {info['returns']}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Wiki Text Template Parser for Abstract Wikipedia")
        print("=" * 50)
        print()
        print("Usage:")
        print("  python wikitext_parser.py <template.wikitext> [var=value ...]")
        print("  python wikitext_parser.py --list-functions")
        print()
        print("Example:")
        print("  python wikitext_parser.py data/templates/shinto_shrine.wikitext deity=Q12345")
        print()
        print("Available functions:")
        print(list_functions())
        sys.exit(0)

    if sys.argv[1] == "--list-functions":
        print(list_functions())
        sys.exit(0)

    filepath = sys.argv[1]
    variables = {}
    for arg in sys.argv[2:]:
        if "=" in arg:
            key, _, value = arg.partition("=")
            variables[key] = value

    result = template_from_file(filepath, variables)
    print(json.dumps(result, indent=2))
