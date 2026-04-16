"""Tests for paragraph compilation, section headers, and rendering.

Verifies that:
- Everything is implicitly one paragraph; {{p}} midway starts a new one
- ==QID== section headers compile to Z31465(Z10771(Z24766(QID, $lang)))
- Section headers cause paragraph breaks
- One paragraph = one clipboard paste operation
- Jupiter (Q319) article compiles to a single paragraph
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

# Jupiter wikitext as produced by convert_article.py
JUPITER_WIKITEXT = """{{p}}
{{is a|SUBJECT|Q634}}
{{superlative|SUBJECT|Q12935276|Q634|Q544}}
{{is a|SUBJECT|Q121750}}
{{comparative measurement|SUBJECT|Q525|Q11423|1/1048}}
{{comparative measurement|SUBJECT|Q2|Q37221|11}}"""


class TestParagraphCompilation:
    """Test that {{p}} markers produce Z32123(Z32234([...])) clipboard items."""

    def test_single_paragraph_produces_one_item(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        assert len(result) == 1, "Jupiter should compile to exactly 1 clipboard item"

    def test_paragraph_outer_is_z32123(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        value = result[0]["value"]
        assert value["Z7K1"]["Z9K1"] == "Z32123", "Outer function should be Z32123 (paragraph)"

    def test_paragraph_inner_is_z32234(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        inner = result[0]["value"]["Z32123K1"]
        assert inner["Z7K1"]["Z9K1"] == "Z32234", "Inner function should be Z32234 (join text to html)"

    def test_typed_list_structure(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        typed_list = result[0]["value"]["Z32123K1"]["Z32234K1"]
        assert isinstance(typed_list, list)
        assert typed_list[0] == "Z1", "Typed list must start with 'Z1'"

    def test_typed_list_has_five_calls(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        typed_list = result[0]["value"]["Z32123K1"]["Z32234K1"]
        calls = [x for x in typed_list if isinstance(x, dict)]
        assert len(calls) == 5, "Jupiter paragraph should have 5 function calls"

    def test_typed_list_has_separators(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        typed_list = result[0]["value"]["Z32123K1"]["Z32234K1"]
        seps = [x for x in typed_list if isinstance(x, str) and x != "Z1"]
        assert len(seps) == 4, "5 calls need 4 separators between them"
        assert all(s == "  " for s in seps), "Separators should be double spaces"

    def test_inner_calls_are_correct_functions(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        typed_list = result[0]["value"]["Z32123K1"]["Z32234K1"]
        calls = [x for x in typed_list if isinstance(x, dict)]
        func_ids = [c["Z7K1"]["Z9K1"] for c in calls]
        assert func_ids == ["Z26039", "Z27243", "Z26039", "Z32229", "Z32229"]

    def test_clipboard_envelope(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        item = result[0]
        assert item["itemId"] == "Q319.1#1"
        assert item["originKey"] == "Q319.1"
        assert item["originSlotType"] == "Z89"
        assert item["resolvingType"] == "Z89"

    def test_subject_resolved_in_inner_calls(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        typed_list = result[0]["value"]["Z32123K1"]["Z32234K1"]
        first_call = typed_list[1]  # Z26039
        # K1 should be SUBJECT -> Z18(Z825K1)
        assert first_call["Z26039K1"]["Z18K1"]["Z6K1"] == "Z825K1"

    def test_qids_resolved_in_inner_calls(self):
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        typed_list = result[0]["value"]["Z32123K1"]["Z32234K1"]
        first_call = typed_list[1]  # Z26039 with Q634
        assert first_call["Z26039K2"]["Z6091K1"]["Z6K1"] == "Q634"


class TestMultipleParagraphs:
    """Test wikitext with multiple {{p}} markers."""

    def test_two_paragraphs(self):
        template = """{{p}}
{{is a|SUBJECT|Q634}}
{{superlative|SUBJECT|Q12935276|Q634|Q544}}
{{p}}
{{is a|SUBJECT|Q121750}}
{{comparative measurement|SUBJECT|Q525|Q11423|1/1048}}"""
        result = compile_template(template, {"subject": "Q319"})
        assert len(result) == 2, "Two {{p}} markers should produce 2 clipboard items"

    def test_two_paragraphs_both_z32123(self):
        template = """{{p}}
{{is a|SUBJECT|Q634}}
{{p}}
{{is a|SUBJECT|Q121750}}"""
        result = compile_template(template, {"subject": "Q319"})
        assert result[0]["value"]["Z7K1"]["Z9K1"] == "Z32123"
        assert result[1]["value"]["Z7K1"]["Z9K1"] == "Z32123"

    def test_single_sentence_paragraph(self):
        """Even a single sentence with {{p}} gets wrapped as a paragraph."""
        template = """{{p}}
{{is a|SUBJECT|Q634}}"""
        result = compile_template(template, {"subject": "Q319"})
        assert len(result) == 1
        value = result[0]["value"]
        assert value["Z7K1"]["Z9K1"] == "Z32123"
        inner = value["Z32123K1"]
        assert inner["Z7K1"]["Z9K1"] == "Z32234"
        typed_list = inner["Z32234K1"]
        calls = [x for x in typed_list if isinstance(x, dict)]
        assert len(calls) == 1

    def test_paragraph_item_ids_increment(self):
        template = """{{p}}
{{is a|SUBJECT|Q634}}
{{p}}
{{is a|SUBJECT|Q121750}}"""
        result = compile_template(template, {"subject": "Q319"})
        assert result[0]["itemId"] == "Q319.1#1"
        assert result[1]["itemId"] == "Q319.2#1"


class TestImplicitParagraph:
    """Templates without {{p}} markers are grouped into one paragraph."""

    def test_no_p_markers_single_paragraph(self):
        template = """{{Z26039|SUBJECT|Q634}}
{{Z26570|SUBJECT|Q634|Q544}}"""
        result = compile_template(template, {"subject": "Q319"})
        assert len(result) == 1, "Without {{p}}, all templates form one paragraph"

    def test_no_p_markers_wraps_as_paragraph(self):
        template = "{{Z26039|SUBJECT|Q634}}"
        result = compile_template(template, {"subject": "Q319"})
        # Now wraps as Z32123 paragraph, not individually
        assert result[0]["value"]["Z7K1"]["Z9K1"] == "Z32123"

    def test_shrine_template_one_paragraph(self):
        template = """---
