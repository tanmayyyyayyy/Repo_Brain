#!/usr/bin/env python3
"""
Captures high-resolution screenshots of the RepoBrain Mission Control console
at 1440x900 (Desktop) and 390x844 (Mobile) in dark and light themes.
"""
import os
import re
import subprocess
import sys
import tempfile
import time
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_DIR = os.path.join(ROOT, "docs", "ui")
PORT = 8792


def main():
    os.makedirs(UI_DIR, exist_ok=True)
    tmp_demo_dir = tempfile.mkdtemp(prefix="repobrain-screenshot-")
    env = {**os.environ, "REPOBRAIN_DEMO_DIR": tmp_demo_dir}

    print(f"Launching demo server on port {PORT}...")
    server_cmd = [sys.executable, "-m", "repobrain", "serve", "--demo", "--no-browser", "--port", str(PORT)]
    proc = subprocess.Popen(server_cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    url = None
    try:
        for _ in range(30):
            line = proc.stdout.readline()
            m = re.search(r"http://127\.0\.0\.1:\d+/\?t=\S+", line)
            if m:
                url = m.group(0)
                break
        if not url:
            raise RuntimeError(f"Server did not start. Output: {proc.stdout.read()[:500]}")
        print(f"Server ready at: {url}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # Desktop 1440x900
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(url, wait_until="networkidle")
            page.wait_for_selector(".verdict", timeout=10000)

            # 1. Blocked Review (Dark)
            print("Capturing 01: Blocked Review (1440 Dark)...")
            page.screenshot(path=os.path.join(UI_DIR, "01_blocked_review_1440_dark.png"))

            # 1. Blocked Review (Light)
            print("Capturing 01: Blocked Review (1440 Light)...")
            page.evaluate("document.documentElement.setAttribute('data-theme', 'light'); updateThemeIcon('light');")
            page.wait_for_timeout(300)
            page.screenshot(path=os.path.join(UI_DIR, "01_blocked_review_1440_light.png"))
            page.evaluate("document.documentElement.setAttribute('data-theme', 'dark'); updateThemeIcon('dark');")
            page.wait_for_timeout(200)

            # 2. File Diff Inspector with Inline Annotations
            print("Opening diff for .github/workflows/ci.yml...")
            page.locator("code:has-text('.github/workflows/ci.yml')").first.click()
            page.wait_for_selector(".diff-viewer", timeout=10000)
            page.wait_for_timeout(400)
            print("Capturing 02: File Diff with Annotations (1440 Dark)...")
            page.screenshot(path=os.path.join(UI_DIR, "02_file_diff_annotations_1440_dark.png"))

            page.evaluate("document.documentElement.setAttribute('data-theme', 'light'); updateThemeIcon('light');")
            page.wait_for_timeout(300)
            print("Capturing 02: File Diff with Annotations (1440 Light)...")
            page.screenshot(path=os.path.join(UI_DIR, "02_file_diff_annotations_1440_light.png"))
            page.evaluate("document.documentElement.setAttribute('data-theme', 'dark'); updateThemeIcon('dark');")

            # Close diff modal with Esc
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

            # 3. Command Palette
            print("Opening Command Palette (Cmd+K)...")
            page.keyboard.press("Meta+k")
            page.wait_for_selector(".cmd-box", timeout=5000)
            page.wait_for_timeout(300)
            print("Capturing 05: Command Palette (1440 Dark)...")
            page.screenshot(path=os.path.join(UI_DIR, "05_command_palette_1440_dark.png"))
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

            # 4. Scenario B & Optimizer
            print("Switching to Scenario B (messy AI PR)...")
            page.locator("button:has-text('B · messy AI PR')").click()
            page.wait_for_selector(".v-CHANGES_REQUIRED", timeout=10000)

            print("Running Optimizer on Scenario B...")
            page.locator("button:has-text('Run optimizer →')").click()
            page.wait_for_selector(".pill:has-text('verified')", timeout=15000)
            page.wait_for_timeout(400)
            print("Capturing 03: Optimizer Verified (1440 Dark)...")
            page.screenshot(path=os.path.join(UI_DIR, "03_optimizer_verified_1440_dark.png"))

            page.evaluate("document.documentElement.setAttribute('data-theme', 'light'); updateThemeIcon('light');")
            page.wait_for_timeout(300)
            print("Capturing 03: Optimizer Verified (1440 Light)...")
            page.screenshot(path=os.path.join(UI_DIR, "03_optimizer_verified_1440_light.png"))
            page.evaluate("document.documentElement.setAttribute('data-theme', 'dark'); updateThemeIcon('dark');")

            # 5. Audit Chain with Tamper Simulation
            print("Switching to Audit & Report tab...")
            page.locator("#btnTabAudit").click()
            page.wait_for_selector(".audit-timeline", timeout=10000)

            print("Simulating in-memory tampering...")
            page.locator("button:has-text('Simulate tampering')").click()
            page.wait_for_selector("text=DETECTED", timeout=10000)
            page.wait_for_timeout(400)
            print("Capturing 04: Audit Chain Tampered (1440 Dark)...")
            page.screenshot(path=os.path.join(UI_DIR, "04_audit_chain_tampered_1440_dark.png"))

            page.evaluate("document.documentElement.setAttribute('data-theme', 'light'); updateThemeIcon('light');")
            page.wait_for_timeout(300)
            print("Capturing 04: Audit Chain Tampered (1440 Light)...")
            page.screenshot(path=os.path.join(UI_DIR, "04_audit_chain_tampered_1440_light.png"))
            page.evaluate("document.documentElement.setAttribute('data-theme', 'dark'); updateThemeIcon('dark');")

            # Mobile 390x844 (iPhone 14 / modern mobile)
            page_mobile = browser.new_page(viewport={"width": 390, "height": 844})
            page_mobile.goto(url, wait_until="networkidle")
            page_mobile.wait_for_selector(".verdict", timeout=10000)
            print("Capturing Mobile 390x844 Blocked Review (Dark)...")
            page_mobile.screenshot(path=os.path.join(UI_DIR, "01_blocked_review_390_dark.png"))

            page_mobile.evaluate("document.documentElement.setAttribute('data-theme', 'light'); updateThemeIcon('light');")
            page_mobile.wait_for_timeout(300)
            print("Capturing Mobile 390x844 Blocked Review (Light)...")
            page_mobile.screenshot(path=os.path.join(UI_DIR, "01_blocked_review_390_light.png"))

            browser.close()

        print(f"\nAll screenshots successfully captured in {UI_DIR}/!")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        import shutil
        shutil.rmtree(tmp_demo_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
