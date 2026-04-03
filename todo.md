# AbstractTestBot Roadmap

## Completed

- [x] Shrine article creation via Playwright clipboard injection (`create_rich_onepass.py`)
- [x] Location fragment using Z26570 (State location using entity and class)
- [x] Deity fragment using Z28016 (defining role sentence)
- [x] Full Wikifunctions catalog (3,911 functions, 71 types)
- [x] Curated shortlist of promising functions for article building

## In Progress

- [ ] **Markdown-to-article system**: Build a system that translates a simple markdown file
  into Abstract Wikipedia article content using Wikifunctions Z-objects.
  - The markdown would describe an article in human-readable terms
  - The system converts each section/sentence into the appropriate nested Z-object JSON
  - Fragments are injected into the editor clipboard and published via Playwright
  - This decouples "what the article says" from the complex Z-object nesting format

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
