"""Smoke tests of the Streamlit page itself."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_app_renders_without_error():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert "Browser Testing Agent" in at.title[0].value
    assert any("Run scenario" in b.label for b in at.button)


def test_running_a_blocked_scenario_shows_the_guard_message():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.radio[0].set_value("Attacks on the agent").run()      # group selector
    at.button[0].click().run()                               # runs the first scenario of that group
    assert not at.exception
    assert any("BLOCKED BY THE AGENT" in w.value for w in at.warning), [e.value for e in at.error]
