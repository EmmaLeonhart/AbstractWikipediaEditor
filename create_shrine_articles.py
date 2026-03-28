"""Create Abstract Wikipedia articles for Shinto shrines.

Copies the exact article structure from Q11581011 (Kotai Jingu) to other
Shinto shrine items. The JSON template uses Wikifunctions calls that
dynamically generate text like "[Name] is a Shinto shrine in [Location], Japan."

Usage:
    python create_shrine_articles.py                # Dry run (no edits)
    python create_shrine_articles.py --apply        # Actually create articles
    python create_shrine_articles.py --apply --max-edits 10  # Limit edits
"""

import io
import sys
import os
import json
import time
import argparse
import requests
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()

API_URL = "https://abstract.wikipedia.org/w/api.php"
EDIT_DELAY = 1.5  # seconds between edits


def build_article_json(qid):
    """Build the Abstract Wikipedia article JSON for a given QID.

    This is an exact copy of the Q11581011 article structure.
    The Wikifunctions calls inside (Z26570 etc.) dynamically pull
    the entity name and location from Wikidata, so the same template
    works for any Shinto shrine.
    """
    return json.dumps({
        "qid": qid,
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


def login(session):
    """Log in to Abstract Wikipedia using bot credentials."""
    username = os.environ["WIKI_USERNAME"]
    password = os.environ["WIKI_PASSWORD"]

    # Step 1: Get login token
    r = session.get(API_URL, params={
        "action": "query",
        "meta": "tokens",
        "type": "login",
        "format": "json",
    })
    r.raise_for_status()
    login_token = r.json()["query"]["tokens"]["logintoken"]

    # Step 2: Log in
    r = session.post(API_URL, data={
        "action": "login",
        "lgname": username,
        "lgpassword": password,
        "lgtoken": login_token,
        "format": "json",
    })
    r.raise_for_status()
    result = r.json()["login"]
    if result["result"] != "Success":
        raise RuntimeError(f"Login failed: {result}")
    print(f"Logged in as {result['lgusername']}")


def get_csrf_token(session):
    """Get a CSRF token for editing."""
    r = session.get(API_URL, params={
        "action": "query",
        "meta": "tokens",
        "format": "json",
    })
    r.raise_for_status()
    return r.json()["query"]["tokens"]["csrftoken"]


def page_exists(session, title):
    """Check if a page already exists on Abstract Wikipedia."""
    r = session.get(API_URL, params={
        "action": "query",
        "titles": title,
        "format": "json",
    })
    r.raise_for_status()
    pages = r.json()["query"]["pages"]
    return "-1" not in pages


def create_article(session, csrf_token, qid, dry_run=True):
    """Create an Abstract Wikipedia article for a Shinto shrine QID."""
    title = qid
    content = build_article_json(qid)

    if page_exists(session, title):
        print(f"  SKIP {qid} - page already exists")
        return "skip"

    if dry_run:
        print(f"  DRY RUN: Would create {qid}")
        return "dry_run"

    r = session.post(API_URL, data={
        "action": "edit",
        "title": title,
        "text": content,
        "summary": "Creating Shinto shrine article (copied from Q11581011 template)",
        "contentmodel": "zobject",
        "createonly": "1",
        "bot": "1",
        "token": csrf_token,
        "format": "json",
    })
    r.raise_for_status()
    result = r.json()

    if "edit" in result and result["edit"].get("result") == "Success":
        print(f"  CREATED {qid}")
        return "created"
    elif "error" in result:
        print(f"  ERROR {qid}: {result['error']}")
        return "error"
    else:
        print(f"  UNEXPECTED {qid}: {result}")
        return "unexpected"


def main():
    parser = argparse.ArgumentParser(description="Create Abstract Wikipedia Shinto shrine articles")
    parser.add_argument("--apply", action="store_true", help="Actually create articles (default: dry run)")
    parser.add_argument("--max-edits", type=int, default=100, help="Maximum number of articles to create")
    parser.add_argument("--run-tag", type=str, default="", help="Tag for this run (unused, for workflow compat)")
    parser.add_argument("--qids-file", type=str, default="shrine_qids.json", help="JSON file with QIDs to process")
    args = parser.parse_args()

    if not os.path.exists(args.qids_file):
        print(f"QIDs file not found: {args.qids_file}")
        print("Run fetch_shinto_shrines.py first to generate it.")
        sys.exit(1)

    with open(args.qids_file, "r", encoding="utf-8") as f:
        qids = json.load(f)

    print(f"Loaded {len(qids)} QIDs from {args.qids_file}")
    if not args.apply:
        print("DRY RUN mode (use --apply to actually create articles)\n")
    else:
        print(f"LIVE mode - will create up to {args.max_edits} articles\n")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "AbstractTestBot/1.0 (Shinto shrine article creator)"
    })

    if args.apply:
        login(session)
        csrf_token = get_csrf_token(session)
    else:
        csrf_token = None

    stats = {"created": 0, "skip": 0, "error": 0, "dry_run": 0}

    for i, qid in enumerate(qids):
        if stats["created"] >= args.max_edits:
            print(f"\nReached max edits limit ({args.max_edits}), stopping.")
            break

        print(f"[{i+1}/{len(qids)}] Processing {qid}...")
        result = create_article(session, csrf_token, qid, dry_run=not args.apply)
        stats[result] = stats.get(result, 0) + 1

        if args.apply and result == "created":
            time.sleep(EDIT_DELAY)

    print(f"\nDone! Stats: {json.dumps(stats)}")


if __name__ == "__main__":
    main()
