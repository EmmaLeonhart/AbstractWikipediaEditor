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
import io
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from concurrent.futures import as_completed

import requests
import wikifunctions as wf

if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from wikitext_parser import compile_template  # noqa: E402

ENGLISH_ZID = "Z1002"
RENDER_TIMEOUT = 30  # per-line wall-clock budget (wf.call has no built-in timeout)
MAX_WORKERS = 6  # be polite to the evaluator


def _is_template_line(line):
    """True if this line is a single {{template|...}} call that should be
    rendered via the Wikifunctions evaluator."""
    s = line.strip()
    return s.startswith("{{") and s.endswith("}}") and not s.lower() == "{{p}}"


def _substitute_local_args(obj, subject_qid):
    """Walk a Z-object tree and rewrite references the standalone
    evaluator can't resolve on its own.

      Z18K1 == "Z825K1"  ->  Z6091 ref to the subject QID
      Z18K1 == "Z825K2"  ->  Z9 ref to Z1002 (English)

    Z825K1/K2 only exist inside the outer article-renderer scope; the
    standalone `wikifunctions_run` evaluator rejects them, so we
    pre-substitute concrete values before sending.

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
    """Call the Wikifunctions evaluator via the `wikifunctions` PyPI
    library and extract the rendered HTML. Returns (html, error_string).

    Our `compile_template` already produces a canonical Z7 function call
    (e.g. `Z32123(Z32234([...]))`) with nested Z-objects in each `{zid}K{i}`
    slot. `wf.call(zid, *args)` wants the outer function ZID and its
    arguments as separate parameters, then rebuilds the same Z7 shape
    internally. So we decompose our compiled object — pull the outer ZID
    out of `Z7K1` and collect `{zid}K1, K2, ...` in order — and hand them
    to `wf.call()`, which POSTs to `wikifunctions_run` and returns the
    parsed Z22 response. The round-trip is byte-identical to posting the
    dict ourselves, we just go through the library so any future behavior
    tweaks (caching, auth, rate limiting) land by upgrading the pip.
    """
    try:
        z7k1 = zobj.get("Z7K1")
        outer_zid = z7k1.get("Z9K1") if isinstance(z7k1, dict) else z7k1
        if not isinstance(outer_zid, str) or not outer_zid.startswith("Z"):
            return None, f"bad outer function ref: {outer_zid!r}"

        args = []
        i = 1
        while True:
            key = f"{outer_zid}K{i}"
            if key not in zobj:
                break
            args.append(zobj[key])
            i += 1

        z22 = wf.call(outer_zid, *args)
    except requests.RequestException as e:
        return None, f"http error: {e}"
    except (ValueError, KeyError, TypeError) as e:
        return None, f"library error: {e}"
    except Exception as e:  # noqa: BLE001 — wf.call can raise anything
        return None, f"wf.call error: {type(e).__name__}: {e}"

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

    # Render template lines in parallel. Each future gets its own
    # wall-clock budget via future.result(timeout=...), because wf.call()
    # has no built-in timeout — a hung evaluator request could otherwise
    # stall a live-preview render indefinitely.
    if template_indices:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(render_line, lines[i], subject): i
                for i in template_indices
            }
            try:
                for fut in as_completed(futures, timeout=RENDER_TIMEOUT + 5):
                    i = futures[fut]
                    try:
                        results[i] = fut.result(timeout=RENDER_TIMEOUT)
                    except FutureTimeout:
                        results[i] = {"html": None, "error": f"timeout after {RENDER_TIMEOUT}s"}
                    except Exception as e:
                        results[i] = {"html": None, "error": f"worker error: {e}"}
            except FutureTimeout:
                # Outer iterator timed out — any still-unfinished futures get
                # flagged as timeouts; finished-but-unseen ones already have
                # their result set above.
                pass
            for fut, i in futures.items():
                if results[i] is None:
                    results[i] = {"html": None, "error": f"timeout after {RENDER_TIMEOUT}s"}

    json.dump(results, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
