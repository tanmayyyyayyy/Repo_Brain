# RepoBrain

[![Test Suite](https://github.com/tanmayyyyayyy/Repo_Brain/actions/workflows/test.yml/badge.svg)](https://github.com/tanmayyyyayyy/Repo_Brain/actions/workflows/test.yml)

> **Judges start here (quick evaluation guide):**
> - **Live Demo (Zero Install)**: **[repobrain-demo.onrender.com](https://repobrain-demo.onrender.com)** — instant 1-click persona switcher (Admin, Developer, Tester, Security).
> - **Try the Five Killer Scenarios in 60 Seconds**:
>   1. **Scenario A (Adversarial Agent PR)**: Click `A · risky AI PR` $\to$ **`BLOCKED`**. Catches split secret concatenation (`'AKIA' + '...'`), protected workflow tampering, and multi-line prompt injections.
>   2. **Scenario B (AI Spaghetti Code)**: Click `B · messy AI PR` $\to$ click `Run optimizer` $\to$ review the scoped proof evidence, test result, and 1,000 fuzz inputs across 4 functions $\to$ approve as `Priya Sharma` $\to$ verdict becomes **`ALLOWED`**.
>   3. **Scenario C (High-Complexity Refactor)**: Click `C · AI refactor` $\to$ safely refactor legacy code (cyclomatic 27) with base-branch policy gating.
>   4. **Scenario D (Clean AI PR - The Golden Path)**: Click `D · clean PR` $\to$ **`ALLOWED`** with 0 blocking findings. This seeded example shows the clean-change path; it is not a general false-positive benchmark.
>   5. **Scenario E (Polyglot Multi-Language PR)**: Click `E · polyglot PR` $\to$ full-stack AI governance across TypeScript, Shell, Dockerfile, and Python.
>   6. **Audit Ledger & Verifiable PR Receipt**: Click `Audit` $\to$ click `Simulate tampering` (instant detection) $\to$ click `Merkle Inclusion Proof` $\to$ generate an $O(\log N)$ offline-verifiable cryptographic inclusion proof $\to$ download the **Verifiable Decision Receipt** (`repobrain verify-receipt <file>`).
> - **Final Demo Video**: [`docs/demo/repobrain_demo_edited.mp4`](docs/demo/repobrain_demo_edited.mp4) (narrated 1080p60 with captions; 3–5 minute submission version) · **Live PRs**: [`repobrain-demo-eval#1`](https://github.com/tanmayyyyayyy/repobrain-demo-eval/pull/1), [`#2`](https://github.com/tanmayyyyayyy/repobrain-demo-eval/pull/2) & [`Repo_Brain#1`](https://github.com/tanmayyyyayyy/Repo_Brain/pull/1).
> - **Interactive Pitch Deck**: [`docs/slides.html`](docs/slides.html) (or visit `/slides` in console) · Markdown: [`docs/SLIDE_DECK.md`](docs/SLIDE_DECK.md).
> - **Quick Local Run**: `pip install -r requirements.txt && python server.py` (or Docker: `docker run --rm -p 8765:8765 repobrain`).
> - **Verification**: Latest local test run: 223 passed, 1 skipped. The CI workflow defines an OS matrix; check its live status before claiming a current green run. Shield evaluation details and scope are in [`SHIELD_EVAL.md`](docs/SHIELD_EVAL.md).
> - **Runtime Stack**: Python standard library plus PyYAML; install the declared requirements with the setup instructions below.

**A vendor-neutral safety, cleanup and audit layer for repos that AI agents write to.**
It does not write code. It applies repository policy to proposed changes, checks supported Python rewrites with tests, fuzzing, and scoped symbolic proof evidence, and records tamper-evident audit data.

![RepoBrain Architecture](docs/architecture.svg)

## Why Existing Tools Fail on AI-Authored Code

Classic linters and secret scanners emit advisory warnings that autonomous agents ignore, and rely on single-line heuristics easily defeated by AI-generated evasions:

| AI Adversarial Evasion Scenario | Gitleaks / detect-secrets | radon / Linters | Semgrep (OSS) | RepoBrain Governance Engine |
|---|:---:|:---:|:---:|:---:|
| **Concatenated Secret Literal**<br>`k = 'AKIA' + 'IOSFODNN7EXAMPLE'` | ❌ **MISSED**<br>Regex splits token | ⚪ N/A<br>No secret scan | ❌ **MISSED**<br>Regex fails on split | 🛡️ **BLOCKED**<br>AST concat normalization |
| **Multi-Line Prompt Injection**<br>`# ignore \n # all previous instructions` | ❌ **MISSED**<br>Single-line check | ❌ **MISSED**<br>Ignored as comment | ❌ **MISSED**<br>Line-by-line rule | 🛡️ **BLOCKED**<br>Sliding window + ML Guard |
| **High-Complexity Spaghetti**<br>`discount_for()` (Cyclomatic 27, depth 6) | ⚪ N/A<br>No complexity check | ⚠️ **WARN ONLY**<br>Advisory; agent may ignore | ⚪ N/A<br>No refactoring | ⚡ **REWRITTEN & CHECKED**<br>Scoped proof evidence + tests |
| **Taint Flow to Shell Sink**<br>`user_input` $\to$ `subprocess(shell=True)` | ⚪ N/A<br>No taint analysis | ⚪ N/A<br>No taint analysis | ❌ **MISSED**<br>Needs custom rules | 🔍 **BLOCKED (CWE-78)**<br>Sequential taint engine |

## Business & Market Impact

- **Target Audience & Buyers**: Enterprise Platform Engineering, DevSecOps, and Security teams deploying autonomous coding agents (Claude Code, Cursor, Copilot Workspace, Devin) across production engineering teams.
- **The Core Problem**: *"We want developers to use coding agents without letting an agent change the policy that reviews its own pull request, and we need a clear record of the checks and human approval."*
- **The Competitive Moat**:
  1. **Scoped AST Proof Evidence**: The symbolic prover checks equivalence for supported pure control-flow rewrites. Other rewrites rely on tests and differential fuzzing; this is not a proof of arbitrary Python behavior.
  2. **Data-Flow Taint Analysis**: Pure Python intra-procedural taint propagation tracing untrusted inputs to dangerous sinks (CWE-78/95/22).
  3. **Cryptographic Merkle Proofs & Verifiable Receipts**: $O(\log N)$ offline-verifiable inclusion proofs allowing auditors to verify PR governance decisions without requiring access to other log records.
  4. **Base-Branch Policy Provenance**: Rules are anchored strictly in `origin/main`—an agent's PR can never soften its own compliance gates.
  5. **Role-Based Access**: Four demo roles, configurable corporate-domain checks, and PBKDF2-HMAC-SHA256 password hashing. This prototype does not claim FIPS validation or compliance certification.

## Novel Technical Contributions

RepoBrain includes four Python governance components implemented primarily with the standard library:

### 1. Symbolic AST Formal Equivalence Prover (`repobrain/prover.py`)
Provides symbolic equivalence evidence for AST-rewritten functions within its supported subset:
- Focuses on pure control-flow rewrites: guard clause hoisting, boolean expression simplification, and dead-branch elimination under De Morgan laws.
- Extracts all symbolic execution paths as `{condition_set → return_value}` pairs.
- Bidirectionally matches extracted paths for supported pure control-flow rewrites; this is not a proof of arbitrary Python behavior.
- Proof results appear in optimizer proposals and decision receipts as `formal_proofs` with a theorem hash. The receipt records this evidence; the receipt verifier does not rerun the prover.
- **Graceful Fallback**: If functions fall outside the symbolic prover's supported subset, RepoBrain uses tests on a scratch copy and differential fuzzing. The seeded Scenario B run checks 1,000 inputs across 4 functions; this is run evidence, not a general correctness guarantee.

```python
from repobrain.prover import ProofEngine
result = ProofEngine().verify(original_source, optimized_source)
# → {"proven": True, "paths_verified": 6, "theorem_hash": "a3f8c...", "theorem": "∀ ..."}
```

### 2. Intra-Procedural Taint Analysis Engine (`repobrain/taint.py`)
Traces untrusted function parameters through assignment chains into dangerous sinks:
- CWE-78 (command injection), CWE-95 (eval), CWE-22 (path traversal), CWE-502 (pickle), CWE-918 (SSRF)
- Sequential `_traverse_stmts` traversal (not `ast.walk`) for correct assignment ordering
- Recognizes sanitizers (`int()`, `shlex.quote()`, `os.path.basename()`, etc.)
- Integrated into Shield's `scan_text()` pipeline — taint violations appear as `rule: "taint-flow"` findings

```python
from repobrain.taint import scan_source
findings = scan_source(python_source, "myfile.py")
# → [{"cwe": "CWE-78", "function": "run_cmd", "taint_chain": ["param 'x'", "subprocess.call()"], ...}]
```

### 3. RFC-6962 Binary Merkle Audit Tree (`repobrain/merkle.py`)
Builds a binary Merkle tree over audit log entries with RFC-6962 domain separation:
- Leaf hash: `SHA-256(0x00 || entry_hash)`, internal: `SHA-256(0x01 || left || right)`
- $O(\log N)$ audit proofs — prove any entry exists without requiring access to other entries
- Full cryptographic inclusion verification via sibling path reconstruction
- API: `GET /api/audit/proof?seq=N`, `POST /api/audit/verify-proof`

```python
from repobrain.merkle import MerkleTree, verify_inclusion_proof
tree = MerkleTree(log_records)
proof = tree.audit_proof(0)         # O(log N) sibling path
valid = verify_inclusion_proof(log_records[0], proof)  # True
```

### 4. Verifiable PR Decision Receipt Engine (`repobrain/receipt.py`)
Generates a downloadable, self-contained **Decision Receipt** cryptographically binding review findings, base policy hash (`origin/main`), formal AST theorem proof, differential fuzzing results, human approver, and RFC-6962 Merkle inclusion proof into one verifiable artifact:
- Offline verification CLI: `python -m repobrain verify-receipt repobrain-receipt.json`
- Zero external dependencies: verifies file integrity, Merkle root, and policy provenance without network or database access.

```bash
# Generate decision receipt for current PR
python -m repobrain receipt --out receipt.json

# Offline verification by external auditors or CI
python -m repobrain verify-receipt receipt.json
```


## Run it in 60 seconds

```bash
pip install -r requirements.txt          # pyyaml (+ pytest, coverage, playwright in requirements-dev.txt). Python 3.10+, git
python server.py                         # seeds a demo git repo with HMAC signing enabled and opens the console
python -m pytest -q tests                # All suites pass cleanly (live Anthropic API test skipped when key unset)
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
| **Shield** | Reads `git diff base...HEAD`. Identifies AI authorship per file (commit author/committer, `Co-authored-by:`). Protected-path behavior follows `blocked_for` policy (default `all`); scans for hardcoded secrets (patterns, entropy, concatenated and base64 forms), prompt-injection text in added lines (multi-line window plus warn-only Naive Bayes guard), hidden/bidi Unicode, risky shell/PowerShell commands, and dependency typosquatting. Evidence is masked. |
| **Policy** | `repobrain.yml`, validated, read from the **trusted base branch** — a PR (or an agent) cannot loosen its own rules. Supports `min_function_coverage` to enforce test execution of rewritten functions, `fuzz: true` for differential fuzzing, and `ml_guard: true`. |
| **Complexity gate** | Cyclomatic + cognitive + nesting depth, only on functions the PR touched (legacy debt doesn't block). `repobrain scan` lists the legacy debt separately. |
| **Optimizer** | AST rewrites that are semantics-preserving (else-after-return, guard clauses, merge nested ifs, bool returns, loop→comprehension, `== None`, unused imports). Only changed functions are re-emitted; **everything else stays byte-identical** with original CRLF/LF line endings preserved, comments are kept, functions whose inline comments would be lost are skipped. Result is run against **your test suite on a scratch copy with CPU/memory rlimits** (with Bubblewrap container isolation and unshared network when user namespaces are available; on hosts without unprivileged user namespaces like Render free tier, rlimit and env-allowlist protection applies, and `require_sandbox: true` can be configured to fail closed) and **differentially fuzzed** (constants + type-confused inputs compared against the original function); any divergence immediately discards the proposal. Applying needs a named human, refuses stale proposals, commits with `Approved-by:`. |
| **Optimizer – AI tier** *(optional)* | For functions still over limits: prompts an LLM (Groq `openai/gpt-oss-120b` or Anthropic `claude-sonnet-5-5`, selectable via `REPOBRAIN_LLM_PROVIDER`) to refactor *one function*, scans the reply with Shield before accepting, then test-gates and differentially fuzzes it. Off unless `allow_llm: true` **and** `--ai` **and** `GROQ_API_KEY` or `ANTHROPIC_API_KEY` is set. Verified against local mock API servers in automated tests. |
| **Failure Explainer** | 18 rule-based patterns (Python/Node/CI/infra) → cause, fix, file:line, failed tests. Optional LLM summary with secrets redacted. |
| **Audit** | Append-only JSONL, SHA-256 hash chain with optional HMAC-SHA256 signing (`REPOBRAIN_AUDIT_KEY`, auto-provisioned ephemerally in `--demo`), `verify`, `--expect <anchored head>`, `--anchor-file <path>`, `--write-anchor <path>`, SARIF, CSV, JSON export, markdown review report. |
| **Agent Preflight API** | Vendor-neutral HTTP endpoint (`/api/preflight`), CLI (`repobrain preflight`), MCP server (`integrations/mcp_server.py`), and pre-execution tool hooks (`integrations/claude-code/`) allowing external agents to check permissions before writing files. |
| **RBAC & Auth** | Configurable corporate-domain validation, PBKDF2-HMAC-SHA256 password hashing (600,000 iterations), four demo roles (Admin, Security Lead, Tester, Developer), permission checks, persona switcher, and audit logging. No FIPS validation is claimed. |
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
python -m repobrain report   --out report.md                                 # review report (markdown)
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
- **Prompt injection and ML Guard limits**: Combines multi-line regex rules with a lightweight Naive Bayes classifier. Evaluated on a 772-sample corpus (including a negative corpus of 530 UI strings and JavaScript files) via 5-fold cross-validation: precision 0.939, recall 0.639, F1 0.760 (hybrid: precision 0.941, recall 0.667, F1 0.780) with a measured 0.0% false-positive rate on 530 JS/UI string samples and 0.03% on 4,000 Python stdlib documentation comments. Because the positive attack corpus is small and team-written, these numbers are not a production accuracy claim. Architectural rule: deterministic rules can block; the ML model can only warn.
- Not a hosted GitHub App yet (multi-repo web dashboard, SAML SSO) — that is on the roadmap.

## AI assistance & third-party material

- **Originality & Authorship**: RepoBrain was designed and built originally for this project; there was no pre-existing external codebase prior to development.
- **Use of AI Coding Assistants**: AI assistants were used during development as pair-programming tools for boilerplate scaffolding, test fixture expansion, CSS accessibility token tuning, and documentation formatting. All architecture decisions, threat modeling, AST transformation rules, evaluation runs, and Playwright/pytest verifications were reviewed, executed, and validated by the author.
- **Third-Party Components & Data**: Listed cleanly in [`THIRD_PARTY.md`](THIRD_PARTY.md) (Python stdlib, `PyYAML` [MIT], dev test tools `pytest`/`coverage`/`playwright`, PSF-licensed stdlib prose samples in `repobrain/data/negative_prose.txt`, and AWS published documentation placeholder keys `AKIAIOSFODNN7EXAMPLE` used strictly in test/demo fixtures).

## Layout

```text
repobrain/          policy · metrics · gitutil · shield · rewrite · optimizer · prover · taint · merkle · receipt · fuzz · deps · mlguard · llm · review · explainer · audit · export · report · demo · server · cli
repobrain/web/      index.html single-file WCAG 2.1 AA Mission Control UI
demo_assets/        files for the seeded demo repo
integrations/       MCP server and Claude Code pre-execution hook templates
tests/              223 passing tests (1 skipped) incl. symbolic formal prover, intra-procedural taint analysis, RFC-6962 Merkle tree, verifiable PR decision receipts with CI trust anchors, multi-scenario coverage (A-E), zero-failure resilience, security audit fixes, non-demo isolation, differential fuzzing, ML guard evaluation, mock LLM tests, tamper detection, server security, Playwright UI & a11y
scripts/            contrast check, screenshot matrix, headless demo check, real-commit evaluator, video pipeline
```

## Roadmap & Future Scope

- **Hosted GitHub App & Multi-Repo Dashboard**: Production GitHub App deployment expanding the architectural prototype in [`repobrain/webhook.py`](repobrain/webhook.py) with organization-wide policy management and SAML SSO (GitHub Actions workflow and CLI preflight remain the core production integrations today).
- **Multi-Language AST Optimizers**: Expand verified AST complexity reduction to TypeScript and Go.
- **Public Cryptographic Anchoring**: Sigstore Rekor / RFC 3161 timestamping for external audit root attestation.
- **Native IDE Sidecars**: VS Code and JetBrains extensions wired directly to `/api/preflight`.
