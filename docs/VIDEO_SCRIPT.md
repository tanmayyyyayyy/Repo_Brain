# RepoBrain 90-Second Demo Video Script (Finals Master Arc)

> **Core Arc**: **"Agent Tries Bad → Blocked Instantly → Fixed & Mathematically Proven → Named Human Approves → Cryptographically Proven"**  
> **Target Duration**: Exactly 90 seconds (1:30)  
> **Resolution & Framerate**: 1920×1080 60fps, dark mode, high-contrast typography, crisp voiceover & synchronized captions.

---

## ⏱️ Timeline & Precise Cues

### [0:00 - 0:15] The Hook: The AI Coding Agent Dilemma
- **Visual**: Mission Control Console at `http://127.0.0.1:8765`. Camera pans across the persistent left telemetry rail showing the 5-stage pipeline: `Shield → Gate → Optimizer → Human → Audit`.
- **Narration**:
  > "Autonomous coding agents are shipping thousands of PRs a week. Classic tools only warn, miss split secrets, and get evaded by multi-line injections.
  >
  > **RepoBrain** is vendor-neutral governance, verified AST cleanup, and cryptographic audit—enforced from your trusted base branch."

---

### [0:15 - 0:35] Step 1: Agent Tries Something Bad (The Adversarial PR)
- **Visual**: Switch to `Scenario A: risky AI PR` (press `1`). The screen renders a bold red **`BLOCKED`** hero with 4 critical violations. Click `.github/workflows/ci.yml` in the PR map to show the unified diff with red inline annotations.
- **Narration**:
  > "Here, an autonomous agent opens a PR containing four evasions that defeat classic tools: a split AWS key, an unauthorized workflow edit, a multi-line comment injection, and an untrusted shell execution sink.
  >
  > Gitleaks and Semgrep miss these. RepoBrain normalizes the AST and blocks them instantly.
  >
  > Most critically: even if the agent tries to weaken `repobrain.yml` in its PR branch, RepoBrain reads policy strictly from `origin/main`. The agent cannot loosen its own rules."

---

### [0:35 - 0:55] Step 2 & 3: Complexity Gate & AST Optimizer with Formal Proof
- **Visual**: Switch to `Scenario B: messy AI PR` (press `2`). The verdict changes to yellow **`CHANGES REQUIRED`** with `discount_for()` flagged for nesting depth 4 > 3 and cognitive complexity 15 > 10. Click **Run optimizer**.
- **Narration**:
  > "In Scenario B, the code is safe but introduces unmaintainable spaghetti debt.
  >
  > Instead of hallucinations, we click **Run optimizer**.
  > Inside an isolated sandbox, RepoBrain executes semantics-preserving AST rewrites, passes the repo's test suite, and differentially fuzzes 500 edge inputs with zero divergences.
  >
  > Crucially, our **Symbolic Formal Prover** mathematically proves that original and optimized AST execution paths are 100% equivalent across all inputs—emitting an immutable theorem hash. Cognitive complexity drops from 15 to 10."

---

### [0:55 - 1:15] Step 4: Named Human Approval & Policy Clearance
- **Visual**: Focus on the human approval card. Type `Priya Sharma` into the full name field. Click **Approve & apply**. The commit is created with git trailer `Approved-by: Priya Sharma`. Return to PR Review and click **Re-run**; verdict flips to bold green **`ALLOWED`**.
- **Narration**:
  > "RepoBrain strictly enforces `approval: human`. The optimizer never commits on its own.
  >
  > Release manager Priya Sharma signs off with one click, creating a clean git commit with an `Approved-by:` trailer.
  >
  > We re-evaluate the change: with complexity resolved and human sign-off recorded, the verdict flips to **ALLOWED**."

---

