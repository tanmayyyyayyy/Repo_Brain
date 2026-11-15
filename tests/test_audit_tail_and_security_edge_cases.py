import hashlib
import json
import os
import shutil
import tempfile
import time
import pytest

from repobrain import audit, auth, policy, shield, optimizer
from repobrain.audit import AuditLog, AuditCorruptionError, GENESIS


def test_audit_tail_seek_empty_file():
    tmp = tempfile.mkdtemp(prefix="repobrain-tail-empty-")
    try:
        p = os.path.join(tmp, "audit.jsonl")
        # File doesn't exist
        assert audit._tail_last_record(p) == (0, GENESIS)
        # File exists with 0 bytes
        with open(p, "wb") as f:
            pass
        assert audit._tail_last_record(p) == (0, GENESIS)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_audit_tail_seek_large_record_over_4kb():
    tmp = tempfile.mkdtemp(prefix="repobrain-tail-large-")
    try:
        log = AuditLog(tmp)
        # Append a normal record
        log.append("init", "system", "OK", "initial setup")
        # Append a huge record with > 6 KB payload
        big_payload = "A" * 7000
        r2 = log.append("large-event", "evaluator", "SUCCESS", big_payload)
        assert len(json.dumps(r2)) > 7000

        # Verify O(1) backward tail seek accurately extracts this huge record
        seq, last_h = audit._tail_last_record(log.path)
        assert seq == 2
        assert last_h == r2["hash"]

        # Append next record on top of the huge record
        r3 = log.append("after-large", "evaluator", "SUCCESS", "following big record")
        assert r3["seq"] == 3
        assert r3["prev"] == r2["hash"]

        # Entire audit log verify should pass cleanly
        v = log.verify()
        assert v["ok"] is True
        assert v["count"] == 3
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_audit_tail_seek_partial_line_from_crash():
    tmp = tempfile.mkdtemp(prefix="repobrain-tail-crash-")
    try:
        log = AuditLog(tmp)
        log.append("event-1", "user", "OK", "step 1")
        log.append("event-2", "user", "OK", "step 2")

        # Simulate abrupt process crash / power loss mid-write of record 3
        with open(log.path, "a", encoding="utf-8") as f:
            f.write('{"seq": 3, "ts": "2026-11-16T01:00:00", "event": "incompl')

        # _tail_last_record must refuse to continue on broken tail
        with pytest.raises(AuditCorruptionError) as exc_info:
            audit._tail_last_record(log.path)
        assert "malformed" in str(exc_info.value).lower()

        # append() must refuse to append onto corrupt chain
        with pytest.raises(AuditCorruptionError):
            log.append("event-4", "user", "OK", "should be refused")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_audit_tail_seek_tampered_hash_corruption():
    tmp = tempfile.mkdtemp(prefix="repobrain-tail-tamper-")
    try:
        log = AuditLog(tmp)
        log.append("step-1", "admin", "OK", "valid record 1")
        r2 = log.append("step-2", "admin", "OK", "valid record 2")

        # Manually alter the last line's hash
        lines = open(log.path, "r", encoding="utf-8").readlines()
        corrupt_rec = json.loads(lines[-1])
        corrupt_rec["hash"] = "0000000000000000000000000000000000000000000000000000000000000000"
        lines[-1] = json.dumps(corrupt_rec) + "\n"
        with open(log.path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        # Must refuse to append onto corrupt / tampered trailing hash
        with pytest.raises(AuditCorruptionError) as exc_info:
            audit._tail_last_record(log.path)
        assert "tampered or corrupt hash" in str(exc_info.value).lower()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_audit_concurrent_appends_with_flock():
    import concurrent.futures
    tmp = tempfile.mkdtemp(prefix="repobrain-tail-concurrent-")
    try:
        log = AuditLog(tmp)
        num_appends = 40

        def do_append(idx):
            return log.append("concurrent-event", f"worker-{idx}", "OK", f"item {idx}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(do_append, range(num_appends)))

        assert len(results) == num_appends
        v = log.verify()
        assert v["ok"] is True
        assert v["count"] == num_appends
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_otp_verification_limits_and_security():
    tmp = tempfile.mkdtemp(prefix="repobrain-otp-sec-")
    try:
        mgr = auth.AuthManager(tmp, is_demo=False)
        u, tok = mgr.register(
            email="dev@acmeworks.internal",
            password="SecurePassword123!",
            name="Dev User",
            company="Acme Corp"
        )

        # 1. Verification code is NEVER exposed in registered user payload
        assert "verification_code" not in u
        assert u["email_verified"] is False

        # 2. Resend code also never exposes the raw code in API response
        res = mgr.resend_verification_code("dev@acmeworks.internal")
        assert "code" not in res
        assert res["status"] == "sent"
        assert res["expires_in"] == 900

        # 3. Arbitrary wrong code is rejected
        with pytest.raises(ValueError) as exc1:
            mgr.verify_email("dev@acmeworks.internal", "000000")
        assert "4 attempt(s) remaining" in str(exc1.value)

        # 4. Attempt limit lockout after 5 failures
        for _ in range(4):
            with pytest.raises(ValueError):
                mgr.verify_email("dev@acmeworks.internal", "999999")

        # 5th subsequent attempt must lock out
        with pytest.raises(ValueError) as exc_lock:
            mgr.verify_email("dev@acmeworks.internal", "123456")
        assert "exceeded maximum attempt limit" in str(exc_lock.value)

        # 5. Expiration check: simulating expired code
        mgr._users["dev@acmeworks.internal"]["otp_attempts"] = 0
        mgr._users["dev@acmeworks.internal"]["otp_expires_at"] = time.time() - 100
        with pytest.raises(ValueError) as exc_exp:
            mgr.verify_email("dev@acmeworks.internal", "123456")
        assert "expired" in str(exc_exp.value).lower()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_bootstrap_first_admin_outside_demo_mode():
    tmp = tempfile.mkdtemp(prefix="repobrain-bootstrap-admin-")
    try:
        # Non-demo mode starts with empty user store
        mgr = auth.AuthManager(tmp, is_demo=False)
        assert len(mgr.list_users()) == 0

        # Bootstrap first administrator
        admin_u, tok1 = mgr.bootstrap_admin(
            email="founder@acmeworks.internal",
            password="AdminPassword123!",
            name="Enterprise Admin",
            company="Acme Corp"
        )
        assert admin_u["role"] == "admin"
        assert admin_u["role_badge"] == "ADMIN"

        # Subsequent attempt to bootstrap another admin must fail
        with pytest.raises(PermissionError):
            mgr.bootstrap_admin(
                email="imposter@acmeworks.internal",
                password="ImposterPassword123!",
                name="Imposter Admin"
            )

        # Subsequent user registering must be forced to developer
        dev_u, tok2 = mgr.register(
            email="employee@acmeworks.internal",
            password="DevPassword123!",
            name="Developer One",
            company="Acme Corp",
            role="admin"  # Malicious attempt to claim admin via register
        )
        assert dev_u["role"] == "developer"
        assert dev_u["role_badge"] == "DEV"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_github_noreply_ai_detection_no_false_positive():
    pol = policy.DEFAULT

    # Normal human developer committing with GitHub web-UI or privacy email
    human1 = "Priya Sharma <priya@users.noreply.github.com>"
    human2 = "John Doe <12345678+johndoe@users.noreply.github.com>"
    assert shield.is_ai(human1, pol) is False
    assert shield.is_ai(human2, pol) is False

    # AI bot commits with bot identity or bot pattern
    bot1 = "refactor-bot[bot] <refactor-bot@users.noreply.github.com>"
    bot2 = "demo-agent <demo-agent@users.noreply.local>"
    bot3 = "Copilot Agent <copilot@github.com>"
    assert shield.is_ai(bot1, pol) is True
    assert shield.is_ai(bot2, pol) is True
    assert shield.is_ai(bot3, pol) is True


def test_require_sandbox_policy_enforcement():
    # If require_sandbox: True is set in policy, run_tests must fail if bwrap container unavailable
    pol = {**policy.DEFAULT, "require_sandbox": True}
    res = optimizer.run_tests(os.getcwd(), {"dummy.py": "x = 1"}, pol)
    if not (os.name == "posix" and sys_platform_linux() and shutil.which("bwrap")):
        assert res["ran"] is False
        assert "require_sandbox" in res["output"]
        assert res["sandbox"]["enforced"] is False


def sys_platform_linux():
    import sys
    return sys.platform.startswith("linux")

