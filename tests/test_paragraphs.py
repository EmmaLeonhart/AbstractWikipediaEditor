"""Tests for paragraph compilation, section headers, and rendering.

Verifies that:
- Multiple ``{{...}}`` calls within a paragraph bundle into one
  Z32123(Z32234([Z1, call1, "  ", call2, ...])) clipboard item
- Blank lines and ``{{p}}`` markers split paragraphs
- ==QID== section headers compile to Z31465(Z10771(Z24766(QID, $lang)))
  and also act as paragraph breaks
- Citations (``{{cite web|...}}``) bundle into the same paragraph as
  the sentence they follow
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

# Jupiter wikitext as one bundled paragraph: 5 calls, one paragraph.
JUPITER_WIKITEXT = """{{is a|SUBJECT|Q634}}
{{superlative|SUBJECT|Q12935276|Q634|Q544}}
{{is a|SUBJECT|Q121750}}
{{comparative measurement|SUBJECT|Q525|Q11423|1/1048}}
{{comparative measurement|SUBJECT|Q2|Q37221|11}}"""


class TestBundledParagraphCompilation:
    """Calls between paragraph breaks bundle into one Z32123(Z32234)."""

    def test_bundles_into_single_paragraph(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        assert len(result) == 1, "5 calls, no breaks -> 1 paragraph"

    def test_outer_is_z32123(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        assert result[0]["value"]["Z7K1"]["Z9K1"] == "Z32123"

    def test_inner_is_z32234(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        assert result[0]["value"]["Z32123K1"]["Z7K1"]["Z9K1"] == "Z32234"

    def test_typed_list_holds_all_calls_with_separators(self):
        """The bundled list is [Z1, call1, "  ", call2, "  ", ...]."""
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        typed_list = result[0]["value"]["Z32123K1"]["Z32234K1"]
        assert typed_list[0] == "Z1"
        calls = [x for x in typed_list if isinstance(x, dict)]
        seps = [x for x in typed_list if isinstance(x, str) and x != "Z1"]
        assert len(calls) == 5
        assert seps == ["  "] * 4  # n-1 separators

    def test_inner_call_function_ids(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        typed_list = result[0]["value"]["Z32123K1"]["Z32234K1"]
        func_ids = [x["Z7K1"]["Z9K1"] for x in typed_list if isinstance(x, dict)]
        assert func_ids == ["Z26039", "Z27243", "Z26039", "Z32229", "Z32229"]

    def test_clipboard_envelope(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        item = result[0]
        assert item["itemId"] == "Q319.1#1"
        assert item["originKey"] == "Q319.1"
        assert item["originSlotType"] == "Z89"
        assert item["resolvingType"] == "Z89"

    def test_subject_resolved_in_first_inner_call(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        first_call = result[0]["value"]["Z32123K1"]["Z32234K1"][1]
        assert first_call["Z26039K1"]["Z18K1"]["Z6K1"] == "Z825K1"

    def test_qids_resolved_in_inner_calls(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        first_call = result[0]["value"]["Z32123K1"]["Z32234K1"][1]
        assert first_call["Z26039K2"]["Z6091K1"]["Z6K1"] == "Q634"


class TestParagraphBreaks:
    """{{p}} and blank lines split bundled paragraphs."""

    def test_explicit_p_marker_splits(self):
        template = """{{is a|SUBJECT|Q634}}
{{p}}
{{is a|SUBJECT|Q121750}}"""
        result = compile_template(template, {"subject": "Q319"})
        assert len(result) == 2

    def test_blank_line_splits(self):
        template = """{{is a|SUBJECT|Q634}}

{{is a|SUBJECT|Q121750}}"""
        result = compile_template(template, {"subject": "Q319"})
        assert len(result) == 2

    def test_two_calls_in_first_paragraph_one_in_second(self):
        template = """{{is a|SUBJECT|Q634}}
{{is a|SUBJECT|Q121750}}

{{is a|SUBJECT|Q515}}"""
        result = compile_template(template, {"subject": "Q319"})
        assert len(result) == 2
        first_calls = [
            x for x in result[0]["value"]["Z32123K1"]["Z32234K1"]
            if isinstance(x, dict)
        ]
        second_calls = [
            x for x in result[1]["value"]["Z32123K1"]["Z32234K1"]
            if isinstance(x, dict)
        ]
        assert len(first_calls) == 2
        assert len(second_calls) == 1

    def test_leading_p_marker_is_no_op(self):
        """A {{p}} at the start of the body doesn't create an empty paragraph."""
        template = """{{p}}
{{is a|SUBJECT|Q634}}"""
        result = compile_template(template, {"subject": "Q319"})
        assert len(result) == 1


