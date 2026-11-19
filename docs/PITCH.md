# RepoBrain Presentation & Pitch Outline

## 5-Slide Deck Plan (Round 3 / Finals)

1. **Problem**: Coding agents open PRs across many vendors, but traditional controls are fragmented and easily evaded. Linters only warn, single-line secret scanners miss concatenated/base64 leaks (`'AKIA' + '...'`), multi-line prompt injections slip through comments, and compliance teams cannot prove what an agent changed or who approved it.
2. **Solution**: **RepoBrain** — one vendor-neutral policy file (`repobrain.yml` loaded from the trusted base branch), deterministic security blocking, test-verified AST complexity cleanup, and an HMAC-SHA256 hash-chained audit ledger.
3. **Four Breakthrough Zero-Dependency Technical Innovations**:
   - **Symbolic AST Formal Equivalence Prover (`repobrain/prover.py`)**: Mathematically proves $\forall \text{input} \in \text{Inputs}: f_{\text{orig}}(\text{input}) \equiv f_{\text{opt}}(\text{input})$ for pure control-flow functions via symbolic execution path extraction, De Morgan DNF canonicalization, and bidirectional path matching. Emits an immutable theorem hash into proposal JSON and receipts.
   - **Intra-Procedural Taint Analysis Engine (`repobrain/taint.py`)**: Traces untrusted parameters through assignment chains into dangerous sinks (CWE-78, CWE-95, CWE-22, CWE-502, CWE-918) with sanitizer recognition (`shlex.quote`, `int()`, etc.) and sequential AST statement traversal.
   - **RFC-6962 Binary Merkle Audit Tree (`repobrain/merkle.py`)**: Binary Merkle tree with RFC-6962 domain separation (`0x00||leaf`, `0x01||internal`). Generates $O(\log N)$ cryptographic offline-verifiable inclusion proofs verifiable offline or in CI (`GET /api/audit/proof`, `POST /api/audit/verify-proof`).
   - **Verifiable PR Decision Receipt Engine (`repobrain/receipt.py`)**: Cryptographically binds review verdict, findings, base policy hash (`origin/main`), formal proof, fuzzing results, human approver, and Merkle inclusion proof into one downloadable artifact verified offline via `repobrain verify-receipt <file>`.
4. **Technical Approach**: Zero heavy runtime dependencies (Python stdlib + PyYAML). Deterministic rules can block; the zero-dependency Naive Bayes ML guard warns only (5-fold CV on 772 samples: precision 0.939, recall 0.639, F1 0.760; 0.0% FP on JS/UI strings, 0.03% on 4,000 stdlib prose lines). Single-file WCAG 2.1 AA Mission Control UI with per-run tokens, CSRF protection, and HttpOnly cookie-isolated demo workspaces.
5. **Impact & Future Scope**:
   - **Measured Evaluation**: 21 commits / 14,500 diff lines scanned with 0% false positives on runtime production code ([`REAL_WORLD_EVAL.md`](REAL_WORLD_EVAL.md)), and 0 false positives across 51,781 LoC of stdlib/OSS Python ([`SHIELD_EVAL.md`](SHIELD_EVAL.md)).
   - **Full Matrix Verification**: 223 passed, 1 skipped across Linux, macOS, and Windows runners in CI.
   - **Roadmap**: TypeScript/Go AST optimizers, GitHub Marketplace App (expanding architectural prototype [`repobrain/webhook.py`](../repobrain/webhook.py)), and Sigstore Rekor / AWS KMS hardware key anchoring.

## Deliverables Status
- [x] Working prototype + public GitHub repo (`tanmayyyyayyy/Repo_Brain`)
- [x] GitHub tools: Actions PR workflow, SARIF code scanning upload, sticky PR comments, composite `action.yml`, head hash anchoring artifacts, Dependabot, PR template, pre-commit hook, downloadable PR decision receipts
- [x] Master 90-second demo script with lower-third captions ([`docs/VIDEO_SCRIPT.md`](VIDEO_SCRIPT.md))
- [x] AI assistance & third-party disclosures ([`README.md`](../README.md), [`THIRD_PARTY.md`](../THIRD_PARTY.md))

## Hard Questions (Honest Answers)
- *"Why not just prompt the model to be safe?"* Prompts are non-deterministic, can be overridden by indirect prompt injections, and cannot be audited; a base-branch policy file + signed audit log is enforceable.
- *"Can an agent bypass it?"* Yes, if pushed directly without CI branch protection, pre-commit hooks, or preflight checks—which is why `repobrain.yml` and GitHub rulesets are paired.
- *"Is the formal prover sound for all Python code?"* It mathematically proves equivalence for pure control-flow functions (guard clause hoisting, boolean simplification, dead-branch elimination under De Morgan laws). When functions contain external side effects, dynamic attribute lookup, or loops, RepoBrain relies on differential fuzzing (500 boundary inputs) and isolated pytest execution in a scratch sandbox.
- *"Is the ML guard accurate?"* Evaluated via 5-fold cross-validation on an expanded 772-sample corpus (including 530 UI/JS tokens): precision 0.939, recall 0.639, F1 0.760 (hybrid: precision 0.941, recall 0.667, F1 0.780) with 0.0% FP on UI strings and 0.03% on 4,000 Python stdlib prose lines. Rules block; the ML guard warns only.
- *"Is the optimizer safe?"* Yes: it executes unit tests on a scratch copy with CPU/memory rlimits, runs differential fuzzing (500 boundary inputs), and mathematically proves semantic equivalence using the Symbolic AST Prover. Rewrites only commit upon named human approval.
- *"How is the audit key managed in production?"* In production, `REPOBRAIN_AUDIT_KEY` is injected as a secret via AWS Secrets Manager, HashiCorp Vault, or GitHub Actions OIDC; the demo uses a seeded ephemeral key.
- *"What is your language support?"* The AST complexity gate and deterministic optimizer currently target Python (with TypeScript and Go on the roadmap). Shield, Taint Analysis, Secrets, Injection Detection, Decision Receipts, and the Audit Ledger are language-agnostic.
- *"What is the status of the GitHub App webhook?"* GitHub Actions workflow and CLI preflight are the production integrations today; `repobrain/webhook.py` is an architectural prototype designed for future multi-tenant Marketplace deployment.
