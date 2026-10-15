"""
Browser Testing Agent: public demo.

Pick a preset scenario. A scripted "model" drives a real headless Chromium against a small
demo shop that ships with the repo, and the deterministic runner decides pass/fail. No API
key and no URL input: the public app cannot be pointed at other sites.
"""

import json
import subprocess
import sys
from pathlib import Path

import streamlit as st

from bta.demo_scenarios import BY_ID, GROUPS, SCENARIOS, DATA

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Browser Testing Agent demo", page_icon="🧪", layout="wide")


@st.cache_resource(show_spinner="Setting up the browser (first visit only, about a minute)...")
def ensure_browser() -> str | None:
    """Downloads Chromium once per server start. Returns an error text, or None when ready."""
    try:
        done = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                              capture_output=True, text=True, timeout=600)
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}"
    return None if done.returncode == 0 else (done.stderr or done.stdout)[-600:]


def run_in_subprocess(scenario_id: str) -> dict:
    """A separate process: a browser crash or hang cannot take this web app down."""
    done = subprocess.run([sys.executable, "-m", "bta.demo_run", scenario_id],
                          capture_output=True, text=True, timeout=90, cwd=ROOT)
    if done.returncode != 0:
        raise RuntimeError((done.stderr or "browser run failed")[-600:])
    return json.loads(done.stdout.strip().splitlines()[-1])


st.title("🧪 Browser Testing Agent")
st.markdown(
    "An LLM **proposes** browser actions; deterministic code **decides** pass or fail and enforces the rules. "
    "Pick a scenario below. Each one is replayed in a **real headless Chromium** against a demo shop. "
    "This public demo uses scripted actions so it is free and cannot be aimed at other sites."
)

with st.sidebar:
    st.header("Scenario")
    group = st.radio("Group", GROUPS, label_visibility="collapsed")
    options = [s for s in SCENARIOS if s["group"] == group]
    chosen = st.radio("Scenario", options, format_func=lambda s: s["title"], label_visibility="collapsed")
    run_clicked = st.button("▶ Run scenario", type="primary", use_container_width=True)
    st.caption(f"Test data keys the model may use: `{', '.join(sorted(DATA))}`. It never sees their values.")
    st.markdown("[Source code on GitHub](https://github.com/REZAULKARIM2024/browser-testing-agent)")

st.subheader(chosen["title"])
st.write(f"**Goal given to the agent:** {chosen['goal']}")
with st.expander("Actions the (scripted) model will propose"):
    st.json(chosen["steps"])

if run_clicked:
    error = ensure_browser()
    if error:
        st.error("The browser could not be set up on this server, so the scenario cannot run here. "
                 "Run it locally instead (see the README: `pytest` or `python -m bta.demo_run`).")
        st.code(error)
        st.stop()
    with st.spinner("Running in headless Chromium..."):
        try:
            st.session_state["last"] = run_in_subprocess(chosen["id"])
        except Exception as e:  # noqa: BLE001
            st.session_state.pop("last", None)
            st.error(f"The run did not complete: {type(e).__name__}. Try again.")
            st.code(str(e)[-400:])

last = st.session_state.get("last")
if last and last["id"] == chosen["id"]:
    scenario = BY_ID[last["id"]]
    blocked = last["reason"].startswith("policy violation")
    if last["passed"]:
        st.success(f"✅ **TEST PASSED**: {last['reason']}  ({last['assertions_passed']} verified assertions)")
    elif blocked:
        st.warning(f"🛡️ **BLOCKED BY THE AGENT'S RULES**: {last['reason']}")
    else:
        st.error(f"❌ **TEST FAILED**: {last['reason']}")
    if last["matches_expectation"]:
        st.caption("The runner gave the verdict this scenario is designed to demonstrate.")
    else:
        st.error("Unexpected verdict for this scenario. That is a bug in the demo, not a test result.")
    st.info(f"**What this shows:** {scenario['lesson']}")

    st.markdown("#### Step by step")
    rows = [{"step": t["step"], "page": t["url"].replace("http://demo-site", "") or "/",
             "action proposed": json.dumps(t["action"]), "result": t["outcome"],
             "page text had injection": "yes, removed" if t["injection_flags"] else ""} for t in last["trace"]]
    st.dataframe(rows, use_container_width=True, hide_index=True)

    with st.expander("What the model saw (after sanitising)"):
        st.caption("This is the only page information a real model would receive. Suspicious sentences are removed first.")
        for i, seen in enumerate(last["model_saw"], 1):
            st.markdown(f"**Step {i}**" + (f" (removed: {', '.join(seen['injection_flags'])})" if seen["injection_flags"] else ""))
            st.code(seen["text"], language="text")

st.divider()
st.caption(
    "Limits: this demo replays fixed scripts, so it shows how the *rules* behave, not how well a model plans. "
    "To let Claude drive for real, run it locally with your own `ANTHROPIC_API_KEY` (see the README). "
    "The injection filter is heuristic and documented as such in the repo."
)
