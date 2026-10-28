"""Optional LLM tier (stdlib only). Used ONLY when policy.allow_llm is true AND the caller opts in,
never on files with Shield findings, and every result is test-gated like any other change."""
import json
import os
import urllib.request

API = "https://api.anthropic.com/v1/messages"


def available():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def ask(prompt, system="", max_tokens=2000):
    body = {"model": os.environ.get("REPOBRAIN_MODEL", "claude-sonnet-5-5"), "max_tokens": max_tokens,
            "system": system, "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(API, json.dumps(body).encode(), {
        "content-type": "application/json", "anthropic-version": "2023-06-01",
        "x-api-key": os.environ["ANTHROPIC_API_KEY"]})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
