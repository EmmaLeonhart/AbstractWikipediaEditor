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
    "Z32982": {
        "name": "non-defining role sentence",
        "example": "Honshu is a part of Japan.",
        "params": [
            {"key": "K1", "name": "subject", "type": "entity_ref"},
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
    "it": "Z825K1",         # alias of SUBJECT; "it" is not used in published articles
    "$lang": "Z825K2",      # language
}

# Wikitext aliases that resolve to Wikidata items. These are author-facing
# shortcuts so the source text reads naturally instead of forcing the writer
# to remember an opaque QID. They compile to a Z6091 entity reference, never
# a Z6 string — the literal alias word must not appear in the published JSON.
QID_ALIASES = {
}


# Param types in FUNCTION_REGISTRY that require an entity-typed value
# (Z6091/Z18). A plain Z6 string in one of these slots is a type error
# and must be rejected at compile time so the editor cannot push bad
# data — that class of bug is invisible in preview renderers and
# silently corrupts published articles.
ENTITY_PARAM_TYPES = frozenset({"Q-item", "entity_ref"})


def resolve_value(raw_value, variables=None, expected_type=None):
    """Convert a raw template value into a Z-object.

    Resolution rules:
    - "SUBJECT" / "$lang" -> Z18 argument reference
    - "$varname" -> look up in variables dict, then treat result as a value
    - QID_ALIASES key -> Z6091 Wikidata item reference
    - "Q..." (Wikidata QID) -> Z6091 Wikidata item reference
    - "Z..." that looks like a Z-ID -> Z9 reference
    - Anything else -> Z6 string literal (only allowed if expected_type
      is not an entity slot — entity slots reject plain strings)
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
        return resolve_value(resolved, variables, expected_type)

    # Wikitext aliases for Wikidata items
    if raw_value in QID_ALIASES:
        return z6091(QID_ALIASES[raw_value])

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

    # Plain string — only legal in slots that explicitly accept strings.
    # In entity slots, refuse to fall through to z6() because that
    # silently puts a Z6 in a Z6091 slot and corrupts the article.
    if expected_type in ENTITY_PARAM_TYPES:
        alias_hint = ", ".join(sorted(QID_ALIASES.keys()))
        raise ValueError(
            f"'{raw_value}' is not a valid value for an entity slot "
            f"(expected a Q-item, $variable, SUBJECT, or alias: {alias_hint}). "
            f"Plain strings in entity positions are rejected because they "
            f"silently corrupt the published JSON."
        )
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
# Lowercase-keyed index so alias lookup is actually case-insensitive.
# The canonical JSON stores some keys with uppercase letters (e.g.
# "is the X of") — without this index, typing "is the x of" would fall
# through and be treated as a literal function name, then blow up on
# push with a "not a Z-id" error. There are no case-collisions in the
# canonical file as of writing (checked at build time), so collapsing
# to lowercase loses no information.
_FUNCTION_ALIASES_LC = {k.lower(): v for k, v in _FUNCTION_ALIASES.items()}


def resolve_function_name(name):
    """Resolve a function name or alias to a Z-ID.

    Accepts Z-IDs directly (e.g. "Z26570") or English aliases
    (e.g. "location", "is a", "role", "is the x of"). Alias lookup is
    case-insensitive — both "is the X of" and "is the x of" resolve
    to the same Z-id.

    Unknown names pass through unchanged, which lets callers error out
    later with a more specific "not a Z-id" message instead of us
    silently replacing the name with garbage.
    """
    name = name.strip()
    # Already a Z-ID
    if re.match(r'^Z\d+$', name):
        return name
    return _FUNCTION_ALIASES_LC.get(name.lower(), name)


# Infix form predicate map. `{{infix|subject|predicate|object}}` is a
# natural-language shortcut that gets rewritten to a concrete function
# call at parse time. The predicate determines both the target function
# (a role Z-ID) and the role QID that fills the middle slot.
#
# Example: {{infix|Q4830453|part of|Q50831573}} rewrites to
# {{Z32982|Q4830453|Q66305721|Q50831573}} — "Coca Cola is a part of in S&P 500".
#
# Predicate lookup is case-insensitive. Add entries here as new
# natural-language relations get wired up.
INFIX_PREDICATES = {
    "part of": ("Z32982", "Q66305721"),
}


def parse_template_calls(body):
    """Extract all {{...}} template calls from the body text.

    Returns a list of dicts:
        {"func_id": "Z26570", "args": [...], "named_args": {...}, "line": N}

    Supports both positional and named arguments:
        {{Z26570|SUBJECT|Q845945|Q17}}
        {{location|SUBJECT|Q845945|Q17}}
        {{Z26570|entity=SUBJECT|class=Q845945|location=Q17}}

    Also supports the infix form:
        {{infix|subject|part of|object}}
    which rewrites to the appropriate role-sentence function (see
    INFIX_PREDICATES) before the normal function-registry path runs.
    Unknown predicates are left alone; the caller gets a "function
    infix not found" error downstream, which is the right failure mode.
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

        # Infix rewrite: {{infix|X|predicate|Y}} -> {{target_zid|X|role_qid|Y}}
        # Handled here, before resolve_function_name, because the whole
        # point is that the predicate word (part 2) drives the target
        # function — a plain alias map can't express "the second argument
        # decides which function this is".
        if parts[0].lower() == "infix" and len(parts) >= 4:
            predicate = parts[2].lower()
            mapping = INFIX_PREDICATES.get(predicate)
            if mapping:
                target_zid, role_qid = mapping
                parts = [target_zid, parts[1], role_qid, parts[3]] + parts[4:]

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
            args_dict[full_key] = resolve_value(raw_value, variables, param.get("type"))
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
            args_dict[full_key] = resolve_value(raw_value, variables, param.get("type"))

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

    Wraps multiple function calls in Z33068([Z1, call1, call2, ...]).
    Z33068 ("paragraph from sentences") takes a typed list of sentences
    and produces the Z89 HTML paragraph directly — no separator strings
    needed, because the function inserts spacing between sentences itself.
    """
    inner_calls = []
    for frag_def in fragment_defs:
        func_call, _return_type = build_func_call(frag_def, variables)
        inner_calls.append(func_call)

    typed_list = ["Z1", *inner_calls]

    z33068_call = z7_call("Z33068", {"Z33068K1": typed_list})

    return build_clipboard_item(z33068_call, index=index, origin_qid=origin_qid)


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




# Paragraph-break markers in wikitext: a blank line, an explicit
# {{p}} token, or a ==QID== section header. The first two split the
# body into bundled paragraphs (multi-call Z33068 items); section
# headers also emit a Z31465 item.
_PARAGRAPH_SPLIT_RE = re.compile(
    r'(\{\{\s*p\s*\}\}|^==\s*(.+?)\s*==$|\n[ \t]*\n)',
    re.IGNORECASE | re.MULTILINE,
)


def compile_template(text, variables=None):
    """Compile a wikitext template into clipboard-ready JSON.

    Multiple ``{{...}}`` calls within a paragraph are bundled into a
    single Z33068([Z1, call1, call2, ...]) clipboard item — Z33068
    ("paragraph from sentences") inserts spacing between sentences
    itself, so no separator strings are stored. Paragraph breaks are
    introduced by:

    * a blank line in the source,
    * an explicit ``{{p}}`` token,
    * or a ``==QID==`` section header (which also emits a Z31465 item).

    Citations (e.g. ``{{cite web|URL}}``) are just regular calls, so
    they bundle into the same paragraph as the sentence they follow,
    matching how ``<sup>``-style refs are meant to render.

    History note: there was a brief period where every call became its
    own paragraph. That was a misread of the WF Project chat — the
    consensus is multi-sentence paragraphs with paragraph breaks, not
    one paragraph per sentence.

    ``==QID==`` uses the QID directly; ``==anything else==`` auto-
    assigns natural number QIDs starting at Q199.

    Args:
        text: Template string in wikitext format.
        variables: Dict mapping variable names to values (e.g. {"deity": "Q12345"}).

    Returns:
        List of clipboard item dicts, ready for inject_clipboard().
    """
    variables = variables or {}
    _, body = parse_frontmatter(text)
    origin_qid = variables.get("subject", "Q0")

    clipboard_items = []
    section_counter = 0  # for auto-numbering non-QID headings

    def emit_paragraph(segment_text):
        """Compile a paragraph's calls into one bundled Z32123 item."""
        fragments = parse_template_calls(segment_text)
        if not fragments:
            return
        item = compile_paragraph(
            fragments, variables, origin_qid, len(clipboard_items)
        )
        clipboard_items.append(item)

    last_end = 0
    for match in _PARAGRAPH_SPLIT_RE.finditer(body):
        segment = body[last_end:match.start()]
        if segment.strip():
            emit_paragraph(segment)

        header_text = match.group(2)
        if header_text is not None:
            if re.match(r'^Q\d+$', header_text):
                section_qid = header_text
            else:
                section_counter += 1
                section_qid = f"Q{198 + section_counter}"
            header_item = compile_section_header(
                section_qid, variables, origin_qid, len(clipboard_items)
            )
            clipboard_items.append(header_item)
        # {{p}} or blank line: just a flush, nothing to emit for the marker itself.

        last_end = match.end()

    remaining = body[last_end:]
    if remaining.strip():
        emit_paragraph(remaining)

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
