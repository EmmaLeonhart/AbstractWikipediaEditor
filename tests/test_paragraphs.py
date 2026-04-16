"""Tests for paragraph compilation, section headers, and rendering.

Verifies that:
- Every ``{{...}}`` call becomes its own paragraph (Z32123(Z32234([Z1, call])))
- There is no ``{{p}}`` marker — explicit paragraph control was dropped
  because bundling calls caused recursive evaluator errors
- ==QID== section headers compile to Z31465(Z10771(Z24766(QID, $lang)))
- One clipboard paste per emitted item
"""

import json
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wikitext_parser import (
    z6, z9s, z6091, z18, z7_call,
    compile_template, compile_paragraph, compile_section_header,
    build_func_call, parse_template_calls, FUNCTION_REGISTRY,
)


# Cached Wikidata labels for Jupiter (Q319) — avoids network calls in tests
JUPITER_LABELS = {
    "Q319": "Jupiter",
    "Q634": "planet",
    "Q12935276": "largeness",
    "Q544": "Solar System",
    "Q121750": "gas giant",
    "Q525": "Sun",
    "Q11423": "mass",
    "Q2": "Earth",
    "Q37221": "diameter",
}

# Jupiter wikitext. No {{p}} — every function is its own paragraph now.
JUPITER_WIKITEXT = """{{is a|SUBJECT|Q634}}
{{superlative|SUBJECT|Q12935276|Q634|Q544}}
{{is a|SUBJECT|Q121750}}
{{comparative measurement|SUBJECT|Q525|Q11423|1/1048}}
{{comparative measurement|SUBJECT|Q2|Q37221|11}}"""


