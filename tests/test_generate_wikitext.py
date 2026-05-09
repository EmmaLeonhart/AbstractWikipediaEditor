"""Tests for generate_wikitext.py — specifically the bundling rule
that all auto-generated sentences land in a single paragraph.

The trigger: JJP's three points on User_talk:Immanuelle (2026-04-28)
— "Don't have separate paragraphs for each sentence" — and the
follow-up Project chat threads (Theki, 2026-05-02 / 2026-05-04) that
diagnosed Q100 etc. as the same one-paragraph-per-sentence problem.
The compile path was already correct (Z33068 with K2 lang); the
generator was the side that kept inserting blank lines.
"""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_wikitext as gw
from wikitext_parser import compile_template


# A minimal Wikidata payload covering several claim types the generator
# normally emits as separate "is a" / location / occupation sentences.
# The shape mirrors what wbgetentities returns; only the fields the
# generator actually reads are populated.
def _claim(prop, qid):
    return {
        "mainsnak": {
            "snaktype": "value",
            "datavalue": {"type": "wikibase-entityid", "value": {"id": qid}},
        },
        "references": [],
    }


SAMPLE_ENTITY = {
    "labels": {"en": {"value": "Sample"}},
    "descriptions": {"en": {"value": "A sample item"}},
    "claims": {
        # P31 (instance of) -> Z26039 "is a"
        "P31": [_claim("P31", "Q634")],
        # P17 (country) -> location sentence
        "P17": [_claim("P17", "Q30")],
        # Another P31 to ensure multiple "is a" stay bundled
        # (intentionally not Q5 so the human-skip rule doesn't apply)
    },
}


def _generate(entity):
    with patch.object(gw, "fetch_item_data", return_value=entity):
        wikitext, used_props, label = gw.generate_wikitext("Q12345")
    return wikitext


def _body(wikitext):
    """Strip the YAML frontmatter so we can count blank lines between
    fragments without the frontmatter's own blank line confusing us."""
    parts = wikitext.split("---\n", 2)
    return parts[2] if len(parts) >= 3 else wikitext


class TestSingleParagraphBundling:
    """Auto-generated wikitext must put every sentence in one paragraph
    so the compile step produces a single Z33068 fragment per article,
    not one Z33068-of-one-sentence per claim."""

    def test_no_blank_line_between_sentences(self):
        body = _body(_generate(SAMPLE_ENTITY))
        # Trim trailing newline
        body = body.rstrip("\n")
        # Body should be N non-empty fragment lines, no blank line
        # separators between them.
        lines = body.split("\n")
        # Drop any leading blank line from the frontmatter terminator.
        while lines and not lines[0].strip():
            lines.pop(0)
        assert all(line.strip() for line in lines), (
            f"expected no blank lines between sentences, got: {lines!r}"
        )
        # Sanity: at least two non-empty lines were emitted (multiple
        # claims), so we're actually testing the bundling case.
        assert len(lines) >= 2

    def test_compiles_to_one_z33068(self):
        """End-to-end: generator output -> compile_template -> 1 fragment."""
        wikitext = _generate(SAMPLE_ENTITY)
        # Strip frontmatter for compile_template (it ignores it but
        # the body is what matters).
        result = compile_template(wikitext, {"subject": "Q12345"})
        assert len(result) == 1, (
            "all auto-emitted sentences should bundle into one Z33068 — "
            f"got {len(result)} fragments"
        )
        assert result[0]["value"]["Z7K1"]["Z9K1"] == "Z33068"

    def test_empty_claims_emits_no_paragraph(self):
        """An entity with no mappable claims should not emit an empty
        paragraph (the initial [[]] sentinel must be skipped)."""
        empty_entity = {
            "labels": {"en": {"value": "Empty"}},
            "descriptions": {"en": {"value": ""}},
            "claims": {},
        }
        body = _body(_generate(empty_entity)).strip()
        assert body == "", f"expected empty body, got: {body!r}"
