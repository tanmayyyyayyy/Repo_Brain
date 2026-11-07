# RepoBrain — Unstop Round 2 Prototype Submission

> **Project Name:** RepoBrain  
> **Tagline:** The Vendor-Neutral Safety, Cleanup & Cryptographic Audit Layer for Repositories Touched by AI Agents  
> **GitHub Repository:** [https://github.com/tanmayyyyayyy/Repo_Brain](https://github.com/tanmayyyyayyy/Repo_Brain)  
> **Track:** Developer Tools / AI Governance / Cyber Security / Open Innovation  

---

## 1. Executive Summary & Problem Statement

### The Problem
Autonomous AI coding agents (Claude Code, GitHub Copilot Workspace, Cursor, Devin, SWE-bench bots) are writing and committing code directly to production repositories. However, modern software engineering controls were built for humans, not probabilistic agents:
1. **No Shared Governance Across AI Vendors:** Each tool has siloed, non-portable rules. Engineering teams cannot enforce uniform policy across Copilot, Claude, Cursor, and custom internal agents.
2. **Hidden Security & Integrity Risks:** AI agents hallucinate dependencies (typosquatting), inject high-entropy credentials, incorporate prompt injections hidden in markdown/code comments, and introduce subtle semantic changes.
3. **Unchecked Cognitive Bloat:** Agents produce deeply nested, bloated code that technically passes tests but increases maintenance debt exponentially.
4. **No Cryptographic Proof for Compliance:** When an incident occurs or during audits, organizations cannot answer: *"Which lines were authored by AI, which rules evaluated them, which tests judged them, and which human approved them?"*

### The RepoBrain Solution
RepoBrain is an open-source, vendor-neutral governance, cleanup, and audit gate that sits between AI agents and production git branches. **It does not write code.** It decides what AI (and humans) may change, cleans up what they wrote with tests and differential fuzzing as the judge, and preserves tamper-evident cryptographic proof of every decision.

```
PR / Agent Push ──► Shield ──► Complexity Gate ──► Optimizer (Tests + Fuzzing) ──► Named Human ──► Merge
                       └───────────── Cryptographic Audit Log (HMAC-SHA256) ◄────────────────┘
```

---

## 2. Core Features & Unique Selling Propositions (USPs)

| Feature | Description | Engineering Implementation |
|---|---|---|
| **Multi-Layered Shield** | Zero false-positive safety scanner focused exclusively on added git hunks. | Regex + Shannon entropy for secrets (AWS, GitHub, Slack, Stripe, Anthropic, OpenAI, JWT, GCP, Azure, Twilio, SendGrid); Trojan Source hidden Unicode; risky shell invocations (`curl \| sh`, `chmod 777`); and Damerau-Levenshtein package typosquatting against top 5,000 PyPI/npm packages. |
| **Learned Prompt Injection Guard (ML Guard)** | Catches paraphrased agent instructions and system prompt overrides that escape rigid regex. | Pure-Python Naive Bayes classifier evaluated via 5-fold cross-validation on a 242-sample team-written corpus: precision 0.938, recall 0.625, F1 0.750 (hybrid: precision 0.940, recall 0.653, F1 0.770) with 0.03% false-positive rate on 4,000 stdlib prose comments. The corpus is small and team-written (not a production claim); rules can block, but the ML model can only warn. |
| **Differential Fuzzing Optimizer** | Flattens cognitive complexity and nesting through semantics-preserving AST rewrites. | Rewrites only touched functions (leaving untouched code byte-identical with CRLF preserved); executes full test suite on a scratch copy with resource limits; then **differentially fuzzes** original vs. rewritten functions with 750+ mined constants and type-confused inputs. Any behavioral divergence immediately rejects the proposal. |
| **Cryptographic HMAC Audit Ledger** | Append-only proof of all reviews, preflights, and human approvals. | SHA-256 hash chaining committed to previous records with optional HMAC-SHA256 signing (`REPOBRAIN_AUDIT_KEY`) and CI anchor verification (`--expect <hash>`, `--anchor-file`). Instantly detects record modification, reordering, or history truncation. |
| **Vendor-Neutral Agent Preflight API** | Universal hook enabling agents to check permissions *before* disk write. | Local HTTP endpoint (`/api/preflight`) and CLI (`repobrain preflight`) consumable by any AI agent in 3 lines of standard Python. |
| **Mission Control Console** | High-density developer review UI with dark/light themes and full accessibility. | Custom single-page cockpit with persistent 290px telemetry rail, interactive unified diff viewer with syntax highlighting and inline Shield annotations, horizontal complexity threshold bars, animated audit timeline, and presenter mode (WCAG 2.1 AA compliant). |
| **CI/CD Integration & GitHub Actions** | Production-ready CI automation. | Composite GitHub Action (`action.yml`) uploading SARIF alerts to GitHub Code Scanning, posting sticky PR verdict summaries, and verifying audit anchors. |

---

## 3. Architecture & Technical Workflow

```
┌────────────────────────────────────────────────────────────────────────┐
│                        AI AGENT / DEVELOPER PR                         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 1. SHIELD                                                              │
│    • Protected Paths (.github/, prod configs)                          │
│    • Secrets (Shannon entropy + regex: AWS, GitHub, Stripe, OpenAI...) │
│    • Prompt Injections (Multi-line comment continuation + ML Guard)    │
│    • Risky Commands (curl | sh, permissions: write-all)                │
│    • Dependency Typosquats (Damerau-Levenshtein vs PyPI/npm)           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                         Pass / Warn│ Blocked ──► [VERDICT: BLOCKED]
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 2. COMPLEXITY GATE                                                     │
│    • Analyzes ONLY functions modified by the PR                        │
│    • Cyclomatic, Cognitive, Nesting Depth against repobrain.yml        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                      Within Limits │ Exceeds Limit
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 3. OPTIMIZER                                                           │
│    • Semantics-preserving AST rewrites (flatten guards, loops, etc.)   │
│    • Test suite executed on scratch copy with resource limits          │
│    • Differential Fuzzing: 750+ inputs mined & type-mutated           │
│    • Optional LLM refactor tier (Groq free tier / Claude 3.5 Sonnet)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 4. NAMED HUMAN APPROVAL                                                │
│    • Applies proposal to repo, creates commit with `Approved-by:`     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 5. CRYPTOGRAPHIC AUDIT LOG                                             │
│    • Append-only JSONL with SHA-256 hash chain & HMAC signing          │
│    • Anchor verification against CI artifacts                          │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Tech Stack & Dependencies

- **Core Engine:** Python 3.10+ (Standard Library: `ast`, `hashlib`, `hmac`, `http.server`, `urllib`, `shlex`, `difflib`, `subprocess`).
- **Configuration & Policy:** PyYAML (`pyyaml>=6.0`).
- **Testing & Verification:** Pytest (`pytest>=7.0`), Coverage.py (`coverage>=7.0`), Playwright (`playwright` for headless browser tests).
- **Frontend / Console UI:** Pure Vanilla JavaScript (ES6+), WebGL2 telemetry shaders, semantic CSS variables (zero CDN, strict Content Security Policy, zero external assets).
- **CI/CD:** GitHub Actions composite action (`action.yml`), SARIF v2.1.0 output for GitHub Security tab.

---

## 5. Live Demo & Instructions to Run Locally

### Quick Start (Under 60 Seconds)

```bash
# 1. Clone the repository
git clone https://github.com/tanmayyyyayyy/Repo_Brain.git
cd Repo_Brain

# 2. Install dependencies (standard Python environment)
pip install -r requirements.txt

# 3. Launch the Mission Control Console
python server.py
```

*The server automatically provisions a realistic demo git repository with pre-seeded scenarios and opens `http://127.0.0.1:8765/?t=<token>` in your browser.*

### Interactive Console Walkthrough (3 Minutes)
1. **Scenario A (Risky AI PR):** Click the **A · risky AI PR** pill. The verdict hero immediately flags **BLOCKED** with high-contrast signal badges: protected workflow file `.github/workflows/ci.yml` modified by an AI author, hardcoded AWS credentials, a prompt injection payload, and a deleted legacy test file. Click `.github/workflows/ci.yml` to view unified diff annotations.
2. **Scenario B (Messy AI PR):** Switch to **B · messy AI PR**. Notice the complexity gate flags `shop/pricing.py:discount_for` (cognitive complexity 15, depth 4). Click **Run Optimizer**: RepoBrain applies semantics-preserving AST transformations, executes the tests in a clean copy, runs differential fuzzing, and reduces cognitive complexity from 15 to 10.
3. **Named Human Approval:** Enter your name in the reviewer input and click **Approve & Apply**. A real git commit is created with an `Approved-by:` trailer. Re-running review turns the verdict to **ALLOWED**.
4. **Audit Trail & Tampering Detection:** Jump to the **Audit** tab. View the live SHA-256 hash chain. Click **Simulate Tampering**: an in-memory modification is introduced into block #8. RepoBrain's audit engine instantly detects the corruption, invalidating the broken block and highlighting all downstream links.
5. **Scenario C (AI Refactor Tier):** Experience automated legacy debt refactoring on high-complexity functions (`shop/orders.py`, cyclomatic 27) via test-gated LLM execution (Groq / Anthropic).

### Automated Verification Script
Run the headless Playwright automation script to verify the entire system end-to-end:
```bash
python scripts/demo_check.py
# Output: ALL DEMO CHECK PASSES SUCCESSFULLY! REPOBRAIN IS GREEN. (7/7 steps)

python -m pytest -q tests
# Output: 104 passed, 1 skipped in 32s
```

---

## 6. Screenshots & Visual Assets

All high-resolution screenshots are located in [`docs/ui/`](docs/ui/) and [`docs/screenshots/`](docs/screenshots/):

| View | Dark Theme (Mission Control) | Light Theme (Instrument Paper) |
|---|---|---|
| **1. Blocked Review** | `docs/ui/01_blocked_review_1440_dark.png` | `docs/ui/01_blocked_review_1440_light.png` |
| **2. Diff Inspector with Shield Annotations** | `docs/ui/02_file_diff_annotations_1440_dark.png` | `docs/ui/02_file_diff_annotations_1440_light.png` |
| **3. Optimizer Result with Fuzzing Telemetry** | `docs/ui/03_optimizer_verified_1440_dark.png` | `docs/ui/03_optimizer_verified_1440_light.png` |
| **4. Cryptographic Audit Chain with Tamper Marking** | `docs/ui/04_audit_chain_tampered_1440_dark.png` | `docs/ui/04_audit_chain_tampered_1440_light.png` |

---

## 7. 90-Second Video Demo Script

- **[0:00 - 0:15] Hook:** "AI agents are opening PRs directly to your codebase. But how do you know what they touched, whether they leaked secrets, or if their rewrites broke subtle behaviors? Meet RepoBrain — the vendor-neutral governance and audit layer for AI-written code."
- **[0:15 - 0:35] Shield & Risk Index:** [Show Scenario A] "An AI agent attempts to push a PR. RepoBrain's Shield intercepts it: 97/100 critical risk. It caught a hardcoded AWS key, an unauthorized CI workflow modification, and a prompt injection hidden in a markdown comment. Verdict: BLOCKED. Not waivable."
- **[0:35 - 0:55] Complexity Gate & Verified Optimizer:** [Show Scenario B] "Here's a messy AI PR with deeply nested logic. The complexity gate flags `discount_for`. We click *Run Optimizer*: RepoBrain flattens nested conditions, runs your tests on a scratch copy with resource limits, and runs differential fuzzing with 750 inputs. Everything passes, cognitive complexity drops from 15 to 10. A named human approves, and it merges."
- **[0:55 - 1:15] Cryptographic Audit Chain:** [Show Audit Tab] "Every action is hashed into a tamper-evident SHA-256 chain. If anyone tampers with a historical log entry — we click *Simulate Tampering* — the cryptographic chain immediately breaks at block #8, flagging every downstream commit as invalidated."
- **[1:15 - 1:30] Conclusion:** "One policy file, zero vendor lock-in, tamper-evident proof. That's RepoBrain."

---

## 8. Honest Limitations & Ethical AI Disclosure

We believe in engineering transparency:
1. **Language Scope:** The Complexity Gate and AST Optimizer currently analyze Python. The Shield, Audit Ledger, Failure Explainer, and Agent Preflight API are completely language-agnostic.
2. **Safety Net Dependency:** The Optimizer's guarantee depends on the project's test suite and differential fuzzing. The optimizer runs tests on a scratch copy with resource limits (timeout and rlimits), but without OS network/filesystem isolation — execute only code you trust to run in CI.
3. **Defense-in-Depth & ML Guard Limits:** Prompt injection detection uses a hybrid approach (multi-line regex rules + trained Naive Bayes classifier). Cross-validation on our 242-sample team-written corpus reports precision 0.938, recall 0.625, F1 0.750 (hybrid: precision 0.940, recall 0.653, F1 0.770) and a 0.03% false-positive rate on 4,000 Python stdlib comments. These figures are not a production accuracy claim. Rules block; the ML model only warns.
4. **Governance Boundary:** RepoBrain governs what passes through it (CI workflows, pre-commit hooks, and preflight APIs). Direct un-gated pushes must be restricted using GitHub branch rulesets.

---

## 9. Team & Submission Details

- **GitHub Repository:** [https://github.com/tanmayyyyayyy/Repo_Brain](https://github.com/tanmayyyyayyy/Repo_Brain)
- **License:** MIT License
- **Status:** Complete Functional Prototype (Round 2 Ready)

