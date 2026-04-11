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

### Paragraph Model (`{{p}}`) and Section Headers (`==QID==`)
All templates are implicitly within one paragraph. A `{{p}}` midway starts a new paragraph.
Each paragraph compiles into a single Z32123(Z32234([...])) clipboard item (one paste per paragraph).

Section headers use wiki-style `==QID==` syntax, where the QID references a Wikidata item.
They compile to Z31465(Z10771(Z24766(QID, $lang))) and cause implicit paragraph breaks.

- `generate_wikitext.py` outputs templates without any initial `{{p}}`
- `convert_article.py` handles Z31465 section titles as `==QID==`
- `{{p}}` is only used between paragraphs, never at the start

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
- `src/renderer.ts` -- Renderer process. Parses wikitext line-by-line and shows a live preview where each template is rendered by the **real Wikifunctions evaluator** (see [Live Preview Rendering](#live-preview-rendering) below), with per-line caching keyed by `(subject, line)`. Also handles the login overlay UI.
- `src/preload.ts` -- Context bridge exposing `window.api` to renderer.
- `index.html` -- Editor UI with login button, QID input, preview pane, wikitext textarea, and login overlay.
- The login button opens an overlay where users enter their Wikimedia credentials. Credentials are saved to `.env` in the project root.
- Python path is hardcoded to `C:/Users/Immanuelle/AppData/Local/Programs/Python/Python313/python.exe`.
- `npm run dist` builds a Windows .exe installer via electron-builder.

### Live Preview Rendering
The editor's live preview pane shows what each sentence **actually** renders to, by calling the real Wikifunctions evaluator — not a hand-rolled approximation. This means the preview matches publication exactly and automatically picks up upstream function changes.

**Pipeline** (`render_wikitext.py` invoked from `main.ts`'s `render-wikitext` IPC):
1. For each template line, run `wikitext_parser.compile_template(line, {"subject": qid})` to get the same Z-object the editor would paste on push.
2. Walk the tree and substitute the two local-argument references the Abstract Wikipedia renderer normally fills in at publish time:
   - `Z18(Z825K1)` → `Z6091(<subject qid>)` — this is `SUBJECT`
   - `Z18(Z825K2)` → `Z9(Z1002)` — this is `$lang`, fixed to English for the preview
   Without these substitutions, the standalone evaluator returns a `Z5` error because those slots only exist inside the outer renderer's scope.
3. POST the patched object to `https://www.wikifunctions.org/w/api.php?action=wikifunctions_run` with the Z-object as `function_call`.
4. Parse the `Z22` response and extract `Z22K1.Z89K1` — the rendered HTML fragment.
5. Strip the outer `<p>...</p>` wrapper that `Z32123` adds (the preview uses a line-aligned gutter, not block paragraphs).

**Caching.** TypeScript caches results in a `{"${subject}::${trimmed_line}": RenderLineResult}` dict, so editing one line in a 20-line article only renders that one line. A monotonic `renderSeq` counter lets newer renders cancel older ones if the user keeps typing — no stale output overwrites fresh output.

**Not routed through the evaluator.** Section headers (`==QID==`) are still rendered locally as `<h2>{wikidata_label}</h2>` because the Z31465 function's output is effectively just a label lookup — round-tripping through the API would be pure latency. Paragraph breaks (`{{p}}`) and blank lines are also handled in TypeScript.

### `wikifunctions` PyPI library (Feeglgeef)
Installed via `pip install wikifunctions`. See `https://pypi.org/project/wikifunctions/`.

**What it is:** a thin Python wrapper around the Wikifunctions function-evaluation API, plus builders for Z-object types (`ZFunctionCall`, `ZReference`, `ZMonolingualText`, `ZNaturalNumber`, `ZWikidataItemReference`, etc.). Internally `wf.call(zid, *args)` builds `{"Z1K1":"Z7","Z7K1":zid,"{zid}K{i}":arg_i}` and POSTs to `/w/api.php?action=wikifunctions_run`, returning the parsed `Z22` result. Each arg can be any Python value including a fully-built nested Z-object dict — the server handles evaluation.

**What it can do in this project:**
- **Render Z-objects by calling the real evaluator.** This is how the editor's live preview works (see above). We bypass the `wf.call(zid, *args)` helper and POST our pre-built Z-objects directly, because our `compile_template` already produces Z-objects with the correct `{zid}K{n}` arg keys and no intermediate wrapper helps.
- **Validate compiler output in tests.** Future work: a `pytest` suite can compile a known wikitext snippet, send it to the evaluator, and assert the English comes back matching. The `"it"` pronoun bug that corrupted 61 articles would have been caught by one such test — a bare string in an entity slot fails the evaluator's type check immediately.

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
- `renderer.js` -- Client-side renderer **originally** ported from `editor/src/renderer.ts`. Currently still uses the hand-rolled switch-statement rendering; **out of sync** with the editor, which now uses the real Wikifunctions evaluator. Future work: either call `wikifunctions_run` directly from the browser (the API allows CORS with `origin=*`), or accept the divergence and document it here.
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
