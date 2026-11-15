import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import pytest

from repobrain import audit, auth, demo, gitutil, policy, server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_pr_cannot_inject_own_policy_when_base_has_no_policy(tmp_path):
    root = str(tmp_path)
    gitutil.git(root, "init", "-b", "main")
    gitutil.git(root, "config", "user.name", "Tester")
    gitutil.git(root, "config", "user.email", "tester@test.local")
    
    # Base commit with no repobrain.yml
    dummy = os.path.join(root, "app.py")
    with open(dummy, "w") as f:
        f.write("def foo(): return 1\n")
    gitutil.git(root, "add", "app.py")
    gitutil.git(root, "commit", "-m", "initial commit")

    # PR branch adds permissive repobrain.yml
    gitutil.git(root, "checkout", "-b", "pr-branch")
    pr_policy = os.path.join(root, "repobrain.yml")
    with open(pr_policy, "w") as f:
        f.write("blocked: []\ncomplexity_threshold: 999\n")
    gitutil.git(root, "add", "repobrain.yml")
    gitutil.git(root, "commit", "-m", "pr policy tampering")

    pol = policy.load_for(root, "main")
    # Must enforce trusted base defaults and reject PR's loosened policy
    assert pol["complexity_threshold"] == 10
    assert ".github/workflows/" in pol["blocked"]
    assert "trusted base fallback" in pol["_source"]


def test_preflight_path_traversal_blocked_before_disk_access(tmp_path):
    root = str(tmp_path)
    res = server.preflight(root, "agent", [{"path": "../../../etc/passwd"}])
    assert res["decision"] == "block"
    assert any("path escapes the repository" in f["msg"] for f in res["findings"])


def test_register_forces_developer_role_and_cannot_self_escalate():
    with tempfile.TemporaryDirectory() as td:
        mgr = auth.AuthManager(td, is_demo=False)
        user, tok = mgr.register(
            email="mallory@evil-corp.internal",
            password="Password123!",
            name="Mallory",
            role="admin"  # Maliciously attempt to self-provision admin
        )
        # Forced to developer
        assert user["role"] == "developer"
        assert user["role_badge"] == "DEV"
        assert "manage_users" not in user["permissions"]


def test_audit_verification_fails_when_signatures_present_but_key_missing(tmp_path, monkeypatch):
    log_dir = str(tmp_path)
    monkeypatch.setenv("REPOBRAIN_AUDIT_KEY", "secret-test-key-12345")
    log = audit.AuditLog(log_dir)
    log.append("test-event", "actor", "ALLOWED", "test detail")
    
    # Verify with key succeeds
    assert log.verify()["ok"] is True

    # Remove key: verification must fail rather than passing silently
    monkeypatch.delenv("REPOBRAIN_AUDIT_KEY", raising=False)
    v = log.verify()
    assert v["ok"] is False
    assert "REPOBRAIN_AUDIT_KEY is not configured" in v["reason"]


def test_optimizer_commit_scoped_to_proposal_paths(tmp_path):
    from repobrain import optimizer
    root = str(tmp_path)
    gitutil.git(root, "init", "-b", "main")
    gitutil.git(root, "config", "user.name", "Tester")
    gitutil.git(root, "config", "user.email", "tester@test.local")
    
    # Create test repo files
    f1 = os.path.join(root, "f1.py")
    with open(f1, "w") as f:
        f.write("def f1():\n    return 1\n")
    gitutil.git(root, "add", "f1.py")
    gitutil.git(root, "commit", "-m", "init")

    # Stage an extra unapproved file
    extra = os.path.join(root, "extra.txt")
    with open(extra, "w") as f:
        f.write("unapproved staged content")
    gitutil.git(root, "add", "extra.txt")

    # Apply proposal for f1.py only
    home = os.path.join(root, ".repobrain")
    os.makedirs(os.path.join(home, "proposals"), exist_ok=True)
    pid = "20261115-120000-abcdef"
    prop = {
        "id": pid,
        "head": gitutil.head(root),
        "applicable": True,
        "files": [{"path": "f1.py", "before_sha": optimizer.sha("def f1():\n    return 1\n"), "after": "def f1():\n    return 2\n"}]
    }
    with open(os.path.join(home, "proposals", f"{pid}.json"), "w") as f:
        json.dump(prop, f)

    res = optimizer.apply(root, home, pid, "Alex Mercer\nInject-Trailer: Bad")
    
    # extra.txt must NOT be committed
    diff_staged = gitutil.git(root, "diff", "--cached", "--name-only")
    assert "extra.txt" in diff_staged
    # Log commit message should have sanitized actor
    last_log = gitutil.git(root, "log", "-1")
    assert "Approved-by: Alex Mercer Inject-Trailer: Bad" in last_log


def test_server_security_guards_and_non_demo_isolation():
    """Verify non-demo mode access token requirement, fail-closed auth, and Content-Length guards."""
    import socket, time
    with tempfile.TemporaryDirectory() as td:
        repo_dir = os.path.join(td, "repo")
        home_dir = os.path.join(td, "home")
        demo.seed(repo_dir)
        port = 8798
        # Start server in production (non-demo) mode
        cmd = [sys.executable, "-m", "repobrain", "--repo", repo_dir, "--home", home_dir, "serve", "--no-browser", "--port", str(port)]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            line = proc.stdout.readline()
            tok_match = None
            for _ in range(20):
                if not line:
                    break
                m = re.search(r"t=(\S+)", line)
                if m:
                    tok_match = m.group(1)
                    break
                line = proc.stdout.readline()
            assert tok_match is not None, "Failed to extract server per-run token"

            def req(path, token_hdr=None, x_hdr=None, body=None, cl_override=None, method="GET"):
                h = {"Content-Type": "application/json"}
                if token_hdr:
                    h["X-RepoBrain-Token"] = token_hdr
                if x_hdr:
                    h["X-RepoBrain"] = x_hdr
                data = json.dumps(body).encode() if body is not None else None
                if cl_override is not None:
                    h["Content-Length"] = str(cl_override)
                r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=h, method=method)
                try:
                    with urllib.request.urlopen(r, timeout=3) as resp:
                        return resp.status, resp.read().decode()
                except urllib.error.HTTPError as e:
                    return e.code, e.read().decode()

            # 1. Access token required: static X-RepoBrain: 1 does NOT grant access without token
            st, _ = req("/api/state", token_hdr="", x_hdr="1")
            assert st == 401, f"Expected 401 without token, got {st}"

            # Valid token works
            st, _ = req("/api/state", token_hdr=tok_match)
            assert st == 200

            # 2. Content-Length: -1 rejected with 400 (does not hang)
            st, _ = req("/api/review", token_hdr=tok_match, body={}, cl_override=-1, method="POST")
            assert st == 400

            # 3. switch-demo-role fails in production mode (requires --demo)
            st, _ = req("/api/auth/switch-demo-role", token_hdr=tok_match, body={"role": "admin"}, method="POST")
            assert st == 403

            # 4. Fail-closed: update-role and waive without user session fail with 403
            st, _ = req("/api/auth/update-role", token_hdr=tok_match, body={"email": "x@corp.internal", "role": "admin"}, method="POST")
            assert st == 403
            st, _ = req("/api/waive", token_hdr=tok_match, body={"actor": "Anonymous", "reason": "test"}, method="POST")
            assert st == 403

        finally:
            proc.terminate()
            proc.wait()

