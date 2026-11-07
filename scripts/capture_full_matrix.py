#!/usr/bin/env python3
"""
Captures the complete 16-screenshot matrix for the redesigned RepoBrain UI
(4 views x 2 viewports [1440x900, 390x844] x 2 themes [dark, light])
plus the 4-screenshot 'before' baseline from commit 37b7551^.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_DIR = os.path.join(ROOT, "docs", "ui")
BEFORE_DIR = os.path.join(UI_DIR, "before")
INDEX_PATH = os.path.join(ROOT, "repobrain", "web", "index.html")


def start_server(port, env):
    cmd = [sys.executable, "-m", "repobrain", "serve", "--demo", "--no-browser", "--port", str(port)]
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    url = None
    for _ in range(30):
        line = proc.stdout.readline()
        m = re.search(r"http://127\.0\.0\.1:\d+/\?t=\S+", line)
        if m:
            url = m.group(0)
            break
    if not url:
        raise RuntimeError(f"Server on port {port} failed to start. Output: {proc.stdout.read()[:500]}")
    return proc, url


def clear_toasts(page):
    page.evaluate("() => document.querySelectorAll('#toast-container .toast').forEach(el => el.remove())")


def capture_before_set():
    print("=== [1/2] Capturing Before Baseline (commit 37b7551^) ===")
    os.makedirs(BEFORE_DIR, exist_ok=True)

    # Save current redesigned index.html content
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        current_html = f.read()

    # Get original index.html from commit 37b7551^
    before_html = subprocess.check_output(["git", "show", "37b7551^:static/index.html"], cwd=ROOT).decode("utf-8")

    try:
        # Swap in before_html
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            f.write(before_html)

        tmp_demo = tempfile.mkdtemp(prefix="repobrain-before-")
        env = {**os.environ, "REPOBRAIN_DEMO_DIR": tmp_demo}
        port = 8788
        proc, url = start_server(port, env)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
                page.goto(url, wait_until="networkidle")
                page.wait_for_selector(".verdict", timeout=10000)

                # 1. Blocked Review (Before)
                print("  Capturing 01_blocked_review_before.png...")
                page.screenshot(path=os.path.join(BEFORE_DIR, "01_blocked_review_before.png"))

                # 2. File diff (Before)
                # The original console had no dedicated diff inspector; it rendered
                # the unified diff inside the optimizer view. Capture that diff as
                # the closest pre-overhaul equivalent.
                print("  Capturing 02_file_diff_before.png (original optimizer diff)...")
                page.locator("button:has-text('B · messy AI PR')").click()
                page.wait_for_selector(".v-CHANGES_REQUIRED", timeout=10000)
                page.evaluate("go('optimizer')")
                page.wait_for_timeout(300)
                page.locator("button:has-text('Run optimizer')").first.click()
                page.wait_for_selector(".pill:has-text('verified')", timeout=15000)
                page.locator("pre.diff").first.scroll_into_view_if_needed()
                page.wait_for_timeout(200)
                page.screenshot(path=os.path.join(BEFORE_DIR, "02_file_diff_before.png"))

                # 3. Optimizer Result (Before)
                print("  Capturing 03_optimizer_verified_before.png...")
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(200)
                page.screenshot(path=os.path.join(BEFORE_DIR, "03_optimizer_verified_before.png"))

                # 4. Audit Chain Tampered (Before)
                print("  Capturing 04_audit_chain_tampered_before.png...")
                page.evaluate("go('audit')")
                page.wait_for_timeout(300)
                page.locator("button:has-text('Simulate tampering')").click()
                page.wait_for_selector("text=DETECTED", timeout=10000)
                page.screenshot(path=os.path.join(BEFORE_DIR, "04_audit_chain_tampered_before.png"))

                browser.close()
        finally:
            proc.terminate()
            try: proc.wait(timeout=3)
            except subprocess.TimeoutExpired: proc.kill()
            shutil.rmtree(tmp_demo, ignore_errors=True)
    finally:
        # Restore redesigned index.html
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            f.write(current_html)


def capture_after_matrix():
    print("\n=== [2/2] Capturing Full 16-Screenshot Redesigned Matrix ===")
    os.makedirs(UI_DIR, exist_ok=True)
    tmp_demo = tempfile.mkdtemp(prefix="repobrain-after-")
    env = {**os.environ, "REPOBRAIN_DEMO_DIR": tmp_demo}
    port = 8789
    proc, url = start_server(port, env)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # Viewports: Desktop (1440x900) & Mobile (390x844)
            viewports = [
                (1440, 900, "1440"),
                (390, 844, "390")
            ]

            for width, height, vp_label in viewports:
                print(f"\n--- Viewport: {vp_label} ({width}x{height}) ---")
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(url, wait_until="networkidle")
                page.wait_for_selector(".verdict", timeout=10000)
                # Ensure reset to Scenario A (risky PR)
                page.evaluate("async () => { await scenario('risky'); }")
                page.wait_for_selector(".v-BLOCKED", timeout=10000)

                for theme in ["dark", "light"]:
                    print(f"  Setting theme: {theme}...")
                    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}'); updateThemeIcon('{theme}');")
                    page.wait_for_timeout(200)
                    clear_toasts(page)

                    # View 1: Blocked Review
                    page.evaluate("go('review')")
                    page.wait_for_selector(".verdict", timeout=5000)
                    out_path = os.path.join(UI_DIR, f"01_blocked_review_{vp_label}_{theme}.png")
                    page.screenshot(path=out_path)
                    print(f"  ✓ Saved {os.path.basename(out_path)}")

                    # View 2: File Diff with Annotations
                    clear_toasts(page)
                    page.evaluate("async () => { await openDiff('.github/workflows/ci.yml'); }")
                    page.wait_for_selector(".diff-viewer", timeout=10000)
                    page.wait_for_timeout(300)
                    out_path = os.path.join(UI_DIR, f"02_file_diff_annotations_{vp_label}_{theme}.png")
                    page.screenshot(path=out_path)
                    print(f"  ✓ Saved {os.path.basename(out_path)}")
                    page.evaluate("closeDiffModal()")
                    page.wait_for_timeout(200)

                # Switch to Scenario B for View 3 & 4
                page.evaluate("async () => { await scenario('pricing'); }")
                page.wait_for_selector(".v-CHANGES_REQUIRED", timeout=10000)
                page.evaluate("async () => { go('optimizer'); await runOpt(); }")
                page.wait_for_selector(".pill:has-text('verified')", timeout=15000)
                page.wait_for_timeout(300)

                for theme in ["dark", "light"]:
                    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}'); updateThemeIcon('{theme}');")
                    page.wait_for_timeout(200)
                    clear_toasts(page)

                    # View 3: Optimizer Result
                    out_path = os.path.join(UI_DIR, f"03_optimizer_verified_{vp_label}_{theme}.png")
                    page.screenshot(path=out_path)
                    print(f"  ✓ Saved {os.path.basename(out_path)}")

                # Audit Tab & Tamper Simulation for View 4
                page.evaluate("async () => { go('audit'); await tamper(); }")
                page.wait_for_selector("text=DETECTED", timeout=10000)
                page.wait_for_timeout(300)

                for theme in ["dark", "light"]:
                    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}'); updateThemeIcon('{theme}');")
                    page.wait_for_timeout(200)
                    clear_toasts(page)

                    # View 4: Audit Chain Tampered
                    out_path = os.path.join(UI_DIR, f"04_audit_chain_tampered_{vp_label}_{theme}.png")
                    page.screenshot(path=out_path)
                    print(f"  ✓ Saved {os.path.basename(out_path)}")

                page.close()

            browser.close()
    finally:
        proc.terminate()
        try: proc.wait(timeout=3)
        except subprocess.TimeoutExpired: proc.kill()
        shutil.rmtree(tmp_demo, ignore_errors=True)


def main():
    capture_before_set()
    capture_after_matrix()
    print("\n=======================================================")
    print("ALL 20 SCREENSHOTS (16 AFTER + 4 BEFORE) CAPTURED SUCCESSFULLY!")
    print(f"Artifacts saved in {UI_DIR}/")
    print("=======================================================")


if __name__ == "__main__":
    main()
