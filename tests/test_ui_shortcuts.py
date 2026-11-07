import os
import re
import subprocess
import sys
import tempfile
import time
import pytest
pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_single_key_shortcuts_ignored_in_inputs_and_contenteditable():
    tmp_demo_dir = tempfile.mkdtemp(prefix="repobrain-shortcuts-test-")
    env = {**os.environ, "REPOBRAIN_DEMO_DIR": tmp_demo_dir}
    port = 8793
    cmd = [sys.executable, "-m", "repobrain", "serve", "--demo", "--no-browser", "--port", str(port)]
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    url = None
    try:
        for _ in range(30):
            line = proc.stdout.readline()
            m = re.search(r"http://127\.0\.0\.1:\d+/\?t=\S+", line)
            if m:
                url = m.group(0)
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

            # 1. Switch to Scenario B to access the complexity waiver inputs
            page.locator("button:has-text('B · messy AI PR')").click()
            page.wait_for_selector("#wactor", timeout=10000)

            # 2. Focus input #wactor and type single-key shortcut characters
            page.locator("#wactor").focus()
            page.keyboard.type("123oap?")

            # Verify input received all typed characters
            typed_val = page.locator("#wactor").input_value()
            assert typed_val == "123oap?", f"Expected '123oap?' in input, got '{typed_val}'"

            # Verify active tab remained on 'review' and did NOT switch to optimizer (2) or audit (5)
            active_btn = page.locator(".rail-nav-btn.active")
            assert "PR review" in active_btn.inner_text(), f"Tab switched unexpectedly to {active_btn.inner_text()}"
            # Verify no shortcuts modal was opened
            assert page.locator(".modal-window").count() == 0, "Shortcuts modal opened while typing in input"

            # 3. Test with a contenteditable element
            page.evaluate("""() => {
                const ce = document.createElement('div');
                ce.id = 'testContentEditable';
                ce.contentEditable = 'true';
                ce.textContent = '';
                document.body.appendChild(ce);
            }""")
            page.locator("#testContentEditable").focus()
            page.keyboard.type("123")
            ce_val = page.locator("#testContentEditable").inner_text()
            assert ce_val == "123", f"Expected '123' in contenteditable, got '{ce_val}'"
            active_btn = page.locator(".rail-nav-btn.active")
            assert "PR review" in active_btn.inner_text(), "Tab switched while in contenteditable"

            # 4. Blur / click canvas, then verify shortcuts work when NOT focused on input
            page.locator(".verdict").click()

            # Press '2' -> should navigate to Optimizer
            page.keyboard.press("2")
            page.wait_for_selector("button:has-text('Run optimizer')", timeout=5000)
            active_btn = page.locator(".rail-nav-btn.active")
            assert "Optimizer" in active_btn.inner_text(), "Failed to navigate to Optimizer via '2'"

            # Press '1' -> should navigate back to PR Review
            page.keyboard.press("1")
            page.wait_for_selector(".verdict", timeout=5000)
            active_btn = page.locator(".rail-nav-btn.active")
            assert "PR review" in active_btn.inner_text(), "Failed to navigate to PR review via '1'"

            # Press 'P' -> should toggle Presenter Mode
            assert not page.evaluate("() => document.body.classList.contains('presenter-mode')")
            page.keyboard.press("p")
            assert page.evaluate("() => document.body.classList.contains('presenter-mode')"), "Failed to toggle presenter mode via 'p'"
            page.keyboard.press("p")
            assert not page.evaluate("() => document.body.classList.contains('presenter-mode')"), "Failed to toggle off presenter mode"

            # Press '?' -> should open shortcuts sheet
            page.keyboard.press("?")
            page.wait_for_selector("h3:has-text('Keyboard Shortcuts')", timeout=5000)
            assert page.locator(".modal-window").count() == 1, "Shortcuts modal did not open via '?'"

            # Press 'Escape' -> closes modal
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            assert page.locator(".modal-window").count() == 0, "Escape did not close shortcuts modal"

            browser.close()

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        import shutil
        shutil.rmtree(tmp_demo_dir, ignore_errors=True)
