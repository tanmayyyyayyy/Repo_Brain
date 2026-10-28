# RepoBrain Demo Script (5-Minute Live Pitch)

> **Goal**: Show judges a live, vendor-neutral governance, cleanup, and audit layer for AI coding agents.
> **Key Mantra**: RepoBrain does not write code. It decides what agents may touch, cleans up messy additions using tests as the judge, and keeps tamper-evident proof of everything.

---

## ⏱️ Timeline & Click-by-Click Guide

### [0:00 - 0:45] The Problem & Architecture Hook
**What to say**:
> "Autonomous coding agents like Claude Code, Cursor, and Devin are generating massive pull requests. But today, teams face two bad choices: either slow down to manually audit thousands of lines of unmaintainable, AI-generated spaghetti, or risk catastrophic security breaches from hardcoded keys, prompt injections, or corrupted CI workflows.
>
> Meet **RepoBrain**: a vendor-neutral safety, cleanup, and audit layer for repos that AI agents write to. It does not write new code. It acts as an immutable governor between the AI PR and your main branch."

**Action**:
- Show `README.md` pipeline diagram or open the console at `http://127.0.0.1:8793`. Point to the header showing the current branch, commit SHA, and trusted base branch.

---

### [0:45 - 2:00] Scenario A: The Malicious / Risky AI PR
**What to say**:
> "Let's start with **Scenario A**. An AI agent was tasked with updating an AWS config. But look at what it actually attempted: it hardcoded an AWS access key, silently modified our protected GitHub Actions workflow, deleted a test it thought was flaky, and ingested a prompt-injection payload hidden in markdown notes."

**Action**:
1. Click **A · risky AI PR** at the top right of the console.
2. The verdict immediately renders in bold red: **`BLOCKED`**.
3. Point out the findings table:
   - `shop/config.py:1`: `secret` (AWS access key masked).
   - `.github/workflows/ci.yml`: `blocked-path` (AI changes to protected paths are forbidden).
   - `docs/AGENT_NOTES.md:5`: `prompt-injection` (instructions telling the agent to exfiltrate keys).
   - `tests/test_legacy.py`: `test-deleted` warning.
4. **Key Point**: "Notice the policy source: `origin/main`. Even if the AI modifies `repobrain.yml` in its PR branch, RepoBrain reads policy strictly from the trusted base branch. The agent cannot loosen its own rules."

---

### [2:00 - 3:30] Scenario B: The Messy AI PR & Safe AST Optimizer
**What to say**:
> "Now let's switch to **Scenario B**. Here, an AI agent wrote a new pricing discount module. The code is secure—no secrets, no injections—but it's classic AI slop: deep nesting, redundant else-branches, high cognitive complexity."

**Action**:
1. Click **B · messy AI PR**.
2. The verdict renders in yellow: **`CHANGES REQUIRED`**.
3. Point out the Complexity Gate table:
   - Function `shop/pricing.py::discount_for` exceeds policy: `nesting depth 4 > 3`, cognitive complexity `15`.
   - "Notice RepoBrain only gates functions *this PR touched*. Legacy tech debt in the rest of the repo doesn't block developers."
4. Click **Run optimizer →**.
5. Click **Run optimizer** button.
   - Watch the optimizer execute semantics-preserving AST rewrites on a temporary sandbox copy and run the test suite (`26 passed`).
   - Show the metrics diff: cognitive **15 → 10**, nesting depth **4 → 3**, lines **69 → 47**.
   - Show the unified diff: else-after-return stripped, loop converted to list comprehension, inline comments preserved.
6. **The Human In The Loop**:
   - "RepoBrain never auto-applies code. It generates an applicable proposal that requires a named human."
   - Type `Priya Sharma` into the reviewer input field.
   - Click **Approve & apply**.
   - The proposal commits directly to the repo with git trailer: `Approved-by: Priya Sharma`.
7. Click **PR review** nav tab → click **Re-run**.
   - Verdict flips to bold green: **`ALLOWED`**.

---

### [3:30 - 4:15] Tamper-Evident Audit Trail
**What to say**:
> "In an enterprise, compliance and security teams need proof of what happened. Every AI file authored, every blocked secret, every optimizer rewrite, and every human approval is recorded in a cryptographic hash chain."

**Action**:
1. Click **Audit & report** nav tab.
2. Point out the header pill: `chain ✓ 12 entries` with SHA-256 head hash.
3. Click **Simulate tampering**.
4. The system flips: **`DETECTED - entry #X hash mismatch`**.
5. "If anyone mutates an audit event or truncates history, the hash chain breaks instantly."

---

### [4:15 - 5:00] Live GitHub Actions Verification & Closing
**What to say**:
> "This isn't just a localhost UI. We have it running live on GitHub Actions on real pull requests right now."

**Action**:
- Show `https://github.com/tanmayyyyayyy/repobrain-demo-eval/pull/1` and `pull/2`.
- Show the automated PR comments formatted with markdown tables and status check badges.
- Conclude: "RepoBrain gives engineering leaders confidence to let AI agents write code at scale, without compromising security, maintainability, or compliance."

---

## 🎯 3 Hard Questions Judges Will Ask (With Honest Answers)

### Question 1: "What if the repository's test suite is weak or missing?"
> **Honest Answer**:
> "The test suite is our ultimate safety net. If a repository has no tests, RepoBrain flags proposals as `unverified-no-tests` and refuses to make them applicable by default (`require_tests: true`).
> We deliberately do not claim that AST rewrites or AI refactors are infallible. Without tests, RepoBrain will gate complexity and block secrets, but it will *not* allow automated cleanup to be applied without explicit policy opt-out. Strong guarantees require real tests."

### Question 2: "How does this compare to GitHub Copilot code review, SonarQube, or CodeRabbit?"
> **Honest Answer**:
> "SonarQube and CodeRabbit are advisory linters and bot reviewers—they comment on PRs with suggestions or static analysis warnings, but they don't safely fix complexity or enforce immutable blast-radius boundaries based on AI author identity.
> Copilot writes code; RepoBrain governs the agent.
> RepoBrain is vendor-neutral, reads policy strictly from the base branch so agents cannot game it, performs semantics-preserving AST cleanups verified by running your real test suite on isolated copies, and produces a SHA-256 hash-chained audit trail suitable for SOC2 / ISO compliance."

### Question 3: "What if a rogue developer or agent bypasses the PR and pushes directly to main?"
> **Honest Answer**:
> "RepoBrain can only govern what passes through it. If someone has administrator rights to force-push directly to an unprotected `main` branch, no client-side tool can stop them.
> That is why RepoBrain's production deployment model relies on GitHub Branch Rulesets: `main` requires linear history, blocks force pushes, restricts workflow edits, and mandates the `RepoBrain` status check to pass before merging. That shifts enforcement to the repository host, making bypasses mathematically impossible for non-admin tokens."
