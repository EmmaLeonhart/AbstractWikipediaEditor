"""Render wikitext template lines to their actual Wikifunctions HTML output.

Used by the Electron editor's live preview to show the *real* rendered
English for each sentence instead of a hand-rolled TypeScript
approximation. Previously renderer.ts had a switch statement with one
case per function ZID that emitted strings like "${a[0]} is a ${a[1]}."
— a half-port of Wikifunctions' own rendering logic that silently
drifted whenever a function changed upstream. This script replaces that
with calls to the real evaluator on www.wikifunctions.org, so the
preview matches production exactly.

Pipeline, per line of wikitext:
    1. Run `compile_template(line, {"subject": qid})` to get the
       clipboard Z-object the editor would paste (same code path as
       `push-article` — pulling and pushing share the compiler).
    2. Walk the tree and replace the two local-argument references the
       Abstract Wikipedia renderer fills in at publish time:
         - Z18(Z825K1) -> Z6091(subject_qid)       (SUBJECT)
         - Z18(Z825K2) -> Z9(Z1002)                ($lang = English)
       Without these substitutions the evaluator errors out because
       Z825K1/K2 only exist inside the outer renderer's scope.
    3. POST the Z-object to the `wikifunctions_run` MediaWiki API
       action on www.wikifunctions.org. Parse the returned Z22 and
       extract Z22K1.Z89K1 — the rendered HTML fragment.

Calls are parallelized with a small thread pool since each request is
independent and the evaluator takes ~100ms of server orchestration plus
HTTP round-trip.

Input (via --input <path> to a JSON file):
    {"subject": "Q144", "lines": ["{{is a|SUBJECT|Q146}}", "==Q1==", ...]}

Output (stdout, JSON):
    [{"html": "<p>Dog is a cat.</p>", "error": null}, ...]
    - One entry per input line, in the same order.
    - `html` is null and `error` is a short string when a line isn't a
      template, failed to compile, or the API returned a Z5 error.

Non-template lines (blank, `{{p}}`, `==...==` section headers) are
returned as `{"html": null, "error": null}` so the caller can decide
whether to skip them or render something else (the editor handles
paragraph breaks and section headers directly in TypeScript, using
Wikidata labels, because those don't benefit from the real renderer).
"""

import argparse
import copy
import io
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from wikitext_parser import compile_template  # noqa: E402

WIKIFUNCTIONS_API = "https://www.wikifunctions.org/w/api.php"
ENGLISH_ZID = "Z1002"
IT_PRONOUN_QID = "Q6091500"  # Wikidata item for the English pronoun "it"
RENDER_TIMEOUT = 30
MAX_WORKERS = 6  # be polite to the evaluator

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "AbstractTestBot/1.0 (Electron editor live preview)",
})


def _is_template_line(line):
    """True if this line is a single {{template|...}} call that should be
    rendered via the Wikifunctions evaluator."""
    s = line.strip()
    return s.startswith("{{") and s.endswith("}}") and not s.lower() == "{{p}}"


def _substitute_local_args(obj, subject_qid):
    """Walk a Z-object tree and rewrite references the standalone
    evaluator can't resolve on its own.

      Z18K1 == "Z825K1"             ->  Z6091 ref to the subject QID
      Z18K1 == "Z825K2"             ->  Z9 ref to Z1002 (English)
      Z6091 ref to Q6091500 ("it")  ->  Z6091 ref to the subject QID

    The last one mirrors Abstract Wikipedia's own renderer: at publish
    time it replaces the "it" pronoun entity with whatever the article
    is about, so the reader sees "A dog is a pet" instead of "An it is
    a pet." The standalone `wikifunctions_run` evaluator doesn't know
    about this substitution (it just looks up the English label of
    Q6091500, which is literally "it"), so we do the swap here for the
    preview to match production.

    Returns a new tree; does not mutate the input.
    """
    if isinstance(obj, dict):
        z1k1 = obj.get("Z1K1")
        inner_type = z1k1.get("Z9K1") if isinstance(z1k1, dict) else z1k1

        if inner_type == "Z18":
            ref = obj.get("Z18K1")
            ref_val = ref.get("Z6K1") if isinstance(ref, dict) else ref
            if ref_val == "Z825K1":
                return {
                    "Z1K1": {"Z1K1": "Z9", "Z9K1": "Z6091"},
                    "Z6091K1": {"Z1K1": "Z6", "Z6K1": subject_qid},
                }
            if ref_val == "Z825K2":
                return {"Z1K1": {"Z1K1": "Z9", "Z9K1": "Z9"}, "Z9K1": ENGLISH_ZID}

        if inner_type == "Z6091":
            qid_slot = obj.get("Z6091K1")
            qid_val = qid_slot.get("Z6K1") if isinstance(qid_slot, dict) else qid_slot
            if qid_val == IT_PRONOUN_QID and subject_qid:
                return {
                    "Z1K1": {"Z1K1": "Z9", "Z9K1": "Z6091"},
                    "Z6091K1": {"Z1K1": "Z6", "Z6K1": subject_qid},
                }

        return {k: _substitute_local_args(v, subject_qid) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_local_args(v, subject_qid) for v in obj]
    return obj


