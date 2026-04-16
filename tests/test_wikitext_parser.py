"""Tests for the wikitext template parser."""

import json
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wikitext_parser import (
    z6, z9s, z6091, z18, z7_call,
    resolve_value, parse_frontmatter, parse_template_calls,
    build_func_call, compile_template, parse_template,
    wrap_as_fragment, build_clipboard_item, FUNCTION_REGISTRY,
    resolve_function_name,
)


class TestResolveFunctionName:
    """Alias resolution must be truly case-insensitive. The canonical
    function_aliases.json stores some keys with mixed case (e.g.
    "is the X of"), and the editor's live preview goes through this
    function on every render — any miss here surfaces as "not a Z-id"
    errors in the preview pane. Regression test for the case where
    "is the x of" (lowercase x) passed through unchanged because the
    dict was keyed on the mixed-case string and lookup only lowercased
    the input, not the keys."""

    def test_already_a_zid_passes_through(self):
        assert resolve_function_name("Z26570") == "Z26570"
        assert resolve_function_name("Z801") == "Z801"

    def test_lowercase_alias(self):
        assert resolve_function_name("is a") == "Z26039"
        assert resolve_function_name("location") == "Z26570"

    def test_mixed_case_canonical_key(self):
        # "is the X of" is the key in the JSON — must match regardless of user case
        assert resolve_function_name("is the X of") == "Z28016"
        assert resolve_function_name("is the x of") == "Z28016"
        assert resolve_function_name("IS THE X OF") == "Z28016"
        assert resolve_function_name("Is The X Of") == "Z28016"

    def test_multi_word_alias_case_insensitive(self):
        assert resolve_function_name("cite web") == "Z32053"
        assert resolve_function_name("CITE WEB") == "Z32053"
        assert resolve_function_name("Cite Web") == "Z32053"

    def test_unknown_alias_passes_through(self):
        # Unknown names should pass through unchanged so the caller can
        # error out later with a specific "not a Z-id" message.
        assert resolve_function_name("xyzzy not an alias") == "xyzzy not an alias"

    def test_whitespace_trimmed(self):
        assert resolve_function_name("  is a  ") == "Z26039"


# ============================================================
# Z-object helper tests
# ============================================================

class TestZObjectHelpers:
    def test_z6_string(self):
        assert z6("hello") == {"Z1K1": "Z6", "Z6K1": "hello"}

    def test_z9s_reference(self):
        assert z9s("Z7") == {"Z1K1": "Z9", "Z9K1": "Z7"}

    def test_z6091_qid(self):
        result = z6091("Q42")
        assert result["Z1K1"] == z9s("Z6091")
        assert result["Z6091K1"] == z6("Q42")

    def test_z18_arg_ref(self):
        result = z18("Z825K1")
        assert result["Z1K1"] == z9s("Z18")
        assert result["Z18K1"] == z6("Z825K1")

    def test_z7_call(self):
        result = z7_call("Z26570", {"Z26570K1": z6("test")})
        assert result["Z1K1"] == z9s("Z7")
        assert result["Z7K1"] == z9s("Z26570")
        assert result["Z26570K1"] == z6("test")


# ============================================================
# Value resolution tests
# ============================================================

class TestResolveValue:
    def test_subject_ref(self):
        result = resolve_value("SUBJECT")
        assert result == z18("Z825K1")

    def test_lang_ref(self):
        result = resolve_value("$lang")
        assert result == z18("Z825K2")

    def test_qid(self):
        result = resolve_value("Q845945")
        assert result == z6091("Q845945")

    def test_variable_resolves_to_qid(self):
        result = resolve_value("$deity", {"deity": "Q12345"})
        assert result == z6091("Q12345")

    def test_undefined_variable_raises(self):
        with pytest.raises(ValueError, match="Undefined variable"):
            resolve_value("$unknown")

    def test_z_reference(self):
        result = resolve_value("Z41")
        assert result == z9s("Z41")

    def test_boolean_true(self):
        result = resolve_value("true")
        assert result == z9s("Z41")

    def test_boolean_false(self):
        result = resolve_value("false")
        assert result == z9s("Z42")

    def test_plain_string(self):
        result = resolve_value("hello world")
        assert result == z6("hello world")

    def test_whitespace_stripped(self):
        result = resolve_value("  Q42  ")
        assert result == z6091("Q42")


# ============================================================
# Frontmatter parsing tests
# ============================================================

