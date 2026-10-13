"""ClaudePlanner with a fake Anthropic client: offline, free."""
from types import SimpleNamespace

from bta.planner import SYSTEM_PROMPT, ClaudePlanner, parse_action

OBS = {"url": "http://x.test/login", "title": "Log in", "text": "Log in", "injection_flags": [],
       "elements": [{"id": 0, "tag": "input", "type": "password", "name": "Password", "href": ""}]}


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.reply)])


def test_parse_plain_and_fenced_json():
    assert parse_action('{"type": "click", "target": "Go"}')["type"] == "click"
    assert parse_action('```json\n{"type": "press", "key": "Enter"}\n```')["key"] == "Enter"
    assert parse_action('Sure! {"type": "finish", "passed": false, "reason": "x"} done')["type"] == "finish"


def test_garbage_becomes_an_invalid_marker_not_an_exception():
    assert parse_action("I cannot do that")["type"] == "invalid_output"
    assert parse_action("{not json}")["type"] == "invalid_output"
    assert parse_action("[1, 2]")["type"] == "invalid_output"


def test_planner_sends_goal_keys_and_untrusted_page_but_never_secret_values():
    client = FakeClient('{"type": "fill", "target": "Password", "value_key": "password"}')
    action = ClaudePlanner(client).next_action("log in", OBS, [], ["email", "password"])
    sent = client.calls[0]["messages"][0]["content"]
    assert action == {"type": "fill", "target": "Password", "value_key": "password"}
    assert "log in" in sent and "email, password" in sent
    assert "<page>" in sent and "</page>" in sent
    assert "Test#1234" not in sent            # values are never part of the prompt
    assert "untrusted" in client.calls[0]["system"] and client.calls[0]["system"] == SYSTEM_PROMPT


def test_history_is_included_and_truncated():
    history = [{"action": {"type": "press", "key": "Tab"}, "outcome": f"ok{i}"} for i in range(20)]
    client = FakeClient('{"type": "finish", "passed": false}')
    ClaudePlanner(client).next_action("g", OBS, history, [])
    sent = client.calls[0]["messages"][0]["content"]
    assert "ok19" in sent and "ok0 " not in sent and "ok11" not in sent
