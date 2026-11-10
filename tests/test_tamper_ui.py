import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest
pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_tamper_ui_marks_server_reported_blocks():
    tmp_demo_dir = tempfile.mkdtemp(prefix="repobrain-tamper-ui-test-")
    env = {**os.environ, "REPOBRAIN_DEMO_DIR": tmp_demo_dir}
    port = 8794
    cmd = [sys.executable, "-m", "repobrain", "serve", "--demo", "--no-browser", "--port", str(port)]
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

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
                    pytest.skip(f"Playwright browser executable not installed: {e}")
                raise
            page = browser.new_page()
            page.goto(url, wait_until="networkidle")
            page.wait_for_selector(".verdict", timeout=10000)

            # Verify diff inspector syntax highlighter produces clean markup on ci.yml (no class="syn-*" leak)
            page.locator("tr:has-text('.github/workflows/ci.yml')").first.click()
            page.wait_for_selector(".diff-viewer .diff-code", timeout=10000)
            diff_text = "\n".join(el.inner_text() for el in page.locator(".diff-viewer .diff-code").all())
            assert "curl" in diff_text and 'class="syn-' not in diff_text and 'syn-str">' not in diff_text, (
                f"Broken highlight markup leaked into rendered diff: {diff_text[:300]}"
            )
            page.keyboard.press("Escape")
            page.wait_for_timeout(150)

            page.locator("#btnTabAudit").click()
            page.wait_for_selector(".audit-timeline", timeout=10000)
            assert "hmac-signed" in page.locator("#chainStatus").inner_text().lower()
            assert "hmac-signed" in page.locator("#main").inner_text().lower()
            page.locator("button:has-text('Simulate tampering')").click()
            page.wait_for_selector("text=DETECTED", timeout=10000)

            response = page.evaluate("() => S.tamper")
            assert response["ok"] is False
            expected_invalidated = [str(seq) for seq in response["invalidated_seqs"]]

            actual_tampered = [
                node.get_attribute("data-seq")
                for node in page.locator(".audit-node.tampered").all()
            ]
            actual_downstream = [
                node.get_attribute("data-seq")
                for node in page.locator(".audit-node.downstream-broken").all()
            ]
            actual_invalidated = [
                node.get_attribute("data-seq")
                for node in page.locator(
                    ".audit-node[data-tamper-state='tampered'], "
                    ".audit-node[data-tamper-state='downstream-broken']"
                ).all()
            ]

            assert actual_tampered == [str(response["tampered_seq"])]
            assert actual_downstream == [str(seq) for seq in response["downstream_seqs"]]
            assert actual_invalidated == expected_invalidated

            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(tmp_demo_dir, ignore_errors=True)
