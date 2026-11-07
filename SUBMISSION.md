# RepoBrain — Hackathon Prototype Submission

> **One-Sentence Pitch**: RepoBrain is a vendor-neutral safety, cleanup, and cryptographic audit layer for repositories that AI coding agents write to—deciding what agents may touch, simplifying complex additions with test-backed proof, and anchoring every decision in an HMAC-signed hash chain.

- **Track / Category**: Developer Tools & Infrastructure / AI Safety & Governance / Cyber Security / Open Innovation
- **GitHub Repository**: [https://github.com/tanmayyyyayyy/Repo_Brain](https://github.com/tanmayyyyayyy/Repo_Brain)
- **License**: MIT
- **Status**: Production-Grade Working MVP (124 passed tests, 1 skipped)

---

## 1. Why This Is Hard & What We Built

- **Why Traditional Controls Fail on AI Agents**: Standard linters (Ruff, SonarQube) are purely advisory; they post comments but cannot halt autonomous agents or distinguish probabilistic code from human commits. Meanwhile, secret scanners inspect single lines and miss concatenated tokens (`'AKIA' + '...'`) or multi-line prompt injections (`# ignore \n # all previous \n # instructions`).
- **Verified Code Remediation Without Regressions**: When an AI PR exceeds complexity limits (cyclomatic, cognitive, nesting depth), RepoBrain's AST optimizer doesn't send the code back for another hallucinatory rewrite loop. It simplifies the code directly via semantics-preserving AST rewrites, executes your project's unit tests in a scratch copy with resource limits, and runs differential fuzzing (mining 750+ boundary constants and type mutations) to guarantee behavioral equivalence.
- **Tamper-Evident Proof of Everything**: Organizations need non-repudiable compliance answers. RepoBrain records every review, preflight check, waiver, and human approval in an append-only JSONL ledger hash-chained with SHA-256 and signed via HMAC-SHA256 (`REPOBRAIN_AUDIT_KEY`). If any historical entry is altered—even if hashes are recalculated—downstream verification immediately breaks.

---

## 2. How to Run (3 Commands)

```bash
# 1. Clone the repository
git clone https://github.com/tanmayyyyayyy/Repo_Brain.git && cd Repo_Brain

# 2. Install dependencies (standard library + PyYAML runtime)
pip install -r requirements.txt

# 3. Launch the Mission Control Console
python server.py
```

*The server automatically provisions a realistic demo git repository with pre-seeded scenarios and opens `http://127.0.0.1:8765/?t=<token>` in your browser.*

To verify the test suite:
```bash
python -m pytest -q tests
# 124 passed, 1 skipped (requires ANTHROPIC_API_KEY)
```

---

## 3. Architecture Summary

```
PR / Agent Push ──► Shield ──► Complexity Gate ──► Optimizer (Tests + Fuzzing) ──► Named Human ──► Merge
                       └───────────── Cryptographic Audit Log (HMAC-SHA256) ◄────────────────┘
```

1. **Shield**: Evaluates added diff hunks against protected paths (`.github/workflows/`, `repobrain.yml`), hardcoded secrets (pattern + entropy + concatenation normalization + base64 decoding), prompt injection (multi-line sliding window + Naive Bayes ML guard), and dependency typosquatting (Damerau-Levenshtein against top 5,000 PyPI/npm packages).
2. **Complexity Gate**: Inspects *only* functions touched by the PR against policy thresholds (cyclomatic $\le 10$, cognitive $\le 15$, nesting depth $\le 3$).
3. **Verified Optimizer**: Performs AST rewrites on touched functions, executes the repository's test suite, and differentially fuzzes original vs rewritten functions in a resource-limited subprocess.
4. **Human Approval**: Enforces `approval: human`. The optimizer never merges on its own; a named human committer approves the change, generating a git commit with an `Approved-by:` trailer.
5. **Cryptographic Audit Ledger**: An append-only JSONL log with SHA-256 hash chaining, HMAC signing, and CI head anchoring (`--anchor-file`, `--expect <seq>`).

---

## 4. Key Documentation & Proof Links

- [**Real-World Evaluation (`docs/REAL_WORLD_EVAL.md`)**](docs/REAL_WORLD_EVAL.md): Shield evaluated across 21 real commits (177 file revisions, 14,500 diff lines) with 0 false positives on runtime application code.
- [**Tool Comparison Matrix (`docs/COMPARISON.md`)**](docs/COMPARISON.md): Factual side-by-side comparison of RepoBrain vs Gitleaks, detect-secrets, radon/lizard, and Semgrep across 8 capabilities and 3 adversarial evasions.
- [**Threat Model (`THREAT_MODEL.md`)**](THREAT_MODEL.md): Analysis of protected assets, 4 attacker personas, attack paths, mitigations, and explicit non-goals.
- [**Shield Quality & False-Positive Evaluation (`docs/SHIELD_EVAL.md`)**](docs/SHIELD_EVAL.md): Evaluation across 124 open-source files (51,781 lines of code) and 5-fold cross-validation of the ML injection guard.
- [**GitHub Actions & CI Rulesets (`docs/GITHUB_ACTIONS.md`)**](docs/GITHUB_ACTIONS.md): Verification report on a real public repository ([`tanmayyyyayyy/repobrain-demo-eval`](https://github.com/tanmayyyyayyy/repobrain-demo-eval)) and CI head anchoring.
- [**Frequently Asked Questions (`docs/FAQ.md`)**](docs/FAQ.md): 10 detailed answers regarding linters, offline verification, test timeouts, and non-Python support.
- [**Video Presentation Script (`docs/VIDEO_SCRIPT.md`)**](docs/VIDEO_SCRIPT.md): 2.5-minute step-by-step walkthrough script with judge Q&A prep.

---

## 5. Honest Limitations & Boundaries

1. **Language Scope**: The AST complexity gate and optimizer currently analyze Python code. Shield, Audit Ledger, Failure Explainer, and Agent Preflight API are completely language-agnostic.
2. **Execution Sandbox**: The optimizer executes repository test suites in a scratch copy with timeout and resource limits (CPU/memory rlimits). It does not provide network namespace virtualization—only run repository tests in CI environments you trust.
3. **ML Guard Guardrails**: The learned prompt injection classifier (evaluated on a 242-sample team-written corpus: precision 0.938, recall 0.625, F1 0.75; 0.03% false-positive rate on 4,000 stdlib lines) is a second-opinion heuristic. Architectural rule: deterministic rules can block; the ML model only produces warnings.
4. **Governance Boundary**: RepoBrain governs what passes through it (CI status checks, pre-commit hooks, preflight APIs). Direct pushes bypassing GitHub rulesets bypass CI; enforce branch rulesets with admin bypass disabled.
