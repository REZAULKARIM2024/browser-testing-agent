"""End-to-end tests: a real headless Chromium against the local demo site, with a scripted
(offline, free) planner. They check the agent's SAFETY RULES as much as its happy path."""
from bta.planner import ScriptedPlanner
from bta.runner import run

DATA = {"email": "demo@example.com", "password": "Test#1234"}

LOGIN = [
    {"type": "goto", "url": "{site}/login.html"},
    {"type": "fill", "target": "Email", "value_key": "email"},
    {"type": "fill", "target": "Password", "value_key": "password"},
    {"type": "click", "target": "Sign in"},
]


def _script(site, *extra, base=LOGIN):
    steps = [{**a, "url": a["url"].format(site=site)} if a["type"] == "goto" else a for a in base]
    return ScriptedPlanner(steps + list(extra))


def _run(page, site, planner, **kw):
    return run(page, "test goal", f"{site}/index.html", planner, kw.pop("data", DATA), **kw)


def test_login_happy_path_passes_with_verified_assertions(page, site):
    planner = _script(site,
        {"type": "expect_url_contains", "text": "dashboard.html"},
        {"type": "expect_text", "text": "Welcome back"},
        {"type": "finish", "passed": True, "reason": "logged in"})
    result = _run(page, site, planner)
    assert result.passed and result.assertions_passed == 2


def test_negative_login_is_a_valid_passing_test(page, site):
    planner = _script(site,
        {"type": "expect_text", "text": "Invalid credentials"},
        {"type": "finish", "passed": True, "reason": "error shown"},
        base=[
            {"type": "goto", "url": "{site}/login.html"},
            {"type": "fill", "target": "Email", "value": "nobody@example.com"},
            {"type": "fill", "target": "Password", "value_key": "password"},
            {"type": "click", "target": "Sign in"},
        ])
    assert _run(page, site, planner).passed


def test_failed_assertion_fails_the_run_even_if_model_would_say_pass(page, site):
    planner = _script(site,
        {"type": "expect_text", "text": "Welcome back"},   # wrong credentials below, so absent
        {"type": "finish", "passed": True, "reason": "model is optimistic"},
        base=[
            {"type": "goto", "url": "{site}/login.html"},
            {"type": "fill", "target": "Email", "value": "nobody@example.com"},
            {"type": "fill", "target": "Password", "value_key": "password"},
            {"type": "click", "target": "Sign in"},
        ])
    result = _run(page, site, planner)
    assert not result.passed and "expected text not found" in result.reason


def test_claiming_pass_without_any_assertion_is_rejected(page, site):
    planner = _script(site, {"type": "finish", "passed": True, "reason": "trust me"})
    result = _run(page, site, planner)
    assert not result.passed and "without any verified assertion" in result.reason


def test_goto_to_other_host_is_blocked(page, site):
    planner = ScriptedPlanner([{"type": "goto", "url": "https://evil.example/steal"}])
    result = _run(page, site, planner)
    assert not result.passed and result.reason.startswith("policy violation")
    assert "evil.example" in result.reason


def test_clicking_a_link_to_another_host_is_blocked(page, site):
    planner = ScriptedPlanner([{"type": "click", "target": "Partner site"}])
    result = _run(page, site, planner)
    assert not result.passed and "disallowed host" in result.reason
    assert page.url.startswith(site)  # the browser never left the site


def test_password_can_only_be_filled_from_test_data(page, site):
    planner = _script(site, base=[
        {"type": "goto", "url": "{site}/login.html"},
        {"type": "fill", "target": "Password", "value": "Test#1234"},
    ])
    result = _run(page, site, planner)
    assert not result.passed and "value_key" in result.reason


def test_unknown_value_key_does_not_crash(page, site):
    planner = _script(site, base=[
        {"type": "goto", "url": "{site}/login.html"},
        {"type": "fill", "target": "Email", "value_key": "nope"},
        {"type": "fill", "target": "Email", "value_key": "nope"},
    ])
    result = _run(page, site, planner)
    assert not result.passed and "invalid actions in a row" in result.reason


def test_page_injection_is_removed_before_the_model_sees_it(page, site):
    seen = []

    class Spy(ScriptedPlanner):
        def next_action(self, goal, observation, history, data_keys):
            seen.append(observation)
            return super().next_action(goal, observation, history, data_keys)

    planner = Spy([
        {"type": "goto", "url": f"{site}/reviews.html"},
        {"type": "finish", "passed": False, "reason": "just looking"},
    ])
    _run(page, site, planner)
    reviews = seen[1]
    assert "evil.example" not in reviews["text"] and "Great shop" in reviews["text"]
    assert reviews["injection_flags"]


