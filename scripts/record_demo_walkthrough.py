#!/usr/bin/env python3
"""Automated Demo Walkthrough for Screen Recording RepoBrain in Google Chrome."""
import subprocess
import time
import json
import urllib.request
import sys

URL = "http://127.0.0.1:8765/?t=G6havEKhhbVA93CWKYwOH4J0m445BEih"
API = "http://127.0.0.1:8765"

def run_js(code):
    clean = code.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    cmd = f'tell application "Google Chrome" to tell active tab of window 1 to execute javascript "{clean}"'
    subprocess.run(["osascript", "-e", cmd], capture_output=True)

def activate_chrome():
    subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to activate'], capture_output=True)

def open_url(url):
    cmd = f'tell application "Google Chrome" to tell active tab of window 1 to set URL to "{url}"'
    subprocess.run(["osascript", "-e", cmd], capture_output=True)

def open_new_tab(url):
    script = f'''
tell application "Google Chrome"
    activate
    tell window 1
        make new tab with properties {{URL:"{url}"}}
    end tell
end tell
'''
    subprocess.run(["osascript", "-e", script], capture_output=True)

def pause(sec):
    time.sleep(sec)

def post(endpoint, data=None):
    req = urllib.request.Request(
        f"{API}{endpoint}",
        data=json.dumps(data or {}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-RepoBrain": "1"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"API Error {endpoint}: {e}")
        return None

def main():
    print("=" * 60)
    print("🎬 STARTING REPOBRAIN AUTOMATED DEMO WALKTHROUGH")
    print("=" * 60)

    # Reset server state
    print("-> Resetting server demo state to clean Scenario A (risky)...")
    post("/api/reset")
    pause(1)

    # Bring Chrome to front and navigate to demo URL
    activate_chrome()
    open_url(URL)
    pause(3)

    # Overlay banner to guide recording
    run_js("""
    let b = document.createElement('div');
    b.id = 'demo-indicator';
    b.style.cssText = 'position:fixed;bottom:20px;right:20px;background:#0369a1;color:#fff;padding:10px 18px;border-radius:24px;font-family:sans-serif;font-size:14px;font-weight:700;z-index:99999;box-shadow:0 4px 15px rgba(0,0,0,0.5);display:flex;align-items:center;gap:8px;transition:all 0.3s ease;';
    b.innerHTML = '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#34d399;animation:pulse 1s infinite"></span> <span id="demo-indicator-text">Demo: Scenario A (Risky AI PR)</span>';
    document.body.appendChild(b);
    """)

    def set_badge(text):
        print(f"  [DEMO] {text}")
        run_js(f"document.getElementById('demo-indicator-text').innerText = '{text}';")

    # ─────────────────────────────────────────────────────────────
    # STEP 1: Scenario A - Risky AI PR (BLOCKED)
    # ─────────────────────────────────────────────────────────────
    set_badge("Scenario A: Risky AI PR (BLOCKED)")
    run_js("scenario('risky'); go('review'); window.scrollTo({top: 0, behavior: 'smooth'});")
    pause(3)

    # Smooth scroll down findings
    run_js("window.scrollBy({top: 400, behavior: 'smooth'});")
    pause(3)
    run_js("window.scrollBy({top: 400, behavior: 'smooth'});")
    pause(3)
    run_js("window.scrollTo({top: 0, behavior: 'smooth'});")
    pause(2)

    # ─────────────────────────────────────────────────────────────
    # STEP 2: Scenario B - Pricing PR & AST Optimizer
    # ─────────────────────────────────────────────────────────────
    set_badge("Scenario B: Complexity Gate (CHANGES REQUIRED)")
    run_js("scenario('pricing'); go('review');")
    pause(3)

    set_badge("Switching to AST Optimizer Tab")
    run_js("go('optimizer'); window.scrollTo({top: 0, behavior: 'smooth'});")
    pause(2)

    set_badge("Running AST Optimizer (scratch copy + tests)")
    run_js("runOpt();")
    pause(5)

    # Scroll down to show diff and metrics
    run_js("window.scrollBy({top: 380, behavior: 'smooth'});")
    pause(3)

    set_badge("Human Approval Gate: Entering Approver Name")
    run_js("""
    let inp = document.getElementById('aactor');
    if (inp) {
        inp.scrollIntoView({behavior: 'smooth', block: 'center'});
        inp.value = 'Tanmay Jain <tanmay@example.com>';
        checkApproverName();
    }
    """)
    pause(2)

    set_badge("Approving & Applying Refactored Code")
    run_js("approve();")
    pause(3)

    set_badge("Review: Verdict Flipped to ALLOWED")
    run_js("go('review'); window.scrollTo({top: 0, behavior: 'smooth'});")
    pause(4)

    # ─────────────────────────────────────────────────────────────
    # STEP 3: Shield Playground
    # ─────────────────────────────────────────────────────────────
    set_badge("Shield Playground: Pre-flight Evasion Checks")
    run_js("go('shield'); window.scrollTo({top: 0, behavior: 'smooth'});")
    pause(2)

    set_badge("Shield Check 1: Hardcoded Secret Key")
    run_js("ex(1); runShield();")
    pause(3)

    set_badge("Shield Check 2: Prompt Injection Attack")
    run_js("ex(2); runShield();")
    pause(3)

    # ─────────────────────────────────────────────────────────────
    # STEP 4: Autonomous Failure Explainer
    # ─────────────────────────────────────────────────────────────
    set_badge("Failure Explainer: Autonomous Log Diagnostic")
    run_js("go('explainer'); window.scrollTo({top: 0, behavior: 'smooth'});")
    pause(2)

    set_badge("Analyzing Traceback & Root-Cause Fix")
    run_js("exEx(); runExpl();")
    pause(3)
    run_js("window.scrollBy({top: 350, behavior: 'smooth'});")
    pause(3)

    # ─────────────────────────────────────────────────────────────
    # STEP 5: Cryptographic Audit Trail & Tamper Detection
    # ─────────────────────────────────────────────────────────────
    set_badge("Audit Trail: SHA-256 HMAC Hash Chain")
    run_js("go('audit'); window.scrollTo({top: 0, behavior: 'smooth'});")
    pause(3)

    set_badge("Simulating Tampering on Audit Block")
    run_js("tamper();")
    pause(4)

    # Scroll down to show tampered block in red
    run_js("window.scrollBy({top: 320, behavior: 'smooth'});")
    pause(4)

    # ─────────────────────────────────────────────────────────────
    # STEP 6: Policy Tab (Trusted Base Policy)
    # ─────────────────────────────────────────────────────────────
    set_badge("Policy Tab: Enforced from Trusted Base Branch")
    run_js("go('policy'); window.scrollTo({top: 0, behavior: 'smooth'});")
    pause(3)

    # ─────────────────────────────────────────────────────────────
    # STEP 7: Live GitHub Enforcement Proof
    # ─────────────────────────────────────────────────────────────
    set_badge("Live GitHub PR: Automated Enforcement Proof")
    open_new_tab("https://github.com/tanmayyyyayyy/Repo_Brain/pull/1")
    pause(4)

    run_js("window.scrollBy({top: 550, behavior: 'smooth'});")
    pause(4)
    run_js("window.scrollBy({top: 500, behavior: 'smooth'});")
    pause(4)
    run_js("window.scrollTo({top: 0, behavior: 'smooth'});")
    pause(2)

    print("=" * 60)
    print("✅ DEMO WALKTHROUGH COMPLETED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    main()

