# AbstractTestBot Roadmap

## Completed

- [x] Shrine article creation via Playwright clipboard injection (`create_rich_onepass.py`)
- [x] Location fragment using Z26570 (State location using entity and class)
- [x] Deity fragment using Z28016 (defining role sentence)
- [x] Three-fragment articles with admin territory (`create_rich_threepass.py`)
- [x] Full Wikifunctions catalog (3,911 functions, 71 types)
- [x] Curated shortlist of promising functions for article building
- [x] Wiki text template parser (`wikitext_parser.py`)
- [x] Complete Wikidata properties catalog (13,347 properties)
- [x] Property-to-function mapping (18 common properties mapped)
- [x] Auto-generate wikitext from any Wikidata item (`generate_wikitext.py`)

## In Progress

- [ ] **General article pipeline**: Take any Wikidata QID, auto-generate wikitext from
  its properties, compile to clipboard JSON, and create the Abstract Wikipedia article.
  - `generate_wikitext.py` fetches item properties and produces wikitext
  - `wikitext_parser.py` compiles wikitext to clipboard JSON
  - Playwright injects and publishes
- [ ] **Function aliases**: English name aliases for Z-functions so templates can use
  human-readable names like `{{location | $subject | Q515 | Q17}}` instead of Z-IDs
- [ ] **Chrome extension**: Package the template parser + clipboard injection as a
  browser extension anyone can use to create Abstract Wikipedia pages

## Long-Term Vision

The end goal is a system where:
1. A user writes a simple markdown/wikitext file describing an article
2. The system auto-maps Wikidata properties to Wikifunctions
3. Templates use human-readable function aliases
4. Articles are created on Abstract Wikipedia with one command
5. Any domain with Wikidata coverage can have articles generated automatically

## Next Steps

- [ ] Test pipeline on 10 random Wikidata items of different types
- [ ] Expand property-to-function mapping as more functions are tested
- [ ] Explore ArticlePlaceholder functions (Z29822, Z29786) as shortcuts
