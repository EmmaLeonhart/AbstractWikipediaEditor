# AbstractTestBot

Bot for creating Shinto shrine articles on [Abstract Wikipedia](https://abstract.wikipedia.org/) via browser automation.

## What it does

Creates articles by injecting Wikifunctions fragments directly into the editor's clipboard, then pasting both a location and deity fragment in a single editor session. The script queries Wikidata via SPARQL for shrines with deities, checks which already have articles, and creates the missing ones.

## Why browser automation?

Abstract Wikipedia's API **does not support creating articles** (as of March 2026). The `abstractwiki` content model requires `wikilambda-abstract-create` rights, which bot passwords cannot access. See [DOCUMENTATION.md](DOCUMENTATION.md) for the full story of what we tried and why.

## Scripts

| Script | Purpose |
|--------|---------|
| `create_rich_onepass.py` | Single-pass shrine creation via clipboard injection (current standard) |
| `runcreate.bat` | Quick launcher: creates 10 shrines in headed mode |
| `create_shrine_articles.py` | API-based approach (blocked by permissions, kept for reference) |

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
