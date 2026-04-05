# Abstract Wikipedia Editor

Desktop editor and automation toolkit for creating and editing articles on [Abstract Wikipedia](https://abstract.wikipedia.org/).

Abstract Wikipedia stores articles as language-neutral function calls (Z-objects) that get rendered into every language automatically. This project provides:

- **Electron desktop app** for writing, previewing, and publishing articles
- **Project website** with live-rendered article previews

**[Project website](https://emmaleonhart.github.io/AbstractEditing/)** | **[Article catalog](https://emmaleonhart.github.io/AbstractEditing/catalog.html)**

## Desktop editor

The Electron app is the main way to use this project. It provides a wikitext editor with live English preview, pull from Wikidata/Abstract Wikipedia, and push to publish.

```bash
cd editor
npm install
npm start
```

Or double-click `runeditor.bat` on Windows.

To build a distributable .exe installer:

```bash
cd editor
npm run dist
```

### Features

- Enter any Wikidata QID and auto-generate a wikitext template from its properties
- Live preview renders English sentences with resolved Wikidata labels
- Pull existing articles from Abstract Wikipedia and edit them
- Push articles to Abstract Wikipedia via Playwright browser automation

## Project structure

| Path | Purpose |
|------|---------|
| `editor/` | Electron desktop app (TypeScript) -- the main product |
| `data/` | Property mappings, function aliases, generated templates |
| `site/` | Project website (deployed via GitHub Pages) |
| `*.py` | CLI scripts for batch operations and debugging |
| `tests/` | Unit tests |

## Wikitext template syntax

```
---
title: Shinto Shrine
variables:
  deity: Q-item
---
{{location | $subject | Q845945 | Q17}}
{{spo | Q1762010 | $subject | $deity}}
```

Each `{{...}}` block becomes one article fragment. Supports Z-function IDs, human-readable aliases (`location`, `role`, `spo`), `$subject`/`$lang` references, Q-item auto-wrapping, and template variables.

## Why browser automation?

Abstract Wikipedia's API does not support creating `abstractwiki` content. The `wikilambda-abstract-create` right is required but bot passwords cannot access it. So we automate the visual editor's clipboard-paste workflow via Playwright. See [DOCUMENTATION.md](DOCUMENTATION.md) for details.

## Configuration

Create a `.env` file in the project root:

```
WIKI_USERNAME=YourUsername@BotName
WIKI_MAIN_PASSWORD=main_account_password
```

Main account credentials are required -- bot passwords cannot create articles.

## GitHub Actions

| Workflow | Purpose |
|----------|---------|
| `pages.yml` | Builds the [project website](https://emmaleonhart.github.io/AbstractEditing/) and article catalog daily |
| `ci.yml` | Runs tests on push/PR |
| `create-shrine-articles.yml` | Disabled -- VPN-triggered email verification blocks CI login |
