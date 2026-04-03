"""Test different edit parameter combos on Abstract Wikipedia."""

import io
import sys
import os
import json
import requests
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
load_dotenv()

API_URL = "https://abstract.wikipedia.org/w/api.php"
TEST_QID = "Q29682"

ARTICLE_JSON = json.dumps({
    "qid": TEST_QID,
    "sections": {
        "Q8776414": {
            "index": 0,
            "fragments": [
                "Z89",
                {
                    "Z1K1": "Z7",
                    "Z7K1": "Z27868",
                    "Z27868K1": {
                        "Z1K1": "Z7",
                        "Z7K1": "Z14396",
                        "Z14396K1": {
                            "Z1K1": "Z7",
                            "Z7K1": "Z26570",
                            "Z26570K1": {"Z1K1": "Z18", "Z18K1": "Z825K1"},
                            "Z26570K2": {"Z1K1": "Z6091", "Z6091K1": "Q845945"},
                            "Z26570K3": {"Z1K1": "Z6091", "Z6091K1": "Q17"},
                            "Z26570K4": {"Z1K1": "Z18", "Z18K1": "Z825K2"}
                        }
                    }
                }
            ]
        }
    }
}, ensure_ascii=False)

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

r = session.get(API_URL, params={"action": "query", "meta": "tokens", "format": "json"})
csrf = r.json()["query"]["tokens"]["csrftoken"]

# Try 1: No contentmodel, no bot flag
print("\n--- Try 1: action=edit, NO contentmodel, NO bot flag ---")
r = session.post(API_URL, data={
    "action": "edit",
    "title": TEST_QID,
    "text": ARTICLE_JSON,
    "summary": "Creating Shinto shrine article",
    "token": csrf,
    "format": "json",
})
result = r.json()
if "error" in result:
    print(f"Error: {result['error']['code']} - {result['error']['info']}")
else:
    print(f"Result: {json.dumps(result, indent=2)}")

# Try 2: With contentmodel but no bot/createonly
print("\n--- Try 2: action=edit, contentmodel=abstractwiki, NO bot ---")
r = session.post(API_URL, data={
    "action": "edit",
    "title": TEST_QID,
    "text": ARTICLE_JSON,
    "summary": "Creating Shinto shrine article",
    "contentmodel": "abstractwiki",
    "token": csrf,
    "format": "json",
})
result = r.json()
if "error" in result:
    print(f"Error: {result['error']['code']} - {result['error']['info']}")
else:
    print(f"Result: {json.dumps(result, indent=2)}")

# Try 3: contentformat=text/plain
print("\n--- Try 3: action=edit, contentmodel=abstractwiki, contentformat=text/plain ---")
r = session.post(API_URL, data={
    "action": "edit",
    "title": TEST_QID,
    "text": ARTICLE_JSON,
    "summary": "Creating Shinto shrine article",
    "contentmodel": "abstractwiki",
    "contentformat": "text/plain",
    "token": csrf,
    "format": "json",
})
result = r.json()
if "error" in result:
    print(f"Error: {result['error']['code']} - {result['error']['info']}")
else:
    print(f"Result: {json.dumps(result, indent=2)}")
