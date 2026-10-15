"""
Runs ONE preset scenario against the bundled demo site in real headless Chromium and prints
the result as JSON. The Streamlit app calls this in a separate process so a browser crash or
hang can never take the web app down.

    python -m bta.demo_run login_ok
"""

import functools
import http.server
import json
import sys
import threading
from pathlib import Path

from .demo_scenarios import BY_ID, DATA, fill_site, outcome_matches, start_path
from .observe import render
from .planner import ScriptedPlanner
from .runner import run

DEMO_SITE = Path(__file__).resolve().parent.parent / "demo_site"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class _Recording(ScriptedPlanner):
    """Remembers exactly the text the model would have been shown at each step."""

    def __init__(self, actions):
        super().__init__(actions)
        self.seen = []

    def next_action(self, goal, observation, history, data_keys):
        self.seen.append({"text": render(observation), "injection_flags": observation["injection_flags"]})
        return super().next_action(goal, observation, history, data_keys)


def run_scenario(scenario_id: str) -> dict:
    from playwright.sync_api import sync_playwright

    scenario = BY_ID[scenario_id]
    handler = functools.partial(_Quiet, directory=str(DEMO_SITE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    site = f"http://127.0.0.1:{server.server_address[1]}"
    planner = _Recording(fill_site(scenario["steps"], site))
    try:
        with sync_playwright() as p:
            # --no-sandbox is needed inside most containers. Safe here: the browser only ever
            # loads the bundled demo pages, and the host allow-list blocks everything else.
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            page = browser.new_context().new_page()
            result = run(page, scenario["goal"], f"{site}/{start_path(scenario)}", planner, dict(DATA),
                         max_steps=scenario.get("max_steps", 15))
            browser.close()
    finally:
        server.shutdown()

    def mask(text):
        return text.replace(site, "http://demo-site") if isinstance(text, str) else text

    trace = [{"step": t["step"], "url": mask(t["url"]), "action": json.loads(mask(json.dumps(t["action"]))),
              "outcome": mask(t.get("outcome", "")), "injection_flags": t["injection_flags"]} for t in result.trace]
    return {
        "id": scenario_id,
        "passed": result.passed,
        "reason": mask(result.reason),
        "steps": result.steps,
        "assertions_passed": result.assertions_passed,
        "matches_expectation": outcome_matches(scenario, result.passed, result.reason),
        "trace": trace,
        "model_saw": [{"text": mask(s["text"]), "injection_flags": s["injection_flags"]} for s in planner.seen],
        "test_data_keys": sorted(DATA),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in BY_ID:
        sys.exit(f"usage: python -m bta.demo_run <{'|'.join(BY_ID)}>")
    print(json.dumps(run_scenario(sys.argv[1])))
