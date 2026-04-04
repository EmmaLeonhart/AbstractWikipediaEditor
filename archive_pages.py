"""
Fetch the last 500 new pages from Abstract Wikipedia and submit each to the Wayback Machine.
Pages are processed oldest-first so the archive builds chronologically.
"""

import io
import sys
import time

import requests
from bs4 import BeautifulSoup

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HEADERS = {"User-Agent": "AbstractTestBot/1.0"}
NEW_PAGES_URL = "https://abstract.wikipedia.org/w/index.php?title=Special:NewPages&offset=&limit=500"
WAYBACK_SAVE_URL = "https://web.archive.org/save/"
ABSTRACT_WIKI_BASE = "https://abstract.wikipedia.org/wiki/"
DELAY = 15
RETRY_DELAY = 30
MAX_RETRIES = 3


def fetch_new_pages():
    """Fetch Special:NewPages and return a list of page titles."""
    print(f"Fetching new pages from {NEW_PAGES_URL} ...")
    resp = requests.get(NEW_PAGES_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    titles = []
    # Each entry in Special:NewPages has an <a> with class "mw-newpages-pagename"
    for link in soup.select("a.mw-newpages-pagename"):
        title = link.get("title")
        if title:
            titles.append(title)

    print(f"Found {len(titles)} pages.")
    return titles


def submit_to_wayback(page_title):
    """Submit a single page URL to the Wayback Machine's Save Page Now endpoint.
    Uses POST to the SPN2-style endpoint which is more reliable than GET.
    Retries on rate limits (429) and server errors (5xx)."""
    page_url = ABSTRACT_WIKI_BASE + page_title

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                WAYBACK_SAVE_URL,
                headers=HEADERS,
                data={"url": page_url, "capture_all": "on"},
                timeout=120,
            )
            if resp.status_code == 429:
                wait = RETRY_DELAY * (attempt + 1)
                print(f"rate-limited, waiting {wait}s... ", end="", flush=True)
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                wait = RETRY_DELAY * (attempt + 1)
                print(f"{resp.status_code}, retrying in {wait}s... ", end="", flush=True)
                time.sleep(wait)
                continue
            # 200 or 302 both indicate success
            if resp.status_code in (200, 302):
                return page_url
            resp.raise_for_status()
            return page_url
        except requests.exceptions.Timeout:
            if attempt < MAX_RETRIES - 1:
                print(f"timeout, retrying... ", end="", flush=True)
                time.sleep(15)
                continue
            raise

    raise RuntimeError(f"Failed after {MAX_RETRIES} retries")


def main():
    titles = fetch_new_pages()
    if not titles:
        print("No pages found. Exiting.")
        return

    # Reverse so we process oldest first (the list comes newest-first)
    titles.reverse()

    total = len(titles)
    success = 0
    failed = 0

    for i, title in enumerate(titles, 1):
        print(f"[{i}/{total}] Archiving {title} ... ", end="", flush=True)
        try:
            submit_to_wayback(title)
            success += 1
            print("OK")
        except Exception as e:
            failed += 1
            print(f"FAILED: {e}")

        if i < total:
            time.sleep(DELAY)

    print(f"\nDone. {success} archived, {failed} failed out of {total} total.")


if __name__ == "__main__":
    main()