class TestParseFrontmatter:
    def test_with_frontmatter(self):
        text = """---
title: Test
variables:
  deity: Q-item
---
{{Z26570|SUBJECT|Q845945|Q17}}"""
        meta, body = parse_frontmatter(text)
        assert meta["title"] == "Test"
        assert "deity" in meta["variables"]
        assert "{{Z26570" in body

    def test_without_frontmatter(self):
        text = "{{Z26570|SUBJECT|Q845945|Q17}}"
        meta, body = parse_frontmatter(text)
        assert meta == {}
        assert "{{Z26570" in body

    def test_empty_frontmatter(self):
        text = """---
---
{{Z26570|SUBJECT|Q845945|Q17}}"""
        meta, body = parse_frontmatter(text)
        assert meta == {}
        assert "{{Z26570" in body


# ============================================================
# Template call parsing tests
# ============================================================

class TestParseTemplateCalls:
    def test_single_call(self):
        body = "{{Z26570|SUBJECT|Q845945|Q17}}"
        result = parse_template_calls(body)
        assert len(result) == 1
        assert result[0]["func_id"] == "Z26570"
        assert result[0]["args"] == ["SUBJECT", "Q845945", "Q17"]

    def test_multiple_calls(self):
        body = """{{Z26570|SUBJECT|Q845945|Q17}}
{{Z28016|$deity|Q11591100|SUBJECT}}"""
        result = parse_template_calls(body)
        assert len(result) == 2
        assert result[0]["func_id"] == "Z26570"
        assert result[1]["func_id"] == "Z28016"

    def test_named_args(self):
        body = "{{Z26570|entity=SUBJECT|class=Q845945|location=Q17}}"
        result = parse_template_calls(body)
        assert result[0]["named_args"]["entity"] == "SUBJECT"
        assert result[0]["named_args"]["class"] == "Q845945"
        assert result[0]["named_args"]["location"] == "Q17"
        assert result[0]["args"] == []

    def test_mixed_args(self):
        body = "{{Z26570|SUBJECT|class=Q845945|Q17}}"
        result = parse_template_calls(body)
        assert result[0]["args"] == ["SUBJECT", "Q17"]
        assert result[0]["named_args"]["class"] == "Q845945"

    def test_url_with_query_string_is_positional(self):
        """URLs with ?key=value query strings should not be parsed as named args."""
        body = "{{cite web|https://ja.wikipedia.org/w/index.php?title=Foo&oldid=12345}}"
        result = parse_template_calls(body)
        assert result[0]["args"] == [
            "https://ja.wikipedia.org/w/index.php?title=Foo&oldid=12345"
        ]
        assert result[0]["named_args"] == {}

    def test_comments_ignored(self):
        body = """# This is a comment
{{Z26570|SUBJECT|Q845945|Q17}}
# Another comment"""
        result = parse_template_calls(body)
        assert len(result) == 1

    def test_line_numbers(self):
        body = """# Comment
{{Z26570|SUBJECT|Q845945|Q17}}

{{Z28016|$deity|Q11591100|SUBJECT}}"""
        result = parse_template_calls(body)
        assert result[0]["line"] == 2
        assert result[1]["line"] == 4


# ============================================================
# Function call building tests
# ============================================================

class TestBuildFuncCall:
    def test_z26570_positional(self):
        frag = {
            "func_id": "Z26570",
            "args": ["SUBJECT", "Q845945", "Q17"],
            "named_args": {},
        }
        call, ret_type = build_func_call(frag)
        assert ret_type == "Z11"
        assert call["Z7K1"] == z9s("Z26570")
        # K1 = entity = SUBJECT -> Z825K1
        assert call["Z26570K1"] == z18("Z825K1")
        # K2 = class = Q845945
        assert call["Z26570K2"] == z6091("Q845945")
        # K3 = location = Q17
        assert call["Z26570K3"] == z6091("Q17")
        # K4 = language = auto-filled
        assert call["Z26570K4"] == z18("Z825K2")

    def test_z28016_with_variable(self):
        frag = {
            "func_id": "Z28016",
            "args": ["$deity", "Q11591100", "SUBJECT"],
            "named_args": {},
        }
        call, ret_type = build_func_call(frag, {"deity": "Q99999"})
        assert ret_type == "Z11"
        # K1 = subject = $deity -> Q99999
        assert call["Z28016K1"] == z6091("Q99999")
        # K2 = role = Q11591100
        assert call["Z28016K2"] == z6091("Q11591100")
        # K3 = dependency = SUBJECT -> Z825K1
        assert call["Z28016K3"] == z18("Z825K1")
        # K4 = language = auto
        assert call["Z28016K4"] == z18("Z825K2")

    def test_z26039_returns_z6(self):
        frag = {
            "func_id": "Z26039",
            "args": ["SUBJECT", "Q515"],
            "named_args": {},
        }
        call, ret_type = build_func_call(frag)
        assert ret_type == "Z6"

    def test_named_args(self):
        frag = {
            "func_id": "Z26570",
            "args": [],
            "named_args": {
                "entity": "SUBJECT",
                "class": "Q845945",
                "location": "Q17",
            },
        }
        call, _ = build_func_call(frag)
        assert call["Z26570K1"] == z18("Z825K1")
        assert call["Z26570K2"] == z6091("Q845945")
        assert call["Z26570K3"] == z6091("Q17")

    def test_unknown_function(self):
        frag = {
            "func_id": "Z99999",
            "args": ["Q42", "Q17"],
            "named_args": {},
        }
        call, ret_type = build_func_call(frag)
        assert call["Z7K1"] == z9s("Z99999")
        assert "Z99999K1" in call
        assert "Z99999K2" in call

    def test_missing_args_raises(self):
        frag = {
            "func_id": "Z26570",
            "args": ["SUBJECT"],  # Missing class and location
            "named_args": {},
        }
        with pytest.raises(ValueError, match="Not enough arguments"):
            build_func_call(frag)

    def test_unknown_named_param_raises(self):
        frag = {
            "func_id": "Z26570",
            "args": [],
            "named_args": {"nonexistent": "Q42"},
        }
        with pytest.raises(ValueError, match="Unknown parameter"):
            build_func_call(frag)


