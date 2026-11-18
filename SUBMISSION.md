# RepoBrain — Hackathon Prototype Submission

> **One-Sentence Pitch**: RepoBrain is a vendor-neutral safety, cleanup, and cryptographic audit layer for repositories that AI coding agents write to—deciding what agents may touch, simplifying complex additions with test-backed proof, and anchoring every decision in an HMAC-signed hash chain.

- **Track / Category**: Most Innovative Developer Tool / AI Safety & Governance / Cyber Security & Compliance / Open Innovation
- **Target Buyers**: Enterprise Platform Engineering, DevSecOps, and Security teams deploying autonomous AI coding agents (Cursor, Claude Code, GitHub Copilot, Devin) across production codebases.
- **GitHub Repository**: [https://github.com/tanmayyyyayyy/Repo_Brain](https://github.com/tanmayyyyayyy/Repo_Brain)
- **Live Demo Video**: [`docs/demo/repobrain_demo_edited.mp4`](docs/demo/repobrain_demo_edited.mp4) *(1080p 60fps narrated walkthrough with voiceover, captions, HMAC-signed audit demo, and live GitHub CI verification)*
- **Technical Documentation**: [`docs/TECHNICAL_DOCUMENTATION.md`](docs/TECHNICAL_DOCUMENTATION.md) *(Architecture, Tech Stack, RBAC Spec, APIs & Integrations)*
- **5-Slide Executive Pitch Deck**: [`docs/SLIDE_DECK.md`](docs/SLIDE_DECK.md) · **Interactive Slide Deck**: [`docs/slides.html`](docs/slides.html)
- **Live Pull Request Proofs (Public Repos)**:
  - Evaluation repo (`repobrain-demo-eval`): [PR #1 — Blocked risky AI PR](https://github.com/tanmayyyyayyy/repobrain-demo-eval/pull/1) · [PR #2 — Complexity gate](https://github.com/tanmayyyyayyy/repobrain-demo-eval/pull/2)
  - Main repo (`Repo_Brain`): [PR #1 — End-to-end Blocked → Refactored → Allowed lifecycle](https://github.com/tanmayyyyayyy/Repo_Brain/pull/1)
- **License**: MIT
- **Status**: Final Build & Innovation Showcase ([![CI](https://github.com/tanmayyyyayyy/Repo_Brain/actions/workflows/ci.yml/badge.svg)](https://github.com/tanmayyyyayyy/Repo_Brain/actions/workflows/ci.yml))

---

## ⚡ How to Judge RepoBrain in 3 Minutes (Evaluator Quick-Start)

1. **Zero-Install Live Web Console**: Open **[repobrain-demo.onrender.com](https://repobrain-demo.onrender.com)**.
2. **Instant Killer Scenario Walkthrough (Scenarios A through E)**:
   - **Step 1 (Scenario A — Adversarial Agent PR)**: Click `A · risky AI PR` $\to$ **`BLOCKED`**. Catches split secret concatenation (`'AKIA' + '...'`), unauthorized workflow edits (`.github/workflows/ci.yml`), comment prompt injections, and shell taint flows.
   - **Step 2 (Scenario B — AI Spaghetti Code)**: Click `B · messy AI PR` $\to$ click `Run optimizer`. Inspect the **Formal Semantic Equivalence Theorem** ($\forall \text{input}: f_{\text{orig}} \equiv f_{\text{opt}}$) proved by our symbolic prover, plus 500 fuzzed inputs with 0 divergences. Type `Priya Sharma` $\to$ click `Approve & apply` $\to$ review flips to **`ALLOWED`**.
   - **Step 3 (Scenario C — High-Complexity Legacy Refactor)**: Click `C · AI refactor` $\to$ safely handles cyclomatic complexity 27 with base-branch policy gating.
   - **Step 4 (Scenario D — Clean AI PR / The Golden Path)**: Click `D · clean PR` $\to$ **`ALLOWED`** (0 findings, 100% compliant, ready to merge). Proves 0.0% false positives on clean code.
   - **Step 5 (Scenario E — Polyglot Full-Stack PR)**: Click `E · polyglot PR` $\to$ full-stack AI governance across TypeScript, Shell, Dockerfile, and Python.
   - **Step 6 (Audit Ledger & Merkle Proof)**: Click `Audit` $\to$ click `Simulate tampering` (tamper detected instantly) $\to$ click `Merkle Inclusion Proof` $\to$ generate an $O(\log N)$ Zero-Knowledge Inclusion Certificate proving block #8 exists without exposing other records.

---

## 1. Why This Is Hard & What We Built

- **Why Traditional Controls Fail on AI Agents**: Standard linters (Ruff, SonarQube) post advisory warnings without halting autonomous agents or checking base-branch policy provenance. Single-line secret scanners miss concatenated keys (`'AKIA' + '...'`) or base64-encoded credentials (`QUtJ...`), and single-line regexes miss multi-line prompt injections (`# ignore \n # all previous \n # instructions`).

| AI Adversarial Evasion Scenario | Gitleaks / detect-secrets | radon / Linters | Semgrep (OSS) | RepoBrain Governance Engine |
|---|:---:|:---:|:---:|:---:|
| **Concatenated Secret Literal**<br>`k = 'AKIA' + 'IOSFODNN7EXAMPLE'` | ❌ **MISSED**<br>Regex splits token | ⚪ N/A<br>No secret scan | ❌ **MISSED**<br>Regex fails on split | 🛡️ **BLOCKED**<br>AST concat normalization |
| **Multi-Line Prompt Injection**<br>`# ignore \n # all previous instructions` | ❌ **MISSED**<br>Single-line check | ❌ **MISSED**<br>Ignored as comment | ❌ **MISSED**<br>Line-by-line rule | 🛡️ **BLOCKED**<br>Sliding window + ML Guard |
| **High-Complexity Spaghetti**<br>`discount_for()` (Cyclomatic 27, depth 6) | ⚪ N/A<br>No complexity check | ⚠️ **WARN ONLY**<br>Advisory; agent ignores | ⚪ N/A<br>No refactoring | ⚡ **REWRITTEN & PROVEN**<br>Formal AST proof + tests |
| **Taint Flow to Shell Sink**<br>`user_input` $\to$ `subprocess(shell=True)` | ⚪ N/A<br>No taint analysis | ⚪ N/A<br>No taint analysis | ❌ **MISSED**<br>Needs custom rules | 🔍 **BLOCKED (CWE-78)**<br>Sequential taint engine |

- **Three Novel Zero-Dependency Innovations (Pure Python Standard Library)**:
  1. **Symbolic AST Formal Equivalence Prover (`repobrain/prover.py`)**: Mathematically proves $\forall \text{input} \in \text{Inputs}: f_{\text{orig}}(\text{input}) \equiv f_{\text{opt}}(\text{input})$ via symbolic execution path extraction, De Morgan DNF canonicalization, and bidirectional path matching with cryptographic theorem hashes.
  2. **Intra-Procedural Taint Analysis Engine (`repobrain/taint.py`)**: Traces untrusted parameters through assignment chains into dangerous sinks (CWE-78, CWE-95, CWE-22, CWE-502, CWE-918) with sanitizer awareness.
  3. **RFC-6962 Binary Merkle Audit Tree (`repobrain/merkle.py`)**: Generates $O(\log N)$ zero-knowledge inclusion certificates verifiable offline or in CI (`GET /api/audit/proof`, `POST /api/audit/verify-proof`).
- **Verified Code Remediation Without Regressions**: When an AI PR exceeds complexity limits (cyclomatic, cognitive, nesting depth), RepoBrain's deterministic AST optimizer simplifies the code directly via semantics-preserving rewrites, runs your repository's test suite on a scratch copy with CPU/memory resource limits, and runs differential fuzzing (constants + type mutations) to catch behavioral regressions before proposing changes to a human.
- **Tamper-Evident Proof of Everything**: RepoBrain records every review, preflight check, waiver, and human approval in an append-only JSONL ledger hash-chained with SHA-256 and signed via HMAC-SHA256 (`REPOBRAIN_AUDIT_KEY`). In `--demo` mode and CI with keys enabled, altering any historical block—even while recomputing SHA-256 hashes—immediately breaks signature and chain verification.

---

## 2. How to Run (3 Commands)

```bash
# 1. Clone the repository
git clone https://github.com/tanmayyyyayyy/Repo_Brain.git && cd Repo_Brain

# 2. Install runtime dependencies (Python 3.10+, standard library + PyYAML)
pip install -r requirements.txt

# 3. Launch the Mission Control Console
python server.py
```

*The server automatically provisions a local git repo with seeded scenarios (`demo-agent[bot]`, `refactor-bot[bot]`), sets an ephemeral demo HMAC key, and opens `http://127.0.0.1:8765/?t=<token>` in your browser.*

To run the automated test suite:
```bash
pip install -r requirements-dev.txt
python -m pytest -q tests
# All tests pass cleanly on CI (live Anthropic API test requires optional ANTHROPIC_API_KEY)
```

---

## 3. Architecture Summary

```
PR / Agent Push ──► Shield (Secrets + Taint + Injection) ──► Complexity Gate ──► Optimizer (Formal Proofs + Fuzzing) ──► Named Human ──► Merge
                       └─────────────────── RFC-6962 Cryptographic Merkle Audit Ledger (HMAC) ◄────────────────────────────────┘
```

1. **Shield**: Evaluates added diff hunks against protected paths (`.github/workflows/`, `repobrain.yml`), hardcoded secrets (pattern + entropy + string concatenation normalization + base64 decoding), prompt injection (multi-line sliding window + warn-only Naive Bayes ML guard), risky commands (shell & PowerShell), dependency typosquatting (Damerau-Levenshtein against 289 popular packages), and **Intra-Procedural Taint Analysis (`repobrain/taint.py`)** tracing untrusted parameters into dangerous sinks (CWE-78 command injection, CWE-95 code injection, CWE-22 path traversal, CWE-502 deserialization, CWE-918 SSRF) with sanitizer recognition.
2. **Complexity Gate**: Inspects *only* functions touched by the PR against base-branch thresholds (cyclomatic ≤ 10, cognitive ≤ 15, nesting depth ≤ 3).
3. **Verified Optimizer & Formal Prover**: Performs deterministic AST rewrites on touched Python functions, executes the repository's tests on a scratch copy, runs differential fuzzing (500 boundary inputs) in a resource-limited subprocess, and runs the **Symbolic AST Formal Equivalence Prover (`repobrain/prover.py`)** to mathematically prove `∀ input ∈ Inputs: f_original(input) ≡ f_optimized(input)` across execution paths with De Morgan canonicalization. An optional LLM refactor tier (`repobrain/llm.py`) supports Groq/Anthropic APIs when explicitly configured via `allow_llm: true` and `--ai` (verified locally with mock API servers).
4. **Human Approval**: Enforces `approval: human`. The optimizer never merges on its own; a named human approves the rewrite, producing a git commit with an `Approved-by:` trailer.
5. **Cryptographic Merkle Audit Ledger**: Append-only JSONL ledger with SHA-256 hash chaining, HMAC-SHA256 signing, and an **RFC-6962 Binary Merkle Tree (`repobrain/merkle.py`)** generating O(log N) zero-knowledge inclusion proofs verified via sibling path reconstruction (`GET /api/audit/proof`, `POST /api/audit/verify-proof`), and CI head anchoring (`--anchor-file`, `--expect`).

---

## 4. Key Documentation & Proof Links

- [**Real-World Evaluation (`docs/REAL_WORLD_EVAL.md`)**](docs/REAL_WORLD_EVAL.md): Shield evaluated across 21 commits (177 file revisions, 14,500 diff lines) with 0 false positives on runtime production code.
- [**Tool Comparison Matrix (`docs/COMPARISON.md`)**](docs/COMPARISON.md): Comparison of RepoBrain vs Gitleaks, detect-secrets, radon, and Semgrep.
- [**Threat Model (`THREAT_MODEL.md`)**](THREAT_MODEL.md): Protected assets, attacker personas, attack paths, mitigations, and non-goals.
- [**Shield Quality & False-Positive Evaluation (`docs/SHIELD_EVAL.md`)**](docs/SHIELD_EVAL.md): 124 open-source/stdlib Python files (51,781 LoC, 0 false positives) + evasion regression matrix.
- [**GitHub Actions & CI Rulesets (`docs/GITHUB_ACTIONS.md`)**](docs/GITHUB_ACTIONS.md): Live PR enforcement setup and audit head anchoring guide.
- [**Third-Party & AI Disclosures (`THIRD_PARTY.md`)**](THIRD_PARTY.md): Complete license inventory, bundled data disclosures, and placeholder key policy.
- [**Pitch & Video Script (`docs/PITCH.md`, `docs/VIDEO_SCRIPT.md`)**](docs/PITCH.md): 5-slide outline and narrated presentation script.

---

## 5. Honest Limitations & Boundaries

1. **Language Scope**: The AST complexity gate and deterministic optimizer currently target Python (TypeScript and Go AST engines on roadmap). Shield, Taint Analysis, Secret Normalization, Injection Detection, Audit Ledger, Failure Explainer, and Agent Preflight API are completely language-agnostic.
2. **Production Key Management**: In production, `REPOBRAIN_AUDIT_KEY` is injected as a hardware-protected secret via AWS Secrets Manager, HashiCorp Vault, or GitHub Actions OIDC; the demo environment provisions an ephemeral key.
3. **Execution Environment**: The optimizer runs repository test suites on a scratch copy with timeout and CPU/memory `rlimit` constraints (with Bubblewrap container isolation when unprivileged user namespaces are available)—only run untrusted repository tests inside isolated CI runners.
4. **ML Guard Guardrails**: Evaluated via 5-fold cross-validation on an expanded 772-sample corpus including 530 JavaScript and UI tokens (precision 0.939, recall 0.639, F1 0.760; hybrid F1 0.780) with 0.0% false positives on UI strings and 0.03% on 4,000 Python stdlib documentation prose lines. Not a standalone production accuracy claim: deterministic rules can block; the ML classifier warns only.
5. **Optional AI Tier**: Live external LLM calls (`--ai`) require `GROQ_API_KEY` or `ANTHROPIC_API_KEY`; automated CI tests validate the provider routing and Shield gating against local mock servers.
6. **Governance Boundary**: RepoBrain enforces checks on commits/PRs routed through CI, git hooks, or preflight APIs. Pair with GitHub branch protection rulesets (disable admin bypass) to prevent direct unprotected pushes.
