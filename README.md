# RepoBrain

[![Test Suite](https://github.com/tanmayyyyayyy/Repo_Brain/actions/workflows/test.yml/badge.svg)](https://github.com/tanmayyyyayyy/Repo_Brain/actions/workflows/test.yml)

> **Judges start here:**
> - **Pitch**: Vendor-neutral safety, AST complexity cleanup, and HMAC-signed audit layer for repos touched by AI coding agents—enforcing policy from the trusted base branch.
> - **Live Demo**: **[repobrain-demo.onrender.com](https://repobrain-demo.onrender.com)** — no install, opens the seeded Mission Control console.
> - **Demo Video (2m 05s, narrated 1080p60)**: [`docs/demo/repobrain_demo_edited.mp4`](docs/demo/repobrain_demo_edited.mp4) · **Live Public PRs**: [`repobrain-demo-eval#1`](https://github.com/tanmayyyyayyy/repobrain-demo-eval/pull/1), [`#2`](https://github.com/tanmayyyyayyy/repobrain-demo-eval/pull/2) & [`Repo_Brain#1`](https://github.com/tanmayyyyayyy/Repo_Brain/pull/1)
> - **Quick Run**: `pip install -r requirements.txt && python server.py` (or Docker CLI: `docker build -t repobrain . && docker run --rm -v "$(pwd)":/repo repobrain review --base origin/main`)
> - **Measured Impact**: 21 commits / 14,500 diff lines scanned with 0 runtime FPs ([`REAL_WORLD_EVAL.md`](docs/REAL_WORLD_EVAL.md)); 51,781 OSS Python LoC scanned with 0 FPs ([`SHIELD_EVAL.md`](docs/SHIELD_EVAL.md)).
> - **Limits**: AST optimizer targets Python only (Shield/Audit are language-agnostic); ML guard warns only (0.625 recall); optional `--ai` refactor tier requires `GROQ_API_KEY` or `ANTHROPIC_API_KEY`.

**A vendor-neutral safety, cleanup and audit layer for repos that AI agents write to.**
It does not write code. It decides what AI (and humans) may change, cleans up what they wrote
(with your tests as the judge), and keeps tamper-evident proof of everything.

![RepoBrain Architecture](docs/architecture.svg)

## Run it in 60 seconds

```bash
pip install -r requirements.txt          # pyyaml (+ pytest, coverage, playwright in requirements-dev.txt). Python 3.10+, git
python server.py                         # seeds a demo git repo with HMAC signing enabled and opens the console
python -m pytest -q tests                # 126 passed, 1 skipped (live Anthropic API test skipped when key unset)
```

Console walkthrough (≈3 min):
- **A · risky AI PR** (`demo-agent[bot]`) → BLOCKED (protected workflow file, AWS published example key, prompt-injection text, deleted test)
- **B · messy AI PR** (`refactor-bot[bot]`) → CHANGES REQUIRED → *Run optimizer* → real AST diff, your tests run on a scratch copy, coverage tracked, complexity before/after (cognitive 15→10, depth 4→3) → *Approve & apply* (a commit is created with `Approved-by:`) → review passes → *Audit* (HMAC-signed) → *Simulate tampering* → detected.
- **C · AI refactor** *(optional tier, requires API key)* → high-debt `shop/orders.py` (cyclomatic 27) branch; provider routing and Shield checks are verified against local mock API servers in [`tests/test_ai_tier.py`](tests/test_ai_tier.py).

## Deploy the live demo

**Live instance:** [https://repobrain-demo.onrender.com](https://repobrain-demo.onrender.com)

The console stays localhost-only by default. To host the seeded demo publicly:

```bash
# Render (recommended): push this repo, then New > Blueprint > select render.yaml
# Railway: New Project > Deploy from GitHub (uses Procfile + the PORT env var)

# Any Docker host:
docker build -t repobrain .
docker run --rm -p 8765:8765 repobrain
# open http://localhost:8765  (public URL is provided by your platform)
```

Deployment is controlled by environment variables:

| Variable | Purpose |
|---|---|
| `REPOBRAIN_HOST` | Bind address (`0.0.0.0` to expose; default `127.0.0.1`). |
| `PORT` / `REPOBRAIN_PORT` | Port to listen on (platform-assigned on Render/Railway). |
| `REPOBRAIN_OPEN_DEMO=1` | Skip the per-run token so anyone with the URL can use the sandboxed demo. |
| `REPOBRAIN_ALLOWED_HOSTS` | Comma-separated Host allowlist; `*` accepts any (needed behind a proxy). |
| `REPOBRAIN_AUDIT_KEY` | HMAC-SHA256 key for the audit chain (Render generates one). |

> **Security note:** `REPOBRAIN_OPEN_DEMO=1` is only appropriate for the seeded demo repo. For real repositories keep the default token + localhost binding.

## Live Demo Walkthrough

> 📹 **Watch the Narrated Master Demo Video (1080p 60fps)**: [`docs/demo/repobrain_demo_edited.mp4`](docs/demo/repobrain_demo_edited.mp4) — problem intro, clean full-UI framing, fixed diff syntax highlighting, HMAC-signed audit chain, and live GitHub Actions PR proof.

![RepoBrain Workflow Walkthrough](docs/demo.gif)

## UI overhaul screenshots

Full 4-view × 2-viewport × 2-theme matrix lives in [`docs/ui/`](docs/ui/); the pre-overhaul baseline from `37b7551^` is in [`docs/ui/before/`](docs/ui/before/).

| Blocked review | File diff with annotations |
|---|---|
| ![Blocked review in dark mode](docs/ui/01_blocked_review_1440_dark.png) | ![File diff with inline Shield annotations](docs/ui/02_file_diff_annotations_1440_dark.png) |
| **Optimizer result** | **Audit chain with a tampered block** |
| ![Optimizer verified result](docs/ui/03_optimizer_verified_1440_dark.png) | ![Audit chain showing the tampered block and broken downstream links](docs/ui/04_audit_chain_tampered_1440_dark.png) |

**Before / after — blocked review (1440×900, dark)**

| Before (`37b7551^`, original console) | After (Mission Control) |
|---|---|
| ![Original blocked review](docs/ui/before/01_blocked_review_before.png) | ![Redesigned blocked review](docs/ui/01_blocked_review_1440_dark.png) |

## What is real

| Module | What it actually does |
|---|---|
| **Shield** | Reads the real `git diff base...HEAD`. Finds the AI author per file (commit author/committer, `Co-authored-by:`). Blocks protected paths for AI (warns for humans), hardcoded secrets (AWS/GitHub/Slack/Stripe/Anthropic/OpenAI/private keys/GCP/Azure/Twilio/SendGrid/JWT/generic high-entropy credentials via Shannon entropy, split string concatenation, and base64-encoded tokens), prompt-injection text in *added* lines (3-4 line multi-line window across comments + warn-only Naive Bayes ML guard at p≥0.85), hidden/bidi Trojan Source Unicode, risky shell/PowerShell commands (`curl \| sh`, `iex (iwr ...)`), and dependency typosquatting (Damerau-Levenshtein against a curated list of 289 popular packages: 198 PyPI, 91 npm, homoglyphs, VCS URLs). Evidence is masked. |
| **Policy** | `repobrain.yml`, validated, read from the **trusted base branch** — a PR (or an agent) cannot loosen its own rules. Supports `min_function_coverage` to enforce test execution of rewritten functions, `fuzz: true` for differential fuzzing, and `ml_guard: true`. |
| **Complexity gate** | Cyclomatic + cognitive + nesting depth, only on functions the PR touched (legacy debt doesn't block). `repobrain scan` lists the legacy debt separately. |
| **Optimizer** | AST rewrites that are semantics-preserving (else-after-return, guard clauses, merge nested ifs, bool returns, loop→comprehension, `== None`, unused imports). Only changed functions are re-emitted; **everything else stays byte-identical** with original CRLF/LF line endings preserved, comments are kept, functions whose inline comments would be lost are skipped. Result is run against **your test suite on a scratch copy with CPU/memory rlimits** and **differentially fuzzed** (constants + type-confused inputs compared against the original function); any divergence immediately discards the proposal. Applying needs a named human, refuses stale proposals, commits with `Approved-by:`. |
| **Optimizer – AI tier** *(optional)* | For functions still over limits: prompts an LLM (Groq `openai/gpt-oss-120b` or Anthropic `claude-sonnet-5-5`, selectable via `REPOBRAIN_LLM_PROVIDER`) to refactor *one function*, scans the reply with Shield before accepting, then test-gates and differentially fuzzes it. Off unless `allow_llm: true` **and** `--ai` **and** `GROQ_API_KEY` or `ANTHROPIC_API_KEY` is set. Verified against local mock API servers in automated tests. |
| **Failure Explainer** | 18 rule-based patterns (Python/Node/CI/infra) → cause, fix, file:line, failed tests. Optional LLM summary with secrets redacted. |
| **Audit** | Append-only JSONL, SHA-256 hash chain with HMAC-SHA256 signing (`REPOBRAIN_AUDIT_KEY`, auto-provisioned ephemerally in `--demo`), `verify`, `--expect <anchored head>`, `--anchor-file <path>`, `--write-anchor <path>`, SARIF, CSV, JSON export, markdown compliance report. |
| **Agent Preflight API** | Vendor-neutral HTTP endpoint (`/api/preflight`), CLI (`repobrain preflight`), MCP server (`integrations/mcp_server.py`), and pre-execution tool hooks (`integrations/claude-code/`) allowing external agents to check permissions before writing files. |
| **Console** | Localhost-only Mission Control UI (`repobrain/web/index.html`); per-run token, Host check, JSON-only POSTs (CSRF guard); HTML-escaped; WCAG 2.1 AA contrast verified; interactive diff inspector with single-pass syntax highlighting, complexity bars, presenter mode, and `Cmd+K` palette. |

## CLI

```bash
python -m repobrain init                                                     # write starter repobrain.yml
python -m repobrain review  --base main [--actor LOGIN] [--comment pr.md]   # CI entry point, exit 1 if not ALLOWED
python -m repobrain scan                                                     # legacy complexity debt
python -m repobrain shield   --path .github/workflows/ci.yml --actor bot     # check files or proposed action
python -m repobrain gate     --base main                                     # check complexity gate violations
python -m repobrain optimize --base main [--diff] [--apply --actor NAME] [--ai] [--all]
python -m repobrain explain  --log build.log                                 # rule-based + LLM log explanation
python -m repobrain audit    [--expect HASH] [--anchor-file FILE] [--export] # exit 1 if chain is broken
python -m repobrain waive    --actor NAME --reason "why"                     # complexity gate override (logged)
python -m repobrain report   --out report.md                                 # compliance report (markdown)
python -m repobrain preflight --actor my-agent --path ok.py                  # agent hook before writing
python -m repobrain ml-eval                                                  # cross-validate learned prompt injection guard
python -m repobrain install-hook                                             # install local git pre-commit hook
python -m repobrain hook-check                                               # pre-commit check on staged changes
python -m repobrain ci       --base origin/main --sarif repobrain.sarif      # full CI pipeline + SARIF upload
python -m repobrain serve    [--demo] [--repo PATH --base main]              # launch review console (localhost)
python -m repobrain demo                                                     # run full console demo in terminal
```

## GitHub tools used

- **GitHub Actions PR Gate** ([`.github/workflows/repobrain.yml`](.github/workflows/repobrain.yml) & [`action.yml`](action.yml)): Runs `repobrain ci` on pull requests against trusted base-branch policy.
- **Sticky PR Comment**: Automatically posts/updates the governance verdict, blocking findings table, and complexity deltas in PR conversations (verified on [`repobrain-demo-eval#1`](https://github.com/tanmayyyyayyy/repobrain-demo-eval/pull/1) & [`Repo_Brain#1`](https://github.com/tanmayyyyayyy/Repo_Brain/pull/1)).
- **SARIF Code Scanning**: Exports `repobrain.sarif` for GitHub Code Scanning Alerts integration.
- **Audit Head Anchoring Artifacts**: Stores the chain head hash outside the working tree via `--anchor-file` / `--write-anchor` to detect log truncation or full history rewrites ([`docs/GITHUB_ACTIONS.md`](docs/GITHUB_ACTIONS.md)).
- **CI Test Matrix** ([`.github/workflows/test.yml`](.github/workflows/test.yml)): Runs pytest across Ubuntu and macOS on Python 3.10–3.13.
- **Dependabot & PR Governance** ([`.github/dependabot.yml`](.github/dependabot.yml), [`.github/pull_request_template.md`](.github/pull_request_template.md)): Weekly ecosystem dependency checks and human authorship attestation checklist.
- **Pre-Commit Hook** ([`.pre-commit-hooks.yaml`](.pre-commit-hooks.yaml)): Local pre-commit gating on staged changes via `repobrain hook-check`.

## Put it on a real repo

1. Copy `repobrain.yml` to your **default branch** (`python -m repobrain init`).
2. Add `.github/workflows/repobrain.yml` and make `repobrain` a **required** check in a branch ruleset with admin bypass disabled (see [`docs/GITHUB_ACTIONS.md`](docs/GITHUB_ACTIONS.md)).
3. Open a PR → the workflow comments the verdict, fails the check when blocked, verifies the audit chain against the anchored head artifact, and uploads the updated audit log and anchor.

## Honest limits (say these before a judge does)

- **Python only** for complexity + optimizer. Shield, audit and explainer are language-agnostic.
- Rules reduce **nesting and cognitive complexity** (the thing that hurts readability) but cannot lower cyclomatic complexity — that needs real refactors (human or LLM tier). In Scenario B: cognitive 15→10, depth 4→3, 69→47 lines.
- Rewritten functions are re-formatted by `ast.unparse` (float literals like `0.10` print as `0.1`; run `format_command` or your formatter after).
- **The test suite is the safety net.** Weak tests ⇒ weak guarantee. RepoBrain integrates with `coverage.py` to flag proposals where rewritten functions were never executed (`min_function_coverage`). Tests run on a scratch copy with CPU/memory rlimits rather than full OS/network isolation.
- The **AI refactor tier (`--ai`)** routes to Groq or Anthropic APIs and is validated against local mock servers in CI (`tests/test_ai_tier.py`, `tests/test_llm_providers.py`); live API execution requires `GROQ_API_KEY` or `ANTHROPIC_API_KEY` and is skipped when keys are absent.
- RepoBrain only governs what passes through it. A direct push to an unprotected branch bypasses it — enforce via GitHub branch rulesets.
- A hash chain proves *edits* happened; detecting a fully rewritten log needs HMAC signing (`REPOBRAIN_AUDIT_KEY`) paired with an out-of-band anchored head (`--anchor-file` stored in CI artifacts).
- **Prompt injection and ML Guard limits**: Combines multi-line regex rules with a lightweight Naive Bayes classifier. Evaluated on a 242-sample team-written corpus via 5-fold cross-validation: precision 0.938, recall 0.625, F1 0.75 (hybrid: precision 0.940, recall 0.653, F1 0.770) with a measured 0.03% false-positive rate on 4,000 Python stdlib documentation comments. Because the corpus is small and team-written, these numbers are not a production accuracy claim. Architectural rule: deterministic rules can block; the ML model can only warn.
- Not a hosted GitHub App yet (multi-repo web dashboard, SAML SSO) — that is on the roadmap.

## AI assistance & third-party material

- **Originality & Authorship**: RepoBrain was designed and built originally for this project; there was no pre-existing external codebase prior to development.
- **Use of AI Coding Assistants**: AI assistants were used during development as pair-programming tools for boilerplate scaffolding, test fixture expansion, CSS accessibility token tuning, and documentation formatting. All architecture decisions, threat modeling, AST transformation rules, evaluation runs, and Playwright/pytest verifications were reviewed, executed, and validated by the author.
- **Third-Party Components & Data**: Listed cleanly in [`THIRD_PARTY.md`](THIRD_PARTY.md) (Python stdlib, `PyYAML` [MIT], dev test tools `pytest`/`coverage`/`playwright`, PSF-licensed stdlib prose samples in `repobrain/data/negative_prose.txt`, and AWS published documentation placeholder keys `AKIAIOSFODNN7EXAMPLE` used strictly in test/demo fixtures).

## Layout

```text
repobrain/          policy · metrics · gitutil · shield · rewrite · optimizer · fuzz · deps · mlguard · llm · review · explainer · audit · export · report · demo · server · cli
repobrain/web/      index.html single-file WCAG 2.1 AA Mission Control UI
demo_assets/        files for the seeded demo repo
integrations/       MCP server and Claude Code pre-execution hook templates
tests/              124+ tests incl. differential fuzzing, ML guard evaluation, mock LLM tests, tamper detection, server security, Playwright UI & a11y
scripts/            contrast check, screenshot matrix, headless demo check, real-commit evaluator, video pipeline
```

## Roadmap

- **Hosted GitHub App & Multi-Repo Dashboard**: Production GitHub App deployment expanding [`repobrain/webhook.py`](repobrain/webhook.py) with organization-wide policy management and SAML SSO.
- **Multi-Language AST Optimizers**: Expand verified AST complexity reduction to TypeScript and Go.
- **Public Cryptographic Anchoring**: Sigstore Rekor / RFC 3161 timestamping for external audit root attestation.
- **Native IDE Sidecars**: VS Code and JetBrains extensions wired directly to `/api/preflight`.
