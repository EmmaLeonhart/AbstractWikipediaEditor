"""Loop runner for edit_from_qid.py --random with random delays.

Picks 5 random existing articles, regenerates their wikitext (with
proper implicit paragraphs), and re-publishes them. Repeats with a
random delay of 300 +/- 120 seconds (180-420s) between runs.

Usage:
    python reformat_loop.py
"""

import subprocess
import sys
import time
import random

PYTHON = r"C:\Users\Immanuelle\AppData\Local\Programs\Python\Python313\python.exe"
BASE_DELAY = 300   # 5 minutes
JITTER = 120       # +/- 2 minutes

def main():
    run_count = 0
    while True:
        run_count += 1
        print(f"\n{'#'*60}", flush=True)
        print(f"Run #{run_count} starting at {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        print(f"{'#'*60}\n", flush=True)

        result = subprocess.run(
            [PYTHON, "edit_from_qid.py", "--random", "5", "--apply", "--headed"],
            cwd=r"C:\Users\Immanuelle\Documents\Github\AbstractTestBot",
        )
        print(f"\nRun #{run_count} finished with exit code {result.returncode}", flush=True)

        delay = BASE_DELAY + random.randint(-JITTER, JITTER)
        print(f"Waiting {delay} seconds ({delay/60:.1f} min) before next run...", flush=True)
        time.sleep(delay)


if __name__ == "__main__":
    main()
