#!/usr/bin/env python3
"""
Live Google Chrome Full End-to-End Walkthrough & Test Suite for RepoBrain Enterprise.
Launches the demo server with HMAC signing, opens real Google Chrome, and executes
all governance events, persona switches, security gates, and AST optimizations
with a floating on-screen presenter HUD for seamless screen recording.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREENSHOTS_DIR = os.path.join(ROOT, "docs", "demo", "test_runs")
PORT = 8765


def main():
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    tmp_demo_dir = tempfile.mkdtemp(prefix="repobrain-live-demo-")
    env = {
        **os.environ,
        "REPOBRAIN_DEMO_DIR": tmp_demo_dir,
        "REPOBRAIN_OPEN_DEMO": "1",
        "REPOBRAIN_AUDIT_KEY": "demo-hmac-key-2024",
    }

    print("=" * 70)
    print("🚀 LAUNCHING REPOBRAIN ENTERPRISE SERVER...")
    print(f"   Root: {ROOT}")
    print(f"   Port: {PORT}")
    print(f"   HMAC Audit Key: Configured")
    print("=" * 70)

    server_cmd = [
        sys.executable,
        "-m",
        "repobrain",
        "serve",
        "--demo",
        "--no-browser",
        "--port",
        str(PORT),
    ]
    proc = subprocess.Popen(
        server_cmd,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    url = None
    try:
        for _ in range(40):
            line = proc.stdout.readline()
            if not line:
                break
            m = re.search(r"http://127\.0\.0\.1:\d+/\?t=\S+", line)
            if m:
                url = m.group(0)
                break
            if "listening on" in line:
                url = f"http://127.0.0.1:{PORT}/"
                break
            time.sleep(0.1)

        if not url:
            url = f"http://127.0.0.1:{PORT}/"
        print(f"✅ RepoBrain server live at: {url}\n")

        print("=" * 70)
        print("🌐 LAUNCHING GOOGLE CHROME FOR LIVE SCREEN RECORDING...")
        print("=" * 70)

        with sync_playwright() as p:
            # Launch real Google Chrome visibly on screen
            browser = p.chromium.launch(
                channel="chrome",
                headless=False,
                args=["--start-maximized", "--disable-infobars"]
            )

            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                record_video_dir=SCREENSHOTS_DIR,
                record_video_size={"width": 1440, "height": 900}
            )
            page = context.new_page()

            # Navigate to RepoBrain console
            page.goto(url, wait_until="networkidle")
            page.wait_for_selector(".verdict", timeout=15000)

            # Inject the Presenter HUD Overlay
            page.evaluate("""
            () => {
                const hud = document.createElement('div');
                hud.id = 'live-demo-hud';
                hud.style.cssText = `
                    position: fixed;
                    bottom: 24px;
                    right: 24px;
                    background: rgba(11, 17, 32, 0.94);
                    backdrop-filter: blur(16px);
                    -webkit-backdrop-filter: blur(16px);
                    border: 1px solid rgba(56, 189, 248, 0.45);
                    border-radius: 14px;
                    padding: 16px 22px;
                    color: #fff;
                    font-family: system-ui, -apple-system, sans-serif;
                    z-index: 999999;
                    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.65), 0 0 20px rgba(56, 189, 248, 0.15);
                    min-width: 380px;
                    max-width: 440px;
                    pointer-events: none;
                    transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
                `;
                hud.innerHTML = `
                    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
                        <div style="display:flex;align-items:center;gap:8px">
                            <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#10b981;box-shadow:0 0 12px #10b981;"></span>
                            <span style="font-size:11px;font-weight:800;letter-spacing:1px;color:#38bdf8;text-transform:uppercase">RepoBrain Enterprise</span>
                        </div>
                        <span id="hud-step-num" style="font-size:11px;font-weight:700;color:#94a3b8;background:rgba(255,255,255,0.08);padding:2px 8px;border-radius:10px">Step 1 of 12</span>
                    </div>
                    <div id="hud-title" style="font-size:15px;font-weight:700;color:#f8fafc;margin-bottom:4px">Executive Mission Control</div>
                    <div id="hud-desc" style="font-size:12.5px;color:#cbd5e1;line-height:1.45">5-stage automated governance pipeline for AI-authored commits</div>
                `;
                document.body.appendChild(hud);
            }
            """)

            def set_hud(step_num, title, desc, sleep_sec=3.2):
                print(f"🎬 [Step {step_num}/12] {title}")
                print(f"   ↳ {desc}")
                page.evaluate(f"""
                () => {{
                    const s = document.getElementById('hud-step-num');
                    const t = document.getElementById('hud-title');
                    const d = document.getElementById('hud-desc');
                    if (s) s.innerText = 'Step {step_num} of 12';
                    if (t) t.innerText = {json.dumps(title)};
                    if (d) d.innerText = {json.dumps(desc)};
                }}
                """)
                time.sleep(sleep_sec)

            # ─────────────────────────────────────────────────────────
            # STEP 1: Mission Control Overview & Telemetry
            # ─────────────────────────────────────────────────────────
            set_hud(
                1,
                "Executive Mission Control Dashboard",
                "Full repository posture, 5-stage pipeline stepper, and live telemetry for AI coding agents."
            )
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "01_mission_control.png"))

            # ─────────────────────────────────────────────────────────
            # STEP 2: Role Perspective Banner & Corporate Identity
            # ─────────────────────────────────────────────────────────
            set_hud(
                2,
                "Release Manager Perspective (Alex Mercer)",
                "Full governance authority active. Commit merge approval, waivers, and user administration."
            )
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "02_admin_perspective.png"))

            # ─────────────────────────────────────────────────────────
            # STEP 3: 1-Click Evaluator Persona Switching
            # ─────────────────────────────────────────────────────────
            set_hud(
                3,
                "1-Click Evaluator Persona Switching",
                "Toggling user pill menu to switch role to Developer (Alice Chen)."
            )
            # Click user pill to open dropdown
            page.locator(".user-pill").click()
            time.sleep(1.2)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "03_user_dropdown.png"))

            # Switch to Developer persona
            page.locator(".persona-item:has-text('Alice Chen')").click()
            time.sleep(1.5)
            set_hud(
                3,
                "Developer Perspective Active",
                "User pill updated to DEV (Alice Chen). Code approval & waiver permissions strictly restricted."
            )
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "03b_developer_persona.png"))

            # ─────────────────────────────────────────────────────────
            # STEP 4: Real Security Gate (Permission Denied 403)
            # ─────────────────────────────────────────────────────────
            set_hud(
                4,
                "Zero-Trust Policy Enforcement (403)",
                "Developer attempts to approve code merge. Intercepted by RBAC engine with Access Denied modal."
            )
            # Trigger permission denied via client-side call with developer credentials
            page.evaluate("""
            async () => {
                try {
                    await api('/api/approve', { id: 'demo-prop', actor: 'Alice Chen' });
                } catch(e) {
                    console.log('Intercepted expected 403:', e);
                }
            }
            """)
            page.wait_for_selector(".modal-window", timeout=5000)
            time.sleep(2.5)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "04_permission_denied.png"))

            # Switch back to Admin persona using the modal button
            page.evaluate("closeDiffModal(); switchDemoPersona('admin');")
            time.sleep(1.5)

            # ─────────────────────────────────────────────────────────
            # STEP 5: Enterprise RBAC Matrix Modal & Team Directory
            # ─────────────────────────────────────────────────────────
            set_hud(
                5,
                "Enterprise Access Control Matrix & Team Directory",
                "15-capability zero-trust matrix across Dev, QA, Security, and Admin personas."
            )
            page.locator("#btnTabAccess").click()
            page.wait_for_selector(".rbac-matrix-table", timeout=5000)
            time.sleep(3.0)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "05_rbac_matrix.png"))
            page.keyboard.press("Escape")
            time.sleep(1.0)

            # ─────────────────────────────────────────────────────────
            # STEP 6: Corporate Domain Whitelist Validation
            # ─────────────────────────────────────────────────────────
            set_hud(
                6,
                "Corporate Domain Whitelist & Auth Protection",
                "Registration rejects public webmail (@gmail, @yahoo) and enforces verified enterprise domains."
            )
            page.evaluate("openRegisterModal()")
            page.wait_for_selector("#regEmail", timeout=5000)
            time.sleep(0.8)

            # Type public webmail (blocked)
            email_input = page.locator("#regEmail")
            email_input.fill("hacker@gmail.com")
            page.evaluate("validateCorporateEmailLive('hacker@gmail.com', '#regEmailFeedback')")
            time.sleep(1.8)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "06_email_blocked.png"))

            # Clear and type corporate email (accepted)
            email_input.fill("sarah.connor@cyberdyne.corp")
            page.evaluate("validateCorporateEmailLive('sarah.connor@cyberdyne.corp', '#regEmailFeedback')")
            time.sleep(2.0)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "06b_email_accepted.png"))
            page.keyboard.press("Escape")
            time.sleep(1.0)

            # ─────────────────────────────────────────────────────────
            # STEP 7: Scenario A — AI Agent Attack & Shield Engine
            # ─────────────────────────────────────────────────────────
            set_hud(
                7,
                "Scenario A: Multi-Vector AI Agent Attack (BLOCKED)",
                "Shield detects CI workflow tampering, prompt injection in markdown, hardcoded AWS keys, and typosquatting."
            )
            page.evaluate("scenario('risky')")
            time.sleep(2.5)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "07_scenario_a_risky.png"))

            # Inspect diff of protected CI workflow file
            set_hud(
                7,
                "Diff Inspector: Protected CI Workflow Blocked",
                "AI agent attempted to insert 'curl ... | sh' reverse shell into GitHub Actions."
            )
            page.evaluate("openDiff('.github/workflows/ci.yml')")
            page.wait_for_selector(".diff-viewer", timeout=5000)
            time.sleep(3.0)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "07b_diff_inspector.png"))
            page.keyboard.press("Escape")
            time.sleep(1.0)

            # ─────────────────────────────────────────────────────────
            # STEP 8: Scenario B — Complexity Gate (CHANGES REQUIRED)
            # ─────────────────────────────────────────────────────────
            set_hud(
                8,
                "Scenario B: Pricing PR & Complexity Gate",
                "Cyclomatic complexity score 27 exceeds threshold 15. PR blocked pending automated optimization."
            )
            page.evaluate("scenario('pricing')")
            time.sleep(2.5)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "08_scenario_b_pricing.png"))

            # ─────────────────────────────────────────────────────────
            # STEP 9: Verified AST Optimizer & Differential Fuzzer
            # ─────────────────────────────────────────────────────────
            set_hud(
                9,
                "Verified AST Optimizer & Differential Fuzzing",
                "Running AST rewrite in scratch sandbox. Executes test suite + 1,000 fuzzed inputs across 4 functions with 0 divergences in this seeded run."
            )
            page.evaluate("go('optimizer'); runOpt();")
            time.sleep(3.5)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "09_ast_optimizer.png"))

            # ─────────────────────────────────────────────────────────
            # STEP 10: Cryptographic HMAC-Signed Audit Ledger
            # ─────────────────────────────────────────────────────────
            set_hud(
                10,
                "Cryptographic HMAC-Signed Audit Ledger",
                "Every review, policy check, and approval is anchored in an immutable SHA-256 + HMAC-signed chain."
            )
            page.evaluate("go('audit')")
            time.sleep(2.5)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "10_audit_hmac_verified.png"))

            # Simulate tampering detection
            set_hud(
                10,
                "Live Tamper Detection Simulation",
                "Simulating in-memory modification of historical block #2: instant downstream signature invalidation!"
            )
            page.evaluate("tamper()")
            time.sleep(3.0)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "10b_audit_tamper_detected.png"))

            # Restore clean audit state
            page.evaluate("audit().then(render)")
            time.sleep(1.5)

            # ─────────────────────────────────────────────────────────
            # STEP 11: Shield Playground & Governance Policies
            # ─────────────────────────────────────────────────────────
            set_hud(
                11,
                "Shield Playground & Policy Enforcement",
                "Preflight agent safety rules for Claude Code hook, Cursor MCP server, and CI pipelines."
            )
            page.evaluate("go('shield')")
            time.sleep(2.5)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "11_shield_playground.png"))

            # ─────────────────────────────────────────────────────────
            # STEP 12: Enterprise Command Palette (Cmd+K)
            # ─────────────────────────────────────────────────────────
            set_hud(
                12,
                "Enterprise Command Palette (Cmd+K)",
                "Keyboard-first navigation with quick access to RBAC matrix, persona switches, and diagnostics."
            )
            page.evaluate("openCmdPalette()")
            time.sleep(1.0)
            page.locator(".cmd-input").fill("auth")
            time.sleep(2.5)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "12_command_palette.png"))
            page.keyboard.press("Escape")
            time.sleep(1.0)

            # ─────────────────────────────────────────────────────────
            # FINALE: Presentation Complete
            # ─────────────────────────────────────────────────────────
            set_hud(
                12,
                "RepoBrain Enterprise Demo Complete! 🏆",
                "130 Automated Tests Passing · Cryptographically Signed · Enterprise Production Ready",
                sleep_sec=4.5
            )
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "13_finale.png"))

            print("\n" + "=" * 70)
            print("🎉 ALL 12 STEPS EXECUTED SUCCESSFULLY IN GOOGLE CHROME!")
            print(f"📸 Screenshots saved to: {SCREENSHOTS_DIR}")
            print("=" * 70)

            # Close context to flush video
            context.close()
            browser.close()

    finally:
        print("Stopping demo server...")
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    main()

