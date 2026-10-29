import os
import re
import subprocess
import sys
import tempfile
from playwright.sync_api import sync_playwright
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_no_horizontal_scroll_on_mobile_viewports():
    tmp_demo_dir = tempfile.mkdtemp(prefix="repobrain-mobile-test-")
    env = {**os.environ, "REPOBRAIN_DEMO_DIR": tmp_demo_dir}
    port = 8791
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
            browser = p.chromium.launch(headless=True)

            # Viewports specified in prompt: 360px, 390px, 768px
            viewports = [
                {"width": 360, "height": 740, "name": "360px (Small Mobile)"},
                {"width": 390, "height": 844, "name": "390px (Standard iPhone)"},
                {"width": 768, "height": 1024, "name": "768px (Tablet)"},
            ]

            tabs = ["review", "optimizer", "shield", "explainer", "audit", "policy"]

            for vp in viewports:
                page = browser.new_page(viewport={"width": vp["width"], "height": vp["height"]})
                page.goto(url, wait_until="networkidle")
                page.wait_for_selector(".verdict", timeout=10000)

                for tab in tabs:
                    # Switch tab via evaluate to test clean navigation on mobile
                    page.evaluate(f"go('{tab}')")
                    page.wait_for_timeout(150)

                    # Check for horizontal page overflow
                    overflow_data = page.evaluate("""() => {
                        const htmlScroll = document.documentElement.scrollWidth;
                        const bodyScroll = document.body.scrollWidth;
                        const innerW = window.innerWidth;
                        return {
                            htmlScroll,
                            bodyScroll,
                            innerW,
                            overflows: (htmlScroll > innerW || bodyScroll > innerW)
                        };
                    }""")

                    assert not overflow_data["overflows"], (
                        f"Horizontal scroll detected on {vp['name']}, tab '{tab}': "
                        f"htmlScroll={overflow_data['htmlScroll']}, "
                        f"bodyScroll={overflow_data['bodyScroll']}, "
                        f"innerWidth={overflow_data['innerW']}"
                    )

                page.close()

            browser.close()

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        import shutil
        shutil.rmtree(tmp_demo_dir, ignore_errors=True)
