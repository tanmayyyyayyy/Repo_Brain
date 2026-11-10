# RepoBrain — Hackathon Prototype Submission

> **One-Sentence Pitch**: RepoBrain is a vendor-neutral safety, cleanup, and cryptographic audit layer for repositories that AI coding agents write to—deciding what agents may touch, simplifying complex additions with test-backed proof, and anchoring every decision in an HMAC-signed hash chain.

- **Track / Category**: Developer Tools & Infrastructure / AI Safety & Governance / Cyber Security / Open Innovation
- **GitHub Repository**: [https://github.com/tanmayyyyayyy/Repo_Brain](https://github.com/tanmayyyyayyy/Repo_Brain)
- **Live Demo Video**: [`docs/demo/repobrain_demo_edited.mp4`](docs/demo/repobrain_demo_edited.mp4) *(1080p 60fps narrated walkthrough with voiceover, captions, HMAC-signed audit demo, and live GitHub CI verification)*
- **Live Pull Request Proofs (Public Repos)**:
  - Evaluation repo (`repobrain-demo-eval`): [PR #1 — Blocked risky AI PR](https://github.com/tanmayyyyayyy/repobrain-demo-eval/pull/1) · [PR #2 — Complexity gate](https://github.com/tanmayyyyayyy/repobrain-demo-eval/pull/2)
  - Main repo (`Repo_Brain`): [PR #1 — End-to-end Blocked → Refactored → Allowed lifecycle](https://github.com/tanmayyyyayyy/Repo_Brain/pull/1)
- **License**: MIT
- **Status**: Working MVP (`126 passed, 1 skipped` in `python -m pytest -q tests`)

---

## 1. Why This Is Hard & What We Built

- **Why Traditional Controls Fail on AI Agents**: Standard linters (Ruff, SonarQube) post advisory warnings without halting autonomous agents or checking base-branch policy provenance. Single-line secret scanners miss concatenated keys (`'AKIA' + '...'`) or base64-encoded credentials (`QUtJ...`), and single-line regexes miss multi-line prompt injections (`# ignore \n # all previous \n # instructions`).
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
# 126 passed, 1 skipped (live Anthropic API test requires ANTHROPIC_API_KEY)
```

---

## 3. Architecture Summary

```
PR / Agent Push ──► Shield ──► Complexity Gate ──► Optimizer (Tests + Fuzzing) ──► Named Human ──► Merge
                       └───────────── Cryptographic Audit Log (HMAC-SHA256) ◄────────────────┘
```

1. **Shield**: Evaluates added diff hunks against protected paths (`.github/workflows/`, `repobrain.yml`), hardcoded secrets (pattern + entropy + string concatenation normalization + base64 decoding), prompt injection (multi-line sliding window + warn-only Naive Bayes ML guard), risky commands (shell & PowerShell), and dependency typosquatting (Damerau-Levenshtein against a curated list of 289 popular packages: 198 PyPI, 91 npm).
2. **Complexity Gate**: Inspects *only* functions touched by the PR against base-branch thresholds (cyclomatic ≤ 10, cognitive ≤ 15, nesting depth ≤ 3).
3. **Verified Optimizer**: Performs deterministic AST rewrites on touched Python functions, executes the repository's tests on a scratch copy, and differentially fuzzes original vs rewritten functions in a resource-limited subprocess. An optional LLM refactor tier (`repobrain/llm.py`) supports Groq/Anthropic APIs when explicitly configured via `allow_llm: true` and `--ai` (verified locally with mock API servers).
4. **Human Approval**: Enforces `approval: human`. The optimizer never merges on its own; a named human approves the rewrite, producing a git commit with an `Approved-by:` trailer.
5. **Cryptographic Audit Ledger**: Append-only JSONL ledger with SHA-256 hash chaining, HMAC-SHA256 signing, and CI head anchoring (`--anchor-file`, `--expect`).

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

1. **Language Scope**: The AST complexity gate and deterministic optimizer currently target Python. Shield, Audit Ledger, Failure Explainer, and Agent Preflight API work across any text/code language.
2. **Execution Environment**: The optimizer runs repository test suites on a scratch copy with timeout and CPU/memory `rlimit` constraints, without network namespace virtualization—only run untrusted repository tests inside isolated CI runners.
3. **ML Guard Guardrails**: Evaluated via 5-fold cross-validation on a 242-sample team-written corpus (precision 0.938, recall 0.625, F1 0.750; hybrid F1 0.770) and 4,000 Python stdlib documentation prose lines (0.03% FP rate). Not a standalone production accuracy claim: deterministic rules can block; the ML classifier warns only.
4. **Optional AI Tier**: Live external LLM calls (`--ai`) require `GROQ_API_KEY` or `ANTHROPIC_API_KEY`; automated CI tests validate the provider routing and Shield gating against local mock servers.
5. **Governance Boundary**: RepoBrain enforces checks on commits/PRs routed through CI, git hooks, or preflight APIs. Pair with GitHub branch protection rulesets (disable admin bypass) to prevent direct unprotected pushes.
