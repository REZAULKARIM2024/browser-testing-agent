"""
runner.py
The agent loop. The model PROPOSES actions; this code VALIDATES and EXECUTES
them under hard rules, and decides pass/fail itself:

  * only actions from actions.ALLOWED_TYPES run
  * the browser may only visit allowed hosts (default: the start URL's host);
    leaving them is a policy violation and fails the run
  * password fields can only be filled from test_data via `value_key`, so
    credentials never appear in the model prompt or its output
  * a run passes only if the model says so AND at least one deterministic
    expect_* assertion succeeded and none failed. The model's claim alone
    is never enough.
"""

import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from . import observe as observe_mod
from .actions import InvalidAction, validate_action

MAX_INVALID_IN_A_ROW = 2
WAIT_SECONDS = 3.0


@dataclass
class Result:
    passed: bool
    reason: str
    steps: int
    assertions_passed: int
    trace: list = field(default_factory=list)


class PolicyViolation(Exception):
    pass


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def check_url(url: str, allowed_hosts: set[str]):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise PolicyViolation(f"blocked scheme {parsed.scheme!r}: {url}")
    if _host(url) not in allowed_hosts:
        raise PolicyViolation(f"blocked navigation to disallowed host {_host(url)!r}")


def _resolve(observation: dict, target: str) -> dict:
    """Finds the element whose accessible name matches `target` (exact first, then unique substring)."""
    wanted = target.strip().lower()
    elements = observation["elements"]
    exact = [e for e in elements if e["name"].lower() == wanted]
    matches = exact or [e for e in elements if wanted in e["name"].lower()]
    if not matches:
        raise InvalidAction(f"no element named {target!r} on the page")
    if len(matches) > 1:
        raise InvalidAction(f"{len(matches)} elements match {target!r}; be more specific")
    return matches[0]


def _settle(page):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=3000)
    except Exception:  # navigation may not have happened; that is fine
        pass


def _poll(check, seconds=WAIT_SECONDS) -> bool:
    deadline = time.monotonic() + seconds
    while True:
        if check():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.2)


def run(page, goal: str, start_url: str, planner, test_data: dict | None = None,
        allowed_hosts: set[str] | None = None, max_steps: int = 15) -> Result:
    test_data = test_data or {}
    allowed = {h.lower() for h in (allowed_hosts or {_host(start_url)})}
    trace, history = [], []
    assertions_passed = 0
    invalid_streak = 0

    def finish(passed: bool, reason: str, steps: int) -> Result:
        return Result(passed, reason, steps, assertions_passed, trace)

    try:
        check_url(start_url, allowed)
        page.goto(start_url)
    except PolicyViolation as e:
        return finish(False, f"policy violation: {e}", 0)

    for step in range(1, max_steps + 1):
        observation = observe_mod.observe(page)
        entry = {"step": step, "url": page.url, "injection_flags": observation["injection_flags"]}
        trace.append(entry)
        proposed = planner.next_action(goal, observation, history, sorted(test_data))
        entry["action"] = proposed

        try:
            action = validate_action(proposed)
            kind = action["type"]

            if kind == "finish":
                entry["outcome"] = "finish"
                if not action["passed"]:
                    return finish(False, action.get("reason") or "model reported failure", step)
                if assertions_passed == 0:
                    return finish(False, "model claimed a pass without any verified assertion", step)
                return finish(True, action.get("reason") or "all assertions passed", step)

            if kind == "goto":
                check_url(action["url"], allowed)
                page.goto(action["url"])
            elif kind == "click":
                element = _resolve(observation, action["target"])
                if element["href"]:
                    check_url(element["href"], allowed)
                page.locator(f'[data-bta-id="{element["id"]}"]').click(timeout=3000)
                _settle(page)
            elif kind == "fill":
                element = _resolve(observation, action["target"])
                if "value_key" in action:
                    if action["value_key"] not in test_data:
                        raise InvalidAction(f"unknown value_key {action['value_key']!r}")
                    value = test_data[action["value_key"]]
                else:
                    if element["type"] == "password":
                        raise PolicyViolation("password fields may only be filled via value_key")
                    value = action["value"]
                page.locator(f'[data-bta-id="{element["id"]}"]').fill(value, timeout=3000)
            elif kind == "press":
                page.keyboard.press(action["key"])
                _settle(page)
            elif kind == "expect_text":
                text = action["text"].lower()
                ok = _poll(lambda: text in page.evaluate("() => document.body.innerText").lower())
                entry["outcome"] = "assertion passed" if ok else "assertion FAILED"
                if not ok:
                    return finish(False, f"expected text not found: {action['text']!r}", step)
                assertions_passed += 1
            elif kind == "expect_url_contains":
                ok = _poll(lambda: action["text"] in page.url)
                entry["outcome"] = "assertion passed" if ok else "assertion FAILED"
                if not ok:
                    return finish(False, f"URL does not contain {action['text']!r} (is {page.url})", step)
                assertions_passed += 1

            check_url(page.url, allowed)  # catches redirects that left the allowed hosts
            entry.setdefault("outcome", "ok")
            invalid_streak = 0
            history.append({"action": action, "outcome": entry["outcome"]})

        except PolicyViolation as e:
            entry["outcome"] = f"POLICY VIOLATION: {e}"
            return finish(False, f"policy violation: {e}", step)
        except InvalidAction as e:
            entry["outcome"] = f"invalid action: {e}"
            history.append({"action": proposed, "outcome": entry["outcome"]})
            invalid_streak += 1
            if invalid_streak >= MAX_INVALID_IN_A_ROW:
                return finish(False, f"stopped after {invalid_streak} invalid actions in a row", step)
        except Exception as e:  # browser errors (timeouts, detached elements)
            entry["outcome"] = f"error: {type(e).__name__}"
            history.append({"action": proposed, "outcome": entry["outcome"]})
            invalid_streak += 1
            if invalid_streak >= MAX_INVALID_IN_A_ROW:
                return finish(False, f"stopped after repeated errors: {type(e).__name__}", step)

    return finish(False, f"step limit ({max_steps}) reached without finishing", max_steps)
