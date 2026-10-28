import hashlib
import hmac
import json
import pytest

from repobrain import webhook


def test_webhook_verify_signature_valid():
    secret = "my-webhook-secret-12345"
    payload = json.dumps({"action": "opened"}).encode("utf-8")
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert webhook.verify_signature(payload, secret, sig) is True


def test_webhook_verify_signature_invalid():
    secret = "my-webhook-secret-12345"
    payload = json.dumps({"action": "opened"}).encode("utf-8")
    # Tampered signature
    assert webhook.verify_signature(payload, secret, "sha256=deadbeef" * 8) is False
    # Wrong secret
    sig = "sha256=" + hmac.new(b"other-secret", payload, hashlib.sha256).hexdigest()
    assert webhook.verify_signature(payload, secret, sig) is False
    # Missing sha256= prefix
    assert webhook.verify_signature(payload, secret, "invalid_header") is False
    # Empty signature
    assert webhook.verify_signature(payload, secret, "") is False


def test_webhook_handle_ping():
    payload = {"zen": "Keep it logically awesome."}
    res = webhook.handle_event("ping", payload)
    assert res["status"] == "ok"
    assert res["message"] == "pong"
    assert res["zen"] == "Keep it logically awesome."


def test_webhook_handle_pull_request():
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "head": {"sha": "abcdef1234567890"},
            "base": {"ref": "main"},
        },
        "repository": {"full_name": "acme/repo"},
        "sender": {"login": "copilot-swe-agent[bot]"},
    }
    res = webhook.handle_event("pull_request", payload)
    assert res["status"] == "received"
    assert res["pr_number"] == 42
    assert res["review_dispatchable"] is True
    assert res["sender"] == "copilot-swe-agent[bot]"
