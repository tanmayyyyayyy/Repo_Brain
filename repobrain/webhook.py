"""GitHub App webhook endpoint skeleton.

Handles GitHub webhook delivery with HMAC-SHA256 payload signature verification.
Roadmap module: provides the server-side receiver for GitHub App integration.
"""
import hashlib
import hmac
import json
import os


def verify_signature(payload_bytes: bytes, secret: str, signature_header: str) -> bool:
    """Validate GitHub X-Hub-Signature-256 header using constant-time comparison."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected_hex = signature_header[7:].strip()
    mac = hmac.new(secret.encode("utf-8"), msg=payload_bytes, digestmod=hashlib.sha256)
    computed_hex = mac.hexdigest()
    return hmac.compare_digest(expected_hex.lower(), computed_hex.lower())


def handle_event(event_type: str, payload: dict, secret: str = None) -> dict:
    """Process a verified GitHub webhook payload."""
    if event_type == "ping":
        return {"status": "ok", "message": "pong", "zen": payload.get("zen", "")}

    if event_type == "pull_request":
        action = payload.get("action")
        pr = payload.get("pull_request", {})
        repo = payload.get("repository", {})
        number = pr.get("number")
        head_sha = pr.get("head", {}).get("sha", "")
        base_ref = pr.get("base", {}).get("ref", "")
        sender = payload.get("sender", {}).get("login", "")

        return {
            "status": "received",
            "action": action,
            "pr_number": number,
            "head_sha": head_sha,
            "base_ref": base_ref,
            "sender": sender,
            "repo_name": repo.get("full_name", ""),
            "review_dispatchable": action in ("opened", "synchronize", "reopened"),
        }

    return {"status": "ignored", "event": event_type, "message": "Unhandled event type"}
