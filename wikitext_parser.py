"""Wiki text template parser for Abstract Wikipedia pages.

Converts a human-readable template syntax into the nested Z-object clipboard
JSON that Abstract Wikipedia's visual editor expects. Templates use a
MediaWiki-inspired syntax:

    {{Z26570|SUBJECT|Q845945|Q17}}

Each {{...}} block becomes one clipboard fragment. The parser handles:
- Z-function calls with positional or named arguments
- SUBJECT / $lang as implicit article entity/language references
- Q-items automatically wrapped as Wikidata item references (Z6091)
- $variables filled in at render time
- Auto-wrapping: Z11-returning functions get Z29749, Z6-returning get Z27868

Template format:
    ---
    title: My Template
    variables:
      deity: Q-item
    ---
    {{Z26570|SUBJECT|Q845945|Q17}}
    {{Z28016|$deity|Q11591100|SUBJECT}}

Usage:
    from wikitext_parser import compile_template

    clipboard = compile_template(template_text, {
        "deity": "Q12345",
        "subject": "Q67890",
    })
"""

import re
import copy
import os
import json
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


def z20420_date(year, month, day):
    """Build a Z20420 (Gregorian calendar date) object.

    Months are referenced via Z16101 (January) through Z16112 (December).
    Era is hardcoded to AD (Z17814).
    """
    return {
        "Z1K1": "Z20420",
        "Z20420K1": {  # year (with era)
            "Z1K1": "Z20159",
            "Z20159K1": {
                "Z1K1": "Z17813",
                "Z17813K1": "Z17814",  # AD era
            },
            "Z20159K2": {
                "Z1K1": "Z13518",
                "Z13518K1": str(int(year)),
            },
        },
        "Z20420K2": {  # month + day
            "Z1K1": "Z20342",
            "Z20342K1": {
                "Z1K1": "Z16098",
                "Z16098K1": f"Z{16100 + int(month)}",
            },
            "Z20342K2": {
                "Z1K1": "Z13518",
                "Z13518K1": str(int(day)),
            },
        },
    }


def parse_date_string(raw):
    """Parse a YYYY-MM-DD date string into a Z20420 object.

    Accepts forms like '2026-03-14' or '+2026-03-14T00:00:00Z'.
    """
    s = raw.strip()
    if s.startswith("+"):
        s = s[1:]
    if "T" in s:
        s = s.split("T", 1)[0]
    parts = s.split("-")
    if len(parts) < 3:
        raise ValueError(f"Invalid date string: {raw!r}")
    return z20420_date(parts[0], parts[1], parts[2])


def today_z20420():
    """Build a Z20420 object for today's date."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return z20420_date(now.year, now.month, now.day)


def _domain_from_url(url):
    """Extract a domain name from a URL for use as a website name."""
    try:
        from urllib.parse import urlparse
        netloc = urlparse(url).netloc
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc or url
    except Exception:
        return url


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
    "Z32229": {
        "name": "comparative measurement sentence",
        "example": "Jupiter has a mass 1/1,048 times that of the Sun.",
        "params": [
            {"key": "K1", "name": "entity", "type": "entity_ref"},
            {"key": "K2", "name": "comparison_entity", "type": "Q-item"},
            {"key": "K3", "name": "measurement", "type": "Q-item"},
            {"key": "K4", "name": "quantity", "type": "string"},
            {"key": "K5", "name": "language", "type": "language"},
        ],
        "returns": "Z6",
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
    # Citation function: Simple cite web — for citing web sources
    "Z32053": {
        "name": "Simple cite web",
        "example": "Cite a web source with URL, title, site, date.",
        "params": [
            {"key": "K1", "name": "url", "type": "string"},
            {"key": "K2", "name": "title", "type": "string"},
            {"key": "K3", "name": "website", "type": "string"},
            {"key": "K4", "name": "access_date", "type": "date"},
            {"key": "K5", "name": "language", "type": "language"},
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
    "SUBJECT": "Z825K1",    # article entity
    "$lang": "Z825K2",      # language
}


def resolve_value(raw_value, variables=None):
    """Convert a raw template value into a Z-object.

    Resolution rules:
    - "SUBJECT" / "$lang" -> Z18 argument reference
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