class TestParagraphCompilation:
    """Each template call compiles to its own Z32123(Z32234([Z1, call]))."""

    def test_one_paragraph_per_call(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        assert len(result) == 5, "5 calls -> 5 clipboard items"

    def test_each_outer_is_z32123(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        for item in result:
            assert item["value"]["Z7K1"]["Z9K1"] == "Z32123"

    def test_each_inner_is_z32234(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        for item in result:
            assert item["value"]["Z32123K1"]["Z7K1"]["Z9K1"] == "Z32234"

    def test_typed_list_is_single_call(self):
        """Each paragraph's typed list holds exactly one call: [Z1, call]."""
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        for item in result:
            typed_list = item["value"]["Z32123K1"]["Z32234K1"]
            assert typed_list[0] == "Z1"
            calls = [x for x in typed_list if isinstance(x, dict)]
            assert len(calls) == 1, "One call per paragraph, no separators"
            seps = [x for x in typed_list if isinstance(x, str) and x != "Z1"]
            assert seps == []

    def test_inner_calls_are_correct_functions(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        func_ids = [
            item["value"]["Z32123K1"]["Z32234K1"][1]["Z7K1"]["Z9K1"]
            for item in result
        ]
        assert func_ids == ["Z26039", "Z27243", "Z26039", "Z32229", "Z32229"]

    def test_clipboard_envelope(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        first = result[0]
        assert first["itemId"] == "Q319.1#1"
        assert first["originKey"] == "Q319.1"
        assert first["originSlotType"] == "Z89"
        assert first["resolvingType"] == "Z89"

    def test_item_ids_increment_per_paragraph(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        ids = [item["itemId"] for item in result]
        assert ids == ["Q319.1#1", "Q319.2#1", "Q319.3#1", "Q319.4#1", "Q319.5#1"]

    def test_subject_resolved_in_first_call(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        first_call = result[0]["value"]["Z32123K1"]["Z32234K1"][1]  # Z26039
        assert first_call["Z26039K1"]["Z18K1"]["Z6K1"] == "Z825K1"

    def test_qids_resolved_in_inner_calls(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        first_call = result[0]["value"]["Z32123K1"]["Z32234K1"][1]  # Z26039 with Q634
        assert first_call["Z26039K2"]["Z6091K1"]["Z6K1"] == "Q634"


class TestLegacyPMarkersIgnored:
    """Stray {{p}} from legacy content must be silently dropped."""

    def test_p_markers_do_not_affect_output(self):
        with_p = """{{p}}
{{is a|SUBJECT|Q634}}
{{p}}
{{is a|SUBJECT|Q121750}}"""
        without_p = """{{is a|SUBJECT|Q634}}
{{is a|SUBJECT|Q121750}}"""
        a = compile_template(with_p, {"subject": "Q319"})
        b = compile_template(without_p, {"subject": "Q319"})
        assert len(a) == len(b) == 2

    def test_stray_p_does_not_become_a_fragment(self):
        template = "{{p}}\n{{is a|SUBJECT|Q634}}\n{{p}}"
        result = compile_template(template, {"subject": "Q319"})
        assert len(result) == 1
        assert result[0]["value"]["Z7K1"]["Z9K1"] == "Z32123"


class TestSingleTemplateBehavior:
    def test_single_call_produces_single_paragraph(self):
        template = "{{Z26039|SUBJECT|Q634}}"
        result = compile_template(template, {"subject": "Q319"})
        assert len(result) == 1
        assert result[0]["value"]["Z7K1"]["Z9K1"] == "Z32123"

    def test_shrine_template_two_paragraphs(self):
        template = """---
title: Shinto Shrine
variables:
  deity: Q-item
---
{{Z26570|SUBJECT|Q845945|Q17}}
{{Z28016|$deity|Q11591100|SUBJECT}}"""
        result = compile_template(template, {"deity": "Q99999", "subject": "Q12345"})
        assert len(result) == 2, "Two calls -> two paragraphs"
        assert result[0]["value"]["Z7K1"]["Z9K1"] == "Z32123"
        assert result[1]["value"]["Z7K1"]["Z9K1"] == "Z32123"


class TestCompileParagraphDirect:
    """compile_paragraph still accepts multiple fragments (used internally),
    but compile_template now only passes one at a time."""

    def test_compile_paragraph_single_fragment(self):
        frags = parse_template_calls("{{Z26039|SUBJECT|Q634}}")
        item = compile_paragraph(frags, {}, "Q319", 0)
        assert item["value"]["Z7K1"]["Z9K1"] == "Z32123"

    def test_compile_paragraph_inner_not_wrapped(self):
        """Inner calls should NOT have Z29749/Z27868 wrappers."""
        frags = parse_template_calls("{{Z26039|SUBJECT|Q634}}")
        item = compile_paragraph(frags, {}, "Q319", 0)
        typed_list = item["value"]["Z32123K1"]["Z32234K1"]
        inner_call = typed_list[1]
        assert inner_call["Z7K1"]["Z9K1"] == "Z26039"


class TestSectionHeaders:
    """==QID== section header compilation."""

    def test_section_header_structure(self):
        """==QID== produces Z31465(Z10771(Z24766(QID, $lang)))."""
        item = compile_section_header("Q131819891", {}, "Q762", 0)
        val = item["value"]
        assert val["Z7K1"]["Z9K1"] == "Z31465"
        z10771 = val["Z31465K1"]
        assert z10771["Z7K1"]["Z9K1"] == "Z10771"
        z24766 = z10771["Z10771K1"]
        assert z24766["Z7K1"]["Z9K1"] == "Z24766"
        assert z24766["Z24766K1"]["Z6091K1"]["Z6K1"] == "Q131819891"
        assert z24766["Z24766K2"]["Z18K1"]["Z6K1"] == "Z825K2"

    def test_section_header_in_template(self):
        """Header between two calls: 3 items (paragraph, header, paragraph)."""
        template = """{{Z26039|SUBJECT|Q634}}
==Q131819891==
{{Z26039|SUBJECT|Q515}}"""
        result = compile_template(template, {"subject": "Q319"})
        assert len(result) == 3
        assert result[0]["value"]["Z7K1"]["Z9K1"] == "Z32123"
        assert result[1]["value"]["Z7K1"]["Z9K1"] == "Z31465"
        assert result[2]["value"]["Z7K1"]["Z9K1"] == "Z32123"

    def test_multiple_calls_around_section_header(self):
        template = """{{Z26039|SUBJECT|Q634}}
{{Z26570|SUBJECT|Q634|Q544}}
==Q1310239==
{{Z26039|SUBJECT|Q515}}"""
        result = compile_template(template, {"subject": "Q319"})
        # 2 paragraphs + header + 1 paragraph = 4 items
        assert len(result) == 4
        assert [r["value"]["Z7K1"]["Z9K1"] for r in result] == [
            "Z32123", "Z32123", "Z31465", "Z32123",
        ]

    def test_non_qid_heading_gets_natural_number(self):
        template = """{{Z26039|SUBJECT|Q634}}
==Parts==
{{Z26039|SUBJECT|Q515}}"""
        result = compile_template(template, {"subject": "Q319"})
        assert len(result) == 3
        header = result[1]["value"]
        assert header["Z7K1"]["Z9K1"] == "Z31465"
        z24766 = header["Z31465K1"]["Z10771K1"]
        assert z24766["Z24766K1"]["Z6091K1"]["Z6K1"] == "Q199"

    def test_multiple_non_qid_headings_increment(self):
        template = """==Parts==
{{Z26039|SUBJECT|Q634}}
==Types==
{{Z26039|SUBJECT|Q515}}
==Questions==
{{Z26039|SUBJECT|Q544}}"""
        result = compile_template(template, {"subject": "Q319"})
        # 3 headers + 3 paragraphs = 6 items
        assert len(result) == 6
        assert result[0]["value"]["Z31465K1"]["Z10771K1"]["Z24766K1"]["Z6091K1"]["Z6K1"] == "Q199"
        assert result[2]["value"]["Z31465K1"]["Z10771K1"]["Z24766K1"]["Z6091K1"]["Z6K1"] == "Q200"
        assert result[4]["value"]["Z31465K1"]["Z10771K1"]["Z24766K1"]["Z6091K1"]["Z6K1"] == "Q201"

    def test_mixed_qid_and_non_qid_headings(self):
        template = """==Q131819891==
{{Z26039|SUBJECT|Q634}}
==Parts==
{{Z26039|SUBJECT|Q515}}"""
        result = compile_template(template, {"subject": "Q319"})
        assert len(result) == 4
        assert result[0]["value"]["Z31465K1"]["Z10771K1"]["Z24766K1"]["Z6091K1"]["Z6K1"] == "Q131819891"
        assert result[2]["value"]["Z31465K1"]["Z10771K1"]["Z24766K1"]["Z6091K1"]["Z6K1"] == "Q199"


class TestSubjectResolution:
    def test_subject_stays_as_subject_throughout(self):
        """All SUBJECT mentions stay as Z825K1 arg refs (no pronoun substitution)."""
        template = """{{Z26039|SUBJECT|Q634}}
{{Z26570|SUBJECT|Q634|Q544}}
{{Z28016|SUBJECT|Q66305721|Q87982}}"""
        result = compile_template(template, {"subject": "Q5511"})
        for item in result:
            call = item["value"]["Z32123K1"]["Z32234K1"][1]
            fid = call["Z7K1"]["Z9K1"]
            assert call[f"{fid}K1"]["Z18K1"]["Z6K1"] == "Z825K1"

    def test_bare_string_in_entity_slot_rejected(self):
        """A literal that is not a QID, $variable, or SUBJECT must
        be rejected at compile time when it appears in an entity slot.
        """
        template = "{{role|Q813858|Q11591100|garbage}}"
        with pytest.raises(ValueError, match="not a valid value for an entity slot"):
            compile_template(template, {"subject": "Q288312"})

    def test_literal_it_resolves_to_subject(self):
        """'it' is an alias for SUBJECT — both compile to a Z825K1 arg ref."""
        template = "{{role|it|Q11591100|Q813858}}"
        result = compile_template(template, {"subject": "Q288312"})
        call = result[0]["value"]["Z32123K1"]["Z32234K1"][1]
        assert call["Z28016K1"]["Z18K1"]["Z6K1"] == "Z825K1"


class TestCiteWeb:
    def test_cite_web_url_only(self):
        """{{cite web|URL}} fills in defaults: title=URL, site=domain, date=today, lang=$lang."""
        template = "{{cite web|https://example.com/foo}}"
        result = compile_template(template, {"subject": "Q319"})
        inner = result[0]["value"]["Z32123K1"]["Z32234K1"][1]
        assert inner["Z7K1"]["Z9K1"] == "Z32053"
        assert inner["Z32053K1"]["Z6K1"] == "https://example.com/foo"
        assert inner["Z32053K2"]["Z6K1"] == "https://example.com/foo"
        assert inner["Z32053K3"]["Z6K1"] == "example.com"
        assert inner["Z32053K4"]["Z1K1"] == "Z20420"
        assert inner["Z32053K5"]["Z18K1"]["Z6K1"] == "Z825K2"

    def test_cite_web_full_args(self):
        """{{cite web|URL|Title|Site|YYYY-MM-DD}} parses date into Z20420."""
        template = "{{cite web|https://en.wikipedia.org/wiki/Foo|Foo|Wikipedia|2026-03-14}}"
        result = compile_template(template, {"subject": "Q319"})
        inner = result[0]["value"]["Z32123K1"]["Z32234K1"][1]
        assert inner["Z32053K1"]["Z6K1"] == "https://en.wikipedia.org/wiki/Foo"
        assert inner["Z32053K2"]["Z6K1"] == "Foo"
        assert inner["Z32053K3"]["Z6K1"] == "Wikipedia"
        assert inner["Z32053K4"]["Z20420K1"]["Z20159K2"]["Z13518K1"] == "2026"
        assert inner["Z32053K4"]["Z20420K2"]["Z20342K1"]["Z16098K1"] == "Z16103"
        assert inner["Z32053K4"]["Z20420K2"]["Z20342K2"]["Z13518K1"] == "14"
