# AbstractTestBot

Bot for creating Shinto shrine articles on [Abstract Wikipedia](https://abstract.wikipedia.org/) via browser automation.

## What it does

Creates articles by copying the Wikifunctions template from [Q11581011](https://abstract.wikipedia.org/wiki/Q11581011) (Kotai Jingu) and pasting it into new shrine pages. The template dynamically generates text like "[Name] is a Shinto shrine in [Location], Japan." for any shrine entity.

## Why browser automation?

Abstract Wikipedia's API **does not support creating articles** (as of March 2026). The `abstractwiki` content model requires `wikilambda-abstract-create` rights, which bot passwords cannot access. See [DOCUMENTATION.md](DOCUMENTATION.md) for the full story of what we tried and why.

## Scripts

| Script | Purpose |
|--------|---------|
| `fetch_shinto_shrines.py` | SPARQL query for 100 Shinto shrine QIDs |
| `create_via_browser.py` | Browser automation to create articles (the one that works) |
| `create_shrine_articles.py` | API-based approach (blocked by permissions, kept for reference) |

## Usage

```bash
pip install requests python-dotenv playwright
python -m playwright install chromium
python fetch_shinto_shrines.py
python create_via_browser.py --apply --max-edits 10 --headed
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