def _dig_metadata_error(metadata):
    """The Z22K2 metadata map is a (non-canonical) list of {K1: key, K2: value}
    pairs. When evaluation failed, one of those pairs is keyed "errors" and
    its value is a Z5 object with Z5K1 = error type. Pull out the type's ZID
    so we can show the user something better than "no result"."""
    try:
        entries = metadata.get("K1") if isinstance(metadata, dict) else None
        if not isinstance(entries, list):
            return None
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("K1") == "errors":
                err = entry.get("K2", {})
                if isinstance(err, dict):
                    z5k1 = err.get("Z5K1")
                    if isinstance(z5k1, dict):
                        return z5k1.get("Z9K1") or json.dumps(z5k1)[:120]
                    if isinstance(z5k1, str):
                        return z5k1
                return json.dumps(err)[:160]
    except (AttributeError, TypeError):
        pass
    return None


def _extract_html(z22_data):
    """Dig the rendered HTML string out of a Z22 response. Returns
    (html, error_string). The happy path is Z22K1.Z89K1; error shapes
    put Z24 in Z22K1 and drop Z5 error details into Z22K2.K1."""
    result = z22_data.get("Z22K1")
    if result is None or result == "Z24":
        # Z24 is the "null / nothing" sentinel — evaluator couldn't produce a value.
        # Try to surface the underlying Z5 error from Z22K2 metadata.
        err_type = _dig_metadata_error(z22_data.get("Z22K2"))
        if err_type:
            return None, f"evaluator error ({err_type})"
        return None, "evaluator returned Z24 (no result)"
    if isinstance(result, dict):
        t = result.get("Z1K1")
        t_id = t.get("Z9K1") if isinstance(t, dict) else t
        if t_id == "Z89":
            return result.get("Z89K1"), None
        if t_id == "Z6":
            return result.get("Z6K1"), None
        return None, f"unexpected result type {t_id}"
    if isinstance(result, str):
        return result, None
    return None, f"unexpected result shape: {type(result).__name__}"


def _render_zobject(zobj):
    """POST a Z-object to wikifunctions_run and extract the rendered
    HTML. Returns (html, error_string)."""
    try:
        r = SESSION.post(
            WIKIFUNCTIONS_API,
            data={
                "action": "wikifunctions_run",
                "format": "json",
                "function_call": json.dumps(zobj),
                "origin": "*",
            },
            timeout=RENDER_TIMEOUT,
        )
        r.raise_for_status()
        payload = r.json()
    except requests.RequestException as e:
        return None, f"http error: {e}"
    except ValueError as e:
        return None, f"bad json: {e}"

    run = payload.get("wikifunctions_run")
    if not run or "data" not in run:
        # API-level error (e.g. throttling, unknown action)
        err = payload.get("error", {}).get("info", "missing wikifunctions_run.data")
        return None, f"api error: {err}"

    try:
        z22 = json.loads(run["data"])
    except (ValueError, TypeError) as e:
        return None, f"bad Z22 json: {e}"

    return _extract_html(z22)


def render_line(line, subject_qid):
    """Compile a single wikitext line and render it. Returns {html, error}."""
    if not _is_template_line(line):
        return {"html": None, "error": None}

    try:
        clipboard = compile_template(line, {"subject": subject_qid})
    except Exception as e:
        return {"html": None, "error": f"compile error: {e}"}

    if not clipboard:
        return {"html": None, "error": "no clipboard items"}

    # Normally one template line -> one clipboard item (a Z32123 paragraph
    # wrapping a single Z32234 with one sentence). Render them all and
    # concatenate if there are multiple.
    fragments = []
    for item in clipboard:
        value = item.get("value") if isinstance(item, dict) else item
        if not value:
            continue
        patched = _substitute_local_args(value, subject_qid)
        html, err = _render_zobject(patched)
        if err:
            return {"html": None, "error": err}
        if html:
            fragments.append(html)

    if not fragments:
        return {"html": None, "error": "empty render"}

    return {"html": "".join(fragments), "error": None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True,
                    help="Path to JSON input file: {subject, lines}")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        payload = json.load(f)

    subject = payload.get("subject") or ""
    lines = payload.get("lines") or []

    # Pre-seed non-template lines so we don't spawn threads for them
    results = [None] * len(lines)
    template_indices = []
    for i, line in enumerate(lines):
        if _is_template_line(line):
            template_indices.append(i)
        else:
            results[i] = {"html": None, "error": None}

    # Render template lines in parallel
    if template_indices:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(render_line, lines[i], subject): i
                for i in template_indices
            }
            for fut in futures:
                i = futures[fut]
                try:
                    results[i] = fut.result()
                except Exception as e:
                    results[i] = {"html": None, "error": f"worker error: {e}"}

    json.dump(results, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