# ============================================================
# Wrapping tests
# ============================================================

class TestWrapAsFragment:
    def test_z11_wraps_with_z29749(self):
        inner = z7_call("Z28016", {})
        result = wrap_as_fragment("Z28016", inner, "Z11")
        assert result["Z7K1"] == z9s("Z29749")
        assert result["Z29749K1"] == inner
        assert result["Z29749K2"] == z18("Z825K2")

    def test_z6_wraps_with_z27868(self):
        inner = z7_call("Z26039", {})
        result = wrap_as_fragment("Z26039", inner, "Z6")
        assert result["Z7K1"] == z9s("Z27868")
        assert result["Z27868K1"] == inner

    def test_z89_no_wrap(self):
        inner = z7_call("Z29822", {})
        result = wrap_as_fragment("Z29822", inner, "Z89")
        assert result is inner


# ============================================================
# Clipboard item envelope tests
# ============================================================

class TestBuildClipboardItem:
    def test_envelope_structure(self):
        value = {"test": True}
        item = build_clipboard_item(value, index=0, origin_qid="Q12345")
        assert item["itemId"] == "Q12345.1#1"
        assert item["originKey"] == "Q12345.1"
        assert item["originSlotType"] == "Z89"
        assert item["value"] == value
        assert item["objectType"] == "Z7"
        assert item["resolvingType"] == "Z89"

    def test_index_increments(self):
        item0 = build_clipboard_item({}, index=0)
        item1 = build_clipboard_item({}, index=1)
        assert item0["itemId"].endswith(".1#1")
        assert item1["itemId"].endswith(".2#1")


# ============================================================
# Full compile_template integration tests
# ============================================================

class TestCompileTemplate:
    def test_shrine_template(self):
        template = """---
title: Shinto Shrine
variables:
  deity: Q-item
---
{{Z26570|SUBJECT|Q845945|Q17}}
{{Z28016|$deity|Q11591100|SUBJECT}}"""

        result = compile_template(template, {"deity": "Q99999", "subject": "Q12345"})
        # Every call is its own paragraph now
        assert len(result) == 2

        frag0 = result[0]
        assert frag0["resolvingType"] == "Z89"
        assert frag0["itemId"] == "Q12345.1#1"
        # Wrapped as Z32123 paragraph
        assert frag0["value"]["Z7K1"] == z9s("Z32123")

    def test_no_frontmatter(self):
        template = "{{Z26570|SUBJECT|Q845945|Q17}}"
        result = compile_template(template)
        assert len(result) == 1

    def test_three_fragment_shrine(self):
        template = """{{Z26570|SUBJECT|Q845945|Q17}}
{{Z28016|$deity|Q11591100|SUBJECT}}
{{Z26570|SUBJECT|Q845945|$admin}}"""

        result = compile_template(template, {
            "deity": "Q111",
            "admin": "Q222",
        })
        # Each call is its own paragraph
        assert len(result) == 3
        for item in result:
            assert item["value"]["Z7K1"] == z9s("Z32123")

    def test_z6_returning_function_wraps_as_paragraph(self):
        template = "{{Z26039|SUBJECT|Q515}}"
        result = compile_template(template)
        # Single template wraps as Z32123 paragraph
        assert result[0]["value"]["Z7K1"] == z9s("Z32123")


# ============================================================
# Comparison with existing hardcoded templates
# ============================================================

