# RepoBrain Demo Script (90-Second Master Walkthrough)

> **Goal**: Demonstrate live, vendor-neutral governance, verified AST cleanup, and cryptographic audit for AI coding agents.  
> **Key Mantra**: RepoBrain does not write code. It decides what agents may touch, cleans up messy additions using tests and formal proofs as the judge, and keeps tamper-evident proof of everything.

---

## ⏱️ Timeline & Click-by-Click Guide

### [0:00 - 0:15] The Hook & Mission Control
**What to say**:
> "Autonomous coding agents are shipping thousands of PRs a week. Classic tools only warn, miss split secrets, and get evaded by multi-line injections.
>
> **RepoBrain** is vendor-neutral governance, verified AST cleanup, and cryptographic audit—enforced from your trusted base branch."

**Action**:
- Show `http://127.0.0.1:8765`. Point to the header showing the current branch, commit SHA, and trusted base branch (`origin/main`).

---

### [0:15 - 0:35] Step 1: Scenario A — The Malicious / Risky AI PR (Shield Defense)
**What to say**:
> "Here, an autonomous agent opens a PR containing four evasions that defeat classic tools: a split AWS key, an unauthorized workflow edit, a multi-line comment injection, and an untrusted shell execution sink.
>
> Gitleaks and Semgrep miss these. RepoBrain normalizes the AST and blocks them instantly.
>
> Most critically: even if the agent tries to weaken `repobrain.yml` in its PR branch, RepoBrain reads policy strictly from `origin/main`. The agent cannot loosen its own rules."

**Action**:
1. Click **A · risky AI PR** (or press `1`).
2. The verdict immediately renders in bold red: **`BLOCKED`**.
3. Point out the findings table:
   - `shop/config.py:1`: `secret` (concatenated AWS access key normalized and masked).
   - `.github/workflows/ci.yml`: `blocked-path` (AI changes to protected paths are forbidden).
   - `docs/AGENT_NOTES.md:5`: `prompt-injection` (multi-line sliding window catches adversarial agent instructions).
4. **Key Point**: "Notice the policy source: `origin/main`. Even if the AI modifies `repobrain.yml` in its PR branch, RepoBrain reads policy strictly from the trusted base branch. The agent cannot loosen its own rules."

---

### [0:35 - 0:55] Step 2 & 3: Scenario B — The Messy AI PR & AST Optimizer with Formal Proof
**What to say**:
> "Now let's switch to **Scenario B**. Here, an AI agent wrote a new pricing discount module. The code is secure—no secrets, no injections—but it's classic AI slop: deep nesting, redundant else-branches, high cognitive complexity."

**Action**:
1. Click **B · messy AI PR** (or press `2`).
2. The verdict renders in yellow: **`CHANGES REQUIRED`**.
3. Point out the Complexity Gate table:
   - Function `shop/pricing.py::discount_for` exceeds policy: `nesting depth 4 > 3`, cognitive complexity `15 > 10`.
   - "Notice RepoBrain only gates functions *this PR touched*. Legacy tech debt in the rest of the repo doesn't block developers."
4. Click **Run optimizer →** and click **Run optimizer** button.
   - Watch the optimizer execute semantics-preserving AST rewrites on a temporary scratch copy with CPU/memory resource limits.
   - Show the test execution (`26 passed`) and differential fuzzing (500 fuzzed inputs with 0 divergences).
   - Point out the **Formal Semantic Equivalence Proof**: theorem $\forall \text{input} \in \text{Inputs}: f_{\text{original}}(\text{input}) \equiv f_{\text{optimized}}(\text{input})$ proven across all 6 symbolic paths with cryptographic theorem hash!
   - Show the metrics diff: cognitive **15 → 10**, nesting depth **4 → 3**, lines **69 → 47**.

---

### [0:55 - 1:15] Step 4: Human Approval in the Loop
**What to say**:
> "RepoBrain never auto-applies code. It enforces `approval: human` and requires a named human reviewer."

**Action**:
1. Type `Priya Sharma` into the Approver Full Name input field.
2. Click **Approve & apply**.
   - The proposal commits directly to the repo with git trailer: `Approved-by: Priya Sharma`.
3. Click **PR review** nav tab → click **Re-run**.
   - Verdict flips to bold green: **`ALLOWED`**.

---

### [1:15 - 1:30] Step 5: Tamper-Evident Audit Trail & RFC-6962 Merkle Proof
**What to say**:
> "In an enterprise, compliance and security teams need proof of what happened. Every AI file authored, every blocked secret, every optimizer rewrite, and every human approval is recorded in an HMAC-SHA256 cryptographic ledger."

**Action**:
1. Click **Audit & report** nav tab (or press `5`).
2. Point out the header pill: `chain ✓ verified` and `HMAC-signed`.
3. Click **Simulate tampering**.
   - The system flips to red: **`IN-MEMORY TAMPERING SIMULATED: SHA-256 signature invalidated (#8), downstream links broken`**.
4. Click **Merkle Inclusion Proof**, enter sequence `8`, and click **Generate Proof**.
   - Show the $O(\log N)$ sibling path and Zero-Knowledge Inclusion Certificate proving entry #8 exists in the ledger without exposing other records.
5. "If anyone mutates an audit event or truncates history, the hash chain and Merkle root break instantly."

---

### [1:30] Closing & Deliverables
**What to say**:
> "With zero runtime dependencies, 208 passing tests across Linux, macOS, and Windows runners, and proven 0.0% false positives on real UI code, RepoBrain provides deterministic governance for the AI agent era.
>
> *(brief pause)* Thank you."
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
> RepoBrain is vendor-neutral, reads policy strictly from the base branch so agents cannot game it, performs semantics-preserving AST cleanups verified by running your real test suite on scratch copies with resource limits, and produces a SHA-256 hash-chained audit trail suitable for SOC2 / ISO compliance."

### Question 3: "What if a rogue developer or agent bypasses the PR and pushes directly to main?"
> **Honest Answer**:
> "RepoBrain can only govern what passes through it. If someone has administrator rights to force-push directly to an unprotected `main` branch, no client-side tool can stop them.
> That is why RepoBrain's production deployment model relies on GitHub Branch Rulesets: `main` requires linear history, blocks force pushes, restricts workflow edits, and mandates the `RepoBrain` status check to pass before merging. That shifts enforcement to the repository host, making bypasses blocked for non-admin tokens."

