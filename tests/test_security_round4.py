import collections
import ipaddress
import os
import time
import pytest

from repobrain import auth, server


def test_item1_client_ip_ignores_spoofed_xff_when_peer_not_trusted(monkeypatch):
    # Ensure trusted proxies is empty or does not include peer
    monkeypatch.setenv("REPOBRAIN_TRUSTED_PROXIES", "10.0.0.1")
    
    # Mock handler with untrusted socket peer 198.51.100.1
    class DummyHandler:
        client_address = ("198.51.100.1", 54321)
        headers = {"X-Forwarded-For": "203.0.113.99", "X-Real-IP": "203.0.113.99"}

    # Should ignore XFF and return the actual socket peer
    client_ip = server.resolve_client_ip(DummyHandler())
    assert client_ip == "198.51.100.1", f"Expected untrusted peer IP 198.51.100.1, got {client_ip}"


def test_item1_client_ip_resolves_rightmost_untrusted_from_trusted_proxy(monkeypatch):
    # Peer is a trusted reverse proxy
    monkeypatch.setenv("REPOBRAIN_TRUSTED_PROXIES", "10.0.0.0/8,172.16.0.0/12,127.0.0.1")

    class DummyHandler:
        client_address = ("10.0.0.2", 12345)
        # Client 203.0.113.50 went through intermediate proxy 172.16.1.1 then 10.0.0.2
        headers = {"X-Forwarded-For": "203.0.113.50, 172.16.1.1"}

    client_ip = server.resolve_client_ip(DummyHandler())
    assert client_ip == "203.0.113.50", f"Expected rightmost non-trusted IP 203.0.113.50, got {client_ip}"


def test_item1_rate_limiter_memory_is_bounded():
    limiter = server.BoundedRateLimiter(max_keys=10, window=60, max_attempts=5)
    for i in range(50):
        limiter.check(f"user_{i}")
    assert len(limiter) <= 10, f"Limiter memory exceeded max_keys: {len(limiter)}"


def test_item1_rate_limiter_enforces_separate_ip_and_email_limits():
    limiter = server.BoundedRateLimiter(max_keys=100, window=60, max_attempts=5)
    # 5 failed attempts from same IP
    for _ in range(5):
        assert limiter.check("ip:198.51.100.1") is True
    # 6th attempt from same IP blocked
    assert limiter.check("ip:198.51.100.1") is False

    # Different IP with same email: email key is checked separately
    for _ in range(5):
        assert limiter.check("email:target@company.internal") is True
    # 6th attempt for email blocked regardless of IP
    assert limiter.check("email:target@company.internal") is False


# ==============================================================================
# ITEM 2: OTP / Email Verification Security
# ==============================================================================

def test_item2_wrong_code_x5_locks_code(tmp_path):
    from repobrain import auth
    mgr = auth.AuthManager(str(tmp_path), is_demo=True)
    user, _ = mgr.register("alice@corp.internal", "SecurePassword123!", "Alice")
    assert user["email_verified"] is False
    
    # 5 wrong attempts
    for i in range(5):
        with pytest.raises(ValueError, match=r"Invalid verification code|remaining"):
            mgr.verify_email("alice@corp.internal", "000000")
            
    # 6th attempt must indicate locked out
    with pytest.raises(ValueError, match=r"exceeded maximum attempt limit|locked"):
        mgr.verify_email("alice@corp.internal", "000000")


def test_item2_expired_code_rejected(tmp_path):
    from repobrain import auth
    mgr = auth.AuthManager(str(tmp_path), is_demo=True)
    user, _ = mgr.register("bob@corp.internal", "SecurePassword123!", "Bob")
    
    # Manually expire the code in storage
    with mgr._lock:
        mgr._users["bob@corp.internal"]["otp_expires_at"] = time.time() - 10
        mgr._save_users()
        
    code = mgr.get_last_otp_for_test("bob@corp.internal")
    with pytest.raises(ValueError, match=r"expired"):
        mgr.verify_email("bob@corp.internal", code)


