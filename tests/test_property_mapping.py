"""Tests for data/property_function_mapping.json — argument order in the
Z28016 ("defining role sentence") templates.

Z28016 renders "K1 is the [role] of K3". So for properties where the
*value* bears the role (e.g. the country IS the country of origin, the
person IS the author), the template must place $value first and SUBJECT
last. Getting this backwards produced the reversed sentence a user
reported on the AW Project chat: tennis (Q847) rendered as
"Tennis is the country of origin of England." (2026-06-23). P495 was the
lone outlier emitting SUBJECT-first; this test guards the fix.
"""

import json
import os

MAPPING_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "property_function_mapping.json",
)


def _load_mappings():
    with open(MAPPING_PATH, encoding="utf-8") as f:
        return json.load(f)["mappings"]


# Properties whose VALUE bears the role — these must read
# "$value is the <role> of SUBJECT", i.e. $value before SUBJECT.
VALUE_BEARS_ROLE = ["P37", "P38", "P50", "P57", "P112", "P495"]


def test_p495_country_of_origin_is_value_first():
    """The exact regression: P495 must not put SUBJECT first."""
    m = _load_mappings()["P495"]
    assert m["function"] == "Z28016"
    assert m["template"] == "{{Z28016|$value|Q3373417|SUBJECT}}", (
        "P495 must read '$value is the country of origin of SUBJECT'; "
        "SUBJECT-first renders the reversed 'X is the country of origin of <country>'."
    )


def test_value_bearing_role_props_put_value_before_subject():
    """No value-bears-role property may emit SUBJECT before $value in Z28016."""
    mappings = _load_mappings()
    for pid in VALUE_BEARS_ROLE:
        tmpl = mappings[pid]["template"]
        assert mappings[pid]["function"] == "Z28016", pid
        sub_i = tmpl.index("SUBJECT")
        val_i = tmpl.index("$value")
        assert val_i < sub_i, (
            f"{pid}: $value must come before SUBJECT in {tmpl!r} "
            f"(else the role sentence is reversed)"
        )


def test_mapping_file_is_valid_json_with_templates():
    """Every non-skipped mapping has a function and a template."""
    for pid, m in _load_mappings().items():
        if m.get("skip"):
            continue  # e.g. P138 "named after" is deliberately not emitted
        assert m.get("function"), f"{pid} missing function"
        assert m.get("template"), f"{pid} missing template"
