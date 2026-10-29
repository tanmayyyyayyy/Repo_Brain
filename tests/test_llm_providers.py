"""Provider plumbing against a local mock server (no network, no real key)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from repobrain import llm

SEEN = {}


class Mock(BaseHTTPRequestHandler):
    hits = 0

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.update(path=self.path, auth=self.headers.get("authorization"), ua=self.headers.get("user-agent"), body=body)
        Mock.hits += 1
        if self.headers.get("authorization") != "Bearer gsk_test":
            return self._j(401, {"error": {"message": "invalid api key"}})
        if "ratelimit" in body["messages"][-1]["content"] and Mock.hits % 2 == 1:
            self.send_response(429); self.send_header("retry-after", "0"); self.end_headers(); return
        if "empty" in body["messages"][-1]["content"]:
            return self._j(200, {"choices": [{"message": {"content": ""}}]})
        self._j(200, {"choices": [{"message": {"content": "```python\nx = 1\n```"}}]})

    def _j(self, code, obj):
        d = json.dumps(obj).encode()
        self.send_response(code); self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(d))); self.end_headers(); self.wfile.write(d)


@pytest.fixture()
def groq(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("REPOBRAIN_LLM_BASE_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.delenv("REPOBRAIN_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("REPOBRAIN_MODEL", raising=False)
    Mock.hits = 0
    yield
    srv.shutdown()


def test_provider_autodetect(monkeypatch):
    monkeypatch.delenv("REPOBRAIN_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert llm.provider() == "anthropic" and not llm.available()
    monkeypatch.setenv("GROQ_API_KEY", "x")
    assert llm.provider() == "groq" and llm.available() and llm.key_env() == "GROQ_API_KEY"


def test_groq_request_shape_and_user_agent(groq):
    assert "x = 1" in llm.ask("hello", "be brief")
    assert SEEN["path"] == "/chat/completions" and SEEN["auth"] == "Bearer gsk_test"
    assert SEEN["ua"].startswith("repobrain/") and "python-urllib" not in SEEN["ua"].lower()
    assert SEEN["body"]["messages"][0] == {"role": "system", "content": "be brief"}
    assert SEEN["body"]["model"] == "openai/gpt-oss-120b" and SEEN["body"]["max_tokens"] >= 4096


def test_model_override_and_clear_errors(groq, monkeypatch):
    monkeypatch.setenv("REPOBRAIN_MODEL", "llama-3.3-70b-versatile")
    llm.ask("hi")
    assert SEEN["body"]["model"] == "llama-3.3-70b-versatile"
    monkeypatch.setenv("GROQ_API_KEY", "wrong")
    with pytest.raises(llm.LLMError, match="401.*check the API key"):
        llm.ask("hi")
    with pytest.raises(llm.LLMError, match="empty reply"):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test"); llm.ask("empty please")


def test_rate_limit_is_retried(groq):
    assert "x = 1" in llm.ask("ratelimit please")
    assert Mock.hits == 2


def test_missing_key_message(monkeypatch):
    monkeypatch.setenv("REPOBRAIN_LLM_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(llm.LLMError, match="GROQ_API_KEY not set"):
        llm.ask("hi")