def test_item2_resend_rate_limit_and_window_attempt_limit(tmp_path):
    from repobrain import auth
    mgr = auth.AuthManager(str(tmp_path), is_demo=True)
    user, _ = mgr.register("charlie@corp.internal", "SecurePassword123!", "Charlie")
    
    # 3 attempts on initial code
    for _ in range(3):
        with pytest.raises(ValueError):
            mgr.verify_email("charlie@corp.internal", "000000")
            
    # Resend code
    mgr.resend_verification_code("charlie@corp.internal")
    
    # 2 more attempts on new code (total = 5 in this window)
    for _ in range(2):
        with pytest.raises(ValueError):
            mgr.verify_email("charlie@corp.internal", "000000")
            
    # 6th attempt total must be rejected (window exhausted)
    with pytest.raises(ValueError, match=r"exceeded|locked"):
        mgr.verify_email("charlie@corp.internal", "000000")

    # Resend should also reject because window attempts are exhausted
    with pytest.raises(ValueError, match=r"exceeded|locked"):
        mgr.resend_verification_code("charlie@corp.internal")
        
    # Rate limit resends: 3 per hour max (tested on a fresh user)
    mgr.register("charlie2@corp.internal", "SecurePassword123!", "Charlie2")
    mgr.resend_verification_code("charlie2@corp.internal")
    mgr.resend_verification_code("charlie2@corp.internal")
    mgr.resend_verification_code("charlie2@corp.internal")
    # 4th resend in the hour should raise rate limit error
    with pytest.raises(ValueError, match=r"Too many resend requests|rate limit"):
        mgr.resend_verification_code("charlie2@corp.internal")


def test_item2_unverified_user_denied_every_permission(tmp_path):
    from repobrain import auth
    mgr = auth.AuthManager(str(tmp_path), is_demo=True)
    user, token = mgr.register("dave@corp.internal", "SecurePassword123!", "Dave")
    
    assert user["email_verified"] is False
    
    # check_permission must return False for all permissions
    all_perms = [
        "view_pr", "run_optimizer", "run_tests", "request_review",
        "inspect_fuzzing", "inspect_coverage", "run_explainer",
        "configure_shield", "inspect_secrets", "verify_audit",
        "simulate_tamper", "apply_approval", "grant_waiver", "manage_users"
    ]
    for perm in all_perms:
        assert auth.check_permission(user, perm) is False, f"Permission {perm} should be denied to unverified user"


def test_item2_otp_never_in_api_response_or_on_disk(tmp_path):
    import json
    from repobrain import auth
    mgr = auth.AuthManager(str(tmp_path), is_demo=True)
    user, _ = mgr.register("eve@corp.internal", "SecurePassword123!", "Eve")
    resend = mgr.resend_verification_code("eve@corp.internal")
    
    # Check return structures
    assert "otp" not in user and "code" not in user
    assert "otp" not in resend and "code" not in resend
    
    # Check users.json on disk
    users_file = os.path.join(str(tmp_path), "users.json")
    with open(users_file, "r") as f:
        data = json.load(f)
    u_rec = data["eve@corp.internal"]
    assert "verification_code" not in u_rec
    assert "raw_code" not in u_rec
    # Only hash should exist
    assert "otp_hash" in u_rec


