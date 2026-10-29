import os
import re
import shutil
import subprocess
import sys
import tempfile

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
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle")
            page.wait_for_selector(".verdict", timeout=10000)

            page.locator("#btnTabAudit").click()
            page.wait_for_selector(".audit-timeline", timeout=10000)
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
