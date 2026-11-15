# RepoBrain — Comprehensive Technical Documentation
## System Architecture, Technology Stack, APIs, and Enterprise Integrations
### Final Build & Innovation Showcase (Round 3 / Top 150 Finals)

---

## 1. Executive Summary & Value Proposition

**RepoBrain** is an enterprise-grade, vendor-neutral safety, complexity optimization, and cryptographic audit governance system for repositories where AI coding agents (Claude Code, Cursor, Copilot Workspace, Devin, Aider) and human developers collaborate.

As autonomous AI agents generate thousands of lines of code per sprint, software engineering organizations face an unprecedented crisis of **governance, supply-chain contamination, architectural erosion, and audit compliance**. Existing linting tools (Ruff, SonarQube) only post non-blocking advisory comments *after* code is committed, and traditional secret scanners fail to detect concatenated or base64-encoded credentials.

RepoBrain solves this with a **zero-trust, multi-tiered defense architecture**:
1. **Preflight Agent Safety Interceptor**: Stops autonomous agents *before* they write to disk or commit to version control.
2. **Shield Engine**: Protects critical workflows, normalizes and unmasks multi-fragment secrets, detects multi-line prompt injections, and blocks typosquatted dependencies using Damerau-Levenshtein distance.
3. **Verified AST Optimizer & Differential Fuzzing**: Automatically refactors overly complex code and verifies correctness by running tests in isolated scratch sandboxes with differential invariant fuzzing.
4. **Enterprise Role-Based Access Control (RBAC)**: Separates developer authoring, QA testing, and security analysis from human code merge approvals (`Approved-by:` trailers) and policy waivers.
5. **Cryptographic Audit Ledger**: Records every event in an append-only JSONL ledger hash-chained with SHA-256 and signed via HMAC-SHA256, proving tamper-resistance to compliance auditors.

---

## 2. Technology Stack & Architectural Philosophy

RepoBrain is engineered with a **minimal-dependency, high-reliability, zero-telemetry philosophy**. It runs completely offline without sending code or metadata to third-party cloud servers.

| Component | Technology / Standards | Rationale & Enterprise Benefits |
|---|---|---|
| **Runtime Language** | Python 3.10+ (Standard Library) | Zero deployment friction, cross-platform portability across Linux, macOS, and Windows. |
| **Parsing & Ast Engine** | Python `ast`, `tokeneater`, `re` | Deterministic, semantic-preserving code inspection and complexity quantification without external compilers. |
| **Cryptography & Hashing** | Python `hashlib`, `hmac`, `secrets` | FIPS-compliant PBKDF2-HMAC-SHA256 password hashing (600,000 iterations), SHA-256 hash chains, HMAC message authentication. |
| **Configuration** | PyYAML (`repobrain.yml`) | Industry-standard declarative policy schema versioned directly within trusted base branches. |
| **Embedded Console Server** | `http.server.ThreadingHTTPServer` | High-performance multi-threaded HTTP server with zero external web framework dependencies (no FastAPI/Flask/Django bloat). |
| **Frontend Mission Control** | Vanilla Modern JavaScript (ES6+), HTML5, CSS3 | Single-file, zero-build dashboard adhering to WCAG 2.1 AA accessibility standards, responsive from mobile (360px) to 4K displays. |
| **Testing & Quality Assurance** | `pytest`, `playwright` | Comprehensive unit, integration, security audit, and end-to-end browser tests (137 passed tests). |
| **Containerization** | Docker, multi-stage Alpine / Python image | Production-ready container image for on-premise deployment and Kubernetes orchestration. |

---

## 3. High-Level System Architecture