def test_item2_non_demo_without_smtp_fails_closed(tmp_path, monkeypatch):
    from repobrain import auth
    monkeypatch.delenv("REPOBRAIN_SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    
    mgr = auth.AuthManager(str(tmp_path), is_demo=False)
    with pytest.raises(ValueError, match=r"SMTP"):
        mgr.register("frank@corp.internal", "SecurePassword123!", "Frank")


def test_item2_hmac_sha256_storage(tmp_path, monkeypatch):
    import hmac
    import hashlib
    from repobrain import auth
    monkeypatch.setenv("REPOBRAIN_SECRET", "test-secret-key-32-bytes-long-super")
    mgr = auth.AuthManager(str(tmp_path), is_demo=True)
    user, _ = mgr.register("grace@corp.internal", "SecurePassword123!", "Grace")
    
    code = mgr.get_last_otp_for_test("grace@corp.internal")
    salt = mgr._users["grace@corp.internal"]["otp_salt"]
    expected_hmac = hmac.new(b"test-secret-key-32-bytes-long-super", f"{salt}:{code}".encode("utf-8"), hashlib.sha256).hexdigest()
    assert mgr._users["grace@corp.internal"]["otp_hash"] == expected_hmac


def test_item2_stdout_printing_controls(tmp_path, monkeypatch, capsys):
    from repobrain import auth
    
    # 1. Non-demo mode: never print to stdout
    monkeypatch.setenv("REPOBRAIN_SMTP_HOST", "smtp.corp.internal")
    mgr_prod = auth.AuthManager(str(tmp_path / "prod"), is_demo=False)
    mgr_prod.register("prod@corp.internal", "SecurePassword123!", "Prod")
    captured = capsys.readouterr()
    assert "verification code" not in captured.out.lower()
    
    # 2. Demo mode without REPOBRAIN_DEMO_PRINT_OTP=1: do not print
    monkeypatch.delenv("REPOBRAIN_DEMO_PRINT_OTP", raising=False)
    mgr_demo_silent = auth.AuthManager(str(tmp_path / "demo1"), is_demo=True)
    mgr_demo_silent.register("demo1@corp.internal", "SecurePassword123!", "Demo1")
    captured = capsys.readouterr()
    assert "verification code" not in captured.out.lower()
    
    # 3. Demo mode with REPOBRAIN_DEMO_PRINT_OTP=1: print
    monkeypatch.setenv("REPOBRAIN_DEMO_PRINT_OTP", "1")
    mgr_demo_loud = auth.AuthManager(str(tmp_path / "demo2"), is_demo=True)
    mgr_demo_loud.register("demo2@corp.internal", "SecurePassword123!", "Demo2")
    captured = capsys.readouterr()
    assert "verification code" in captured.out.lower()


# ==============================================================================
# ITEM 3: Demo Workspace Isolation
# ==============================================================================

def test_item3_two_concurrent_anonymous_visitors_get_distinct_paths(tmp_path):
    root = os.path.join(str(tmp_path), "base_repo")
    from repobrain import demo
    demo.seed(root)
    home = os.path.join(str(tmp_path), "home")
    ctx = server.Ctx(root, "main", home, is_demo=True)

    wid1 = ctx.create_valid_wid()
    wid2 = ctx.create_valid_wid()
    assert wid1 != wid2

    root1 = ctx.get_workspace_root(wid1)
    root2 = ctx.get_workspace_root(wid2)
    assert root1 != root2
    assert os.path.isdir(root1)
    assert os.path.isdir(root2)


def test_item3_forged_cookie_cannot_collide_with_existing(tmp_path):
    root = os.path.join(str(tmp_path), "base_repo")
    from repobrain import demo
    demo.seed(root)
    home = os.path.join(str(tmp_path), "home")
    ctx = server.Ctx(root, "main", home, is_demo=True)

    legit_wid = ctx.create_valid_wid()
    assert ctx.is_valid_wid(legit_wid) is True

    # Forged wid never issued by server
    forged_wid = "0123456789abcdef0123456789abcdef"
    assert ctx.is_valid_wid(forged_wid) is False

    # Validation should reject forged wid and issue a fresh one
    resolved_wid = ctx.resolve_or_create_wid(forged_wid)
    assert resolved_wid != forged_wid
    assert resolved_wid != legit_wid
    assert ctx.is_valid_wid(resolved_wid) is True


def test_item3_in_use_workspace_not_pruned_while_request_in_flight(tmp_path):
    root = os.path.join(str(tmp_path), "base_repo")
    from repobrain import demo
    demo.seed(root)
    home = os.path.join(str(tmp_path), "home")
    ctx = server.Ctx(root, "main", home, is_demo=True)
    ctx.MAX_DEMO_WORKSPACES = 2

    w1 = ctx.create_valid_wid()
    r1 = ctx.get_workspace_root(w1)

    # Put w1 in-use
    with ctx.acquire_workspace(w1):
        # Force expiration of w1
        with ctx._lock:
            ctx._workspace_access[w1] = time.time() - 99999

        # Create two more workspaces to exceed MAX_DEMO_WORKSPACES (capacity 2)
        w2 = ctx.create_valid_wid()
        ctx.get_workspace_root(w2)
        w3 = ctx.create_valid_wid()
        ctx.get_workspace_root(w3)

        # Trigger cleanup
        ctx._cleanup_workspaces()

        # w1 must still exist because refcount > 0
        assert os.path.isdir(r1), "In-use workspace must not be pruned while request in flight"

    # Once released, cleanup should prune expired w1
    ctx._cleanup_workspaces()
    assert not os.path.isdir(r1), "Expired workspace should be pruned after request finishes"


def test_item3_http_handler_sets_cookie_and_isolates_workspaces(tmp_path):
    root = os.path.join(str(tmp_path), "base_repo")
    from repobrain import demo
    demo.seed(root)
    home = os.path.join(str(tmp_path), "home")
    ctx = server.Ctx(root, "main", home, is_demo=True)
    
    handler_class = server.make_handler(ctx, token="test-tok", port=8000, host="127.0.0.1", open_demo=True)
    
    # 1. Anonymous request without cookie
    class DummyAnonRequest:
        headers = {"Host": "127.0.0.1"}
        path = "/api/state"
        client_address = ("127.0.0.1", 12345)
    
    h1 = handler_class.__new__(handler_class)
    h1.headers = DummyAnonRequest.headers
    h1.path = DummyAnonRequest.path
    h1.client_address = DummyAnonRequest.client_address
    
    wid1 = h1._get_demo_wid()
    assert wid1 is not None
    assert len(wid1) == 32
    assert getattr(h1, "_new_demo_wid", None) == wid1

    # 2. Forged cookie request
    h2 = handler_class.__new__(handler_class)
    h2.headers = {"Host": "127.0.0.1", "Cookie": "repobrain_demo_wid=forged000000000000000000000000000"}
    h2.path = "/api/state"
    h2.client_address = ("127.0.0.1", 12346)
    
    wid2 = h2._get_demo_wid()
    assert wid2 is not None
    assert wid2 != "forged000000000000000000000000000"
    assert wid2 != wid1


# ==============================================================================
# ITEM 4: bootstrap_admin restricted to CLI & env vars (never HTTP)
# ==============================================================================

def test_item4_no_http_endpoint_exposes_bootstrap_admin(tmp_path):
    root = os.path.join(str(tmp_path), "base_repo")
    from repobrain import demo
    demo.seed(root)
    home = os.path.join(str(tmp_path), "home")
    ctx = server.Ctx(root, "main", home, is_demo=False)
    
    # In route(), neither /api/auth/bootstrap-admin nor /api/bootstrap-admin should exist
    with pytest.raises(Exception):
        server.route(ctx, "/api/auth/bootstrap-admin", {"email": "evil@corp.internal", "password": "Password123!"})
    with pytest.raises(Exception):
        server.route(ctx, "/api/bootstrap-admin", {"email": "evil@corp.internal", "password": "Password123!"})


def test_item4_cli_create_admin_on_empty_db_and_refuses_duplicate(tmp_path):
    from repobrain import cli
    home = str(tmp_path)
    
    # 1. Success on empty db
    rc = cli.main(["--home", home, "create-admin", "--email", "admin@enterprise.internal", "--password", "AdminPassword123!", "--name", "Root Admin"])
    assert rc == 0
    
    mgr = auth.AuthManager(home, is_demo=False)
    admin = mgr._users.get("admin@enterprise.internal")
    assert admin is not None
    assert admin["role"] == "admin"
    assert admin["email_verified"] is True
    
    # 2. Second attempt must fail
    rc2 = cli.main(["--home", home, "create-admin", "--email", "admin2@enterprise.internal", "--password", "AdminPassword123!", "--name", "Second Admin"])
    assert rc2 != 0


def test_item4_cli_create_admin_enforces_password_length(tmp_path):
    from repobrain import cli
    home = str(tmp_path)
    # Password shorter than 12 chars
    rc = cli.main(["--home", home, "create-admin", "--email", "admin@enterprise.internal", "--password", "Short123!"])
    assert rc != 0


def test_item4_env_vars_create_admin_once_and_are_scrubbed(tmp_path, monkeypatch):
    monkeypatch.setenv("REPOBRAIN_BOOTSTRAP_ADMIN_EMAIL", "envadmin@enterprise.internal")
    monkeypatch.setenv("REPOBRAIN_BOOTSTRAP_ADMIN_PASSWORD", "SuperSecurePassword2026!")
    
    root = os.path.join(str(tmp_path), "base_repo")
    from repobrain import demo
    demo.seed(root)
    home = os.path.join(str(tmp_path), "home")
    
    ctx = server.Ctx(root, "main", home, is_demo=False)
    
    # Env vars must be scrubbed from os.environ
    assert "REPOBRAIN_BOOTSTRAP_ADMIN_EMAIL" not in os.environ
    assert "REPOBRAIN_BOOTSTRAP_ADMIN_PASSWORD" not in os.environ
    
    # Admin must exist
    mgr = auth.AuthManager(home, is_demo=False)
    admin = mgr._users.get("envadmin@enterprise.internal")
    assert admin is not None
    assert admin["role"] == "admin"


# ==============================================================================
# ITEM 5: Audit Log Robustness & DoS Surface
# ==============================================================================

def test_item5_corrupt_tail_quarantined_and_recovery_entry_written(tmp_path):
    from repobrain import audit as A
    home = str(tmp_path)
    log = A.AuditLog(home)
    
    # Write a valid entry
    log.append("test-event-1", "alice", "ALLOWED", "Initial entry")
    
    # Corrupt the tail by appending garbage
    with open(log.path, "a", encoding="utf-8") as f:
        f.write('{"seq": 2, "broken JSON without closing\n')
        
    # Append should trigger quarantine recovery
    rec = log.append("test-event-2", "bob", "ALLOWED", "Post-crash entry")
    
    # Quarantined file must exist
    corrupt_files = [fn for fn in os.listdir(home) if fn.startswith("audit.corrupt.")]
    assert len(corrupt_files) == 1, f"Expected 1 quarantined file, found {corrupt_files}"
    
    # New ledger must contain recovery entry as first entry
    entries = log.entries()
    assert len(entries) == 2
    assert entries[0]["event"] == "audit-recovery"
    assert entries[0]["seq"] == 1
    assert entries[0]["prev"] == A.GENESIS
    assert entries[0]["quarantined_file"] == corrupt_files[0]
    assert log.is_recovery_pending() is True


def test_item5_approve_and_apply_refused_while_recovery_pending(tmp_path):
    from repobrain import audit as A, optimizer
    root = os.path.join(str(tmp_path), "base_repo")
    from repobrain import demo
    demo.seed(root)
    home = os.path.join(str(tmp_path), "home")
    ctx = server.Ctx(root, "main", home, is_demo=False)
    
    # Mark recovery pending
    ctx.log.set_recovery_pending(True, "audit.corrupt.test")
    
    # Route /api/approve must be refused
    with pytest.raises(PermissionError, match=r"recovery"):
        server.route(ctx, "/api/approve", {"id": "prop-123", "actor": "Alice"}, user={"role": "admin", "email_verified": True})
        
    # optimizer.apply must be refused
    with pytest.raises(PermissionError, match=r"recovery"):
        optimizer.apply(root, {"id": "prop-123", "files": []}, actor="Alice", home=home)


def test_item5_ack_recovery_clears_flag(tmp_path):
    from repobrain import audit as A
    home = str(tmp_path)
    log = A.AuditLog(home)
    log.set_recovery_pending(True, "audit.corrupt.test")
    assert log.is_recovery_pending() is True
    
    res = log.ack_recovery("admin@corp.internal")
    assert res["ok"] is True
    assert log.is_recovery_pending() is False
    
    # Recovery ack entry logged
    entries = log.entries()
    assert any(e.get("event") == "audit-recovery-ack" for e in entries)


def test_item5_verify_reports_broken_chain_across_quarantine(tmp_path):
    from repobrain import audit as A
    home = str(tmp_path)
    log = A.AuditLog(home)
    log.append("test-event-1", "alice", "ALLOWED")
    with open(log.path, "a", encoding="utf-8") as f:
        f.write("{corrupt-tail\n")
        
    log.append("test-event-2", "bob", "ALLOWED")
    
    # While recovery is pending, verify must fail
    v = log.verify()
    assert v["ok"] is False
    assert "recovery" in v["reason"].lower() or "quarantined" in v["reason"].lower()


def test_item5_cached_verification_avoids_reverifying_old_records(tmp_path):
    from repobrain import audit as A
    home = str(tmp_path)
    log = A.AuditLog(home)
    for i in range(10):
        log.append(f"event-{i}", "system", "ALLOWED")
        
    v1 = log.verify()
    assert v1["ok"] is True
    
    # Second verify with no changes should return cached result without scanning
    v2 = log.verify()
    assert v2["ok"] is True
    assert v2.get("cached", False) is True


def test_item5_rate_limit_preflight_and_tamper_blocked_outside_demo(tmp_path):
    root = os.path.join(str(tmp_path), "base_repo")
    from repobrain import demo
    demo.seed(root)
    home = os.path.join(str(tmp_path), "home")
    ctx = server.Ctx(root, "main", home, is_demo=False)
    
    # 1. Tamper blocked outside demo without permissions
    with pytest.raises(PermissionError):
        server.route(ctx, "/api/audit/tamper", {}, user=None)
        
    # 2. Preflight rate limiter enforces max 60/min
    limiter = server.PREFLIGHT_LIMITER
    for _ in range(60):
        assert limiter.check("ip:203.0.113.10") is True
    # 61st attempt blocked
    assert limiter.check("ip:203.0.113.10") is False


# ==============================================================================
# ITEM 6: AI-Identity Spoofing & Trusted CI Identity
# ==============================================================================

def test_item6_bot_suffix_treated_as_ai():
    from repobrain import policy as P
    pol = P.DEFAULT
    assert P.is_ai("dependabot[bot]", pol) is True
    assert P.is_ai("github-actions[bot]@users.noreply.github.com", pol) is True
    assert P.is_ai("my-custom-agent[bot]", pol) is True


def test_item6_web_ui_squash_merge_noreply_not_ai():
    from repobrain import policy as P
    pol = P.DEFAULT
    assert P.is_ai("tanmayjain <123456+tanmayjain@users.noreply.github.com>", pol) is False
    assert P.is_ai("Jane Doe <noreply@github.com>", pol) is False
    assert P.is_ai("octocat <583231+octocat@users.noreply.github.com>", pol) is False


def test_item6_ci_metadata_bot_treated_as_ai(tmp_path, monkeypatch):
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("REPOBRAIN_PR_AUTHOR", "human-looking-name")
    monkeypatch.setenv("REPOBRAIN_PR_AUTHOR_TYPE", "Bot")
    
    from repobrain import demo, review, policy as P
    root = str(tmp_path / "repo")
    demo.seed(root)
    pol = P.load_for(root, "main")
    
    rev = review.run(root, pol, "main", str(tmp_path / "home"), extra_actor="human-looking-name")
    assert any(f["ai"] is True for f in rev["files"])
    assert rev.get("ai_detection_source") == "ci_metadata" or any(f.get("ai_source") == "ci_metadata" for f in rev["files"])


def test_item6_require_signed_commits_rejects_unsigned_commits(tmp_path):
    from repobrain import demo, review, policy as P
    root = str(tmp_path / "repo")
    demo.seed(root)
    pol = dict(P.DEFAULT)
    pol["require_signed_commits"] = True
    
    rev = review.run(root, pol, "main", str(tmp_path / "home"), extra_actor="Human Developer <human@corp.internal>")
    # Unsigned commit claiming human identity must be flagged or rejected
    unsigned_findings = [f for f in rev["findings"] if "unsigned" in f["rule"].lower() or "signature" in f["rule"].lower() or "unsigned" in f["msg"].lower()]
    assert len(unsigned_findings) > 0 or all(f["ai"] is True for f in rev["files"])


def test_item6_default_policy_blocks_protected_paths_for_everyone(tmp_path):
    from repobrain import policy as P, shield
    pol = P.DEFAULT
    # blocked_for must default to "all"
    assert pol.get("blocked_for") == "all"
    
    # A human (ai=False) editing a workflow file must be BLOCKED, not warned
    findings = shield.scan_path(".github/workflows/ci.yml", "M", ai=False, policy=pol)
    assert any(f["severity"] == "block" for f in findings), f"Expected block finding for human on workflow, got {findings}"


# ==============================================================================
# ITEM 7: Policy Provenance (PR Cannot Loosen Its Own Policy)
# ==============================================================================

def test_item7_pr_adding_repobrain_yml_does_not_affect_its_own_review(tmp_path):
    import subprocess
    from repobrain import policy as P, review, gitutil
    root = str(tmp_path / "repo")
    subprocess.run(["git", "init", "-b", "main", root], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Developer"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "dev@corp.internal"], cwd=root, check=True)
    
    # Base commit with no repobrain.yml
    (tmp_path / "repo" / "app.py").write_text("print('hello')\n")
    subprocess.run(["git", "add", "app.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True)
    
    # Feature branch with PR adding a loose repobrain.yml that tries to disable blocked paths
    subprocess.run(["git", "checkout", "-b", "feature-pr"], cwd=root, check=True)
    (tmp_path / "repo" / "repobrain.yml").write_text("blocked: []\ncomplexity_threshold: 999\nblocked_for: nobody\n")
    (tmp_path / "repo" / ".github").mkdir(parents=True, exist_ok=True)
    (tmp_path / "repo" / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (tmp_path / "repo" / ".github" / "workflows" / "deploy.yml").write_text("name: test\n")
    subprocess.run(["git", "add", "repobrain.yml", ".github/workflows/deploy.yml"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "pr with loose policy"], cwd=root, check=True)
    
    # load_for must load strict built-in defaults, not the PR's repobrain.yml
    pol = P.load_for(root, "main")
    assert pol.get("_source") == "built-in defaults"
    assert ".github/workflows/" in pol.get("blocked", [])
    
    rev = review.run(root, pol, "main", str(tmp_path / "home"))
    assert rev["policy_source"] == "built-in defaults"
    # Workflow file should be BLOCKED by default policy
    assert rev["decision"] == "BLOCKED"
    assert any(f["severity"] == "block" for f in rev["findings"])


def test_item7_server_state_does_not_leak_untrusted_working_tree_policy(tmp_path):
    import subprocess
    from repobrain import server
    root = str(tmp_path / "repo")
    subprocess.run(["git", "init", "-b", "main", root], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Developer"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "dev@corp.internal"], cwd=root, check=True)
    
    (tmp_path / "repo" / "app.py").write_text("print('hello')\n")
    subprocess.run(["git", "add", "app.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True)
    
    subprocess.run(["git", "checkout", "-b", "pr-branch"], cwd=root, check=True)
    (tmp_path / "repo" / "repobrain.yml").write_text("blocked: []\ncomplexity_threshold: 999\n")
    subprocess.run(["git", "add", "repobrain.yml"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "pr with loose policy"], cwd=root, check=True)
    
    st = server.state(root, "main")
    assert st["policy_source"] == "built-in defaults"
    assert "999" not in st["policy_yaml"]








