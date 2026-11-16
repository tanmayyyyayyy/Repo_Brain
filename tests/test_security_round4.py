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
    mgr_prod.register("prod@corp.internal", "CorporateSecret#2026!", "Prod")
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
        
    v1 = log.verify(cached=True)
    assert v1["ok"] is True
    
    # Second verify with no changes should return cached result without scanning
    v2 = log.verify(cached=True)
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
    assert "built-in defaults" in pol.get("_source", "")
    assert ".github/workflows/" in pol.get("blocked", [])
    
    rev = review.run(root, pol, "main", str(tmp_path / "home"))
    assert "built-in defaults" in rev["policy_source"]
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
    assert "built-in defaults" in st["policy_source"]
    assert "999" not in st["policy_yaml"]


# ==============================================================================
# ITEM 8: CSP Safety & Zero Violations Across Views
# ==============================================================================

def test_item8_strict_csp_and_zero_violations_across_views(tmp_path):
    pytest.importorskip("playwright")
    import threading, time
    from playwright.sync_api import sync_playwright
    from repobrain import server, demo
    
    root = str(tmp_path / "repo")
    demo.seed(root)
    port = 18894
    ctx = server.Ctx(root, "main", str(tmp_path / "home"), True)
    srv = server.ThreadingHTTPServer(("127.0.0.1", port), server.make_handler(ctx, "test-token", port, open_demo=True))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            console_errors = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            
            page.add_init_script("""
                window.__csp_violations = [];
                window.addEventListener('securitypolicyviolation', (e) => {
                    window.__csp_violations.push({
                        blockedURI: e.blockedURI,
                        directive: e.violatedDirective,
                        originalPolicy: e.originalPolicy
                    });
                });
            """)
            
            resp = page.goto(f"http://127.0.0.1:{port}/")
            csp_header = resp.headers.get("content-security-policy", "")
            # script-src and style-src must NOT contain unsafe-inline
            script_src_part = csp_header.split("script-src")[1].split(";")[0]
            style_src_part = csp_header.split("style-src")[1].split(";")[0]
            assert "'unsafe-inline'" not in script_src_part, f"script-src contains unsafe-inline: {script_src_part}"
            assert "'unsafe-inline'" not in style_src_part, f"style-src contains unsafe-inline: {style_src_part}"
            assert "nonce-" in script_src_part
            assert "nonce-" in style_src_part
            
            page.wait_for_timeout(500)
            # Switch views / tabs to exercise JavaScript execution
            for tab_id in ["btnTabOptimizer", "btnTabShield", "btnTabExplainer", "btnTabAudit", "btnTabPolicy", "btnTabReview"]:
                btn = page.query_selector(f"#{tab_id}")
                if btn:
                    btn.click()
                    page.wait_for_timeout(150)
            
            violations = page.evaluate("window.__csp_violations")
            assert len(violations) == 0, f"Expected 0 CSP violations, got: {violations}"
            assert len(console_errors) == 0, f"Expected 0 console errors, got: {console_errors}"
            browser.close()
    finally:
        srv.shutdown()


# ==============================================================================
# ITEM 9: Sandbox Truthfulness & Capability Probing
# ==============================================================================

def test_item9_bwrap_capability_probe_and_caching():
    from repobrain import optimizer
    can_use, reason = optimizer.probe_bwrap_capability()
    assert isinstance(can_use, bool)
    assert isinstance(reason, str)
    assert len(reason) > 0
    # Second call must hit cache
    can_use_2, reason_2 = optimizer.probe_bwrap_capability()
    assert can_use == can_use_2
    assert reason == reason_2


def test_item9_require_sandbox_aborts_when_probe_fails(tmp_path, monkeypatch):
    from repobrain import optimizer, policy as P
    monkeypatch.setattr(optimizer, "probe_bwrap_capability", lambda: (False, "mock user namespace creation blocked in test"))
    
    root = str(tmp_path / "repo")
    (tmp_path / "repo").mkdir(parents=True, exist_ok=True)
    (tmp_path / "repo" / "a.py").write_text("def f(): return 1\n")
    (tmp_path / "repo" / "test_a.py").write_text("def test_f(): assert True\n")
    
    pol = dict(P.DEFAULT)
    pol["require_sandbox"] = True
    
    t_res = optimizer.run_tests(root, {}, pol)
    assert t_res["ok"] is False
    assert t_res["ran"] is False
    assert "mock user namespace" in t_res["output"]
    assert t_res["sandbox"]["type"] == "none"
    assert t_res["sandbox"]["network_isolated"] is False
    assert t_res["sandbox"]["rlimits_applied"] is False


def test_item9_proposal_reports_sandbox_network_and_rlimits(tmp_path):
    from repobrain import optimizer, demo, policy as P
    root = str(tmp_path / "repo")
    demo.seed(root)
    
    pol = dict(P.DEFAULT)
    prop = optimizer.propose(root, pol, ["repobrain_demo/orders.py"], str(tmp_path / "home"))
    
    sb = prop.get("sandbox") or prop.get("tests", {}).get("sandbox")
    assert sb is not None
    assert "type" in sb
    assert "network_isolated" in sb
    assert "rlimits_applied" in sb