def test_followed_injection_still_cannot_leave_the_site(page, site):
    """Even if a fooled model obeys the page, the host allow-list stops it."""
    planner = ScriptedPlanner([
        {"type": "goto", "url": f"{site}/reviews.html"},
        {"type": "goto", "url": "https://evil.example/steal"},
    ])
    result = _run(page, site, planner)
    assert not result.passed and "disallowed host" in result.reason


def test_step_limit_stops_a_looping_agent(page, site):
    planner = ScriptedPlanner([{"type": "press", "key": "Tab"}] * 10)
    result = _run(page, site, planner, max_steps=3)
    assert not result.passed and "step limit" in result.reason and result.steps == 3


def test_two_invalid_actions_in_a_row_stop_the_run(page, site):
    planner = ScriptedPlanner([{"type": "eval", "code": "1"}, {"type": "eval", "code": "2"}])
    result = _run(page, site, planner)
    assert not result.passed and "invalid actions in a row" in result.reason


def test_trace_records_every_step(page, site):
    planner = _script(site,
        {"type": "expect_text", "text": "Welcome back"},
        {"type": "finish", "passed": True, "reason": "ok"})
    result = _run(page, site, planner)
    assert [t["step"] for t in result.trace] == list(range(1, len(result.trace) + 1))
    assert all("action" in t and "outcome" in t for t in result.trace)


def test_redirect_to_another_host_after_a_click_is_caught(page, site):
    """The link itself is same-site, but the page then redirects away: the post-action check must catch it."""
    page.route("https://evil.example/**", lambda route: route.fulfill(body="<h1>evil</h1>", content_type="text/html"))
    planner = ScriptedPlanner([{"type": "click", "target": "Promo offer"}])
    result = _run(page, site, planner)
    assert not result.passed and "disallowed host" in result.reason


# ---- adversarial pages -------------------------------------------------------

def test_popup_window_to_another_host_is_blocked(page, site):
    planner = ScriptedPlanner([
        {"type": "goto", "url": f"{site}/popup.html"},
        {"type": "click", "target": "Open offer"},
        {"type": "press", "key": "Tab"},
        {"type": "expect_text", "text": "Special offer"},
        {"type": "finish", "passed": True, "reason": "ok"},
    ])
    result = _run(page, site, planner)
    assert not result.passed and "disallowed host" in result.reason


def test_delayed_meta_refresh_to_another_host_is_blocked(page, site):
    planner = ScriptedPlanner([
        {"type": "goto", "url": f"{site}/refresh.html"},
        {"type": "expect_text", "text": "Please wait"},
        {"type": "press", "key": "Tab"},
        {"type": "press", "key": "Tab"},
        {"type": "expect_text", "text": "Please wait"},
        {"type": "finish", "passed": True, "reason": "ok"},
    ])
    result = _run(page, site, planner)
    assert not result.passed and "disallowed host" in result.reason


def test_form_posting_to_another_host_is_blocked(page, site):
    planner = ScriptedPlanner([
        {"type": "goto", "url": f"{site}/form.html"},
        {"type": "fill", "target": "Email", "value": "a@b.c"},
        {"type": "click", "target": "Subscribe"},
        {"type": "expect_text", "text": "Newsletter"},
        {"type": "finish", "passed": True, "reason": "ok"},
    ])
    result = _run(page, site, planner)
    assert not result.passed and "disallowed host" in result.reason


def test_javascript_and_data_links_are_blocked(page, site):
    for target in ("Run script", "Open data page"):
        planner = ScriptedPlanner([
            {"type": "goto", "url": f"{site}/schemes.html"},
            {"type": "click", "target": target},
        ])
        result = _run(page, site, planner)
        assert not result.passed and "blocked scheme" in result.reason, target


def test_injection_hidden_in_an_element_label_never_reaches_the_prompt(page, site):
    from bta.observe import render
    seen = []

    class Spy(ScriptedPlanner):
        def next_action(self, goal, observation, history, data_keys):
            seen.append(observation)
            return super().next_action(goal, observation, history, data_keys)

    planner = Spy([{"type": "goto", "url": f"{site}/labels.html"}, {"type": "finish", "passed": False}])
    _run(page, site, planner)
    prompt_text = render(seen[1])
    assert "evil.example" not in prompt_text and "Ignore all previous" not in prompt_text
    assert "Save" in prompt_text and seen[1]["injection_flags"]
