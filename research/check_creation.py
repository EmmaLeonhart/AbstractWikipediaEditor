"""Check how Q11581011 was created and what rights are needed."""

import io
import sys
import json
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

API_URL = "https://abstract.wikipedia.org/w/api.php"
UA = {"User-Agent": "AbstractTestBot/1.0"}

# Check the creation log for Q11581011
r = requests.get(API_URL, params={
    "action": "query",
    "list": "logevents",
    "letype": "create",
    "letitle": "Q11581011",
    "format": "json",
}, headers=UA)
print("Creation log for Q11581011:")
print(json.dumps(r.json().get("query", {}).get("logevents", []), indent=2))

# Check page creation log (recent)
r = requests.get(API_URL, params={
    "action": "query",
    "list": "logevents",
    "leaction": "create/create",
    "lelimit": "10",
    "format": "json",
}, headers=UA)
print("\nRecent page creations:")
for event in r.json().get("query", {}).get("logevents", []):
    print(f"  {event.get('title')} by {event.get('user')} at {event.get('timestamp')}")

# Check revision history of Q11581011
r = requests.get(API_URL, params={
    "action": "query",
    "titles": "Q11581011",
    "prop": "revisions",
    "rvprop": "user|timestamp|comment|size",
    "rvlimit": "5",
    "format": "json",
}, headers=UA)
print("\nRevision history of Q11581011:")
pages = r.json()["query"]["pages"]
for pid, page in pages.items():
    for rev in page.get("revisions", []):
        print(f"  {rev}")

# Check what rights are needed for abstractwiki namespace
r = requests.get(API_URL, params={
    "action": "query",
    "meta": "siteinfo",
    "siprop": "restrictions|rightsinfo",
    "format": "json",
}, headers=UA)
print("\nSite restrictions:")
print(json.dumps(r.json()["query"], indent=2))