title: Shinto Shrine
variables:
  deity: Q-item
---
{{Z26570|SUBJECT|Q845945|Q17}}
{{Z28016|$deity|Q11591100|SUBJECT}}"""
        result = compile_template(template, {"deity": "Q99999", "subject": "Q12345"})
        assert len(result) == 1
        assert result[0]["value"]["Z7K1"]["Z9K1"] == "Z32123"


class TestCompileParagraphDirect:
    """Test the compile_paragraph function directly."""

    def test_compile_paragraph_basic(self):
        frags = parse_template_calls("{{Z26039|SUBJECT|Q634}}\n{{Z26039|SUBJECT|Q121750}}")
        item = compile_paragraph(frags, {}, "Q319", 0)
        assert item["value"]["Z7K1"]["Z9K1"] == "Z32123"

    def test_compile_paragraph_inner_not_wrapped(self):
        """Inner calls should NOT have Z29749/Z27868 wrappers."""
        frags = parse_template_calls("{{Z26039|SUBJECT|Q634}}")
        item = compile_paragraph(frags, {}, "Q319", 0)
        typed_list = item["value"]["Z32123K1"]["Z32234K1"]
        inner_call = typed_list[1]
        # Should be raw Z26039, not wrapped in Z27868
        assert inner_call["Z7K1"]["Z9K1"] == "Z26039"


class TestJupiterRoundTrip:
    """Test the full Jupiter pipeline: wikitext -> compile -> verify structure."""

    def test_jupiter_one_paste(self):
        """Jupiter should need exactly one paste operation."""
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        assert len(result) == 1

    def test_jupiter_matches_real_structure(self):
        """The compiled output should match the Z-object structure from Abstract Wikipedia.

        Real Q319 has: Z32123(Z32234([Z1, Z26039, ' ', Z27243, ' ', Z26039, ' ', Z32229, ' ', Z32229]))
        """
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        typed_list = result[0]["value"]["Z32123K1"]["Z32234K1"]

        # Type marker
        assert typed_list[0] == "Z1"

        # 5 function calls at positions 1, 3, 5, 7, 9
        assert typed_list[1]["Z7K1"]["Z9K1"] == "Z26039"   # is a planet
        assert typed_list[3]["Z7K1"]["Z9K1"] == "Z27243"   # superlative
        assert typed_list[5]["Z7K1"]["Z9K1"] == "Z26039"   # is a gas giant
        assert typed_list[7]["Z7K1"]["Z9K1"] == "Z32229"   # mass comparison
        assert typed_list[9]["Z7K1"]["Z9K1"] == "Z32229"   # diameter comparison

        # Separators at positions 2, 4, 6, 8
        assert typed_list[2] == "  "
        assert typed_list[4] == "  "
        assert typed_list[6] == "  "
        assert typed_list[8] == "  "

    def test_jupiter_z32229_has_quantity_arg(self):
        """Z32229 calls should have the quantity string as K4."""
        result = compile_template(JUPITER_WIKITEXT, {"subject": "Q319"})
        typed_list = result[0]["value"]["Z32123K1"]["Z32234K1"]
        mass_call = typed_list[7]  # first Z32229
        # K4 = quantity = "1/1048" -> Z6 string
        assert mass_call["Z32229K4"]["Z6K1"] == "1/1048"


class TestSectionHeaders:
    """Test ==QID== section header compilation."""

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
        """Section header produces a separate clipboard item."""
        template = """{{Z26039|SUBJECT|Q634}}
