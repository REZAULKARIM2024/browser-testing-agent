"""
CLI: let Claude drive a browser to check a test goal.

    python -m bta --url https://example.com --goal "Verify the login works" --data-file data.json

data.json holds test data such as {"email": "...", "password": "..."}.
The model is only told the key names, never the values.
Requires ANTHROPIC_API_KEY. Free offline tests: `pytest`.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from anthropic import Anthropic
from playwright.sync_api import sync_playwright

from .planner import ClaudePlanner
from .runner import run


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="start URL (its host is the only one allowed by default)")
    parser.add_argument("--goal", required=True, help="what to verify, in plain English")
    parser.add_argument("--data-file", help="JSON file with test data (secrets stay out of the prompt)")
    parser.add_argument("--allow-host", action="append", default=[], help="extra host the browser may visit")
    parser.add_argument("--max-steps", type=int, default=15)
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    parser.add_argument("--trace", help="write the step-by-step trace to this JSON file")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: set the ANTHROPIC_API_KEY environment variable first.")
        sys.exit(2)

    test_data = json.loads(Path(args.data_file).read_text(encoding="utf-8")) if args.data_file else {}
    planner = ClaudePlanner(Anthropic(api_key=api_key))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        page = browser.new_page()
        result = run(page, args.goal, args.url, planner, test_data,
                     allowed_hosts=set(args.allow_host) | {urlparse(args.url).hostname},
                     max_steps=args.max_steps)
        browser.close()

    for t in result.trace:
        print(f"step {t['step']:>2}  {json.dumps(t.get('action'))}  ->  {t.get('outcome', '')}")
    print(f"\n{'PASS' if result.passed else 'FAIL'}: {result.reason}  ({result.steps} steps, {result.assertions_passed} assertions)")
    if args.trace:
        Path(args.trace).write_text(json.dumps(result.trace, indent=2), encoding="utf-8")
    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    main()
