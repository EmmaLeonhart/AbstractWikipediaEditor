# AbstractTestBot Roadmap

## Completed

- [x] Shrine article creation via Playwright clipboard injection (`create_rich_onepass.py`)
- [x] Location fragment using Z26570 (State location using entity and class)
- [x] Deity fragment using Z28016 (defining role sentence)
- [x] Full Wikifunctions catalog (3,911 functions, 71 types)
- [x] Curated shortlist of promising functions for article building

## In Progress

- [x] **Wiki text template parser** (`wikitext_parser.py`): MediaWiki-inspired template syntax
  that converts human-readable `{{Z26570 | $subject | Q845945 | Q17}}` into clipboard JSON.
  - 13 sentence generators in the function registry
  - Auto-wrapping (Z11 -> Z29749, Z6 -> Z27868, Z89 -> passthrough)
  - YAML frontmatter for metadata and variable declarations
  - Example templates: shrine, city, mountain in `data/templates/`
  - 48 unit tests in `tests/test_wikitext_parser.py`
- [ ] **Chrome extension**: Package the template parser + clipboard injection as a
  browser extension anyone can use to create Abstract Wikipedia pages

## Next Steps

- [ ] Experiment with additional sentence functions from the shortlist:
  - Z26039 (article-less instantiating fragment): "Nairobi is a city."
  - Z26095 (article-ful instantiating fragment): "An antelope is a mammal."
  - Z29591 (describing entity with adjective/class): "Venus is a rocky planet."
  - Z27243 (superlative definition): "Mount Everest is the tallest mountain in Asia."
  - Z29822 (ArticlePlaceholder render article): full auto-generated article from QID
- [ ] Test which functions actually have working implementations (many show 0 implementations in API but may work)
- [ ] Explore ArticlePlaceholder functions (Z29822, Z29786) as a potential shortcut for generating full articles
- [ ] Expand beyond shrines: use the markdown system for other article types (cities, people, albums, etc.)
