# AbstractTestBot

A tool that creates articles on [Abstract Wikipedia](https://abstract.wikipedia.org/) from any Wikidata item, using Playwright browser automation.

Abstract Wikipedia stores articles as language-neutral function calls (Z-objects) that get rendered into every language automatically. This bot takes a Wikidata QID, maps its properties to the right Wikifunctions sentence generators, and publishes the article through the visual editor.

## Why browser automation?

Abstract Wikipedia's API does not support creating articles directly. The `abstractwiki` content model requires `wikilambda-abstract-create` rights, which bot passwords cannot access. So we automate the visual editor's clipboard-paste workflow instead.

## How it works

1. **Generate wikitext** -- `generate_wikitext.py` takes a Wikidata QID, fetches its properties, and produces a wikitext template using a [property-to-function mapping](https://github.com/EmmaLeonhart/AbstractEditing/blob/master/data/property_function_mapping.json)
2. **Compile to clipboard JSON** -- `wikitext_parser.py` turns the wikitext into Z-object JSON that the Abstract Wikipedia editor understands
3. **Publish via browser** -- `create_from_qid.py` opens the editor with Playwright, injects each fragment into the clipboard, pastes them in, and clicks Publish

## Download

**[Download from GitHub](https://github.com/EmmaLeonhart/AbstractEditing)**

```bash
git clone https://github.com/EmmaLeonhart/AbstractEditing.git
cd AbstractEditing
pip install requests python-dotenv pyyaml playwright
python -m playwright install chromium
```

## Quick start

```bash
# Preview what would be generated (dry run)
python generate_wikitext.py Q706499

# Create an article (opens browser for login)
python create_from_qid.py Q706499 --apply --headed

# Batch create multiple articles
python create_from_qid.py --batch Q60,Q1653,Q602 --apply --headed

# Edit an existing article with fresh Wikidata data
python edit_from_qid.py Q706499 --apply --headed
```

You need a `.env` file with your Wikimedia main account credentials (bot passwords cannot create articles):

```
WIKI_USERNAME=YourUsername@BotName
WIKI_MAIN_PASSWORD=main_account_password
```

## Wikitext template syntax

The bot uses a human-readable template format that compiles to Abstract Wikipedia's Z-object JSON:

```
---
title: Shinto Shrine
variables:
  deity: Q-item
---
{{location | $subject | Q845945 | Q17}}
{{spo | Q5765080 | $subject | $deity}}
```

Each `{{...}}` block becomes one article fragment. Supports Z-function IDs, human-readable aliases (`location`, `role`, `spo`), `$subject`/`$lang` references, and Q-item auto-wrapping.

## Property mapping

The bot maps Wikidata properties to Wikifunctions sentence generators:

| Wikidata property | Function | Produces |
|-------------------|----------|----------|
| P31 (instance of) | Z26039 | "X is a Y." |
| P279 (subclass of) | Z26095 | "A X is a Y." |
| P131 (admin territory) | Z26570 | "X is a Y in Z." |
| P825 (dedicated to) | Z26955 | "X is dedicated to Y." |
| P361 (part of) | Z26955 | "X is part of Y." |
| P36 (capital) | Z28016 | "Y is the capital of X." |
| P37 (official language) | Z26955 | "Y is the official language of X." |

See the full [property_function_mapping.json](https://github.com/EmmaLeonhart/AbstractEditing/blob/master/data/property_function_mapping.json) for all 17 supported properties.

## Article catalog

**[Browse all created articles](catalog.html)** -- 438 articles with their language-neutral Z-function representations and English previews.

## Links

- [GitHub repository](https://github.com/EmmaLeonhart/AbstractEditing)
- [Abstract Wikipedia](https://abstract.wikipedia.org/)
- [Full documentation](https://github.com/EmmaLeonhart/AbstractEditing/blob/master/DOCUMENTATION.md)
