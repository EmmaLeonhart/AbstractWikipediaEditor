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

## Architecture and Conventions
- **`create_rich_onepass.py`** is the main working script. It uses Playwright to automate the Abstract Wikipedia visual editor via direct clipboard injection.
- **`runcreate.bat`** is a quick launcher that creates 10 shrines in headed mode.
- **`create_shrine_articles.py`** is the API-based approach that doesn't work due to permission issues. Kept for reference.
- The bot queries Wikidata for shrines with deities, checks which already have Abstract Wikipedia articles, then injects both location and deity fragments into the editor clipboard and publishes in a single pass.
- Main account credentials are required (bot passwords cannot create articles). Stored in `.env` as `WIKI_MAIN_PASSWORD`.
- See `DOCUMENTATION.md` for extensive notes on all the API dead ends and workarounds.
- No edit summary is added when publishing articles.

# currentDate
Today's date is 2026-03-28.
