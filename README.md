# AbstractTestBot

**[Wikifunctions Shortlist](WIKIFUNCTIONS_SHORTLIST.md)** — curated list of functions for building articles | [Full catalog](WIKIFUNCTIONS_CATALOG.md) (3,911 functions) | [Roadmap](todo.md)

Bot for creating Shinto shrine articles on [Abstract Wikipedia](https://abstract.wikipedia.org/) via browser automation.

## What it does

Creates articles by injecting Wikifunctions fragments directly into the editor's clipboard, then pasting both a location and deity fragment in a single editor session. The script queries Wikidata via SPARQL for shrines with deities, checks which already have articles, and creates the missing ones.

## Why browser automation?

Abstract Wikipedia's API **does not support creating articles** (as of March 2026). The `abstractwiki` content model requires `wikilambda-abstract-create` rights, which bot passwords cannot access. See [DOCUMENTATION.md](DOCUMENTATION.md) for the full story of what we tried and why.

## Project Structure

| Directory | Contents |
|-----------|----------|
| `/` (root) | Runtime scripts and launchers |
| `research/` | Exploration, debugging, and test scripts |
| `archive/` | Superseded script versions kept for reference |
| `data/` | Generated data files, cached JSON, HTML artifacts |
| `screenshots/` | Debug and documentation screenshots |
| `credentials/` | Passwords and secrets (gitignored) |

## Scripts

| Script | Purpose |
|--------|---------|
| `create_rich_onepass.py` | Single-pass shrine creation via clipboard injection (current standard) |
| `create_rich_threepass.py` | Three-fragment version with administrative territory |
| `wikitext_parser.py` | Wiki text template parser: converts human-readable templates to clipboard JSON |
| `runcreate.bat` | Quick launcher: creates 10 shrines in headed mode |
| `archive/create_shrine_articles.py` | API-based approach (blocked by permissions, kept for reference) |

## Wiki Text Templates

The `wikitext_parser.py` module provides a MediaWiki-inspired template syntax for defining Abstract Wikipedia articles without hand-crafting nested Z-object JSON.

**Template syntax:**
```
---
title: Shinto Shrine
variables:
  deity: Q-item
---
{{Z26570 | $subject | Q845945 | Q17}}
{{Z28016 | $deity | Q11591100 | $subject}}
```

Each `{{...}}` block becomes one clipboard fragment. The parser handles:
- **Z-function calls** with positional or named arguments
- **`$subject` / `$lang`** as implicit article entity/language references
- **Q-items** automatically wrapped as Wikidata item references (Z6091)
- **`$variables`** filled in at render time from the frontmatter or caller
- **Auto-wrapping**: Z11-returning functions get Z29749, Z6-returning get Z27868

**CLI usage:**
```bash
python wikitext_parser.py data/templates/shinto_shrine.wikitext deity=Q12345
python wikitext_parser.py --list-functions
```

**Python usage:**
```python
from wikitext_parser import compile_template
clipboard = compile_template(template_text, {"deity": "Q12345", "subject": "Q67890"})
```

Example templates in `data/templates/`: shrine, city, mountain, and more.

## Usage

```bash
pip install requests python-dotenv playwright
python -m playwright install chromium

# Dry run
python create_rich_onepass.py

# Create 10 articles
python create_rich_onepass.py --apply --max-edits 10 --headed

# Or just double-click runcreate.bat
```

## Configuration

Create a `.env` file:
```
WIKI_USERNAME=YourUsername@BotName
WIKI_PASSWORD=bot_password
WIKI_MAIN_PASSWORD=main_account_password
```

## Documentation

See [DOCUMENTATION.md](DOCUMENTATION.md) for extensive documentation on Abstract Wikipedia's API, what works, what doesn't, and all the problems we ran into.
