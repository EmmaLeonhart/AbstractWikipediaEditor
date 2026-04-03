"""Check what namespace Q-pages live in on Abstract Wikipedia."""

import io
import sys
import json
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

API_URL = "https://abstract.wikipedia.org/w/api.php"

# Check what namespace Q11581011 is in
r = requests.get(API_URL, params={
    "action": "query",
    "titles": "Q11581011",
    "prop": "info",
    "format": "json",
}, headers={"User-Agent": "AbstractTestBot/1.0"})
print("Q11581011 page info:")
print(json.dumps(r.json()["query"]["pages"], indent=2))

# Also check all namespaces more thoroughly
r = requests.get(API_URL, params={
    "action": "query",
    "meta": "siteinfo",
    "siprop": "namespaces|namespacealiases|restrictions",
    "format": "json",
}, headers={"User-Agent": "AbstractTestBot/1.0"})

# Look for any namespace with "page" in the name
namespaces = r.json()["query"]["namespaces"]
print("\nAll namespaces with protection info:")
for nsid, ns in sorted(namespaces.items(), key=lambda x: int(x[0])):
    name = ns.get("canonical", ns.get("*", "(main)"))
    protection = ns.get("protection", "none")
    content = "CONTENT" if ns.get("content") else ""
    print(f"  {nsid}: {name} {content} protection={protection}")