```
                                      ┌─────────────────────────────────────────────────────────┐
                                      │              DEVELOPER & AGENT INGESTION                │
                                      │  Claude Code CLI / Cursor MCP / GitHub Actions / PRs    │
                                      └────────────────────────────┬────────────────────────────┘
                                                                   │
                                                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                 REPOBRAIN GOVERNANCE PIPELINE                                                   │
│                                                                                                                                 │
│   ┌───────────────────────────┐    ┌───────────────────────────┐    ┌───────────────────────────┐    ┌──────────────────────┐   │
│   │     1. SHIELD ENGINE      │    │    2. COMPLEXITY GATE     │    │   3. VERIFIED OPTIMIZER   │    │  4. HUMAN APPROVAL   │   │
│   │  • Protected Paths        │───►│  • Cyclomatic CC <= 10    │───►│  • Semantic AST Rewrites  │───►│  • Named Human Gate  │   │
│   │  • Unmasked Secrets       │    │  • Cognitive Comp <= 15   │    │  • Isolated Test Runner   │    │  • Git Signed Commit │   │
│   │  • Multi-line Injections  │    │  • Nesting Depth <= 3     │    │  • Differential Fuzzing   │    │  • 'Approved-by:'    │   │
│   │  • Typo Dependency Guard  │    │  • Touched Functions Only │    │  • Invariant Verification │    │  • Release Manager   │   │
│   └─────────────┬─────────────┘    └─────────────┬─────────────┘    └─────────────┬─────────────┘    └──────────┬───────────┘   │
└─────────────────┼────────────────────────────────┼────────────────────────────────┼─────────────────────────┼───────────────────┘
                  │                                │                                │                         │
                  ▼                                ▼                                ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                           CRYPTOGRAPHIC AUDIT LEDGER & ACCESS CONTROL                                           │
│   ┌──────────────────────────────────────────────────────────────────┐  ┌───────────────────────────────────────────────────┐   │
│   │          APPEND-ONLY HMAC-SHA256 CHAINED AUDIT LEDGER            │  │        ENTERPRISE RBAC & DOMAIN AUTHENTICATION       │   │
│   │  • Sequence Numbered • SHA-256 Genesis Hash Chain                │  │  • Corporate Email Enforced (@company.com)       │   │
│   │  • HMAC-SHA256 Signatures • Tamper Invalidation Proof            │  │  • PBKDF2-HMAC-SHA256 Passwords (600k rounds)    │   │
│   │  • Export Formats: SARIF, Markdown, CSV, JSON                    │  │  • Roles: Admin, Security, Tester, Developer     │   │
│   └──────────────────────────────────────────────────────────────────┘  └───────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Enterprise Authentication & Role-Based Access Control (RBAC)

RepoBrain implements enterprise-grade identity governance designed for SOC 2 Type II, ISO 27001, and NIST CSF compliance.

### 4.1. Corporate Email Domain Validation
RepoBrain enforces organization-level email policies:
- **Generic Webmail Prohibition**: Automatically rejects non-business public email services (`@gmail.com`, `@yahoo.com`, `@hotmail.com`, `@outlook.com`, `@proton.me`, `@aol.com`, `@icloud.com`).
- **Domain Whitelisting**: Organizations can configure strict corporate domains (e.g. `allowed_domains: ["acme-corp.com", "enterprise.org"]` in `repobrain.yml` or `REPOBRAIN_COMPANY_DOMAINS` environment variable).

### 4.2. Password Hashing & Cryptographic Storage
- **Algorithm**: `PBKDF2-HMAC-SHA256` matching OWASP 2024+ security guidelines.
- **Iterations**: `600,000` computational rounds.
- **Salt**: 16-byte cryptographically secure random salt generated via `secrets.token_bytes(16)` per user.
- **Constant-Time Verification**: Verification uses `secrets.compare_digest` to prevent timing side-channel attacks.

### 4.3. 4-Tier Enterprise Role Hierarchy

| Role ID | Display Title | Persona | Primary Responsibilities & Permitted Actions |
|---|---|---|---|
| `admin` | **Admin / Release Manager** | Alex Mercer | Full governance authority: approve code merges (`Approved-by:` trailer), issue policy waivers, manage team roles, rotate HMAC audit keys, update organization policies. |
| `security` | **DevSecOps / Security Lead** | Samira Patel | Security telemetry: configure Shield rules, inspect secret patterns, analyze prompt injection telemetry, verify HMAC audit chain, issue security waivers. |
| `tester` | **QA / Test Engineer** | Quinn Vance | Quality assurance: inspect differential fuzzing invariants, verify test coverage gates, run Failure Explainer on CI crash logs. |
| `developer` | **Software Engineer** | Alice Chen | Code authoring: run AST optimizer, view PR diffs, execute preflight safety checks, submit human review requests. |

### 4.4. RBAC Permissions Matrix

| Capability / API Endpoint | Developer | Tester (QA) | Security Lead | Admin (Release Mgr) |
|---|:---:|:---:|:---:|:---:|
| `view_pr` (`/api/diff`, `/api/state`) | **ALLOW** | **ALLOW** | **ALLOW** | **ALLOW** |
| `run_optimizer` (`/api/optimize`) | **ALLOW** | DENIED | DENIED | **ALLOW** |
| `request_review` (`/api/review`) | **ALLOW** | **ALLOW** | **ALLOW** | **ALLOW** |
| `inspect_fuzzing` (`/api/state`) | DENIED | **ALLOW** | DENIED | **ALLOW** |
| `inspect_coverage` (`/api/state`) | DENIED | **ALLOW** | DENIED | **ALLOW** |
| `run_explainer` (`/api/explain`) | DENIED | **ALLOW** | DENIED | **ALLOW** |
| `configure_shield` (`/api/shield`) | DENIED | DENIED | **ALLOW** | **ALLOW** |
| `inspect_secrets` (`/api/diff`) | DENIED | DENIED | **ALLOW** | **ALLOW** |
| `verify_audit` (`/api/audit`) | DENIED | DENIED | **ALLOW** | **ALLOW** |
| `simulate_tamper` (`/api/audit/tamper`) | DENIED | DENIED | **ALLOW** | **ALLOW** |
| `grant_waiver` (`/api/waive`) | DENIED | DENIED | **ALLOW** | **ALLOW** |
| `apply_approval` (`/api/approve`) | DENIED | DENIED | DENIED | **ALLOW** |
| `manage_users` (`/api/auth/update-role`) | DENIED | DENIED | DENIED | **ALLOW** |
| `manage_policy` (`/api/policy`) | DENIED | DENIED | DENIED | **ALLOW** |

---

## 5. Core Governance Engines

### 5.1. Shield Engine (`repobrain/shield.py`)
The Shield engine inspects incoming pull request diffs and file writes before they reach the repository:
- **Path Guard**: Blocks changes to sensitive infrastructure files (`.github/workflows/`, `secrets/`, `credentials/`, `repobrain.yml`) when authored by an AI actor.
- **Secret Scanner**: Identifies high-entropy strings, AWS access keys (`AKIA...`), GitHub Personal Access Tokens (`ghp_...`), private keys (`-----BEGIN PRIVATE KEY-----`), and tokens split across string concatenations (`"AKIA" + "..."`) or encoded in Base64.
- **Prompt Injection Detector**: Multi-line sliding-window scanner detecting delimiter manipulation (`<system>`, `[INST]`), instructions override (`ignore all previous instructions`), and jailbreak attempts.
- **Dependency Typo-Squatting Guard**: Analyzes `requirements.txt`, `pyproject.toml`, and `package.json` against a curated dataset of popular packages using Damerau-Levenshtein edit distance (distance ≤ 2 flags suspicious packages).

### 5.2. AST Complexity Gate (`repobrain/metrics.py`)
Rather than linting whole repositories (which punishes PRs for preexisting legacy technical debt), RepoBrain calculates metrics **strictly on functions touched by the pull request**:
- **Cyclomatic Complexity (CC)**: Threshold ≤ 10 (decision points, branches, comprehensions).
- **Cognitive Complexity**: Threshold ≤ 15 (nesting weight penalties).
- **Maximum Nesting Depth**: Threshold ≤ 3 levels.

### 5.3. Verified AST Optimizer & Differential Fuzzer (`repobrain/optimizer.py`, `repobrain/fuzz.py`)
When functions exceed complexity limits, the Optimizer automatically generates clean, maintainable alternatives:
- **AST Transforms**: Deconstructs deeply nested `if/else` ladders into guard clauses and early returns; splits multi-responsibility functions; eliminates dead code and unused imports.
- **Isolated Sandbox Verification**: Executes the project's test suite inside an ephemeral scratch directory with execution timeouts and memory bounds.
- **Differential Invariant Fuzzing**: Generates type-aware inputs (strings, integers, floats, collections) and verifies that both the original function and the rewritten function yield identical return values and exceptions.
- **Mandatory Human Approval**: RepoBrain adheres to `approval: human`. Optimization proposals require explicit approval by an authorized Release Manager, committing the change with an `Approved-by: Human Name <email>` git trailer.

### 5.4. Cryptographic Audit Ledger (`repobrain/audit.py`)
All events are recorded into an immutable, append-only JSONL log:
- **Hash Chaining**: Each record includes sequence number, UTC timestamp, event type, actor identity, decision, detail, and the SHA-256 hash of the previous record:
  $$H_i = \text{SHA256}(\text{JSON}(R_i \setminus \{\text{hash}, \text{sig}\}) \parallel H_{i-1})$$
- **HMAC Signatures**: When `REPOBRAIN_AUDIT_KEY` is provided, every block receives an HMAC-SHA256 signature:
  $$S_i = \text{HMAC-SHA256}(K, H_i)$$
- **Tamper Detection**: Altering any historical line or signature instantly invalidates all downstream blocks, exposing the exact corruption point.

---

## 6. Complete API Reference

All `/api/*` endpoints require authentication via either:
- HTTP Header: `X-RepoBrain-Session: <token>` or `Authorization: Bearer <token>`
- Or ephemeral CLI token: `X-RepoBrain-Token: <token>`

### 6.1. Authentication & Team Management Endpoints

#### `POST /api/auth/register`
Register a new corporate user with company email, password, and enterprise role.
- **Request Body**:
  ```json
  {
    "email": "sarah.connor@cyberdyne.corp",
    "password": "CorporatePassword2026!",
    "name": "Sarah Connor",
    "role": "developer",
    "company": "Cyberdyne Systems"
  }
  ```
- **Response (200 OK)**:
  ```json
  {
    "user": {
      "id": "usr-8a9b2c3d4e5f",
      "email": "sarah.connor@cyberdyne.corp",
      "name": "Sarah Connor",
      "role": "developer",
      "role_badge": "DEV",
      "role_title": "Software Engineer / Developer",
      "permissions": ["view_pr", "run_optimizer", "run_tests", "request_review"],
      "company": "Cyberdyne Systems"
    },
    "token": "d8F3k...32bytes"
  }
  ```

#### `POST /api/auth/login`
Authenticate corporate user and generate a 7-day session token.
- **Request Body**: `{"email": "alex.mercer@acmeworks.internal", "password": "..."}`
- **Response (200 OK)**: `{"user": {...}, "token": "..."}`

#### `POST /api/auth/logout`
Revoke active session token.
- **Request Body**: `{"token": "..."}`
- **Response (200 OK)**: `{"ok": true}`

#### `GET /api/auth/me`
Retrieve active user profile, corporate permissions, and role definitions.
- **Response (200 OK)**: `{"user": {...}, "roles": {...}, "demo_personas": [...]}`

#### `POST /api/auth/switch-demo-role`
Frictionless persona switcher for evaluators and demonstration environments.
- **Request Body**: `{"role": "admin" | "security" | "tester" | "developer"}`
- **Response (200 OK)**: `{"user": {...}, "token": "..."}`

#### `POST /api/auth/update-role`
Update a user's role (Restricted to `admin`).
- **Request Body**: `{"email": "user@company.com", "role": "security"}`
- **Response (200 OK)**: `{"user": {...}}`

---

### 6.2. Review & Governance Pipeline Endpoints

#### `GET /api/state`
Returns the complete repository governance telemetry, active branch, base comparison, policy rules, and role status.

#### `POST /api/review`
Executes full Shield analysis, complexity gating, and risk scoring on current changes.
- **Response (200 OK)**:
  ```json
  {
    "verdict": "blocked",
    "decision": "BLOCKED",
    "counts": {"blocks": 2, "warns": 1, "gate": 1},
    "findings": [
      {
        "severity": "block",
        "rule": "blocked-path",
        "file": ".github/workflows/ci.yml",
        "msg": "AI actor touches protected path '.github/workflows/'"
      }
    ],
    "risk": {"score": 52, "level": "high"}
  }
  ```

#### `POST /api/optimize`
Runs deterministic AST refactoring on touched functions exceeding complexity thresholds and verifies tests in sandbox.
- **Request Body**: `{"ai": false}`
- **Response (200 OK)**: `{"id": "prop-4a7b", "status": "verified", "files": [...]}`

#### `POST /api/approve`
Applies an optimization proposal and creates a signed git commit with `Approved-by:` trailer.
- **Authorization**: Requires `admin` role (`apply_approval` permission). Returns `403 Forbidden` for other roles.
- **Request Body**: `{"id": "prop-4a7b", "actor": "Alex Mercer <alex@acme.corp>"}`
- **Response (200 OK)**: `{"commit": "3f8e12a...", "applied": ["shop/orders.py"]}`

#### `POST /api/waive`
Issues an authorized technical debt waiver for a pull request, logged to the HMAC audit ledger.
- **Authorization**: Requires `admin` or `security` role (`grant_waiver` permission).
- **Request Body**: `{"reason": "Accepting legacy technical debt for hotfix release", "actor": "Samira Patel"}`
- **Response (200 OK)**: `{"waived": true, "head": "...", "reason": "..."}`

#### `POST /api/preflight`
Vendor-neutral pre-write validation hook for AI agents (Claude Code, Cursor MCP, etc.).
- **Request Body**:
  ```json
  {
    "actor": "claude-code[bot]",
    "files": [{"path": ".github/workflows/ci.yml", "content": "..."}]
  }
  ```
- **Response (200 OK)**: `{"decision": "block", "findings": [...]}`

---

### 6.3. Audit & Compliance Export Endpoints

#### `GET /api/audit`
Returns the append-only audit trail and cryptographic signature verification status.

#### `POST /api/audit/tamper`
Simulates a real-world adversarial ledger alteration in memory, demonstrating exact block invalidation and cryptographic alert triggers.

#### `GET /api/export?fmt=sarif`
Exports all findings in standard OASIS SARIF v2.1.0 format for direct ingestion into GitHub Code Scanning and enterprise SIEM tools.

#### `GET /api/export?fmt=csv`
Exports the complete HMAC audit ledger in CSV format for compliance reporting.

---

## 7. Enterprise Security Hardening & Zero-Trust Controls

1. **DNS-Rebinding Protection**: Validates the `Host` and `X-Forwarded-Host` headers against localhost and explicitly configured domains in `REPOBRAIN_ALLOWED_HOSTS`.
2. **Strict CSRF Defense**: All state-modifying endpoints (`POST`) require `Content-Type: application/json` and `X-RepoBrain: 1` verification, rejecting unauthorized cross-site requests.
3. **Content Security Policy (CSP)**: Strict origin isolation policy — API endpoints enforce `default-src 'none'; frame-ancestors 'none'; sandbox`; UI enforces `connect-src 'self'; default-src 'self'; object-src 'none'; frame-ancestors 'none';` blocking external network egress and third-party script sources.
4. **Corporate Domain Verification**: Strict domain filter rejecting consumer webmail providers (`@gmail.com`, `@yahoo.com`, `@hotmail.com`, etc.) to enforce corporate enterprise identity boundary isolation.
5. **Path Traversal Defenses**: All file access endpoints (`/api/diff?path=...`, `/api/preflight`) validate paths prior to any filesystem access and enforce repository boundary containment via `os.path.commonpath`.
6. **Payload & Resource Limits**: Requests exceeding 2MB or invalid `Content-Length` are rejected with `413 Body Too Large` or `400 Bad Request`. Test subprocesses execute within isolated process groups with POSIX CPU and memory rlimits.

---

## 8. Integrations & Deployment

### 8.1. GitHub Actions CI/CD Integration
```yaml
name: RepoBrain Governance Check
on: [pull_request]
jobs:
  governance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install repobrain
      - name: Enforce Policy
        env:
          REPOBRAIN_AUDIT_KEY: ${{ secrets.REPOBRAIN_AUDIT_KEY }}
        run: python -m repobrain check --base origin/${{ github.base_ref }} --sarif repobrain.sarif
      - uses: github/codeql-action/upload-sarif@v3
        if: always()
        with: { sarif_file: repobrain.sarif }
```

### 8.2. Claude Code Pre-commit Interceptor
```bash
python -m repobrain hook install claude
# Configures vendor-neutral preflight hook stopping agents before files are written.
```

### 8.3. Cursor & MCP Protocol Server
```bash
python -m repobrain.mcp
# Implements JSON-RPC Model Context Protocol exposing tools:
# - repobrain_preflight
# - repobrain_inspect_policy
# - repobrain_verify_audit
```

---

*RepoBrain Technical Documentation — Prepared for Unstop Final Build & Innovation Showcase 2026.*

