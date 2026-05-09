"""Tests for the AWE-mention auto-stop rule in fetch_discussions.

The rule: once a saved snapshot's body no longer references the
Abstract Wikipedia Editor (by name or by the "AWE" acronym), we
stop syncing that page. The check is on the local snapshot file —
not the live wiki — so it's an idempotent decision based on what
we last persisted.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetch_discussions import mentions_awe, should_skip


class TestMentionsAwe:
    def test_phrase_full_case(self):
        assert mentions_awe("see Abstract Wikipedia Editor for details")

    def test_phrase_lowercase(self):
        assert mentions_awe("the abstract wikipedia editor is a tool")

    def test_acronym_whole_word(self):
        assert mentions_awe("AWE generated this article")

    def test_acronym_inside_quotes(self):
        # The wiki uses "AWE" in scare quotes too (see project chat)
        assert mentions_awe('the "AWE" tool')

    def test_acronym_does_not_match_aware(self):
        assert not mentions_awe("I am aware of the issue")

    def test_acronym_does_not_match_award(self):
        assert not mentions_awe("they won an award")

    def test_lowercase_awe_does_not_match(self):
        # The acronym is uppercase on-wiki; lowercase "awe" is just
        # the noun and would mass-flag false positives.
        assert not mentions_awe("the magnitude inspired awe")

    def test_phrase_in_link(self):
        assert mentions_awe("[[User:Immanuelle/Abstract Wikipedia Editor]]")

    def test_empty_body(self):
        assert not mentions_awe("")

    def test_unrelated_content(self):
        assert not mentions_awe(
            "Wikidata problems\nThe latest status update lists "
            "the most used fragments."
        )


class TestShouldSkip:
    def test_missing_file_does_not_skip(self):
        with tempfile.TemporaryDirectory() as d:
            skip, _ = should_skip(os.path.join(d, "nope.wikitext"))
            assert not skip

    def test_existing_with_awe_does_not_skip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.wikitext")
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    "<!-- header -->\n"
                    "Some discussion mentioning AWE behaviour.\n"
                )
            skip, _ = should_skip(path)
            assert not skip

    def test_existing_without_awe_skips(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.wikitext")
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    "<!--\n  Snapshot of foo\n-->\n"
                    "Just unrelated talk page content.\n"
                )
            skip, reason = should_skip(path)
            assert skip
            assert "AWE" in reason or "awe" in reason.lower()

    def test_header_only_match_does_not_count_as_mention(self):
        """The provenance header always references our repo URL, which
        contains 'AbstractWikipediaEditor' as a path component. Make
        sure should_skip strips that header before checking, otherwise
        every page would be considered active forever."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.wikitext")
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    "<!--\n"
                    "  Snapshot of https://example.org/wiki/AbstractWikipediaEditor\n"
                    "-->\n"
                    "Just unrelated content with no editor mention.\n"
                )
            skip, _ = should_skip(path)
            assert skip, "header URL alone shouldn't keep a page alive"
