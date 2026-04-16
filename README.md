# Abstract Wikipedia Editor

Desktop editor for creating and editing articles on [Abstract Wikipedia](https://abstract.wikipedia.org/).

Abstract Wikipedia stores articles as language-neutral function calls (Z-objects) that get rendered into every language automatically. Instead of writing prose, you write function calls like `{{Z26570|SUBJECT|Q845945|Q17}}` which render to sentences like "Kashima Shrine is a Shinto shrine in Kashima" in any language. This project provides tools for writing those function calls and publishing them.

**[Project website](https://emmaleonhart.github.io/AbstractEditing/)** | **[Download latest release](https://github.com/EmmaLeonhart/AbstractWikipediaEditor/releases/latest)**

## How it works

The overall pipeline is:

1. **Enter a Wikidata QID** (e.g. Q7235 for Sophocles)
2. **Auto-generate a wikitext template** by fetching the item's properties from Wikidata and mapping each property to a Wikifunctions sentence generator
3. **Preview** the English rendering with resolved Wikidata labels
4. **Publish** to Abstract Wikipedia via Playwright browser automation (the API does not support article creation — see [DOCUMENTATION.md](DOCUMENTATION.md) for why)

## Desktop editor

The Electron app is the main way to use this project.

```bash
cd editor
npm install
npm start
```

Or double-click `runeditor.bat` on Windows.

### Features

- Enter any Wikidata QID and auto-generate a wikitext template from its properties
- Live preview renders English sentences with resolved Wikidata labels
- Pull existing articles from Abstract Wikipedia and edit them
- **Overwrite protection on Pull from Wikidata.** If the article already exists on Abstract Wikipedia, the first click on "Pull from Wikidata" shows the existing Abstract Wikipedia content instead and displays a warning notice. You have to click "Pull from Wikidata" a second time to actually regenerate from Wikidata and discard what's there. Prevents accidentally nuking hand-edited content.
- Push articles to Abstract Wikipedia via Playwright browser automation
- Built-in login screen for Wikimedia credentials

## Why browser automation?

Abstract Wikipedia's API does not support creating or editing articles. The standard `action=edit` endpoint does not work with the `abstractwiki` content model. So we automate the visual editor's clipboard-paste workflow via Playwright. See [DOCUMENTATION.md](DOCUMENTATION.md) for the full technical details.

## Wikitext template syntax

Articles are written in a template syntax that maps to Abstract Wikipedia's Z-object JSON:

```
---
title: Shinto Shrine
variables:
  deity: Q-item
---
{{location|SUBJECT|Q845945|Q17}}
{{spo|$deity|Q1762010|SUBJECT}}
```

Each `{{...}}` block becomes one article fragment (one sentence). The syntax supports:

- **Z-function IDs** (`Z26570`) or **human-readable aliases** (`location`, `spo`, `role`) — see `data/function_aliases.json` for the full alias list
- **`SUBJECT`** — the article's Wikidata entity (auto-resolved)
- **`$lang`** — the rendering language
- **Q-items** (`Q845945`) — automatically wrapped as Wikidata entity references
- **Template variables** (`$deity`) — declared in the YAML frontmatter and filled at render time

The parser (`wikitext_parser.py`) compiles these templates into the nested Z-object clipboard JSON that Abstract Wikipedia's visual editor expects.

## Property-to-function mapping

The file `data/property_function_mapping.json` is the core configuration that drives auto-generation. It maps Wikidata properties to Wikifunctions sentence generators:

| Property | Wikifunction | Produces |
|----------|-------------|----------|
| P31 (instance of) | Z26039 | "Nairobi is a city." |
| P106 (occupation) | Z26039 | "Marie Curie is a physicist." |
| P27 (citizenship) | Z28016 | "Marie Curie is a physicist of Poland." (combined with P106 when both exist) |
| P131/P17/P30 (location) | Z26570 | "Kashima Shrine is a Shinto shrine in Kashima." |
| P36 (capital) | Z28016 | "Tokyo is the capital of Japan." |
| P37 (official language) | Z28016 | "Japanese is the official language of Japan." |

**Deduplication rules** prevent redundant sentences:
- **Location priority**: P131 > P17 > P30 — only the most specific location is used
- **Occupation over instance**: When P106 (occupation) exists, P31 (instance of) is skipped (avoids "X is a human")
- **Occupation + citizenship combined**: When both P106 and P27 exist, they merge into one sentence ("X is a [occupation] of [country]") instead of two separate ones
- **Capital inverse**: P1376 is skipped when P36 exists (they're inverses of each other)

## Project structure

| Path | Purpose |
|------|---------|
| `editor/` | Electron desktop app (TypeScript) — the main product |
| `data/property_function_mapping.json` | Maps Wikidata properties → Wikifunctions sentence generators |
| `data/function_aliases.json` | Human-readable names for Z-function IDs (e.g. `location` → `Z26570`) |
| `data/templates/` | Hand-crafted wikitext templates (auto-generated ones are gitignored) |
| `discussions/` | Snapshots of Abstract Wikipedia discussion pages the bot watches (updated daily + on push by a GitHub Actions workflow) |
| `site/` | Project website (deployed via GitHub Pages) |
| `tests/` | Unit tests |

### Python scripts

| Script | Purpose |
|--------|---------|
| `generate_wikitext.py` | Fetches a Wikidata item's properties and produces a wikitext template using the property mapping |
| `wikitext_parser.py` | Compiles wikitext templates into Z-object clipboard JSON for Abstract Wikipedia |
| `create_from_qid.py` | Full pipeline: generate wikitext → compile to JSON → publish via Playwright |
| `edit_from_qid.py` | Same as above but for editing existing articles (deletes old fragments, pastes new ones) |
| `convert_article.py` | Reverse direction: fetches an existing article from Abstract Wikipedia and converts its Z-objects back to wikitext |
| `convert_to_aliases.py` | Rewrites Z-IDs in wikitext files to human-readable aliases (e.g. `Z26570` → `location`) |
| `build_pages.py` | Builds the GitHub Pages site from all existing Abstract Wikipedia articles |
| `archive_pages.py` | Submits Abstract Wikipedia pages to the Wayback Machine for archiving |
| `fetch_discussions.py` | Snapshots a hardcoded list of Abstract Wikipedia discussion pages (project chat, talk pages, etc.) into `discussions/` so the bot has offline context. Run automatically on push and daily via GitHub Actions |

## Configuration

Credentials can be entered through the Login button in the desktop editor, or by creating a `.env` file in the project root:

```
WIKI_USERNAME=YourUsername
WIKI_MAIN_PASSWORD=your_password
```
