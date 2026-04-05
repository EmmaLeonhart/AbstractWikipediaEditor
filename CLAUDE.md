# AbstractTestBot

## Workflow Rules
- **Commit early and often.** Every meaningful change gets a commit with a clear message explaining *why*, not just what.
- **Do not enter planning-only modes.** All thinking must produce files and commits. If scope is unclear, create a `planning/` directory and write `.md` files there instead of using an internal planning mode.
- **Keep this file up to date.** As the project takes shape, record architectural decisions, conventions, and anything needed to work effectively in this repo.
- **Update README.md regularly.** It should always reflect the current state of the project for human readers.

## Testing
- **Write unit tests early.** As soon as there is testable logic, create a test file. Use `pytest` for Python projects or the appropriate test framework for the language in use.
- **Set up CI as soon as tests exist.** Create a `.github/workflows/ci.yml` GitHub Actions workflow that runs the test suite on push and pull request. Keep the workflow simple — install dependencies and run tests.
- **Keep tests passing.** Do not commit code that breaks existing tests. If a change requires updating tests, update them in the same commit.

## Project Description
Bot that creates Shinto shrine articles on Abstract Wikipedia using Playwright browser automation. The API doesn't support creating `abstractwiki` content (bot passwords lack `wikilambda-abstract-create` rights), so we automate the visual editor's copy-paste workflow instead.

## Directory Structure
Keep the repo organized as follows. **Only runtime scripts belong in root.** Everything else goes in subdirectories.

| Directory | Contents |
|-----------|----------|
| `/` (root) | Runtime scripts (`create_from_qid.py`, `edit_from_qid.py`), launchers, config, docs |
| `data/` | Generated data files, cached JSON, HTML artifacts |
| `screenshots/` | Debug and documentation screenshots |
| `credentials/` | Passwords and secrets (**gitignored, never committed**) |

## Critical Rules
- **NEVER hardcode Wikidata QIDs without explicitly asking the user first.** Every QID must be verified against the Wikidata API before use. Wrong QIDs (e.g. Q15292583 "Sonardi" instead of "part of", Q787 "pig" instead of "official language") were silently embedded in mappings and propagated into published articles, causing real damage.

## Architecture and Conventions
- **`create_from_qid.py`** is the main creation script. Takes any QID, generates wikitext from Wikidata properties, compiles to clipboard JSON, and publishes via Playwright browser automation.
- **`edit_from_qid.py`** edits existing articles by removing old fragments and pasting fresh ones.
- **`generate_wikitext.py`** maps Wikidata properties to Wikifunctions templates.
- **`wikitext_parser.py`** compiles wikitext templates to Abstract Wikipedia clipboard JSON.
- Main account credentials are required (bot passwords cannot create articles). Stored in `.env` as `WIKI_MAIN_PASSWORD`.
- See `DOCUMENTATION.md` for extensive notes on all the API dead ends and workarounds.
- No edit summary is added when publishing articles.
