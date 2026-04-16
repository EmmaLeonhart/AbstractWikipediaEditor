# Abstract Wikipedia Editor

## Project Description
Desktop editor for creating articles on Abstract Wikipedia. The main product is an Electron app (`editor/`) that provides a wikitext editor with live preview, login screen, and publish-to-wiki capability. Python scripts exist for batch operations and debugging.

The app queries Wikidata for item properties, maps them to Wikifunctions sentence generators, compiles to clipboard JSON, and publishes via Playwright browser automation. The API doesn't support creating `abstractwiki` content (bot passwords lack `wikilambda-abstract-create` rights).

### Batch Scripts (Local Execution)
- `create_from_qid.py` -- Create new articles via Playwright (run locally, NOT via GitHub Actions)
- `edit_from_qid.py` -- Edit existing articles via Playwright (run locally)
- These scripts use `--apply` to actually execute, `--headed` to show the browser
- Authentication uses `.env` credentials and runs through the browser login flow
- Screenshots saved to `screenshots/` directory

### Paragraph Model and Section Headers (`==QID==`)
Every `{{...}}` call becomes its own paragraph (its own Z32123(Z32234([Z1, call])) clipboard item). There is no `{{p}}` wikitext marker — explicit paragraph control was dropped because bundling multiple function calls into one Z32234 list caused recursive evaluator errors that hurt debugging, and every function already gets its own paragraph wrapper for accessibility.

Stray `{{p}}` tokens in legacy content are silently dropped by the parser (`compile_template`), the editor preview, and the site renderer. Don't emit `{{p}}` in new content.

Section headers use wiki-style `==QID==` syntax, where the QID references a Wikidata item. They compile to Z31465(Z10771(Z24766(QID, $lang))) and still act as implicit paragraph boundaries. `==anything non-QID==` auto-assigns natural-number QIDs starting at Q199.

- `generate_wikitext.py` outputs one template call per line, no `{{p}}`
- `convert_article.py` / `build_pages.py` emit one line per wiki fragment, no `{{p}}`

## Workflow Rules
- **Commit early and often.** Every meaningful change gets a commit with a clear message explaining *why*, not just what.
- **Do not enter planning-only modes.** All thinking must produce files and commits.
- **Keep this file up to date.** As the project takes shape, record architectural decisions, conventions, and anything needed to work effectively in this repo.
- **Update README.md regularly.** It should always reflect the current state of the project.

## Testing
- **Write unit tests early.** Use `pytest` for Python.
- **Keep tests passing.** Do not commit code that breaks existing tests.
- CI runs via `.github/workflows/ci.yml`.

## Directory Structure

| Path | Purpose |
|------|---------|
| `editor/` | Electron desktop app (main product) -- TypeScript, builds with `npm run build` |
| `data/` | Property mappings (`property_function_mapping.json`), function aliases, generated templates |
| `site/` | Project website -- `index.md` and `renderer.js` committed, `pages/` and `catalog.md` generated |
| `*.py` | CLI scripts for batch operations and debugging (not the main product) |
| `tests/` | Unit tests |
| `credentials/` | Passwords and secrets (**gitignored, never committed**) |

## Critical Rules
- **NEVER hardcode Wikidata QIDs without explicitly asking the user first.** Every QID must be verified against the Wikidata API before use. Wrong QIDs have been silently embedded in mappings before (e.g. Q1093829 "city in the United States" instead of Q42138 "citizenship", Q787 "pig" instead of Q23492 "official language").

## Architecture

