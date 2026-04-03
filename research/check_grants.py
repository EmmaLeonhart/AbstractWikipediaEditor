"""Check bot password grants and compare with full account rights."""

import io
import sys
import os
import json
import requests
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
load_dotenv()

API_URL = "https://abstract.wikipedia.org/w/api.php"

session = requests.Session()
session.headers.update({"User-Agent": "AbstractTestBot/1.0"})

# Login with bot password
r = session.get(API_URL, params={"action": "query", "meta": "tokens", "type": "login", "format": "json"})
login_token = r.json()["query"]["tokens"]["logintoken"]
r = session.post(API_URL, data={
    "action": "login",
    "lgname": os.environ["WIKI_USERNAME"],
    "lgpassword": os.environ["WIKI_PASSWORD"],
    "lgtoken": login_token,
    "format": "json",
})
print(f"Login: {r.json()['login']['result']}")

# Check full grants info
r = session.get(API_URL, params={
    "action": "query",
    "meta": "userinfo",
    "uiprop": "rights|groups|grants",
    "format": "json",
})
info = r.json()["query"]["userinfo"]
print(f"\nUser: {info['name']}")
print(f"Groups: {info.get('groups', [])}")

rights = info.get('rights', [])
print(f"\nRights ({len(rights)}):")
for r in sorted(rights):
    print(f"  {r}")

# Check what rights exist for editing abstractwiki pages
r = requests.get(API_URL, params={
    "action": "query",
    "meta": "siteinfo",
    "siprop": "restrictions",
    "format": "json",
}, headers={"User-Agent": "AbstractTestBot/1.0"})
print(f"\nSite restrictions: {json.dumps(r.json()['query']['restrictions'], indent=2)}")

# Check all available grants
r = requests.get(API_URL, params={
    "action": "query",
    "meta": "siteinfo",
    "siprop": "extensions",
    "format": "json",
}, headers={"User-Agent": "AbstractTestBot/1.0"})
extensions = r.json()["query"]["extensions"]
wl_ext = [e for e in extensions if "wikilambda" in e.get("name", "").lower() or "abstract" in e.get("name", "").lower()]
print(f"\nRelevant extensions:")
for e in wl_ext:
    print(f"  {e['name']} (v{e.get('version', '?')})")