### [1:15 - 1:30] Step 5: Cryptographic Merkle Proof & Tamper Evidence
- **Visual**: Switch to **Audit & report** view (press `5`). Show the vertical blockchain ledger with the `HMAC-signed` green pill. Click **Simulate tampering**; show the red **`IN-MEMORY TAMPERING DETECTED`** banner. Click **Merkle Inclusion Proof**, enter sequence `8`, and click **Generate Proof**.
- **Narration**:
  > "Every single decision is committed to an HMAC-SHA256 append-only ledger.
  >
  > If an attacker tampers with historical block #8 in memory, the signature instantly breaks downstream verification.
  >
  > And using our **RFC-6962 Binary Merkle Tree**, any team can generate an $O(\log N)$ zero-knowledge inclusion proof—cryptographically proving a commit was reviewed and authorized without exposing other repository history.
  >
  > Pure Python standard library, zero runtime dependencies, 208 passing tests. RepoBrain: deterministic governance for the AI agent era.
  >
  > *(brief pause)* Thank you."

---

## 🎬 Technical Shot & Caption Checklist

| Second | Screen Action | Lower-Third Caption Overlay |
|---|---|---|
| **0:05** | Mission Control home view | `RepoBrain: Vendor-Neutral AI Code Governance & Audit` |
| **0:20** | Scenario A blocked verdict | `BLOCKED: Policy enforced strictly from trusted base branch (origin/main)` |
| **0:30** | Unified diff annotations | `Multi-Vector Shield: Normalized concat secrets + multi-line injection` |
| **0:45** | Complexity gate table | `Complexity Gate: Cyclomatic ≤ 10, Cognitive ≤ 15 on PR diffs only` |
| **0:52** | Optimizer telemetry card | `Symbolic Prover: Mathematical proof ∀ input: f_orig ≡ f_opt (0 regressions)` |
| **1:05** | Human approval input | `Human-in-the-Loop: Mandatory sign-off commits Approved-by: trailer` |
| **1:12** | PR review green verdict | `Verdict: ALLOWED · Clean merge readiness certified` |
| **1:20** | Tamper detection sweep | `Cryptographic HMAC-SHA256 Ledger: Historical edits immediately detected` |
| **1:28** | Merkle proof certificate | `RFC-6962 Merkle Tree: O(log N) Zero-Knowledge Inclusion Proofs` |

---

## 🎤 Judge Q&A Cheat Sheet

1. **"How accurate is your prompt injection detector?"**
   > *Answer*: "We believe in honest metrics: our zero-dependency Naive Bayes classifier was evaluated on an expanded 772-sample corpus via 5-fold cross-validation, achieving 0.939 precision, 0.639 recall, and 0.760 F1 (0.780 hybrid). On 530 real-world frontend UI/JS strings its false-positive rate is 0.0%, and on 4,000 benign Python standard library comments it is 0.03%. Crucially, rigid deterministic rules can block; the ML model only warns and elevates risk—it never blocks on its own."

2. **"Does the optimizer send my proprietary code to OpenAI or Anthropic?"**
   > *Answer*: "No. By default, RepoBrain's AST optimizer runs 100% locally on your machine or CI runner using standard library Python AST rules. External LLM APIs are only engaged if you explicitly set `allow_llm: true` and configure `GROQ_API_KEY` or `ANTHROPIC_API_KEY` for high-complexity Scenario C function refactoring."

3. **"Can an attacker bypass the audit log by rewriting historical entries?"**
   > *Answer*: "In an unsigned chain, an attacker could recompute SHA-256 hashes. That's why RepoBrain supports HMAC-SHA256 signing (`REPOBRAIN_AUDIT_KEY`) and CI head anchoring (`--anchor-file` and `--expect <seq>`). Modifying an entry invalidates the HMAC signature, and truncating tail entries fails the anchored head check in GitHub Actions."

4. **"How does this integrate into our workflow today?"**
   > *Answer*: "RepoBrain runs as a GitHub Action (`action.yml`), a CLI tool (`repobrain review`), a pre-commit hook (`.pre-commit-hooks.yaml`), an MCP server for any agent (`integrations/mcp_server.py`), and a Claude Code pre-execution tool hook (`integrations/claude-code/`)."
