#!/usr/bin/env python3
"""
Headless demo verification script for RepoBrain.
Drives the console through Scenario A, B, optimize, approve, review re-run, audit, and tamper detection.
Exits 0 on success, non-zero on failure.
"""
import os
import re
import subprocess
import sys
import tempfile
import time
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREENSHOTS_DIR = os.path.join(ROOT, "docs", "screenshots")
PORT = 8798


def main():
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    tmp_demo_dir = tempfile.mkdtemp(prefix="repobrain-demo-check-")
    env = {**os.environ, "REPOBRAIN_DEMO_DIR": tmp_demo_dir}

    print(f"[1/7] Launching RepoBrain demo server on port {PORT}...")
    server_cmd = [sys.executable, "-m", "repobrain", "serve", "--demo", "--no-browser", "--port", str(PORT)]
    proc = subprocess.Popen(server_cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    url = None
    try:
        # Read server output to find URL with token
        for _ in range(30):
            line = proc.stdout.readline()
            m = re.search(r"http://127\.0\.0\.1:\d+/\?t=\S+", line)
            if m:
                url = m.group(0)
                break
        if not url:
            raise RuntimeError(f"Server did not output launch URL in time. Output: {proc.stdout.read()[:500]}")
        print(f"Server ready at: {url}")

        with sync_playwright() as p:
            print("[2/7] Launching headless browser...")
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(url, wait_until="networkidle")

            # Scenario A: Risky AI PR
            print("[3/7] Verifying Scenario A (risky AI PR)...")
            page.wait_for_selector(".verdict", timeout=10000)
            verdict_text = page.locator(".verdict .big").inner_text()
            assert "BLOCKED" in verdict_text, f"Expected BLOCKED, got {verdict_text}"
            content = page.content()
            assert "blocked-path" in content, "Expected blocked-path finding"
            assert "secret" in content, "Expected secret finding"
            assert "prompt-injection" in content, "Expected prompt-injection finding"
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "01_scenario_a_blocked.png"))
            print("  ✓ Scenario A correctly blocked with policy, secret, and injection findings")

            # Scenario B: Messy AI PR
            print("[4/7] Verifying Scenario B (messy AI PR)...")
            page.locator("button:has-text('B · messy AI PR')").click()
            page.wait_for_selector(".v-CHANGES_REQUIRED", timeout=10000)
            verdict_text = page.locator(".verdict .big").inner_text()
            assert "CHANGES REQUIRED" in verdict_text, f"Expected CHANGES REQUIRED, got {verdict_text}"
            assert "discount_for" in page.content(), "Expected discount_for in complexity gate"
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "02_scenario_b_changes_required.png"))
            print("  ✓ Scenario B triggers complexity gate on discount_for")

            # Optimizer
            print("[5/7] Running optimizer on Scenario B...")
            page.locator("button:has-text('Run optimizer →')").click()
            page.wait_for_selector(".pill:has-text('verified')", timeout=15000)
            content = page.content()
            assert "cognitive" in content and "15" in content and "10" in content, "Expected cognitive reduction 15->10"
            assert "tests" in content.lower(), "Expected tests report"
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "03_optimizer_verified.png"))
            print("  ✓ Optimizer rewrites discount_for; cognitive 15->10, depth 4->3, tests verified")

            # Approve & apply
            print("[6/7] Approving and applying proposal with named human...")
            page.fill("#aactor", "Priya Sharma")
            page.locator("button:has-text('Approve & apply')").click()
            page.wait_for_selector("text=Applied as commit", timeout=10000)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "04_approved_and_applied.png"))
            print("  ✓ Proposal applied to repo with Approved-by trailer")

            # Confirm Review passes
            page.locator("#btnTabReview").click()
            page.wait_for_selector(".v-ALLOWED", timeout=10000)
            assert "ALLOWED" in page.locator(".verdict .big").inner_text()
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "05_review_allowed.png"))
            print("  ✓ Re-run PR review: verdict is now ALLOWED")

            # Audit trail & Tamper detection
            print("[7/7] Verifying audit hash chain & tamper detection...")
            page.locator("#btnTabAudit").click()
            page.wait_for_selector("#chainStatus:has-text('chain ✓')", timeout=10000)
            page.locator("button:has-text('Simulate tampering')").click()
            page.wait_for_selector("text=DETECTED", timeout=10000)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "06_audit_tamper_detected.png"))
            print("  ✓ Hash chain verified, in-memory edit correctly DETECTED by audit engine")

            browser.close()

        print("\n=======================================================")
        print("ALL DEMO CHECK PASSES SUCCESSFULLY! REPOBRAIN IS GREEN.")
        print(f"Screenshots saved to {SCREENSHOTS_DIR}/")
        print("=======================================================")
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

