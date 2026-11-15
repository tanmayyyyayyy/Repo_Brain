import tempfile
import pytest
from repobrain import auth
from repobrain.audit import AuditLog


def test_validate_company_email():
    # Valid company emails
    ok, err, domain = auth.validate_company_email("alice@acme.corp")
    assert ok is True
    assert domain == "acme.corp"

    ok, err, domain = auth.validate_company_email("john.doe@stripe.com")
    assert ok is True
    assert domain == "stripe.com"

    # Blocked public webmail domains
    for blocked in ["test@gmail.com", "user@yahoo.com", "dev@outlook.com", "anon@proton.me"]:
        ok, err, domain = auth.validate_company_email(blocked)
        assert ok is False
        assert "Personal email domain" in err

    # Allowed domains whitelist
    allowed = ["acme.corp", "initech.internal"]
    ok, err, domain = auth.validate_company_email("bob@initech.internal", allowed)
    assert ok is True
    ok, err, domain = auth.validate_company_email("bob@othercorp.com", allowed)
    assert ok is False
    assert "not in the allowed corporate domain list" in err


def test_password_hashing():
    pw = "SuperSecretCorpPassword123!"
    h1 = auth.hash_password(pw)
    assert h1.startswith("pbkdf2_sha256$600000$")
    assert auth.verify_password(pw, h1) is True
    assert auth.verify_password("WrongPassword!", h1) is False

    # Unique salts
    h2 = auth.hash_password(pw)
    assert h1 != h2
    assert auth.verify_password(pw, h2) is True


def test_user_manager_and_rbac():
    with tempfile.TemporaryDirectory() as td:
        audit_log = AuditLog(td)
        mgr = auth.AuthManager(td)

        # Seeded demo personas exist
        users = mgr.list_users()
        emails = {u["email"] for u in users}
        assert "alex.mercer@acmeworks.internal" in emails
        assert "alice.chen@acmeworks.internal" in emails
        assert "quinn.vance@acmeworks.internal" in emails
        assert "samira.patel@acmeworks.internal" in emails

        # Register new developer
        user, tok = mgr.register(
            email="dev1@enterprise.net",
            password="EnterprisePassword123!",
            name="Diana Prince",
            role="developer",
            audit_log=audit_log
        )
        assert user["email"] == "dev1@enterprise.net"
        assert user["role"] == "developer"
        assert user["role_badge"] == "DEV"
        assert "view_pr" in user["permissions"]
        assert "apply_approval" not in user["permissions"]

        # Duplicate email rejected
        with pytest.raises(ValueError, match="already registered"):
            mgr.register("dev1@enterprise.net", "anotherpwd", "Diana", audit_log=audit_log)

        # Token lookup
        fetched = mgr.get_user_by_token(tok)
        assert fetched is not None
        assert fetched["email"] == "dev1@enterprise.net"

        # Logout
        mgr.logout(tok, audit_log=audit_log)
        assert mgr.get_user_by_token(tok) is None

        # Login again
        u2, tok2 = mgr.login("dev1@enterprise.net", "EnterprisePassword123!", audit_log=audit_log)
        assert u2["email"] == "dev1@enterprise.net"
        assert tok2 is not None

        # Evaluator Persona Switch
        admin_user, admin_tok = mgr.switch_demo_persona("admin", audit_log=audit_log)
        assert admin_user["role"] == "admin"
        assert admin_user["role_badge"] == "ADMIN"
        assert auth.check_permission(admin_user, "apply_approval") is True
        assert auth.check_permission(admin_user, "grant_waiver") is True

        tester_user, tester_tok = mgr.switch_demo_persona("tester", audit_log=audit_log)
        assert tester_user["role"] == "tester"
        assert auth.check_permission(tester_user, "inspect_fuzzing") is True
        assert auth.check_permission(tester_user, "run_explainer") is True
        assert auth.check_permission(tester_user, "apply_approval") is False

        sec_user, sec_tok = mgr.switch_demo_persona("security", audit_log=audit_log)
        assert sec_user["role"] == "security"
        assert auth.check_permission(sec_user, "configure_shield") is True
        assert auth.check_permission(sec_user, "inspect_secrets") is True
        assert auth.check_permission(sec_user, "grant_waiver") is True
        assert auth.check_permission(sec_user, "apply_approval") is False

        # Role change
        updated = mgr.update_role("dev1@enterprise.net", "security", "alex.mercer@acmeworks.internal", audit_log=audit_log)
        assert updated["role"] == "security"
        assert "configure_shield" in updated["permissions"]

        # Audit events verification
        entries = audit_log.entries()
        events = [e["event"] for e in entries]
        assert "auth-register" in events
        assert "auth-login" in events
        assert "auth-logout" in events
        assert "auth-persona-switch" in events
        assert "auth-role-change" in events


