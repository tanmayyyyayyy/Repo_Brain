# Frequently Asked Questions (FAQ)

---

### 1. How does RepoBrain differ from traditional linters (Ruff, flake8, SonarQube)?
Traditional linters and static analysis tools are advisory: they post comments, flag style discrepancies, and report warnings. They do not understand the difference between AI-generated code and human-written code, cannot enforce immutable blast-radius limits based on author identity, do not provide an append-only cryptographic audit trail, and cannot safely rewrite or simplify complex code with test-backed equivalence guarantees. RepoBrain is an active governance and merge gate: it enforces non-waivable policy rules, blocks unauthorized paths, and verifies that code satisfies complexity limits before merging.

### 2. Why not let the AI agent approve its own PR?
Letting an AI agent approve its own PR creates a circular trust vulnerability. If an agent hallucinates, loops, or is subverted via prompt injection, allowing it to approve or merge its own changes breaks the security boundary. RepoBrain enforces `approval: human` in policy: an AI-authored change proposal can only be approved by a verified human committer (recording an `Approved-by:` trailer in the git commit and an HMAC-signed audit log entry).

### 3. What happens if my repository test suite is slow?
RepoBrain provides configurable test execution controls in `repobrain.yml`:
- `test_timeout`: Sets a hard execution deadline (default 180s) for the test runner subprocess.
- `test_command`: Customize the test runner to only execute relevant test subsets (e.g. `pytest -q -m "not slow"`).
- In addition, the optimizer only runs tests against touched files in a scratch copy. If tests exceed the timeout or fail, the proposed optimization is automatically discarded without modifying the repository.

### 4. How do I waive a complexity failure when a function is legitimately complex?
If a function requires higher cyclomatic or cognitive complexity (e.g., a hardware driver or an intricate parser state machine), a human can issue an explicit waiver via the CLI or web console:
```bash
python -m repobrain waive --actor "alice@example.com" --reason "Parser state machine requires switch table"
```
The waiver is permanently recorded in the append-only HMAC audit log with the committer's identity, timestamp, and justification, converting the gate failure into an authorized review pass.

### 5. Is my source code sent to an external LLM API?
**No, by default.** RepoBrain runs 100% locally using standard library AST transformations, regex rules, entropy analysis, and a local multinomial Naive Bayes classifier. No proprietary code or diff content is sent to third-party APIs. Only if you explicitly configure `allow_llm: true` in `repobrain.yml` and provide `GROQ_API_KEY` or `ANTHROPIC_API_KEY` will the AI refactoring tier use an external model for Scenario C high-complexity function decomposition.

### 6. Does RepoBrain work with non-Python languages?
- **Shield (Policy, Secrets, Injections, Protected Paths)**: Works across all programming languages, configuration formats (YAML, JSON), and shell scripts.
- **Audit & Governance Gates**: Language-agnostic.
- **AST Optimizer**: Currently supports Python. If a non-Python file exceeds complexity limits, the gate flags changes required, which can be waived by a human reviewer or resolved manually. Expanding the AST optimizer to TypeScript and Go is on our product roadmap.

### 7. How do I verify the audit log off-line?
The audit log is a self-contained append-only JSONL file stored in `~/.repobrain/<repo-hash>/audit.jsonl` or `$REPOBRAIN_HOME`. You can verify cryptographic integrity completely off-line:
```bash
python -m repobrain audit
```
This verifies that every SHA-256 hash link (`prev -> hash`) is intact and checks all HMAC-SHA256 signatures against `REPOBRAIN_AUDIT_KEY`.

### 8. How does RepoBrain handle merge conflicts or stale PR bases?
RepoBrain executes `git diff base...head` against the trusted base branch (`origin/main`). In GitHub Actions, enabling **"Require branches to be up to date before merging"** in branch rulesets ensures that PRs must be rebased onto current `main` before the final check passes. If files conflict, git diff cannot resolve the revision, and RepoBrain halts until conflicts are settled.

### 9. Can an AI agent bypass RepoBrain by modifying `repobrain.yml`?
**No.** RepoBrain always loads `repobrain.yml` from the trusted base ref (e.g., `origin/main`), not from the PR branch. Any edits made to `repobrain.yml` in the PR diff are completely ignored by the policy evaluator. Furthermore, `repobrain.yml` is listed under protected paths in default policy, meaning an AI actor attempting to modify it is immediately blocked.

### 10. How does differential fuzzing prevent regressions in optimized code?
Before an AST rewrite is proposed, `repobrain/fuzz.py` runs differential fuzzing on pure functions in an isolated subprocess with memory and CPU rlimits. It extracts literal constants from the function and tests both the original and rewritten ASTs with boundary values (integers, floats, negative values, empty strings, None, empty collections). If return values, exceptions, or argument mutations diverge, the rewrite proposal is instantly rejected.
