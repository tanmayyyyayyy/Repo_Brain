# Developer Workflow Agent — Hackathon-Agnostic Playbook

RepoBrain's developer workflow agent is a general-purpose tool, not a demo script. It runs against any Git repository, any language stack, any CI system and any alert provider. The seeded `--demo` repository is only an optional example; the agent itself never depends on it.

## 1. Use it on your own repository

```bash
git clone <this-repo> && cd Repo_Brain
pip install -r requirements.txt
python -m repobrain --repo /path/to/your/project init
python -m repobrain --repo /path/to/your/project agent workflow --base main --with-tests
```

`--repo` can be any local checkout. `--base` accepts any ref (`main`, `origin/main`, `develop`). All findings, test runs, diagnoses and incident briefs are written under the audit home (`--home` or `~/.repobrain/<repo-hash>`), never inside your source tree.

## 2. Configure policy on the default branch

Copy `repobrain.yml` to the default branch of the target repository so a pull request cannot weaken its own rules. Useful general settings:

```yaml
version: 1
test_command: "npm test"          # optional: auto-detected if omitted
optimize: advisory
approval: human
triage:
  code_owners:
    frontend: ["src/.*\\.(tsx?|jsx?)$"]
    backend: ["src/.*\\.(go|py|java|rs)$"]
    security: ["^\\.github/workflows/", "Dockerfile"]
```

When `test_command` is omitted, the agent detects the natural command from the repository: `package.json` scripts (npm/pnpm/yarn), `go.mod`, `Cargo.toml`, `pom.xml`, Gradle wrapper, `Makefile`, or the Python default.

## 3. Run the five workflow tasks

| Task | Command | Inputs |
|---|---|---|
| PR triage | `repobrain triage --base main --pr '{"title":"Hotfix: checkout 500s","labels":["urgent"],"additions":120}'` | Git diff plus optional forge-agnostic PR metadata (title, body, labels, author, draft, additions, deletions) |
| Code review | `repobrain review --base main` | Git diff vs trusted base; Shield + complexity gate |
| Failed-build diagnosis | `repobrain diagnose --log ci.log` | Any CI log (GitHub Actions, GitLab CI, Jenkins, local) |
| Testing | `repobrain test --repeats 2` | Repository suite on a scratch copy; flaky-test detection |
| Initial on-call response | `repobrain incident --alert alert.json --actor "Priya Sharma"` | Alertmanager, PagerDuty, Datadog, Opsgenie, Grafana or generic JSON |
| Everything | `repobrain agent workflow --base main --with-tests --log ci.log --alert alert.json` | All of the above in one audited run |

Every task prints structured JSON (add `--json`) and Markdown (`--out report.md`), persists an artifact, and appends an audit entry. Add `--ai` only when `allow_llm: true` is explicitly configured and a provider key is set.

## 4. Language and ecosystem coverage

| Area | Covered |
|---|---|
| PR metadata | GitHub, GitLab, Bitbucket or local git; labels may be strings or `{name: ...}` objects |
| Failure patterns | Python, Node/npm, Go, Rust, Java/Maven/Gradle, Docker, Make, infra (network, disk, memory, auth) |
| Failure locations | `.py`, `.js/.jsx/.ts/.tsx`, `.go`, `.java`, `.rs`, `.rb`, `.cs`, `.php`, `.kt`, `.swift`, `.c/.cpp/.h` |
| Test command | npm/pnpm/yarn, Go, Cargo, Maven, Gradle, Make, pytest/minitest |
| Test mapping | `test_*.py`, `*_test.go`, `*.test.ts`, `*.spec.js`, `*Test.java`, `*_spec.rb`, `tests/`, `__tests__/` |
| Alert shapes | `{"severity": "critical", ...}`, Alertmanager labels/annotations, PagerDuty `payload`, Datadog `alert_type`, Opsgenie priority, Grafana status |

The complexity gate and deterministic AST optimizer target Python. Shield, triage, diagnosis, test orchestration and incident response work across the languages above.

## 5. Wire it into any CI/CD system

- **GitHub Actions**: use the bundled `action.yml` / `.github/workflows/repobrain.yml`.
- **Other CI systems**: call `repobrain review --base "$CI_DEFAULT_BRANCH"` and `repobrain agent workflow --with-tests` as pipeline steps; fail the job on a non-zero exit code.
- **Alerts**: send the provider payload to `POST /api/agent` with `{"task": "incident", "alert": <payload>}`. Signature verification for generic webhooks is available at `POST /api/webhook` via `REPOBRAIN_WEBHOOK_SECRET`.
- **Agent harnesses**: use `/api/preflight` or the MCP server to stop an agent before it writes a forbidden path, then let `repobrain agent` triage the resulting PR.

## 6. Boundaries

The agent does not merge, page, deploy, roll back or edit repository files. Incident acknowledgement requires Security Lead / Admin authority; code changes still require a named human approver. Pair the agent with branch protection so no change bypasses the checks.