def test_server_auth_rbac_routes():
    from repobrain import demo, server
    with tempfile.TemporaryDirectory() as td:
        repo_dir = f"{td}/repo"
        home_dir = f"{td}/home"
        demo.seed(repo_dir)
        ctx = server.Ctx(repo_dir, "main", home_dir, True)

        # 1. Register through route
        reg_res = server.route(ctx, "/api/auth/register", {
            "email": "sarah.connor@cyberdyne.corp",
            "password": "ResistancePassword2026!",
            "name": "Sarah Connor",
            "role": "developer",
            "company": "Cyberdyne Systems"
        })
        dev_user = reg_res["user"]
        dev_tok = reg_res["token"]
        assert dev_user["email"] == "sarah.connor@cyberdyne.corp"
        assert dev_user["role"] == "developer"
        assert dev_tok is not None

        # 2. Developer cannot approve code
        with pytest.raises(PermissionError, match="Permission Denied"):
            server.route(ctx, "/api/approve", {"id": "prop-123", "actor": "Sarah Connor"}, user=dev_user)

        # 3. Developer cannot grant waiver
        with pytest.raises(PermissionError, match="Permission Denied"):
            server.route(ctx, "/api/waive", {"reason": "quick hotfix", "actor": "Sarah Connor"}, user=dev_user)

        # 4. Switch to Tester persona
        tester_res = server.route(ctx, "/api/auth/switch-demo-role", {"role": "tester"})
        tester_user = tester_res["user"]
        assert tester_user["role"] == "tester"

        # Tester also cannot approve code
        with pytest.raises(PermissionError, match="Permission Denied"):
            server.route(ctx, "/api/approve", {"id": "prop-123", "actor": "Quinn Vance"}, user=tester_user)

        # 5. Switch to Security Lead persona
        sec_res = server.route(ctx, "/api/auth/switch-demo-role", {"role": "security"})
        sec_user = sec_res["user"]
        assert sec_user["role"] == "security"

        # Security can grant waiver
        w = server.route(ctx, "/api/waive", {"reason": "Accepted business risk on legacy dependency", "actor": "Samira Patel"}, user=sec_user)
        assert w["actor"] == "Samira Patel"

        # 6. Switch to Admin persona
        admin_res = server.route(ctx, "/api/auth/switch-demo-role", {"role": "admin"})
        admin_user = admin_res["user"]
        assert admin_user["role"] == "admin"

        # Admin can update roles
        role_up = server.route(ctx, "/api/auth/update-role", {
            "email": "sarah.connor@cyberdyne.corp",
            "role": "admin"
        }, user=admin_user)
        assert role_up["user"]["role"] == "admin"


def test_playwright_auth_rbac_ui():
    import os, re, subprocess, sys
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp_demo_dir = tempfile.mkdtemp(prefix="repobrain-auth-ui-test-")
    env = {**os.environ, "REPOBRAIN_DEMO_DIR": tmp_demo_dir}
    port = 8797
    cmd = [sys.executable, "-m", "repobrain", "serve", "--demo", "--no-browser", "--port", str(port)]
    proc = subprocess.Popen(cmd, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    url = None
    try:
        for _ in range(30):
            line = proc.stdout.readline()
            match = re.search(r"http://127\.0\.0\.1:\d+/\?t=\S+", line)
            if match:
                url = match.group(0)
                break
        assert url is not None, "Server did not launch in time"

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as e:
                if "Executable doesn't exist" in str(e):
                    pytest.skip(f"Playwright browser not installed: {e}")
                raise
            page = browser.new_page()
            page.goto(url, wait_until="networkidle")

            # Verify User Pill renders with default Admin
            page.wait_for_selector(".user-pill", timeout=10000)
            user_pill_text = page.locator(".user-pill").inner_text()
            assert "ADMIN" in user_pill_text

            # Click user pill to open dropdown
            page.locator(".user-pill").click()
            page.wait_for_selector("#userDropdownMenu.open", timeout=5000)

            # Switch persona to Developer (Alice Chen)
            page.locator(".persona-item:has-text('Alice Chen')").click()
            page.wait_for_selector(".user-pill:has-text('DEV')", timeout=5000)

            # Verify persona updated to DEV
            updated_pill = page.locator(".user-pill").inner_text()
            assert "DEV" in updated_pill
            assert "Alice" in updated_pill

            # Verify perspective banner is in Developer Mode
            page.wait_for_selector(".role-perspective-banner:has-text('Developer Perspective')", timeout=5000)
            banner_text = page.locator(".role-perspective-banner").inner_text()
            assert "Developer Perspective" in banner_text

            # Open RBAC Matrix modal from rail
            page.locator("#btnTabAccess").click()
            page.wait_for_selector(".rbac-matrix-table", timeout=5000)
            table_text = page.locator(".rbac-matrix-table").first.inner_text()
            assert "governance capability" in table_text.lower()
            assert "approve code" in table_text.lower()

            # Close modal
            page.keyboard.press("Escape")
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=5)


