"""Fetch 100 Shinto shrine QIDs from Wikidata via SPARQL."""

import io
import sys
import json
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

QUERY = """
SELECT ?item WHERE {
  ?item wdt:P31 wd:Q845945 .
}
LIMIT 100
"""


def fetch_shrine_qids():
    """Fetch 100 Shinto shrine QIDs from Wikidata."""
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


if __name__ == "__main__":
    qids = fetch_shrine_qids()
    print(f"Fetched {len(qids)} Shinto shrine QIDs:")
    for qid in qids:
        print(f"  {qid}")

    with open("shrine_qids.json", "w", encoding="utf-8") as f:
        json.dump(qids, f, indent=2)
    print(f"\nSaved to shrine_qids.json")