==Q131819891==
{{Z26039|SUBJECT|Q515}}"""
        result = compile_template(template, {"subject": "Q319"})
        # paragraph, section header, paragraph = 3 items
        assert len(result) == 3
        assert result[0]["value"]["Z7K1"]["Z9K1"] == "Z32123"
        assert result[1]["value"]["Z7K1"]["Z9K1"] == "Z31465"
        assert result[2]["value"]["Z7K1"]["Z9K1"] == "Z32123"

    def test_section_header_causes_paragraph_break(self):
        """Templates before and after a section header are separate paragraphs."""
        template = """{{Z26039|SUBJECT|Q634}}
{{Z26570|SUBJECT|Q634|Q544}}
==Q1310239==
{{Z26039|SUBJECT|Q515}}"""
        result = compile_template(template, {"subject": "Q319"})
        assert len(result) == 3
        # First paragraph has 2 inner calls
        typed_list = result[0]["value"]["Z32123K1"]["Z32234K1"]
        assert len(typed_list) == 4  # [Z1, call1, "  ", call2]

    def test_p_and_section_header_combined(self):
        """{{p}} and ==QID== can coexist."""
        template = """{{Z26039|SUBJECT|Q634}}
{{p}}
{{Z26039|SUBJECT|Q515}}
==Q131819891==
{{Z26039|SUBJECT|Q544}}"""
        result = compile_template(template, {"subject": "Q319"})
        # para1, para2, header, para3 = 4 items
        assert len(result) == 4
        assert result[0]["value"]["Z7K1"]["Z9K1"] == "Z32123"
        assert result[1]["value"]["Z7K1"]["Z9K1"] == "Z32123"
        assert result[2]["value"]["Z7K1"]["Z9K1"] == "Z31465"
        assert result[3]["value"]["Z7K1"]["Z9K1"] == "Z32123"

    def test_non_qid_heading_gets_natural_number(self):
        """==Parts== gets auto-assigned Q199 (natural number 1)."""
        template = """{{Z26039|SUBJECT|Q634}}
