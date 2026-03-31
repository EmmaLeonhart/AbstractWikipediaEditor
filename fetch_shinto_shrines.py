"""Fetch Shinto shrine QIDs from Wikidata via SPARQL, filtering out those
that already have articles on Abstract Wikipedia."""

import io
import sys
import json
import time
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
ABSTRACT_API = "https://abstract.wikipedia.org/w/api.php"

QUERY = """
SELECT ?item WHERE {
  ?item wdt:P31 wd:Q845945 .
}
LIMIT 1000
"""


def fetch_shrine_qids():
    """Fetch 1000 Shinto shrine QIDs from Wikidata."""
    response = requests.get(
        SPARQL_ENDPOINT,
        params={"query": QUERY, "format": "json"},
        headers={"User-Agent": "AbstractTestBot/1.0 (Shinto shrine article creator)"},
    )
    response.raise_for_status()
    data = response.json()

    qids = []
    for result in data["results"]["bindings"]:
        uri = result["item"]["value"]
        qid = uri.split("/")[-1]
        qids.append(qid)

    return qids


def check_existing_articles(qids):
    """Check which QIDs already have articles on Abstract Wikipedia.
    Uses the API in batches of 50 (API limit for titles parameter)."""
    existing = set()
    session = requests.Session()
    session.headers.update({"User-Agent": "AbstractTestBot/1.0"})

    for i in range(0, len(qids), 50):
        batch = qids[i:i + 50]
        titles = "|".join(batch)
        r = session.get(ABSTRACT_API, params={
            "action": "query",
            "titles": titles,
            "format": "json",
        })
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        for page_id, page_data in pages.items():
            # Pages that exist have positive IDs; missing pages have negative IDs
            if int(page_id) > 0:
                existing.add(page_data["title"])

        checked = min(i + 50, len(qids))
        print(f"  Checked {checked}/{len(qids)} for existing articles...", flush=True)
        time.sleep(0.5)

    return existing


if __name__ == "__main__":
    print("Fetching shrine QIDs from Wikidata...", flush=True)
    qids = fetch_shrine_qids()
    print(f"Fetched {len(qids)} Shinto shrine QIDs", flush=True)

    print("Checking which already have Abstract Wikipedia articles...", flush=True)
    existing = check_existing_articles(qids)
    print(f"Found {len(existing)} existing articles", flush=True)

    filtered = [qid for qid in qids if qid not in existing]
    print(f"{len(filtered)} shrines still need articles", flush=True)

    with open("shrine_qids.json", "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2)
    print(f"Saved to shrine_qids.json")
