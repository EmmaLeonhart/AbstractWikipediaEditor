# AbstractTestBot

Bot that creates articles on [Abstract Wikipedia](https://abstract.wikipedia.org/) from any Wikidata item using Playwright browser automation.

**[Article Catalog](https://emmaleonhart.github.io/AbstractTestBot/)** -- browse all created articles with language-neutral and English views

**[Wikifunctions Shortlist](WIKIFUNCTIONS_SHORTLIST.md)** -- curated list of functions for building articles | [Full catalog](WIKIFUNCTIONS_CATALOG.md) (3,911 functions)

## How it works

1. **`generate_wikitext.py`** takes a Wikidata QID, fetches its properties, and produces a wikitext template using a property-to-function mapping
2. **`wikitext_parser.py`** compiles the wikitext into clipboard-ready Z-object JSON
3. **`create_from_qid.py`** injects the clipboard data into the Abstract Wikipedia visual editor via Playwright and publishes

Abstract Wikipedia's API does not support creating articles directly -- the `abstractwiki` content model requires `wikilambda-abstract-create` rights, which bot passwords cannot access. See [DOCUMENTATION.md](DOCUMENTATION.md) for the full story.

## Quick start

```bash
pip install requests python-dotenv pyyaml playwright
python -m playwright install chromium

# Generate wikitext for any Wikidata item
python generate_wikitext.py Q706499

# Create an article (opens browser)
python create_from_qid.py Q706499 --apply --headed

# Batch create
python create_from_qid.py --batch Q60,Q1653,Q602 --apply --headed
```

## Chrome extension

The `extension/` directory contains a Chrome extension that does the same thing from a browser popup -- enter a QID, generate wikitext, and create the article with one click. Load it as an unpacked extension from `chrome://extensions`.

## Wikitext template syntax

```
---
title: Shinto Shrine
variables:
  deity: Q-item
---
{{location | $subject | Q845945 | Q17}}
{{role | $deity | Q11591100 | $subject}}
```

Each `{{...}}` block becomes one clipboard fragment. Supports Z-function calls, `$subject`/`$lang` references, Q-item auto-wrapping, variables, and human-readable function aliases.

## Project structure

| Directory | Contents |
|-----------|----------|
| `/` | Runtime scripts: `create_from_qid.py`, `generate_wikitext.py`, `wikitext_parser.py` |
| `extension/` | Chrome extension for manual article creation |
| `data/` | Property mappings, function aliases, generated templates |
| `site/` | GitHub Pages article catalog (auto-generated) |
| `research/` | Exploration and debugging scripts |
| `archive/` | Superseded scripts (old shrine-only approach, batch launchers) |

## GitHub Actions

| Workflow | Purpose |
|----------|---------|
| `pages.yml` | Builds the [article catalog](https://emmaleonhart.github.io/AbstractTestBot/) daily, archives pages on the Wayback Machine |
| `ci.yml` | Runs tests on push/PR |

## Configuration

Create a `.env` file:
```
WIKI_USERNAME=YourUsername@BotName
WIKI_MAIN_PASSWORD=main_account_password
```

Main account credentials are required -- bot passwords cannot create articles.