==Parts==
{{Z26039|SUBJECT|Q515}}"""
        result = compile_template(template, {"subject": "Q319"})
        assert len(result) == 3
        header = result[1]["value"]
        assert header["Z7K1"]["Z9K1"] == "Z31465"
        # Should use Q199 (natural number 1)
        z24766 = header["Z31465K1"]["Z10771K1"]
        assert z24766["Z24766K1"]["Z6091K1"]["Z6K1"] == "Q199"

    def test_multiple_non_qid_headings_increment(self):
        """Multiple non-QID headings get Q199, Q200, Q201..."""
        template = """==Parts==
{{Z26039|SUBJECT|Q634}}
==Types==
{{Z26039|SUBJECT|Q515}}
==Questions==
{{Z26039|SUBJECT|Q544}}"""
        result = compile_template(template, {"subject": "Q319"})
        # header, para, header, para, header, para = 6
        assert len(result) == 6
        # Q199, Q200, Q201
        assert result[0]["value"]["Z31465K1"]["Z10771K1"]["Z24766K1"]["Z6091K1"]["Z6K1"] == "Q199"
        assert result[2]["value"]["Z31465K1"]["Z10771K1"]["Z24766K1"]["Z6091K1"]["Z6K1"] == "Q200"
        assert result[4]["value"]["Z31465K1"]["Z10771K1"]["Z24766K1"]["Z6091K1"]["Z6K1"] == "Q201"

    def test_subject_stays_as_subject_throughout_paragraph(self):
        """All SUBJECT mentions stay as Z825K1 arg refs (no pronoun substitution)."""
        template = """{{Z26039|SUBJECT|Q634}}
{{Z26570|SUBJECT|Q634|Q544}}
{{Z28016|SUBJECT|Q66305721|Q87982}}"""
        result = compile_template(template, {"subject": "Q5511"})
        typed_list = result[0]["value"]["Z32123K1"]["Z32234K1"]
        assert typed_list[1]["Z26039K1"]["Z18K1"]["Z6K1"] == "Z825K1"
        assert typed_list[3]["Z26570K1"]["Z18K1"]["Z6K1"] == "Z825K1"
        assert typed_list[5]["Z28016K1"]["Z18K1"]["Z6K1"] == "Z825K1"

    def test_bare_string_in_entity_slot_rejected(self):
        """A literal that is not a QID, $variable, or SUBJECT must
        be rejected at compile time when it appears in an entity slot.
        """
        import pytest
        # role expects entity / Q-item args; "garbage" is none of those
        template = "{{role|Q813858|Q11591100|garbage}}"
        with pytest.raises(ValueError, match="not a valid value for an entity slot"):
            compile_template(template, {"subject": "Q288312"})

    def test_literal_it_resolves_to_subject(self):
        """'it' is an alias for SUBJECT — both compile to a Z825K1 arg ref."""
        template = "{{role|it|Q11591100|Q813858}}"
        result = compile_template(template, {"subject": "Q288312"})
        typed_list = result[0]["value"]["Z32123K1"]["Z32234K1"]
        assert typed_list[1]["Z28016K1"]["Z18K1"]["Z6K1"] == "Z825K1"

    def test_cite_web_url_only(self):
        """{{cite web|URL}} fills in defaults: title=URL, site=domain, date=today, lang=$lang."""
        template = "{{cite web|https://example.com/foo}}"
        result = compile_template(template, {"subject": "Q319"})
        inner = result[0]["value"]["Z32123K1"]["Z32234K1"][1]
        assert inner["Z7K1"]["Z9K1"] == "Z32053"
        assert inner["Z32053K1"]["Z6K1"] == "https://example.com/foo"
        assert inner["Z32053K2"]["Z6K1"] == "https://example.com/foo"
        assert inner["Z32053K3"]["Z6K1"] == "example.com"
        # Date is a Z20420 object
        assert inner["Z32053K4"]["Z1K1"] == "Z20420"
        # Language defaults to $lang
        assert inner["Z32053K5"]["Z18K1"]["Z6K1"] == "Z825K2"

    def test_cite_web_full_args(self):
        """{{cite web|URL|Title|Site|YYYY-MM-DD}} parses date into Z20420."""
        template = "{{cite web|https://en.wikipedia.org/wiki/Foo|Foo|Wikipedia|2026-03-14}}"
        result = compile_template(template, {"subject": "Q319"})
        inner = result[0]["value"]["Z32123K1"]["Z32234K1"][1]
        assert inner["Z32053K1"]["Z6K1"] == "https://en.wikipedia.org/wiki/Foo"
        assert inner["Z32053K2"]["Z6K1"] == "Foo"
        assert inner["Z32053K3"]["Z6K1"] == "Wikipedia"
        # Date: 2026-03-14
        assert inner["Z32053K4"]["Z20420K1"]["Z20159K2"]["Z13518K1"] == "2026"
        assert inner["Z32053K4"]["Z20420K2"]["Z20342K1"]["Z16098K1"] == "Z16103"  # March
        assert inner["Z32053K4"]["Z20420K2"]["Z20342K2"]["Z13518K1"] == "14"

    def test_mixed_qid_and_non_qid_headings(self):
        """QID headings use the QID; non-QID headings auto-number independently."""
        template = """==Q131819891==
{{Z26039|SUBJECT|Q634}}
==Parts==
{{Z26039|SUBJECT|Q515}}"""
        result = compile_template(template, {"subject": "Q319"})
        assert len(result) == 4
        # First header uses actual QID
        assert result[0]["value"]["Z31465K1"]["Z10771K1"]["Z24766K1"]["Z6091K1"]["Z6K1"] == "Q131819891"
        # Second header gets Q199 (first non-QID = 1)
        assert result[2]["value"]["Z31465K1"]["Z10771K1"]["Z24766K1"]["Z6091K1"]["Z6K1"] == "Q199"
