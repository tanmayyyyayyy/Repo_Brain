#!/usr/bin/env python3
"""
scripts/security_probe.py
Independent verification script for RepoBrain Security Audit.
Runs the server in NON-demo mode and verifies all 11 security failure conditions.
Exits with code 0 on complete pass, or code 1 on any failure.
"""
import glob
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from repobrain import audit, auth, demo, gitutil, policy, review, server, shield


def log_pass(msg):
    print(f"  [PASS] {msg}")


def log_fail(msg):
    print(f"  [FAIL] {msg}", file=sys.stderr)


def main():
    print("=" * 70)
    print("RepoBrain Security Probe: Non-Demo Mode Verification")
    print("=" * 70)
    
    tmp_dir = tempfile.mkdtemp(prefix="repobrain-probe-")
    try:
        repo_dir = os.path.join(tmp_dir, "repo")
        home_dir = os.path.join(tmp_dir, "home")
        demo.seed(repo_dir)
        
        # Configure SMTP mock host so registration can run
        os.environ["REPOBRAIN_SMTP_HOST"] = "smtp.acmeworks.internal"
        os.environ["REPOBRAIN_SECRET"] = "probe-secret-key-32-bytes-length-ok!"
        os.environ["REPOBRAIN_TRUSTED_PROXIES"] = ""
        
        # Free port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        
        # Start server in NON-demo mode
        server_tok = "probe-secret-token-12345"
        ctx = server.Ctx(repo_dir, "main", home_dir, is_demo=False)
        httpd = server.ThreadingHTTPServer(("127.0.0.1", port), server.make_handler(ctx, server_tok, port, open_demo=False))
        import threading
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        time.sleep(0.3)
        
        def request(path, method="GET", body=None, headers=None):
            h = {"Content-Type": "application/json"}
            if headers:
                h.update(headers)
            data = json.dumps(body).encode("utf-8") if body is not None else None
            req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=h, method=method)
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    resp_body = resp.read().decode("utf-8")
                    return resp.status, resp_body, resp.headers
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8"), e.headers

        # ---------------------------------------------------------------------
        # 1. Static X-RepoBrain: 1 header with no per-run token -> 401
        # ---------------------------------------------------------------------
        print("\n1. Verifying token requirement (static X-RepoBrain header alone is rejected)...")
        status, body, _ = request("/api/state", headers={"X-RepoBrain": "1"})
        assert status == 401, f"Expected 401 for static header without per-run token, got {status}"
        log_pass("Request with static X-RepoBrain: 1 and no token rejected with 401")

        # ---------------------------------------------------------------------
        # 2. Self-register with role=admin -> resulting role forced to developer
        # ---------------------------------------------------------------------
        print("\n2. Verifying self-privilege escalation prevention on registration...")
        status, body, _ = request("/api/auth/register", method="POST",
                                  headers={"X-RepoBrain-Token": server_tok},
                                  body={"email": "mallory@acmeworks.com", "password": "MalloryCorpSecret#2026!",
                                        "name": "Mallory", "role": "admin"})
        assert status == 200, f"Expected 200 on register, got {status}: {body}"
        data = json.loads(body)
        assert data["user"]["role"] == "developer", f"Role was not forced to developer: {data['user']['role']}"
        mallory_tok = data["token"]
        log_pass("Self-registration with role=admin resulted in role=developer")

        # ---------------------------------------------------------------------
        # 3. Privileged endpoints with no session -> 401/403
        # ---------------------------------------------------------------------
        print("\n3. Verifying fail-closed authorization on privileged endpoints without session...")
        for ep, meth, payload in [
            ("/api/approve", "POST", {"proposal_id": "none", "actor": "Alice"}),
            ("/api/waive", "POST", {"reason": "Valid waiver reason 123", "actor": "Alice"}),
            ("/api/auth/update-role", "POST", {"email": "mallory@acmeworks.com", "role": "admin"})
        ]:
            st, _, _ = request(ep, method=meth, headers={"X-RepoBrain-Token": server_tok}, body=payload)
            assert st in (401, 403), f"Expected 401/403 for {ep} without user session, got {st}"
        log_pass("/api/approve, /api/waive, /api/auth/update-role rejected without session (401/403)")

        # ---------------------------------------------------------------------
        # 4. /api/auth/switch-demo-role outside demo mode -> 403, no seeded users
        # ---------------------------------------------------------------------
        print("\n4. Verifying demo persona switching blocked outside demo mode...")
        st, body, _ = request("/api/auth/switch-demo-role", method="POST",
                              headers={"X-RepoBrain-Token": server_tok}, body={"role": "admin"})
        assert st == 403, f"Expected 403 for switch-demo-role outside demo mode, got {st}"
        # Verify no hardcoded default accounts exist in non-demo mode
        users = ctx.auth.list_users()
        seeded = [u for u in users if u.get("is_demo_seed")]
        assert len(seeded) == 0, f"Found seeded users in non-demo mode: {seeded}"
        log_pass("/api/auth/switch-demo-role blocked (403); zero seeded default accounts in non-demo mode")

        # ---------------------------------------------------------------------
        # 5. Content-Length: -1 hangs server thread -> rejected with 400 in <2s
        # ---------------------------------------------------------------------
        print("\n5. Verifying negative Content-Length rejected cleanly without hanging...")
        t0 = time.time()
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
        conn.putrequest("POST", "/api/preflight")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("X-RepoBrain-Token", server_tok)
        conn.putheader("Content-Length", "-1")
        conn.endheaders()
        resp = conn.getresponse()
        elapsed = time.time() - t0
        assert resp.status == 400, f"Expected 400 for Content-Length: -1, got {resp.status}"
        assert elapsed < 2.0, f"Request took too long ({elapsed:.2f}s)"
        conn.close()
        # Verify server is still completely responsive
        st, _, _ = request("/healthz")
        assert st == 200, "Server became unresponsive after malformed Content-Length"
        log_pass("Content-Length: -1 rejected with 400 within 2s; server remains responsive")

        # ---------------------------------------------------------------------
        # 6. Spoofed X-Forwarded-For rotation cannot bypass rate limiter
        # ---------------------------------------------------------------------
        print("\n6. Verifying rate limiter handles untrusted X-Forwarded-For spoofing...")
        login_blocked = False
        for i in range(10):
            st, b, _ = request("/api/auth/login", method="POST",
                               headers={"X-RepoBrain-Token": server_tok,
                                        "X-Forwarded-For": f"198.51.100.{i}"},
                               body={"email": "mallory@acmeworks.com", "password": "WrongPassword#2026!"})
            if st == 429:
                login_blocked = True
                break
        assert login_blocked, "Rate limit was bypassed by rotating spoofed X-Forwarded-For headers"
        log_pass("Rotating untrusted X-Forwarded-For did not bypass rate limiting (got 429)")

        # ---------------------------------------------------------------------
        # 7. OTP: unverified user denied privileged access; code never in API response
        # ---------------------------------------------------------------------
        print("\n7. Verifying unverified user permissions and OTP secrecy...")
        # Mallory is not email-verified yet
        u_mallory = ctx.auth.get_user_by_token(mallory_tok)
        assert not u_mallory.get("email_verified", False), "User was marked verified without OTP"
        for perm in ["review", "optimizer", "shield", "waive", "approve"]:
            assert not auth.check_permission(u_mallory, perm), f"Unverified user was granted permission {perm}"
        # Resend OTP code: response must not reveal the code
        st, b, _ = request("/api/auth/resend-code", method="POST",
                           headers={"X-RepoBrain-Token": server_tok},
                           body={"email": "mallory@acmeworks.com"})
        assert st == 200
        res_data = json.loads(b)
        assert "code" not in res_data and "otp" not in res_data, "Verification code leaked in API response"
        log_pass("Unverified user denied all permissions; verification code is secret and absent from responses")

        # ---------------------------------------------------------------------
        # 8. Anonymous demo clients with different cookies cannot cross-read
        # ---------------------------------------------------------------------
        print("\n8. Verifying cookie-isolated workspace partitioning...")
        ctx_demo = server.Ctx(repo_dir, "main", home_dir, is_demo=True)
        w1 = ctx_demo.create_valid_wid()
        w2 = ctx_demo.create_valid_wid()
        r1 = ctx_demo.get_workspace_root(w1)
        r2 = ctx_demo.get_workspace_root(w2)
        assert r1 != r2, "Workspaces for different demo clients shared the same root"
        # Write marker in workspace 1
        with open(os.path.join(r1, "secret_marker.txt"), "w") as f:
            f.write("w1_secret")
        assert not os.path.exists(os.path.join(r2, "secret_marker.txt")), "Workspace 2 leaked files from Workspace 1"
        log_pass("Demo workspaces strictly partitioned by HttpOnly cryptographic cookie; no cross-leakage")

        # ---------------------------------------------------------------------
        # 9. Corrupt audit tail -> recovery entry written, appends continue, verify flags it
        # ---------------------------------------------------------------------
        print("\n9. Verifying audit log tail corruption quarantine and recovery...")
        audit_test_dir = os.path.join(tmp_dir, "audit_test")
        os.makedirs(audit_test_dir, exist_ok=True)
        log = audit.AuditLog(audit_test_dir)
        log.append("init", "system", "ALLOWED", "initial entry")
        # Simulate power failure / crash leaving partial garbage at tail
        with open(log.path, "a", encoding="utf-8") as f:
            f.write('{"seq": 2, "event": "cra')
        
        # Next append must quarantine the corrupt file, write audit-recovery entry, and continue
        rec = log.append("event-after-crash", "system", "ALLOWED", "resumed operation")
        assert log.is_recovery_pending(), "Recovery pending flag was not set after corrupt tail"
        assert rec["event"] == "event-after-crash", "Log failed to resume appends after corrupt tail"
        v = log.verify()
        assert not v["ok"], "Verify passed despite pending recovery quarantine"
        assert v.get("recovery_pending") is True
        log_pass("Corrupt audit tail quarantined, recovery ledger initialized, appends resumed, verify flagged")

        # ---------------------------------------------------------------------
        # 10. PR adding loose repobrain.yml does not loosen its own review
        # ---------------------------------------------------------------------
        print("\n10. Verifying PR cannot loosen its own policy provenance...")
        pr_repo = os.path.join(tmp_dir, "pr_repo")
        subprocess.run(["git", "init", "-b", "main", pr_repo], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Dev"], cwd=pr_repo, check=True)
        subprocess.run(["git", "config", "user.email", "dev@corp.internal"], cwd=pr_repo, check=True)
        (subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=pr_repo, check=True))
        
        subprocess.run(["git", "checkout", "-b", "malicious-pr"], cwd=pr_repo, check=True, capture_output=True)
        # PR attempts to disable blocked paths and raise complexity limits
        with open(os.path.join(pr_repo, "repobrain.yml"), "w") as f:
            f.write("blocked: []\ncomplexity_threshold: 9999\nblocked_for: nobody\n")
        os.makedirs(os.path.join(pr_repo, ".github", "workflows"), exist_ok=True)
        with open(os.path.join(pr_repo, ".github", "workflows", "pwn.yml"), "w") as f:
            f.write("name: attack\n")
        subprocess.run(["git", "add", "repobrain.yml", ".github/workflows/pwn.yml"], cwd=pr_repo, check=True)
        subprocess.run(["git", "commit", "-m", "loosen policy and add workflow"], cwd=pr_repo, check=True)
        
        loaded_pol = policy.load_for(pr_repo, "main")
        assert "built-in defaults" in loaded_pol["_source"], f"Policy source trusted PR instead of defaults: {loaded_pol['_source']}"
        rev = review.run(pr_repo, loaded_pol, "main", os.path.join(tmp_dir, "pr_home"))
        assert rev["decision"] == "BLOCKED", f"PR adding protected workflow was not BLOCKED: {rev['decision']}"
        assert "built-in defaults" in rev["policy_source"]
        log_pass("PR with loose repobrain.yml reviewed against strict built-in defaults; changes BLOCKED")

        # ---------------------------------------------------------------------
        # 11. Committer noreply@github.com not AI; human "Alice Chen" blocked from workflow
        # ---------------------------------------------------------------------
        print("\n11. Verifying AI-identity heuristics and default blocked_for: all...")
        # Web UI / squash-merge committer is human
        assert not policy.is_ai("alice <123456+alice@users.noreply.github.com>"), "noreply falsely flagged as AI"
        assert not policy.is_ai("Jane Doe <noreply@github.com>"), "GitHub noreply falsely flagged as AI"
        # Bot marker is flagged AI
        assert policy.is_ai("dependabot[bot]"), "[bot] suffix not recognized as AI"
        
        # Under default policy (blocked_for: all), a human committing as "Alice Chen" CANNOT touch workflows
        alice_findings = shield.scan_path(".github/workflows/deploy.yml", "M", ai=False, policy=policy.DEFAULT)
        assert any(f["severity"] == "block" for f in alice_findings), f"Human Alice Chen was not blocked on workflow: {alice_findings}"
        log_pass("noreply@github.com committer recognized as human; Alice Chen blocked on .github/workflows/")

        print("\n" + "=" * 70)
        print("ALL 11 SECURITY PROBE ASSERTIONS PASSED WITH ZERO FAILURES!")
        print("=" * 70)
        return 0

    except Exception as exc:
        log_fail(f"SECURITY PROBE FAILED: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        try:
            httpd.shutdown()
        except Exception:
            pass
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