class TestMatchesExistingOutput:
    """Verify parser output matches the hardcoded CLIPBOARD_TEMPLATE from create_rich_onepass.py."""

    def test_deity_fragment_structure(self):
        """The deity fragment should match the Z28016 call structure inside a paragraph."""
        template = "{{Z28016|$deity|Q11591100|SUBJECT}}"
        result = compile_template(template, {"deity": "Q99999"})
        para = result[0]["value"]

        # Outer: Z32123 paragraph
        assert para["Z7K1"]["Z9K1"] == "Z32123"

        # Z32234 inside
        z32234 = para["Z32123K1"]
        assert z32234["Z7K1"]["Z9K1"] == "Z32234"

        # Inner call list: [Z1, Z28016_call]
        typed_list = z32234["Z32234K1"]
        inner = typed_list[1]
        assert inner["Z7K1"]["Z9K1"] == "Z28016"

        # Z28016K1 = deity QID
        assert inner["Z28016K1"]["Z6091K1"]["Z6K1"] == "Q99999"
        # Z28016K2 = role (Q11591100)
        assert inner["Z28016K2"]["Z6091K1"]["Z6K1"] == "Q11591100"
        # Z28016K3 = dependency (SUBJECT -> Z825K1)
        assert inner["Z28016K3"]["Z18K1"]["Z6K1"] == "Z825K1"
        # Z28016K4 = language (auto -> Z825K2)
        assert inner["Z28016K4"]["Z18K1"]["Z6K1"] == "Z825K2"

    def test_location_fragment_structure(self):
        """The location fragment uses Z26570 inside a paragraph."""
        template = "{{Z26570|SUBJECT|Q845945|Q17}}"
        result = compile_template(template)
        para = result[0]["value"]

        # Outer: Z32123 paragraph
        assert para["Z7K1"]["Z9K1"] == "Z32123"

        # Inner call inside Z32234
        z32234 = para["Z32123K1"]
        typed_list = z32234["Z32234K1"]
        inner = typed_list[1]
        assert inner["Z7K1"]["Z9K1"] == "Z26570"

        # K1 = entity (SUBJECT -> Z825K1)
        assert inner["Z26570K1"]["Z18K1"]["Z6K1"] == "Z825K1"
        # K2 = class (Q845945)
        assert inner["Z26570K2"]["Z6091K1"]["Z6K1"] == "Q845945"
        # K3 = location (Q17)
        assert inner["Z26570K3"]["Z6091K1"]["Z6K1"] == "Q17"
        # K4 = language (auto Z825K2)
        assert inner["Z26570K4"]["Z18K1"]["Z6K1"] == "Z825K2"


# ============================================================
# Template file loading test
# ============================================================

class TestTemplateFiles:
    """Test that the example template files parse correctly."""

    TEMPLATES_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "templates"
    )

    def test_shinto_shrine_template(self):
        path = os.path.join(self.TEMPLATES_DIR, "shinto_shrine.wikitext")
        with open(path) as f:
            text = f.read()
        parsed = parse_template(text)
        assert parsed["metadata"]["title"] == "Shinto Shrine"
        assert len(parsed["fragments"]) == 2

    def test_shinto_shrine_3frag_template(self):
        path = os.path.join(self.TEMPLATES_DIR, "shinto_shrine_3frag.wikitext")
        with open(path) as f:
            text = f.read()
        parsed = parse_template(text)
        assert len(parsed["fragments"]) == 3

    def test_city_template(self):
        path = os.path.join(self.TEMPLATES_DIR, "city.wikitext")
        with open(path) as f:
            text = f.read()
        result = compile_template(text, {
            "country": "Q30",
            "class": "Q515",
            "subject": "Q60",
        })
        assert len(result) == 1

    def test_mountain_template(self):
        path = os.path.join(self.TEMPLATES_DIR, "mountain.wikitext")
        with open(path) as f:
            text = f.read()
        result = compile_template(text, {
            "adjective": "Q1151067",
            "class": "Q8502",
            "location": "Q48",
            "subject": "Q513",
        })
        assert len(result) == 1
        # Single template wraps as Z32123 paragraph
        assert result[0]["value"]["Z7K1"]["Z9K1"] == "Z32123"


class TestFunctionRegistry:
    def test_all_registered_functions_have_params(self):
        for fid, info in FUNCTION_REGISTRY.items():
            assert "params" in info, f"{fid} missing params"
            assert "returns" in info, f"{fid} missing returns"
            assert "name" in info, f"{fid} missing name"
            assert len(info["params"]) > 0, f"{fid} has no params"

    def test_all_functions_have_language_param(self):
        """Most sentence generators take a language param."""
        for fid, info in FUNCTION_REGISTRY.items():
            lang_params = [p for p in info["params"] if p["type"] == "language"]
            # Every function should have exactly one language param
            assert len(lang_params) == 1, f"{fid} should have exactly 1 language param"
