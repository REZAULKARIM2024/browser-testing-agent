"""
actions.py
The ONLY things the agent is allowed to do. Anything the model proposes is
validated here first; unknown or malformed actions are rejected, not executed.
"""

ALLOWED_TYPES = ("goto", "click", "fill", "press", "expect_text", "expect_url_contains", "finish")
ALLOWED_KEYS = ("Enter", "Tab", "Escape")
MAX_TEXT_LEN = 200


class InvalidAction(ValueError):
    """The proposed action is malformed or not allowed."""


def _require_str(action: dict, field: str) -> str:
    value = action.get(field)
    if not isinstance(value, str) or not value.strip():
        raise InvalidAction(f"'{field}' must be a non-empty string for {action.get('type')!r}")
    if len(value) > MAX_TEXT_LEN:
        raise InvalidAction(f"'{field}' is longer than {MAX_TEXT_LEN} characters")
    return value


def validate_action(action) -> dict:
    """Returns the action if it is well-formed; raises InvalidAction otherwise."""
    if not isinstance(action, dict):
        raise InvalidAction("action must be a JSON object")
    kind = action.get("type")
    if kind not in ALLOWED_TYPES:
        raise InvalidAction(f"unknown action type {kind!r}; allowed: {ALLOWED_TYPES}")

    if kind == "goto":
        _require_str(action, "url")
    elif kind == "click":
        _require_str(action, "target")
    elif kind == "fill":
        _require_str(action, "target")
        has_value = isinstance(action.get("value"), str)
        has_key = isinstance(action.get("value_key"), str)
        if has_value == has_key:
            raise InvalidAction("'fill' needs exactly one of 'value' or 'value_key'")
        if has_value and len(action["value"]) > MAX_TEXT_LEN:
            raise InvalidAction(f"'value' is longer than {MAX_TEXT_LEN} characters")
    elif kind == "press":
        if action.get("key") not in ALLOWED_KEYS:
            raise InvalidAction(f"'key' must be one of {ALLOWED_KEYS}")
    elif kind == "expect_text":
        _require_str(action, "text")
    elif kind == "expect_url_contains":
        _require_str(action, "text")
    elif kind == "finish":
        if not isinstance(action.get("passed"), bool):
            raise InvalidAction("'finish' needs a boolean 'passed'")
        if not isinstance(action.get("reason", ""), str):
            raise InvalidAction("'reason' must be a string")
    return action
