# Abstract Wikipedia Editor Roadmap

## Completed (2026-05-08 batch)

- [x] Built distributable `.exe` installer via electron-builder (`editor/dist/Abstract Wikipedia Editor Setup 1.0.0.exe`). Required moving `electron` from `dependencies` to `devDependencies` and adding an `author` field to `editor/package.json`.
- [x] Switched paragraph emission from `Z32123(Z32234([..., '  ', ...]))` to `Z33068([sentences], $lang)` — Theki/rae diagnosed the prior failure on the Project chat (May 4 2026) as a missing `K2` (language) argument. `convert_article.py` and `build_pages.py` still decode the legacy shape so already-published articles round-trip cleanly.
- [x] Added P50 (author), P57 (director), P112 (founded by) to the property mapping. Verified each role QID against the Wikidata API — Q4479442 is "founder" (Q3736439 looks similar but is "duck", which is the kind of mistake CLAUDE.md's CRITICAL rule warns against).
- [x] Investigated `Z29822` (ArticlePlaceholder render article) and `Z30106` (ArticlePlaceholder format String). `Z29822` is the right shape for an "auto-article from QID" shortcut but currently has no connected implementations, so it cannot be wired up until someone connects one. `Z30106` is a small formatting primitive, not useful as an article shortcut.

## Completed

- [x] Shrine article creation via Playwright clipboard injection
- [x] Location fragment using Z26570 (State location using entity and class)
- [x] Deity fragment using Z28016 (defining role sentence)
- [x] Full Wikifunctions catalog (3,911 functions, 71 types)
- [x] Curated shortlist of promising functions for article building
- [x] Wikitext template parser (`wikitext_parser.py`)
- [x] Complete Wikidata properties catalog (13,347 properties)
- [x] Property-to-function mapping (17 properties mapped)
- [x] Auto-generate wikitext from any Wikidata item (`generate_wikitext.py`)
- [x] General article pipeline: QID -> wikitext -> clipboard -> publish
- [x] Function aliases (human-readable names in templates)
- [x] Electron desktop editor with live preview
- [x] Edit existing articles (`edit_from_qid.py`)
- [x] Convert existing Abstract Wikipedia articles back to wikitext (`convert_article.py`)
- [x] Fix wrong hardcoded QIDs in property mapping
- [x] Fix property collision/dedup (location priority, P31 vs P106, inverse pairs)
- [x] Project website with live renderer (same as Electron app)
- [x] Website landing page with download link
- [x] Edit summaries linking to editor user page
- [x] Named 38 undocumented top-level functions from article scan
- [x] Skip P138 (named after) — always bad
- [x] Migrated P279 mapping from Z26095 to Z26039 to avoid "A X is a Y" misrenders on instance-shaped items (see `data/property_function_mapping.json`). Note: GrounderUK on the WF Project chat argues Z26095 is the semantically correct function for P279; revisit if that becomes consensus.
- [x] Migrated dedicated-to / shrine-rank / citizenship / etc. from Z26955 (deprecated) to Z28016 (defining role sentence) per ChaoticVermillion's note on User_talk:Immanuelle.
- [x] Track Wikifunctions Project chat in `discussions/` so feedback there flows into this repo.
- [x] Local preview "a" vs "an" article selection (mirrors Z21739 on Wikifunctions; raised by QuickQuokka on the WF Project chat).

## Known Issues

- [ ] Edit all previously published articles to fix errors from old wrong QIDs (in progress; tracked alongside the Z26955→Z28016 and "it"→SUBJECT cleanups already done on-wiki).

## In Progress

(none)

## Next Steps

- [ ] Test pipeline on diverse Wikidata items (people, places, organizations, concepts)
- [ ] Expand property-to-function mapping further (P19, P20, P569, P570 — these need a "born sentence"-style multi-property bundle, which the current 1:1 mapping shape does not support)
- [ ] Re-watch `Z29822` ("ArticlePlaceholder render article") for an implementation; it has the right input shape (`language, item, include_no_best_statements`) for a one-click article shortcut, but has no implementations connected as of 2026-05-08
