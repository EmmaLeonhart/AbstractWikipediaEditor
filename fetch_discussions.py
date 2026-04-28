"""Snapshot Abstract Wikipedia and Wikifunctions discussion pages into
discussions/ so the bot (and anything reading this repo for context)
can see what has been said on the project chats and on Immanuelle's
talk pages without having to fetch them live.

Run by .github/workflows/fetch-discussions.yml every day and on every
push to master; the workflow commits the diff if any page has changed
since the last snapshot. There is nothing authenticated here — the
pages are public and we're just pulling their current wikitext.

The pages we track are hardcoded in PAGES below as (host, title,
filename) tuples. To add a new page, append a tuple with the wiki
host (e.g. `abstract.wikipedia.org`), the page title in URL form
(`User_talk:Foo`, not `User talk:Foo`), and the output filename.

Usage:
    python fetch_discussions.py                  # fetch + write
    python fetch_discussions.py --check          # exit 1 if any file would change
    python fetch_discussions.py --out discussions/  # override output dir
"""

import argparse
import io
import json
import os
import sys
import time

import requests

if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# (host, page title on the wiki, output filename under discussions/)
# Title must be in the URL-style form with underscores — this is what
# MediaWiki accepts as titles= and what the wiki URL bar shows. Each
# host gets its own batched API call; pages from different wikis can't
# share a query.
PAGES = [
    ("abstract.wikipedia.org",
     "Abstract_Wikipedia:Project_chat",
     "abstract_wikipedia_project_chat.wikitext"),
    ("abstract.wikipedia.org",
     "Abstract_Wikipedia:Report_a_technical_problem",
     "abstract_wikipedia_report_a_technical_problem.wikitext"),
    ("abstract.wikipedia.org",
     "User_talk:Immanuelle",
     "user_talk_immanuelle.wikitext"),
    ("abstract.wikipedia.org",
     "User_talk:Immanuelle/Abstract_Wikipedia_Editor",
     "user_talk_immanuelle_abstract_wikipedia_editor.wikitext"),
    # Wikifunctions community is also relevant — the editor compiles to
    # Wikifunctions calls and most natural-language-generation issues
    # surface there first.
    ("www.wikifunctions.org",
     "Wikifunctions:Project_chat",
     "wikifunctions_project_chat.wikitext"),
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "AbstractTestBot/1.0 (discussion snapshot; https://github.com/EmmaLeonhart/AbstractWikipediaEditor)",
})


def fetch_wikitext(host, titles):
    """Batch-fetch the current wikitext of each title from the given
    wiki host. Returns a dict title -> wikitext (str) or None if the
    page is missing. The wiki normalizes titles on our behalf (e.g.
    underscores <-> spaces) so we map results back to the input titles
    via both the raw title we sent and the normalizations list the API
    returns."""
    params = {
        "action": "query",
        "titles": "|".join(titles),
        "prop": "revisions",
        "rvprop": "content|timestamp",
        "rvslots": "main",
        "format": "json",
        "formatversion": "2",
    }
    r = SESSION.get(f"https://{host}/w/api.php", params=params, timeout=60)
    r.raise_for_status()
    data = r.json()

    # Build a normalized-title -> original-title map so we can match the
    # API's normalized responses back to our input titles.
    norm_map = {t: t for t in titles}
    for n in data.get("query", {}).get("normalized", []) or []:
        norm_map[n["to"]] = n["from"]

    out = {}
    for page in data.get("query", {}).get("pages", []) or []:
        orig = norm_map.get(page.get("title"), page.get("title"))
        if page.get("missing"):
            out[orig] = None
            continue
        revs = page.get("revisions") or []
        if not revs:
            out[orig] = None
            continue
        slot = revs[0].get("slots", {}).get("main", {})
        out[orig] = slot.get("content", "")
    return out


def header_block(host, title, fetched_at):
    """A small provenance header prepended to each snapshot so a reader
    can tell when it was captured and where from. Kept as wiki-style
    HTML comments so copying the file back to the wiki would still
    render cleanly."""
    return (
        "<!--\n"
        f"  Snapshot of https://{host}/wiki/{title}\n"
        f"  Fetched:   {fetched_at}\n"
        "  Source:    fetch_discussions.py (auto-updated via GitHub Actions)\n"
        "  DO NOT EDIT — any local changes will be overwritten on the next run.\n"
        "-->\n"
    )


def build_snapshot(host, title, wikitext, fetched_at):
    if wikitext is None:
        return header_block(host, title, fetched_at) + f"<!-- page missing or not yet created -->\n"
    # Normalize line endings so a CRLF checkout on Windows doesn't show
    # spurious diffs against a LF-fetched body.
    body = wikitext.replace("\r\n", "\n").replace("\r", "\n")
    if not body.endswith("\n"):
        body += "\n"
    return header_block(host, title, fetched_at) + body


def strip_header(content):
    """Return `content` minus our provenance header, so two snapshots
    can be compared for real changes without the fetched-at timestamp
    creating a false diff."""
    if content.startswith("<!--") and "-->\n" in content:
        return content.split("-->\n", 1)[1]
    return content


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="discussions",
                    help="Output directory (default: discussions)")
    ap.add_argument("--check", action="store_true",
                    help="Don't write; exit 1 if any file would change")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    # Group pages by host so we make one batched API call per wiki.
    by_host = {}
    for host, title, _ in PAGES:
        by_host.setdefault(host, []).append(title)

    print(f"Fetching {len(PAGES)} discussion page(s) from {len(by_host)} wiki(s)...", flush=True)
    contents = {}
    for host, titles in by_host.items():
        try:
            host_contents = fetch_wikitext(host, titles)
        except requests.RequestException as e:
            print(f"ERROR: fetch from {host} failed: {e}", flush=True)
            sys.exit(2)
        for title, wikitext in host_contents.items():
            contents[(host, title)] = wikitext

    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    changed = []
    unchanged = []
    missing = []
    for host, title, filename in PAGES:
        wikitext = contents.get((host, title))
        path = os.path.join(args.out, filename)
        new_content = build_snapshot(host, title, wikitext, fetched_at)

        # Compare against the existing file (ignoring the provenance
        # header, which always differs because of the fetched_at stamp).
        old_body = None
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    old_body = strip_header(f.read())
            except OSError:
                old_body = None

        new_body = strip_header(new_content)

        if wikitext is None:
            missing.append(title)

        if old_body == new_body:
            unchanged.append(title)
            # Still update the header's fetched_at on a real run so the
            # file's mtime roughly tracks when we last checked, but only
            # if we were going to rewrite anyway — in --check mode we
            # do nothing here.
            continue

        changed.append(title)
        if not args.check:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(new_content)
        print(f"  {title}: {'would change' if args.check else 'updated'}", flush=True)

    for title in unchanged:
        print(f"  {title}: unchanged", flush=True)
    for title in missing:
        print(f"  {title}: page missing on wiki", flush=True)

    if args.check and changed:
        sys.exit(1)


if __name__ == "__main__":
    main()
