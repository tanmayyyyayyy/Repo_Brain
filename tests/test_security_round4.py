import collections
import ipaddress
import os
import time
import pytest

from repobrain import server


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