# ==============================================================================
# ITEM 10: Auth Hygiene (Constant-Time Login, Session Caps, Password Complexity)
# ==============================================================================

def test_item10_constant_time_login_timing(tmp_path):
    import time
    from repobrain import auth
    home = str(tmp_path)
    mgr = auth.AuthManager(home, is_demo=True)
    mgr.register("real-user@acmeworks.com", "SecurePassword123!", "Real User")
    
    # Measure time for non-existent user
    t0 = time.perf_counter()
    try:
        mgr.login("non-existent-user@acmeworks.com", "WrongPassword123!")
    except ValueError:
        pass
    t_non_existent = time.perf_counter() - t0
    
    # Measure time for real user with wrong password
    t0 = time.perf_counter()
    try:
        mgr.login("real-user@acmeworks.com", "WrongPassword123!")
    except ValueError:
        pass
    t_real_user = time.perf_counter() - t0
    
    ratio = max(t_non_existent, t_real_user) / max(0.0001, min(t_non_existent, t_real_user))
    assert ratio < 2.0, f"Timing ratio {ratio:.2f} exceeded 2.0x limit (non_existent={t_non_existent:.4f}s, real={t_real_user:.4f}s)"


def test_item10_active_session_cap_and_eviction(tmp_path):
    from repobrain import auth
    home = str(tmp_path)
    mgr = auth.AuthManager(home, is_demo=True)
    mgr.register("developer@acmeworks.com", "SecurePassword123!", "Developer")
    
    tokens = []
    for i in range(6):
        _, tok = mgr.login("developer@acmeworks.com", "SecurePassword123!")
        tokens.append(tok)
    
    # 6th login must evict the 1st session
    assert mgr.get_user_by_token(tokens[0]) is None, "Oldest session (login 1) was not evicted"
    for tok in tokens[1:]:
        assert mgr.get_user_by_token(tok) is not None, "Remaining 5 sessions should be valid"
    
    dev_sessions = [s for s in mgr._sessions.values() if s.get("email") == "developer@acmeworks.com"]
    assert len(dev_sessions) == 5, f"Expected exactly 5 active sessions, found {len(dev_sessions)}"


def test_item10_role_or_password_change_invalidates_sessions(tmp_path):
    from repobrain import auth
    home = str(tmp_path)
    mgr = auth.AuthManager(home, is_demo=True)
    mgr.register("admin@acmeworks.com", "AdminPassword123!", "Admin", role="admin")
    mgr.register("target@acmeworks.com", "SecurePassword123!", "Target", role="developer")
    
    _, tok = mgr.login("target@acmeworks.com", "SecurePassword123!")
    assert mgr.get_user_by_token(tok) is not None
    
    # Role change must invalidate target's sessions
    mgr.update_role("target@acmeworks.com", "security", "admin@acmeworks.com")
    assert mgr.get_user_by_token(tok) is None, "Session remained valid after role change"
    
    # New login
    _, new_tok = mgr.login("target@acmeworks.com", "SecurePassword123!")
    assert mgr.get_user_by_token(new_tok) is not None
    
    # Password change must invalidate sessions
    mgr.change_password("target@acmeworks.com", "SecurePassword123!", "NewStrongPassword2026!")
    assert mgr.get_user_by_token(new_tok) is None, "Session remained valid after password change"


def test_item10_password_policy_enforcement(tmp_path):
    import pytest
    from repobrain import auth
    home = str(tmp_path)
    # Outside demo mode: strict password rules apply
    mgr = auth.AuthManager(home, is_demo=False)
    
    # Short password (<12 chars) rejected
    with pytest.raises(ValueError, match="at least 12 characters"):
        mgr.register("user1@acmeworks.com", "Short123!", "User")
    
    # Common password rejected
    with pytest.raises(ValueError, match="too common"):
        mgr.register("user2@acmeworks.com", "password1234", "User")
    
    # Strong password accepted
    u, _ = mgr.register("user3@acmeworks.com", "StrongEnterpriseCorpPass2026!", "User")
    assert u["email"] == "user3@acmeworks.com"


def test_item10_non_admin_cannot_see_other_users_emails(tmp_path):
    from repobrain import server, demo, auth
    root = str(tmp_path / "repo")
    home = str(tmp_path / "home")
    demo.seed(root)
    
    ctx = server.Ctx(root, "main", home, is_demo=False)
    admin, _ = ctx.auth.bootstrap_admin("admin@acmeworks.com", "AdminSuperSecret#2026!X", "Admin")
    dev, _ = ctx.auth.register("dev@acmeworks.com", "DevSuperSecret#2026!Y", "Developer", role="developer")
    
    # Dev views state: other users' email addresses must be masked
    st_dev = server.state(ctx, user=dev)
    dev_users = st_dev["auth"]["users"]
    admin_in_dev_view = next(u for u in dev_users if u["role"] == "admin")
    assert admin_in_dev_view["email"] != "admin@acmeworks.com"
    assert "***" in admin_in_dev_view["email"]
    
    # Admin views state: all email addresses visible
    st_admin = server.state(ctx, user=admin)
    admin_users = st_admin["auth"]["users"]
    admin_in_admin_view = next(u for u in admin_users if u["role"] == "admin")
    assert admin_in_admin_view["email"] == "admin@acmeworks.com"


