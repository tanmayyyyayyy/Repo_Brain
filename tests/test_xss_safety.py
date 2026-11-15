import json
import os
import subprocess
import sys
import tempfile
import time
import pytest
pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_ui_xss_safety_against_malicious_findings():
    tmp_demo_dir = tempfile.mkdtemp(prefix="repobrain-xss-test-")
    env = {**os.environ, "REPOBRAIN_DEMO_DIR": tmp_demo_dir}
    port = 8794
    cmd = [sys.executable, "-m", "repobrain", "serve", "--demo", "--no-browser", "--port", str(port)]
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    url = None
    try:
        for _ in range(30):
            line = proc.stdout.readline()
            if f":{port}/?t=" in line:
                for token in line.strip().split():
                    if token.startswith("http://"):
                        url = token
                        break
                if url:
                    break
        assert url is not None, "Server did not launch in time"

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as e:
                if "Executable doesn't exist" in str(e):
                    pytest.skip(f"Playwright browser executable not installed: {e}")
                raise
            page = browser.new_page()

            # Listen for any unexpected alert or dialog
            xss_alert = []
            page.on("dialog", lambda dialog: xss_alert.append(dialog.message))

            page.goto(url, wait_until="networkidle")

            # Inject a finding with malicious XSS payloads into the frontend state and re-render
            xss_payload = '<img src="x" onerror="window.__xss_fired=1"><svg onload="window.__xss_fired=1">'
            page.evaluate("""(payload) => {
                window.__xss_fired = undefined;
                if (window.S && window.S.rev) {
                    window.S.rev.findings.push({
                        severity: "block",
                        rule: "test-xss",
                        file: payload,
                        message: "Malicious payload: " + payload,
                        evidence: payload
                    });
                    window.render();
                }
            }""", xss_payload)

            page.wait_for_timeout(300)

            # Assert XSS was never triggered
            fired = page.evaluate("() => window.__xss_fired")
            assert fired is None, f"XSS payload executed! Value: {fired}"
            assert len(xss_alert) == 0, f"Dialog appeared from XSS: {xss_alert}"

            # 2. Test XSS safety inside auth modal, profile tab, and user dropdown
            modal_payload = '<img src=x onerror="window.__xss_modal=1"><script>window.__xss_modal=1</script>'
            page.evaluate("""(payload) => {
                window.__xss_modal = undefined;
                window.S.currentUser = {
                    id: "usr-xss",
                    name: "Malicious " + payload,
                    email: "attacker" + payload + "@evil.com",
                    role: "admin",
                    role_badge: "ADMIN",
                    company: "Injected " + payload,
                    title: "Lead " + payload,
                    email_verified: false,
                    session_hash: "hash" + payload
                };
                window.renderUserRoleBar();
                window.openAuthModal('profile');
            }""", modal_payload)

            page.wait_for_timeout(300)
            fired_modal = page.evaluate("() => window.__xss_modal")
            assert fired_modal is None, f"XSS payload executed in profile modal! Value: {fired_modal}"
            assert len(xss_alert) == 0, f"Dialog appeared from XSS modal: {xss_alert}"

            # Test signin, signup, verify, and matrix tabs with malicious strings
            for tab_name in ("signin", "signup", "verify", "matrix"):
                page.evaluate(f"() => window.setAuthModalTab('{tab_name}')")
                page.wait_for_timeout(150)
                fired_tab = page.evaluate("() => window.__xss_modal")
                assert fired_tab is None, f"XSS payload executed in tab '{tab_name}'! Value: {fired_tab}"

            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        import shutil
        shutil.rmtree(tmp_demo_dir, ignore_errors=True)
