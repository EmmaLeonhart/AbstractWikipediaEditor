# AbstractTestBot

Bot for creating test articles on [Abstract Wikipedia](https://abstract.wikipedia.org/).

## What it does

Creates Shinto shrine articles on Abstract Wikipedia by copying the article template from [Q11581011](https://abstract.wikipedia.org/wiki/Q11581011) (Kotai Jingu). The template uses Wikifunctions calls that dynamically generate text like "[Name] is a Shinto shrine in [Location], Japan." for any Shinto shrine entity.

## How it works

1. **`fetch_shinto_shrines.py`** — Queries Wikidata SPARQL for 100 items with P31 (instance of) = Q845945 (Shinto shrine)
2. **`create_shrine_articles.py`** — Creates Abstract Wikipedia articles for each QID using the template

## Usage

### Via GitHub Actions (recommended)
Go to Actions → "Create Shinto Shrine Articles" → Run workflow. Set `apply` to `true` to actually create articles.

### Locally
```bash
pip install -r requirements.txt
python fetch_shinto_shrines.py
python create_shrine_articles.py          # dry run
python create_shrine_articles.py --apply  # actually create
```

## Configuration

Set these in your GitHub repo:
- **Secret** `WIKI_PASSWORD`: Bot password
- **Variable** `WIKI_USERNAME`: Bot username (e.g., `Immanuelle@AbstractTest`)
