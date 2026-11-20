# RepoBrain Presentation & Pitch Outline

## 5-Slide Deck Plan (Round 3 / Finals)

1. **Problem**: Coding agents open PRs across many vendors, but traditional controls are fragmented and easily evaded. Linters only warn, single-line secret scanners miss concatenated/base64 leaks (`'AKIA' + '...'`), multi-line prompt injections slip through comments, and compliance teams cannot prove what an agent changed or who approved it.
2. **Solution**: **RepoBrain** — one vendor-neutral policy file (`repobrain.yml` loaded from the trusted base branch), deterministic security blocking, test-verified AST complexity cleanup, and an HMAC-SHA256 hash-chained audit ledger.
3. **Core Technical Components**:
   - **Symbolic AST Equivalence Prover (`repobrain/prover.py`)**: Checks equivalence for supported pure control-flow rewrites using symbolic execution paths and bidirectional path matching. It emits proof evidence and a theorem hash; it does not prove arbitrary Python behavior.
   - **Intra-Procedural Taint Analysis Engine (`repobrain/taint.py`)**: Traces untrusted parameters through assignment chains into dangerous sinks (CWE-78, CWE-95, CWE-22, CWE-502, CWE-918) with sanitizer recognition (`shlex.quote`, `int()`, etc.) and sequential AST statement traversal.
   - **RFC-6962 Binary Merkle Audit Tree (`repobrain/merkle.py`)**: Binary Merkle tree with RFC-6962 domain separation (`0x00||leaf`, `0x01||internal`). Generates $O(\log N)$ cryptographic offline-verifiable inclusion proofs verifiable offline or in CI (`GET /api/audit/proof`, `POST /api/audit/verify-proof`).
   - **Verifiable PR Decision Receipt Engine (`repobrain/receipt.py`)**: Cryptographically binds review verdict, findings, base policy hash (`origin/main`), formal proof, fuzzing results, human approver, and Merkle inclusion proof into one downloadable artifact verified offline via `repobrain verify-receipt <file>`.
4. **Technical Approach**: Python standard library plus PyYAML. Deterministic rules can block; the Naive Bayes ML guard warns only. Its documented evaluation reports 5-fold CV on 772 samples: precision 0.939, recall 0.639, F1 0.760; false-positive rates are reported only for the tested JS/UI and stdlib corpora. Mission Control uses per-run tokens and CSRF checks.
5. **Impact & Future Scope**:
   - **Measured Evaluation**: 21 commits / 14,500 diff lines scanned with 0% false positives on runtime production code ([`REAL_WORLD_EVAL.md`](REAL_WORLD_EVAL.md)), and 0 false positives across 51,781 LoC of stdlib/OSS Python ([`SHIELD_EVAL.md`](SHIELD_EVAL.md)).
   - **Test Status**: The latest local run completed with 223 passed and 1 skipped. The repository also contains an OS matrix workflow; check its current GitHub status before presenting it as green.
   - **Roadmap**: TypeScript/Go AST optimizers, GitHub Marketplace App (expanding architectural prototype [`repobrain/webhook.py`](../repobrain/webhook.py)), and Sigstore Rekor / AWS KMS hardware key anchoring.

## Deliverables Status
- [x] Working prototype + public GitHub repo (`tanmayyyyayyy/Repo_Brain`)
- [x] GitHub tools: Actions PR workflow, SARIF code scanning upload, sticky PR comments, composite `action.yml`, head hash anchoring artifacts, Dependabot, PR template, pre-commit hook, downloadable PR decision receipts
- [x] Three-to-five-minute demo script with lower-third captions ([`docs/VIDEO_SCRIPT.md`](VIDEO_SCRIPT.md))
- [x] AI assistance & third-party disclosures ([`README.md`](../README.md), [`THIRD_PARTY.md`](../THIRD_PARTY.md))

## Hard Questions (Honest Answers)
- *"Why not just prompt the model to be safe?"* Prompts are non-deterministic, can be overridden by indirect prompt injections, and cannot be audited; a base-branch policy file + signed audit log is enforceable.
- *"Can an agent bypass it?"* Yes, if pushed directly without CI branch protection, pre-commit hooks, or preflight checks—which is why `repobrain.yml` and GitHub rulesets are paired.
- *"Does the prover cover all Python code?"* No. It checks supported pure control-flow rewrites and records proof evidence. The seeded Scenario B run reports 1,000 fuzz inputs across 4 functions, alongside scratch-copy tests; those checks do not prove arbitrary Python behavior.
- *"Is the ML guard accurate?"* Evaluated via 5-fold cross-validation on an expanded 772-sample corpus (including 530 UI/JS tokens): precision 0.939, recall 0.639, F1 0.760 (hybrid: precision 0.941, recall 0.667, F1 0.780) with 0.0% FP on UI strings and 0.03% on 4,000 Python stdlib prose lines. Rules block; the ML guard warns only.
- *"Is the optimizer safe?"* RepoBrain combines several checks with different scopes: it runs project tests on a scratch copy with resource limits, differentially fuzzes candidate inputs, and uses the symbolic prover for supported pure control-flow rewrites. The prover is not a proof of arbitrary Python behavior. Rewrites only apply after named human approval.
- *"Does a receipt prove authenticity by itself?"* No. Its hashes and Merkle path detect changes relative to a known root, but the verifier needs an independently trusted CI root or HMAC audit key to authenticate the source. Without one, it reports internal consistency only.
- *"How is the audit key managed in production?"* In production, `REPOBRAIN_AUDIT_KEY` is injected as a secret via AWS Secrets Manager, HashiCorp Vault, or GitHub Actions OIDC; the demo uses a seeded ephemeral key.
- *"What is your language support?"* The AST complexity gate and deterministic optimizer currently target Python (with TypeScript and Go on the roadmap). Shield, Taint Analysis, Secrets, Injection Detection, Decision Receipts, and the Audit Ledger are language-agnostic.
- *"What is the status of the GitHub App webhook?"* GitHub Actions workflow and CLI preflight are the production integrations today; `repobrain/webhook.py` is an architectural prototype designed for future multi-tenant Marketplace deployment.