class TestSingleTemplateBehavior:
    def test_single_call_produces_single_paragraph(self):
        template = "{{Z26039|SUBJECT|Q634}}"
        result = compile_template(template, {"subject": "Q319"})
        assert len(result) == 1
        assert result[0]["value"]["Z7K1"]["Z9K1"] == "Z32123"

    def test_shrine_template_one_paragraph_two_calls(self):
        template = """---
title: Shinto Shrine
variables:
  deity: Q-item
---
{{Z26570|SUBJECT|Q845945|Q17}}
{{Z28016|$deity|Q11591100|SUBJECT}}"""
        result = compile_template(template, {"deity": "Q99999", "subject": "Q12345"})
        assert len(result) == 1, "Two adjacent calls bundle into one paragraph"
        typed_list = result[0]["value"]["Z32123K1"]["Z32234K1"]
        calls = [x for x in typed_list if isinstance(x, dict)]
        assert len(calls) == 2


class TestCitationsBundle:
    """{{cite web|...}} fragments bundle into the same paragraph as the
    sentence they follow, instead of becoming standalone paragraphs."""

    def test_sentence_with_citation_is_one_paragraph(self):
        template = """{{is a|SUBJECT|Q634}}
{{cite web|https://example.com/source}}"""
        result = compile_template(template, {"subject": "Q319"})
        assert len(result) == 1
        typed_list = result[0]["value"]["Z32123K1"]["Z32234K1"]
        calls = [x for x in typed_list if isinstance(x, dict)]
        assert len(calls) == 2
        assert calls[0]["Z7K1"]["Z9K1"] == "Z26039"
        assert calls[1]["Z7K1"]["Z9K1"] == "Z32053"

    def test_two_claims_with_citations_split_on_blank_line(self):
        template = """{{is a|SUBJECT|Q634}}
{{cite web|https://a.example.com}}

{{is a|SUBJECT|Q121750}}
{{cite web|https://b.example.com}}"""
        result = compile_template(template, {"subject": "Q319"})
        assert len(result) == 2
        for item in result:
            calls = [
                x for x in item["value"]["Z32123K1"]["Z32234K1"]
                if isinstance(x, dict)
            ]
            assert len(calls) == 2  # claim + citation


class TestCompileParagraphDirect:
    """compile_paragraph bundles fragments — used by compile_template."""

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
        # 1 bundled paragraph (2 calls) + header + 1 paragraph = 3 items
        assert len(result) == 3
        assert [r["value"]["Z7K1"]["Z9K1"] for r in result] == [
            "Z32123", "Z31465", "Z32123",
        ]
        # First paragraph holds both calls bundled.
        first_calls = [
            x for x in result[0]["value"]["Z32123K1"]["Z32234K1"]
            if isinstance(x, dict)
        ]
        assert len(first_calls) == 2

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


class TestInfixForm:
    """{{infix|subject|predicate|object}} rewrites to the appropriate
    role-sentence function based on the predicate word."""

    def test_infix_part_of_maps_to_z32982(self):
        """{{infix|X|part of|Y}} -> {{Z32982|X|Q66305721|Y}}."""
        template = "{{infix|Q4830453|part of|Q50831573}}"
        result = compile_template(template, {"subject": "Q4830453"})
        inner = result[0]["value"]["Z32123K1"]["Z32234K1"][1]
        assert inner["Z7K1"]["Z9K1"] == "Z32982"
        assert inner["Z32982K1"]["Z6091K1"]["Z6K1"] == "Q4830453"
        assert inner["Z32982K2"]["Z6091K1"]["Z6K1"] == "Q66305721"
        assert inner["Z32982K3"]["Z6091K1"]["Z6K1"] == "Q50831573"

    def test_infix_predicate_case_insensitive(self):
        """The predicate lookup ignores case so 'Part Of' also works."""
        template = "{{infix|Q4830453|Part Of|Q50831573}}"
        result = compile_template(template, {"subject": "Q4830453"})
        inner = result[0]["value"]["Z32123K1"]["Z32234K1"][1]
        assert inner["Z7K1"]["Z9K1"] == "Z32982"

    def test_infix_with_subject(self):
        """SUBJECT resolves normally on both sides of the infix form."""
        template = "{{infix|SUBJECT|part of|Q50831573}}"
        result = compile_template(template, {"subject": "Q4830453"})
        inner = result[0]["value"]["Z32123K1"]["Z32234K1"][1]
        assert inner["Z32982K1"]["Z18K1"]["Z6K1"] == "Z825K1"
        assert inner["Z32982K3"]["Z6091K1"]["Z6K1"] == "Q50831573"

    def test_infix_unknown_predicate_is_not_rewritten(self):
        """Unknown predicates leave the call as `infix`, which then fails
        downstream with the normal 'unknown function' path — better to
        surface a clear error than to silently guess a mapping."""
        template = "{{infix|Q4830453|frobnicates|Q50831573}}"
        # Unknown function "infix" falls through to build_func_call's
        # best-effort path, which happily builds an `infix` call with
        # three positional args. Not useful, but not a crash.
        result = compile_template(template, {"subject": "Q4830453"})
        inner = result[0]["value"]["Z32123K1"]["Z32234K1"][1]
        assert inner["Z7K1"]["Z9K1"] == "infix"


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
