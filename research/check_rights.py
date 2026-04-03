"""Check account rights and namespace info on Abstract Wikipedia."""

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

# Login
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

# Check user rights
r = session.get(API_URL, params={
    "action": "query",
    "meta": "userinfo",
    "uiprop": "rights|groups|editcount",
    "format": "json",
})
info = r.json()["query"]["userinfo"]
print(f"\nUser: {info['name']}")
print(f"Groups: {info.get('groups', [])}")
print(f"Edit count: {info.get('editcount', 0)}")
print(f"Rights: {json.dumps(info.get('rights', []), indent=2)}")

# Check namespace info
r = session.get(API_URL, params={
    "action": "query",
    "meta": "siteinfo",
    "siprop": "namespaces|namespacealiases",
    "format": "json",
})
namespaces = r.json()["query"]["namespaces"]
print("\n--- Namespaces ---")
for nsid, ns in sorted(namespaces.items(), key=lambda x: int(x[0])):
    print(f"  {nsid}: {ns.get('canonical', ns.get('*', ''))}")
