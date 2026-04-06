# Abstract Wikipedia Editor Roadmap

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

## Known Issues

- [ ] **P279 (subclass of) → Z26095 is almost always wrong.** Z26095 produces "A X is a Y" which is only correct for class-to-class relationships (e.g. "An antelope is a mammal"). But P279 gets applied to all kinds of items where this phrasing is nonsensical. Need to either skip P279 entirely or add strict filtering to only use it when the item is genuinely a class/type, not an instance.
- [ ] Edit all previously published articles to fix errors from old wrong QIDs

## In Progress

- [ ] Build distributable .exe installer via electron-builder

## Next Steps

- [ ] Test pipeline on diverse Wikidata items (people, places, organizations, concepts)
- [ ] Expand property-to-function mapping as more functions are tested
- [ ] Explore ArticlePlaceholder functions (Z29822, Z29786) as shortcuts
