# RepoBrain Presentation & Pitch Outline

## 5-Slide Deck Plan (Round 3 / Finals)

1. **Problem**: Coding agents open PRs across many vendors, but traditional controls are fragmented. Linters only warn, single-line secret scanners miss concatenated/base64 leaks, multi-line prompt injections slip through comments, and compliance teams cannot prove what an agent changed or who approved it.
2. **Solution**: **RepoBrain** — one vendor-neutral policy file (`repobrain.yml` loaded from the trusted base branch), deterministic security blocking, test-verified AST complexity cleanup, and an HMAC-SHA256 hash-chained audit ledger.
3. **Features & Live Demo**:
   - **Pre-flight Shield & Agent Hooks**: Blocks protected workflows, hardcoded/split/base64 secrets, multi-line prompt injections, risky commands, and curated dependency typosquats (`repobrain preflight`, MCP server, Claude Code hook).
   - **AST Complexity Gate & Optimizer**: Flattens nested `if/else` blocks via guard clauses and early exits, executes your tests on a scratch copy with resource limits, differentially fuzzes pure functions, and requires a named human approver (`Approved-by:` trailer).
   - **Cryptographic Audit Ledger**: Hash-chained JSONL with `REPOBRAIN_AUDIT_KEY` HMAC signing and CI head anchoring (`--anchor-file`).
4. **Technical Approach**: Zero heavy runtime dependencies (Python stdlib + PyYAML). Deterministic rules can block; the zero-dependency Naive Bayes ML guard warns only (5-fold CV on 242 samples: precision 0.938, recall 0.625, F1 0.750; 0.03% FP rate on 4,000 stdlib prose lines). Single-file WCAG 2.1 AA Mission Control UI (`repobrain/web/index.html`) with per-run tokens and host/CSRF guards.
5. **Impact & Future Scope**:
   - **Measured Evaluation**: 21 commits / 14,500 diff lines scanned with 0% false positives on runtime production code ([`REAL_WORLD_EVAL.md`](REAL_WORLD_EVAL.md)), and 0 false positives across 51,781 LoC of stdlib/OSS Python ([`SHIELD_EVAL.md`](SHIELD_EVAL.md)).
   - **Roadmap**: Hosted GitHub App (`webhook.py`), TypeScript/Go AST optimizers, Sigstore Rekor timestamping, and IDE preflight integrations.

## Deliverables Status
- [x] Working prototype + public GitHub repo (`tanmayyyyayyy/Repo_Brain`)
- [x] GitHub tools: Actions PR workflow, SARIF code scanning upload, sticky PR comments, composite `action.yml`, head hash anchoring artifacts, Dependabot, PR template, pre-commit hook
- [x] Edited narrated demo video with overlays ([`docs/demo/repobrain_demo_edited.mp4`](demo/repobrain_demo_edited.mp4))
- [x] AI assistance & third-party disclosures ([`README.md`](../README.md), [`THIRD_PARTY.md`](../THIRD_PARTY.md))

## Hard Questions (Honest Answers)
- *"Why not just prompt the model to be safe?"* Prompts are non-deterministic and un-auditable; a base-branch policy file + signed audit log is enforceable.
- *"Can an agent bypass it?"* Yes, if pushed directly without CI branch protection, pre-commit hooks, or preflight checks—which is why `repobrain.yml` and GitHub rulesets are paired.
- *"Is the ML guard accurate?"* Evaluated via 5-fold cross-validation on a 242-sample team-written corpus: precision 0.938, recall 0.625, F1 0.750 (hybrid: precision 0.940, recall 0.653, F1 0.770) and 0.03% FP rate on 4,000 Python stdlib prose lines. Rules block; the ML guard warns only.
- *"Is the optimizer safe?"* Executes unit tests on a scratch copy with CPU/memory rlimits and runs differential fuzzing (constants + type mutations). Comments are preserved and rewrites apply only on named human approval.
