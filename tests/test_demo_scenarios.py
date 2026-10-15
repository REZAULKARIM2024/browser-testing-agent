"""The public demo must never drift from what the code really does: every preset scenario is run
in real headless Chromium and its verdict is compared with the one the demo promises."""
import pytest

from bta.demo_run import run_scenario
from bta.demo_scenarios import BY_ID, GROUPS, SCENARIOS, outcome_matches


def test_scenario_table_is_consistent():
    ids = [s["id"] for s in SCENARIOS]
    assert len(ids) == len(set(ids)) and len(ids) >= 12
    for s in SCENARIOS:
        assert s["group"] in GROUPS and s["steps"] and s["lesson"] and s["goal"]
        assert isinstance(s["expect"]["passed"], bool)


def test_every_group_has_scenarios():
    assert all(any(s["group"] == g for s in SCENARIOS) for g in GROUPS)


def test_outcome_matching_rules():
    s = BY_ID["optimistic_model"]
    assert outcome_matches(s, False, "Expected text not found: 'x'")
    assert not outcome_matches(s, True, "expected text not found")
    assert not outcome_matches(s, False, "some other failure")


@pytest.mark.parametrize("scenario_id", [s["id"] for s in SCENARIOS])
def test_scenario_gives_the_promised_verdict(scenario_id):
    result = run_scenario(scenario_id)
    assert result["matches_expectation"], (scenario_id, result["passed"], result["reason"])


def test_demo_never_leaks_password_value():
    result = run_scenario("login_ok")
    blob = str(result)
    assert "Test#1234" not in blob and "password" in result["test_data_keys"]


def test_injected_sentence_is_removed_from_what_the_model_saw():
    result = run_scenario("reviews_clean")
    seen = "\n".join(s["text"] for s in result["model_saw"])
    assert "evil.example" not in seen and "Great shop" in seen
    assert any(s["injection_flags"] for s in result["model_saw"])


def test_trace_hides_the_random_local_port():
    result = run_scenario("login_ok")
    assert "127.0.0.1" not in str(result["trace"])
