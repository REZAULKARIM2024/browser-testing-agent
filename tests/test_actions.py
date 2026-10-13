import pytest

from bta.actions import InvalidAction, validate_action


@pytest.mark.parametrize("action", [
    {"type": "goto", "url": "http://x.test/a"},
    {"type": "click", "target": "Sign in"},
    {"type": "fill", "target": "Email", "value": "a@b.c"},
    {"type": "fill", "target": "Password", "value_key": "password"},
    {"type": "press", "key": "Enter"},
    {"type": "expect_text", "text": "Welcome"},
    {"type": "expect_url_contains", "text": "/dashboard"},
    {"type": "finish", "passed": True, "reason": "ok"},
])
def test_valid_actions_pass(action):
    assert validate_action(action) is action


@pytest.mark.parametrize("action", [
    "click the button",                                   # not an object
    {"type": "eval", "code": "alert(1)"},                  # not in the allow-list
    {"type": "click"},                                      # missing target
    {"type": "click", "target": "   "},                    # blank target
    {"type": "fill", "target": "x"},                        # no value or value_key
    {"type": "fill", "target": "x", "value": "a", "value_key": "b"},  # both
    {"type": "press", "key": "F12"},                        # key not allowed
    {"type": "finish", "passed": "yes"},                    # not a bool
    {"type": "expect_text", "text": "x" * 500},             # too long
    {"type": "invalid_output", "raw": "garbage"},
])
def test_invalid_actions_are_rejected(action):
    with pytest.raises(InvalidAction):
        validate_action(action)