### Electron Editor (`editor/`)
- `src/main.ts` -- Main process. Handles IPC for Wikidata fetching, article checking, credential management (.env read/write), and calling Python scripts via `execFile`.
- `src/renderer.ts` -- Renderer process. Parses wikitext templates, fetches Wikidata labels for QID arguments, and renders a line-aligned preview where each sentence is built from a small per-function template (e.g. `Z26039` → `"${a[0]} is a ${a[1]}."`). See [Live Preview Rendering](#live-preview-rendering). Also handles the login overlay UI. This logic is also mirrored in `site/renderer.js` for the project website.
- `src/preload.ts` -- Context bridge exposing `window.api` to renderer.
- `index.html` -- Editor UI with login button, QID input, preview pane, wikitext textarea, and login overlay.
- The login button opens an overlay where users enter their Wikimedia credentials. Credentials are saved to `.env` in the project root.
- Python path is hardcoded to `C:/Users/Immanuelle/AppData/Local/Programs/Python/Python313/python.exe`.
- `npm run dist` builds a Windows .exe installer via electron-builder.

### Live Preview Rendering
The preview pane shows a line-aligned rendering of the editor's wikitext. Each template line (`{{is a|SUBJECT|Q146}}`) is parsed locally in TypeScript, each QID is resolved to its English Wikidata label (via `window.api.fetchLabels`, which hits `wbgetentities` in batches of 50), and the sentence is built from a small hand-rolled per-function template in `renderSentence()` — `Z26039` ("is a") emits `"${subject} is a ${class}."`, `Z26570` ("location") emits `"${subject} is a ${class} in ${place}."`, and so on. SUBJECT is replaced with the current page's QID label, `$lang` renders as a visible placeholder, and each QID becomes a clickable link to `wikidata.org/wiki/${qid}`.

This is an approximation of what Wikifunctions actually produces — fast, offline-ish, and visually familiar, but it doesn't pick up upstream function changes and new function templates have to be added to `renderSentence()`'s switch statement by hand.

There is also experimental infrastructure (`render_wikitext.py` + the `render-wikitext` IPC + `window.api.renderWikitext`) that routes lines through the real Wikifunctions evaluator via `wikifunctions.call()`. It is **not** wired into the live preview because the evaluator-based path produced wrong output for several function shapes — the manual `Z825K1/K2` + `Q6091500` substitution doesn't match what `Z825` (the real article renderer) does internally, so `spo` dropped its predicate, `it` substitution fought with pronoun agreement, and so on. The plumbing is left in place so a future attempt can start from working infrastructure instead of nothing; to re-enable it, replace the body of `renderPreview()` in `src/renderer.ts` with a call to `window.api.renderWikitext(currentQid, lines)` and handle the returned per-line results.

**Caching.** TypeScript caches results in a `{"${subject}::${trimmed_line}": RenderLineResult}` dict, so editing one line in a 20-line article only renders that one line. A monotonic `renderSeq` counter lets newer renders cancel older ones if the user keeps typing — no stale output overwrites fresh output.

**Not routed through the evaluator.** Section headers (`==QID==`) are still rendered locally as `<h2>{wikidata_label}</h2>` because the Z31465 function's output is effectively just a label lookup — round-tripping through the API would be pure latency. Paragraph breaks (`{{p}}`) and blank lines are also handled in TypeScript.

### `wikifunctions` PyPI library (Feeglgeef)
**Optional dependency** — installed with `pip install wikifunctions`. Imported only by `render_wikitext.py`, which is currently unused by the editor (the live preview went back to Wikidata-label-based rendering because the evaluator-based path produced wrong output). See `https://pypi.org/project/wikifunctions/`.

**What it is:** a thin Python wrapper around the Wikifunctions function-evaluation API, plus builders for Z-object types (`ZFunctionCall`, `ZReference`, `ZMonolingualText`, `ZNaturalNumber`, `ZWikidataItemReference`, etc.). Internally `wf.call(zid, *args)` builds `{"Z1K1":"Z7","Z7K1":zid,"{zid}K{i}":arg_i}` and POSTs to `/w/api.php?action=wikifunctions_run`, returning the parsed `Z22` result. Each arg can be any Python value including a fully-built nested Z-object dict — the server handles evaluation.

**What it can do in this project:**
- **Evaluate individual Wikifunctions calls by ZID.** Useful for validating simple function calls in tests: compile a known wikitext snippet, send the resulting Z-object to `wf.call()`, check the returned Z22. Works well for leaf functions (e.g. a `Z26039` "is a" call with two concrete QIDs and a concrete language).
- **Future test suite.** A `pytest` file could compile known templates and assert rendering matches expected English. A bare string in an entity slot fails the evaluator's type check immediately, and we now reject those at compile time.

**What it can *not* do:**
- **Render a full Abstract Wikipedia article the way the wiki does.** Abstract Wikipedia articles are rendered by wrapping everything in `Z825` (the article renderer) which binds `Z825K1` = subject, `Z825K2` = language, and handles pronoun substitution, error recovery, and paragraph assembly. Calling the inner function calls directly (which is what `render_wikitext.py` does, bypassing `Z825`) produces noticeably wrong output for non-trivial shapes — `spo` drops its predicate, `it` substitution doesn't match what `Z825` does internally, etc. A correct end-to-end evaluator-based preview would have to call `Z825` itself, and that's what `render_wikitext.py`'s simulation approach got wrong.
- **Publish / edit articles.** Read-only. All writes to Abstract Wikipedia still go through Playwright browser automation because the MediaWiki API rejects bot-password edits to the `Page` namespace with `protectednamespace`.
- **Fetch articles by QID from Abstract Wikipedia.** It only talks to the function evaluator, not the article store. Pulling an article's JSON still uses a direct MediaWiki `action=query` call (see `convert_article.py` and `check-article` in `main.ts`).
- **Parse or serialize our wikitext.** No overlap with `wikitext_parser.py` or `convert_article.py`; those stay.

**What it can *not* do:**
- **Publish / edit articles.** The library is read-only. All writes to Abstract Wikipedia (`create_from_qid.py`, `edit_from_qid.py`, the editor's push button) still go through Playwright browser automation, because the MediaWiki API rejects bot-password edits to the `Page` namespace with `protectednamespace`. `wikifunctions` doesn't even attempt writes.
- **Fetch articles by QID from Abstract Wikipedia.** It only talks to the function evaluator, not the article store. Pulling an article's JSON still uses a direct MediaWiki `action=query` call (see `convert_article.py` and `check-article` in `main.ts`).
- **Parse or serialize our wikitext.** No overlap with `wikitext_parser.py` or `convert_article.py`; those stay.
- **Replace `wikitext_parser.z7_call` / `z6091` / `z20420_date` / etc.** The library has equivalent builders, but swapping ours out would only be worth it if the byte-for-byte output matches what the wiki expects on save. Untested. Not a priority.

**Standalone-evaluator gotcha:** Any `Z18` reference to `Z825K1` or `Z825K2` (our `SUBJECT` / `$lang` placeholders) must be substituted to a concrete value before sending to `wikifunctions_run`, because `Z825` is the outer article-renderer function and its arguments don't exist outside that scope. `render_wikitext.py`'s `_substitute_local_args` does this.

### Property Mapping (`data/property_function_mapping.json`)
Maps Wikidata properties to Wikifunctions sentence generators. Key dedup rules:
- **Location**: P131 > P17 > P30 (most specific wins, only one used)
- **P31 vs P106**: P31 skipped when P106 (occupation) exists
- **P36 vs P1376**: P1376 skipped when P36 exists (inverse pair)

The mapping is used by `generate_wikitext.py` (Python) and the Electron editor (via Python).

### Website (`site/`)
- `index.md` -- Landing page (committed to git)
- `renderer.js` -- Client-side renderer ported from `editor/src/renderer.ts`. Uses the same Wikidata-label-based rendering path the editor uses.
- `pages/` and `catalog.md` -- Generated by `build_pages.py` (gitignored)
- Article pages are HTML that load `renderer.js` to render wikitext live with Wikidata labels
- Built and deployed by `.github/workflows/pages.yml`

### Authentication
- Main account credentials required (bot passwords cannot create articles)
- Stored in `.env` as `WIKI_MAIN_PASSWORD` (created via the Electron app's login screen)
- VPN usage triggers email verification (not 2FA) -- this is why CI-based creation is disabled
- Without VPN, login works directly

### Key Launcher
- `runeditor.bat` -- Launches the Electron editor