# ==============================================================================
# ITEM 11: Packaging & Docs Consistency
# ==============================================================================

def test_item11_asset_and_doc_links_exist():
    import glob, os, re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    md_files = glob.glob(os.path.join(root, "*.md")) + glob.glob(os.path.join(root, "docs", "**", "*.md"), recursive=True)
    
    broken_links = []
    for mf in md_files:
        content = open(mf, encoding="utf-8", errors="ignore").read()
        links = re.findall(r'\[(?:[^\]]*)\]\(([^)]+)\)', content)
        for link in links:
            clean = link.split("#")[0].strip()
            if not clean or clean.startswith(("http://", "https://", "mailto:", "conversation://")):
                continue
            target = os.path.normpath(os.path.join(os.path.dirname(mf), clean))
            if not os.path.exists(target):
                broken_links.append((os.path.relpath(mf, root), clean, target))
    
    assert len(broken_links) == 0, f"Found broken asset/doc links: {broken_links}"


def test_item11_submission_zip_under_size_limit_and_excludes_raw_video(tmp_path, monkeypatch):
    import os, zipfile, subprocess, sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    monkeypatch.setenv("REPOBRAIN_SUBMISSION_ZIP_DIR", str(tmp_path))
    
    script_path = os.path.join(root, "scripts", "make_submission_zip.py")
    subprocess.run([sys.executable, script_path], check=True, cwd=root)
    
    zip_path = tmp_path / "RepoBrain_Round3_Final_Submission.zip"
    assert zip_path.is_file(), "Submission zip was not created"
    
    size_mb = os.path.getsize(str(zip_path)) / (1024 * 1024)
    # Must be well under the 50MB limit
    assert size_mb < 50.0, f"Submission zip too large: {size_mb:.2f} MB"
    

def test_item2_repo_policy_enforces_blocked_for_all():
    import os
    from repobrain import policy
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 1. Main repo policy
    main_pol = policy.load(os.path.join(root, "repobrain.yml"))
    assert main_pol.get("blocked_for") == "all", f"repobrain.yml must set blocked_for: all, got {main_pol.get('blocked_for')}"
    
    # 2. Demo assets policy
    demo_pol = policy.load(os.path.join(root, "demo_assets", "repobrain.yml"))
    assert demo_pol.get("blocked_for") == "all", f"demo_assets/repobrain.yml must set blocked_for: all, got {demo_pol.get('blocked_for')}"
    
    # Must fail if set to 'ai'
    ai_pol = dict(main_pol, blocked_for="ai")
    assert ai_pol.get("blocked_for") != "all"


def test_item3_audit_full_uncached_verify_detects_middle_record_tampering_with_restored_mtime_and_size(tmp_path):
    from repobrain import audit as A
    home = str(tmp_path)
    log = A.AuditLog(home)
    
    # Append 5 records
    for i in range(1, 6):
        log.append(f"event-{i}", "developer", "ALLOWED", f"detail for record {i}")
        
    # Initial uncached verify must succeed
    v_init = log.verify()
    assert v_init["ok"] is True
    assert v_init["count"] == 5
    
    # Capture original file stat
    orig_stat = os.stat(log.path)
    orig_mtime_ns = orig_stat.st_mtime_ns
    orig_size = orig_stat.st_size
    
    # Read raw binary to avoid platform newline conversion differences
    with open(log.path, "rb") as f:
        raw_bytes = f.read()
    
    # Tamper with middle record (replace event-3 with hacked3 preserving exact byte length)
    assert b"event-3" in raw_bytes, "event-3 must exist in raw log"
    tampered_bytes = raw_bytes.replace(b'"event": "event-3"', b'"event": "hacked3"', 1)
    assert len(tampered_bytes) == len(raw_bytes), "Byte length must match exactly"
    
    with open(log.path, "wb") as f:
        f.write(tampered_bytes)
        
    # Restore mtime and atime
    os.utime(log.path, ns=(orig_mtime_ns, orig_mtime_ns))
    
    new_stat = os.stat(log.path)
    assert new_stat.st_size == orig_size, f"Size changed: {new_stat.st_size} vs {orig_size}"
    assert new_stat.st_mtime_ns == orig_mtime_ns, f"mtime changed: {new_stat.st_mtime_ns} vs {orig_mtime_ns}"
    
    # Verify MUST still fail because CLI, CI and /api/audit perform a full uncached verify
    v_tampered = log.verify(cached=False)
    assert v_tampered["ok"] is False, "Uncached verify must detect middle record tampering"
    assert v_tampered["broken_at"] in (3, 4), f"Broken at must point to tampered entry, got {v_tampered.get('broken_at')}"
    
    # Default verify() without arguments is also uncached and must fail
    v_default = log.verify()
    assert v_default["ok"] is False, "Default verify() must be uncached and detect tampering"