def _load_aliases():
    """Load function aliases from data/function_aliases.json."""
    aliases_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "function_aliases.json")
    try:
        with open(aliases_path, "r", encoding="utf-8") as f:
            return json.load(f).get("aliases", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

_FUNCTION_ALIASES = _load_aliases()


def resolve_function_name(name):
    """Resolve a function name or alias to a Z-ID.

    Accepts Z-IDs directly (e.g. "Z26570") or English aliases
    (e.g. "location", "is a", "role"). Case-insensitive for aliases.
    """
    name = name.strip()
    # Already a Z-ID
    if re.match(r'^Z\d+$', name):
        return name
    # Try alias lookup (case-insensitive)
    return _FUNCTION_ALIASES.get(name.lower(), _FUNCTION_ALIASES.get(name, name))


def parse_template_calls(body):
    """Extract all {{...}} template calls from the body text.

    Returns a list of dicts:
        {"func_id": "Z26570", "args": [...], "named_args": {...}, "line": N}

    Supports both positional and named arguments:
        {{Z26570|SUBJECT|Q845945|Q17}}
        {{location|SUBJECT|Q845945|Q17}}
        {{Z26570|entity=SUBJECT|class=Q845945|location=Q17}}
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

        func_id = resolve_function_name(parts[0])
        positional_args = []
        named_args = {}

        for part in parts[1:]:
            if '=' in part and not part.startswith('$'):
                key, _, value = part.partition('=')
                key = key.strip()
                # Only treat as named arg if the key is a simple identifier.
                # This avoids misparsing URLs (e.g. ?title=Foo) as named args.
                if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', key):
                    named_args[key] = value.strip()
                    continue
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

    Z32053 (cite web) has special defaults: only the URL is required.
    Title and website default to the URL/domain, access date defaults
    to today, and language defaults to $lang.
    """
    func_id = fragment_def["func_id"]
    positional = list(fragment_def["args"])
    named = fragment_def["named_args"]
    variables = variables or {}

    # Z32053 cite web: fill in defaults when only the URL is provided
    if func_id == "Z32053" and len(positional) >= 1 and not named:
        url = positional[0]
        domain = _domain_from_url(url)
        # Pad positional args up to 4 (date is type=date, language auto-fills)
        while len(positional) < 2:
            positional.append(url)
        while len(positional) < 3:
            positional.append(domain)

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
            # Date parameters default to today's date if not provided
            if param["type"] == "date":
                args_dict[full_key] = today_z20420()
                continue
            raise ValueError(
                f"Not enough arguments for {func_id} ({func_info['name']}). "
                f"Missing: {param['name']} ({param['key']})"
            )

        # Date parameters need to be parsed into Z20420 objects
        if param["type"] == "date":
            args_dict[full_key] = parse_date_string(raw_value)
        else:
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


def compile_paragraph(fragment_defs, variables, origin_qid, index):
    """Compile a group of fragments into a single paragraph clipboard item.

    Wraps multiple function calls in Z32123(Z32234([Z1, call1, "  ", call2, ...])).
    Each inner call is NOT individually wrapped — Z32234 handles text
    concatenation and Z32123 produces the final Z89 HTML paragraph.
    """
    inner_calls = []
    for frag_def in fragment_defs:
        func_call, _return_type = build_func_call(frag_def, variables)
        inner_calls.append(func_call)

    # Build typed list with whitespace separators between sentences
    typed_list = ["Z1"]
    for i, call in enumerate(inner_calls):
        if i > 0:
            typed_list.append("  ")
        typed_list.append(call)

    # Z32234 (join text to html) wraps the list
    z32234_call = z7_call("Z32234", {"Z32234K1": typed_list})

    # Z32123 (paragraph) wraps Z32234 to produce Z89
    z32123_call = z7_call("Z32123", {"Z32123K1": z32234_call})

    return build_clipboard_item(z32123_call, index=index, origin_qid=origin_qid)


def compile_section_header(qid, variables, origin_qid, index):
    """Compile a ==QID== section header into a clipboard item.

    Builds Z31465(Z10771(Z24766(QID, $lang))) which renders as a section
    title on Abstract Wikipedia.
    """
    # Z24766: get label for QID in language
    z24766_call = z7_call("Z24766", {
        "Z24766K1": z6091(qid),
        "Z24766K2": z18(IMPLICIT_REFS["$lang"]),
    })

    # Z10771: section title text
    z10771_call = z7_call("Z10771", {
        "Z10771K1": z24766_call,
    })

    # Z31465: section title wrapper
    z31465_call = z7_call("Z31465", {
        "Z31465K1": z10771_call,
    })

    return build_clipboard_item(z31465_call, index=index, origin_qid=origin_qid)


def replace_subject_with_pronoun(segment_text):
    """Replace SUBJECT with Q6091500 ("it") after the first occurrence.

    The first SUBJECT in a paragraph stays as SUBJECT (which compiles to
    the article entity Z825K1). Subsequent SUBJECTs become Q6091500, the
    Wikidata item for the third-person neuter pronoun "it", so they
    compile to a Z6091 entity reference — the structurally correct shape
    for slots that expect a Wikidata item. Substituting the literal
    string "it" instead would produce a Z6 string and break the function
    call's type contract.
    """
    count = [0]
    def replacer(match):
        count[0] += 1
        if count[0] == 1:
            return match.group(0)
        return "Q6091500"
    return re.sub(r'\bSUBJECT\b', replacer, segment_text)


def compile_template(text, variables=None):
    """Compile a wikitext template into clipboard-ready JSON.

    This is the main entry point. Takes a template string and variable
    values, returns a list of clipboard items ready for injection.

    All content is implicitly one paragraph. ``{{p}}`` midway through
    starts a new paragraph. ``==QID==`` section headers also cause
    paragraph breaks and produce Z31465 section title items.

    Within each paragraph, the first SUBJECT mention stays as SUBJECT;
    subsequent SUBJECTs become Q6091500 ("it") so the article doesn't
    keep repeating the subject's name.

    Args:
        text: Template string in wikitext format.
        variables: Dict mapping variable names to values (e.g. {"deity": "Q12345"}).

    Returns:
        List of clipboard item dicts, ready for inject_clipboard().
    """
    variables = variables or {}
    _, body = parse_frontmatter(text)
    origin_qid = variables.get("subject", "Q0")

    # Split body into segments separated by {{p}} or ==...== markers.
    # Each segment becomes a paragraph; ==...== also produces a section header item.
    # ==QID== uses the QID directly; ==anything else== auto-assigns natural number QIDs.
    split_pattern = re.compile(
        r'(\{\{\s*p\s*\}\}|^==\s*(.+?)\s*==$)',
        re.IGNORECASE | re.MULTILINE
    )

    clipboard_items = []
    section_counter = 0  # for auto-numbering non-QID headings
    pending_segments = []  # raw text segments accumulating into the current paragraph

    def flush_paragraph():
        """Compile accumulated fragments into a paragraph and add to items.

        SUBJECT-to-pronoun substitution happens here, scoped to the
        whole paragraph (across all its segments).
        """
        if not pending_segments:
            return
        combined = "\n".join(pending_segments)
        rewritten = replace_subject_with_pronoun(combined)
        fragments = parse_template_calls(rewritten)
        if not fragments:
            return
        item = compile_paragraph(
            fragments, variables, origin_qid, len(clipboard_items)
        )
        clipboard_items.append(item)

    last_end = 0
    for match in split_pattern.finditer(body):
        # Process any template calls before this marker
        segment = body[last_end:match.start()].strip()
        if segment:
            pending_segments.append(segment)

        # Check if this is a section header ==...==
        header_text = match.group(2)
        if header_text is not None:
            # Section header: flush current paragraph, emit header, start new paragraph
            flush_paragraph()
            pending_segments = []
            if re.match(r'^Q\d+$', header_text):
                section_qid = header_text
            else:
                # Non-QID heading: assign natural number QID (Q199=1, Q200=2, ...)
                section_counter += 1
                section_qid = f"Q{198 + section_counter}"
            header_item = compile_section_header(
                section_qid, variables, origin_qid, len(clipboard_items)
            )
            clipboard_items.append(header_item)
        else:
            # {{p}} marker: flush current paragraph, start new one
            flush_paragraph()
            pending_segments = []

        last_end = match.end()

    # Process remaining content after last marker
    remaining = body[last_end:].strip()
    if remaining:
        pending_segments.append(remaining)
    flush_paragraph()

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
