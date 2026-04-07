"""Convert wikitext templates from Z-IDs to human-readable aliases.

Reads wikitext files with {{Z26570|...}} syntax and rewrites them
using English aliases like {{location|...}}.

Usage:
    python convert_to_aliases.py                          # Convert all in data/templates/auto/
    python convert_to_aliases.py data/templates/auto/Q7184.wikitext  # Convert one file
    python convert_to_aliases.py --dry-run                # Preview without writing
"""

import io
import sys
import os
import re
import json
import argparse

if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ALIASES_PATH = os.path.join(SCRIPT_DIR, "data", "function_aliases.json")


def load_reverse_aliases():
    """Load reverse mapping: Z-ID -> preferred English alias."""
    with open(ALIASES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    reverse = data.get("reverse", {})
    # Pick the first (preferred) alias for each Z-ID
    return {zid: aliases[0] for zid, aliases in reverse.items() if aliases}


def convert_line(line, reverse):
    """Convert Z-IDs to aliases in a single line of wikitext."""
    def replace_func(match):
        inner = match.group(1)
        parts = [p.strip() for p in inner.split('|')]
        if not parts:
            return match.group(0)

        func_name = parts[0]
        # Only replace if it's a Z-ID that we have an alias for
        if re.match(r'^Z\d+$', func_name) and func_name in reverse:
            parts[0] = reverse[func_name]

        return '{{' + '|'.join(parts) + '}}'

    return re.sub(r'\{\{(.+?)\}\}', replace_func, line)


def convert_file(path, reverse, dry_run=False):
    """Convert a wikitext file from Z-IDs to aliases."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    converted = []
    for line in content.split('\n'):
        converted.append(convert_line(line, reverse))
    result = '\n'.join(converted)

    if content == result:
        return False  # No changes

    if dry_run:
        print(f"\n--- {os.path.basename(path)} ---")
        print(result)
        return True

    # Write to aliases/ subdirectory
    base_dir = os.path.dirname(path)
    alias_dir = os.path.join(base_dir, "aliases")
    os.makedirs(alias_dir, exist_ok=True)
    out_path = os.path.join(alias_dir, os.path.basename(path))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result)
    print(f"  {os.path.basename(path)} -> aliases/{os.path.basename(path)}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Convert wikitext Z-IDs to English aliases")
    parser.add_argument("files", nargs="*", help="Specific files to convert")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    reverse = load_reverse_aliases()
    print(f"Loaded {len(reverse)} function aliases", flush=True)

    if args.files:
        files = args.files
    else:
        auto_dir = os.path.join(SCRIPT_DIR, "data", "templates", "auto")
        if not os.path.exists(auto_dir):
            print("No auto-generated templates found")
            return
        files = [os.path.join(auto_dir, f) for f in sorted(os.listdir(auto_dir))
                 if f.endswith('.wikitext')]

    if not files:
        print("No wikitext files to convert")
        return

    print(f"Converting {len(files)} files...", flush=True)
    converted = 0
    for path in files:
        if convert_file(path, reverse, dry_run=args.dry_run):
            converted += 1

    print(f"\nConverted {converted}/{len(files)} files", flush=True)


if __name__ == "__main__":
    main()
