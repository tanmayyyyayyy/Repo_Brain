import json
import os
import subprocess
import sys
import tempfile
import time
from playwright.sync_api import sync_playwright
import pytest

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
            browser = p.chromium.launch(headless=True)
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

            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        import shutil
        shutil.rmtree(tmp_demo_dir, ignore_errors=True)
