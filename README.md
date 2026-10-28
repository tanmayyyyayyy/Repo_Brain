# RepoBrain

**A vendor-neutral safety, cleanup and audit layer for repos that AI agents write to.**
It does not write code. It decides what AI (and humans) may change, cleans up what they wrote
(with your tests as the judge), and keeps tamper-evident proof of everything.

```
 PR / agent push ──► Shield ──► Complexity gate ──► Optimizer (tests on a copy) ──► Human approves ──► merge
                        └────────────── hash-chained audit log + report ◄────────────────┘
```

## Run it in 60 seconds

```bash
pip install -r requirements.txt          # pyyaml, pytest, coverage. Python 3.10+, git
python server.py                         # seeds a REAL git repo with AI-authored PRs and opens the console
python -m pytest -q tests                # 57 passed, 1 skipped (requires ANTHROPIC_API_KEY)
```

Console walkthrough (≈3 min):
- **A · risky AI PR** → BLOCKED (protected workflow file, hardcoded AWS key, prompt-injection text, deleted test)
- **B · messy AI PR** → CHANGES REQUIRED → *Run optimizer* → real AST diff, your tests run on a copy, coverage tracked, complexity before/after (cognitive 15→10, depth 4→3) → *Approve & apply* (a commit is created with `Approved-by:`) → review passes → *Audit* → *Simulate tampering* → detected.
- **C · AI refactor** → high-debt legacy code (`shop/orders.py`, cyclomatic complexity 27) decomposed into modular helper functions via test-gated AI tier.

## What is real

| Module | What it actually does |
|---|---|
| **Shield** | Reads the real `git diff base...HEAD`. Finds the AI author per file (commit author/committer, `Co-authored-by:`). Blocks protected paths for AI (warns for humans), hardcoded secrets (AWS/GitHub/Slack/Stripe/Anthropic/OpenAI/private keys/GCP/Azure/Twilio/SendGrid/generic credentials), prompt-injection text in *added* lines (including multi-line injections across comments), hidden/bidi Unicode, blast radius (`max_files_per_run`), flags dependency/build files and deleted tests. Evidence is masked. |
| **Policy** | `repobrain.yml`, validated, read from the **trusted base branch** — a PR (or an agent) cannot loosen its own rules. Supports `min_function_coverage` to enforce test execution of rewritten functions. |
| **Complexity gate** | cyclomatic + cognitive + nesting depth, only on functions the PR touched (legacy debt doesn't block). `repobrain scan` lists the legacy debt separately. |
| **Optimizer** | AST rewrites that are semantics-preserving (else-after-return, guard clauses, merge nested ifs, bool returns, loop→comprehension, `== None`, unused imports). Only changed functions are re-emitted; **everything else stays byte-identical** with original CRLF/LF line endings preserved, comments are kept, functions whose inline comments would be lost are skipped. Result is run against **your test suite on a copy** with optional coverage.py verification (secrets stripped from the env); failing tests ⇒ proposal rejected. Applying needs a named human, refuses stale proposals, commits with `Approved-by:`. |
| **Optimizer – AI tier** *(optional)* | For functions still over limits: prompts Claude (`claude-3-5-sonnet-20241022`) to refactor *one function*, scans the reply with Shield before accepting, then test-gates it (one retry with the failure output). Off unless `allow_llm: true` **and** `--ai` **and** `ANTHROPIC_API_KEY`. Never sends files that have Shield findings. |
| **Failure Explainer** | 18 rule-based patterns (Python/Node/CI/infra) → cause, fix, file:line, failed tests. Optional LLM summary with secrets redacted. |
| **Audit** | Append-only JSONL, SHA-256 hash chain, `verify`, `--expect <anchored head>`, `--anchor-file <path>`, `--write-anchor <path>`, JSON export, markdown compliance report. One entry per AI-authored file + one per review/approval/waiver. |
| **Console** | Localhost only; per-run token, Host check, JSON-only POSTs (a governance tool must not be a CSRF target); all repo-derived text is HTML-escaped. |

## CLI

```
python -m repobrain review  --base main [--actor LOGIN] [--comment pr.md]   # CI entry point, exit 1 if not ALLOWED
python -m repobrain scan                                                     # legacy complexity debt
python -m repobrain optimize --base main [--diff] [--apply --actor NAME] [--ai] [--all]
python -m repobrain shield   --path .github/workflows/ci.yml --actor copilot
python -m repobrain waive    --actor NAME --reason "why"                     # complexity gate only; never shield blocks
python -m repobrain explain  --log build.log
python -m repobrain audit    [--expect HASH] [--anchor-file FILE] [--write-anchor FILE] [--export]  # exit 1 if chain is broken
python -m repobrain report   --out report.md
python -m repobrain serve    [--demo] [--repo PATH --base main]
```

## Put it on a real repo

1. Copy `repobrain.yml` to your **default branch** (`python -m repobrain init`).
2. Add `.github/workflows/repobrain.yml` and make it a **required** check in a branch ruleset (see [docs/GITHUB_ACTIONS.md](docs/GITHUB_ACTIONS.md)).
3. Open a PR → the workflow comments the verdict, fails the check when blocked, verifies the audit chain against the anchored head artifact, and uploads the updated audit log and anchor.

## Honest limits (say these before a judge does)

- **Python only** for complexity + optimizer. Shield, audit and explainer are language-agnostic.
- Rules reduce **nesting and cognitive complexity** (the thing that hurts readability) but cannot lower
  cyclomatic complexity — that needs real refactors (the AI tier, or a human). In the demo: cognitive 15→10, depth 4→3, 69→47 lines.
- Rewritten functions are re-formatted by `ast.unparse` (float literals like `0.10` print as `0.1`; run your formatter after).
- **The test suite is the safety net.** Weak tests ⇒ weak guarantee. RepoBrain integrates with coverage.py to flag proposals where rewritten functions were never executed by tests (`min_function_coverage`).
- The **AI tier is fully implemented and tested with mock API responses and Claude 3.5 Sonnet payload validation**, but live API execution requires `ANTHROPIC_API_KEY` (skipped in CI when absent).
- RepoBrain only governs what passes through it. A direct push to an unprotected branch bypasses it — enforce via branch rulesets.
- A hash chain proves *edits* happened; detecting a fully rewritten log needs the anchored head (`--anchor-file` stored in CI artifacts).
- Prompt-injection detection combines single-line and adjacent-line scanning (across comments); it raises the bar significantly, but cannot guarantee protection against all adversarial linguistic permutations.
- Not a GitHub App yet (webhooks, multi-repo dashboard, SSO) — that is the roadmap, not the demo.

## Layout

```
repobrain/  policy · metrics · gitutil · shield · rewrite · optimizer · llm · review · explainer · audit · report · demo · server · cli
static/index.html   console UI            demo_assets/   files for the seeded demo repo
tests/              57 tests incl. old-vs-new behaviour checks, tamper detection, e2e on a real git repo, server security, AI tier, coverage
scripts/demo_check.py   Playwright-based headless verification of full console walkthrough
```
