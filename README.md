# Abstract Wikipedia Editor

Desktop editor for creating and editing articles on [Abstract Wikipedia](https://abstract.wikipedia.org/).

Abstract Wikipedia stores articles as language-neutral function calls (Z-objects) that get rendered into every language automatically. This project provides an Electron desktop app for writing articles with a live English preview, and publishing them to Abstract Wikipedia.

**[Project website](https://emmaleonhart.github.io/AbstractEditing/)** | **[Download latest release](https://github.com/EmmaLeonhart/AbstractWikipediaEditor/releases/latest)**

## Desktop editor

The Electron app is the main way to use this project. It provides a wikitext editor with live English preview, pull from Wikidata/Abstract Wikipedia, and push to publish.

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
- Push articles to Abstract Wikipedia via Playwright browser automation
- Built-in login screen for Wikimedia credentials

## Why browser automation?

Abstract Wikipedia's API does not support creating or editing articles. The standard `action=edit` endpoint does not work with the `abstractwiki` content model. So we automate the visual editor's clipboard-paste workflow via Playwright. See [DOCUMENTATION.md](DOCUMENTATION.md) for the full technical details.

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

## Project structure

| Path | Purpose |
|------|---------|
| `editor/` | Electron desktop app (TypeScript) -- the main product |
| `data/` | Property mappings, function aliases, wikitext templates |
| `site/` | Project website (deployed via GitHub Pages) |
| `*.py` | CLI scripts used by the editor and for debugging |
| `tests/` | Unit tests |

## Configuration

Credentials can be entered through the Login button in the desktop editor, or by creating a `.env` file in the project root:

```
WIKI_USERNAME=YourUsername
WIKI_MAIN_PASSWORD=your_password
```
