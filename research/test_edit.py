"""Quick test: try different API methods to create an Abstract Wikipedia article."""

import io
import sys
import os
import json
import requests
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
load_dotenv()

API_URL = "https://abstract.wikipedia.org/w/api.php"
TEST_QID = "Q29682"  # A Shinto shrine that doesn't have an article yet

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
                            "Z26570K1": {
                                "Z1K1": "Z18",
                                "Z18K1": "Z825K1"
                            },
                            "Z26570K2": {
                                "Z1K1": "Z6091",
                                "Z6091K1": "Q845945"
                            },
                            "Z26570K3": {
                                "Z1K1": "Z6091",
                                "Z6091K1": "Q17"
                            },
                            "Z26570K4": {
                                "Z1K1": "Z18",
                                "Z18K1": "Z825K2"
                            }
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

# Get CSRF token
r = session.get(API_URL, params={"action": "query", "meta": "tokens", "format": "json"})
csrf = r.json()["query"]["tokens"]["csrftoken"]

# Method 1: action=edit with contentmodel=abstractwiki
print("\n--- Method 1: action=edit, contentmodel=abstractwiki ---")
r = session.post(API_URL, data={
    "action": "edit",
    "title": TEST_QID,
    "text": ARTICLE_JSON,
    "summary": "Test: creating Shinto shrine article",
    "contentmodel": "abstractwiki",
    "createonly": "1",
    "bot": "1",
    "token": csrf,
    "format": "json",
})
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2)}")
