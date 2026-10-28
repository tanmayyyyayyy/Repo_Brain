# GitHub Actions & Branch Ruleset Setup

RepoBrain was verified on a real GitHub repository:
- **Repository**: [`tanmayyyyayyy/repobrain-demo-eval`](https://github.com/tanmayyyyayyy/repobrain-demo-eval)
- **PR #1 (Scenario A - Risky AI PR)**: [`https://github.com/tanmayyyyayyy/repobrain-demo-eval/pull/1`](https://github.com/tanmayyyyayyy/repobrain-demo-eval/pull/1)
  - Result: **BLOCKED** (3 blocking findings: `.github/workflows/ci.yml` protected path, `docs/AGENT_NOTES.md` prompt injection, `shop/config.py` hardcoded AWS key; 2 warnings: deleted test, dependency change). Check exited code 1 (failed). PR comment posted.
- **PR #2 (Scenario B - Messy AI PR)**: [`https://github.com/tanmayyyyayyy/repobrain-demo-eval/pull/2`](https://github.com/tanmayyyyayyy/repobrain-demo-eval/pull/2)
  - Result: **CHANGES REQUIRED** (`discount_for` nesting depth 4 > 3). Check exited code 1. Optimizer step proposed tested cleanup (cognitive 15->10, depth 4->3, tests passed). PR comment posted. Audit log uploaded as workflow artifact.

---

## 1. Workflow Architecture (`.github/workflows/repobrain.yml`)

```yaml
name: RepoBrain
on:
  pull_request:

permissions:
  contents: read
  pull-requests: write

jobs:
  repobrain:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0                       # needed for base...head diff and per-commit authors
      - name: Fetch base branch
        run: git fetch origin "${{ github.base_ref }}"
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install pyyaml pytest
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
      - name: RepoBrain review (shield + complexity gate)
        env:
          PYTHONPATH: .
          REPOBRAIN_HOME: ${{ runner.temp }}/repobrain
          PR_AUTHOR: ${{ github.event.pull_request.user.login }}
          BASE_REF: ${{ github.base_ref }}
        run: python -m repobrain review --base "origin/$BASE_REF" --actor "$PR_AUTHOR" --comment "$RUNNER_TEMP/repobrain.md"
      - name: Propose a tested cleanup (never auto-applied)
        if: failure()
        env:
          PYTHONPATH: .
          REPOBRAIN_HOME: ${{ runner.temp }}/repobrain
          BASE_REF: ${{ github.base_ref }}
        run: python -m repobrain optimize --base "origin/$BASE_REF" --diff | tee "$RUNNER_TEMP/optimize.txt" || true
      - name: Comment on the PR
        if: always()
        continue-on-error: true                # fork PRs get a read-only token
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          if [ -f "$RUNNER_TEMP/repobrain.md" ]; then
            gh pr comment "${{ github.event.pull_request.number }}" --body-file "$RUNNER_TEMP/repobrain.md"
          fi
      - name: Upload audit log
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: repobrain-audit
          path: ${{ runner.temp }}/repobrain
          if-no-files-found: ignore
```

---

## 2. Making the Check Required and Tamper-Proof (Branch Ruleset)

To ensure an AI agent or contributor cannot bypass or disable RepoBrain:

1. **Navigate to Repository Settings**:
   - Go to `https://github.com/<owner>/<repo>/settings/rules`
   - Click **New ruleset** → **New branch ruleset**.

2. **Ruleset Configuration**:
   - **Ruleset Name**: `RepoBrain Enforcement`
   - **Enforcement status**: `Active`
   - **Target branches**: Select `Include default branch` (e.g. `main`).

3. **Protection Rules**:
   - Check **Require a pull request before merging**:
     - Required approvals: `1`
     - Dismiss stale pull request approvals when new commits are pushed: `Checked`
     - Require review from Code Owners (optional): `Checked`
   - Check **Require status checks to pass before merging**:
     - Click **+ Add check** and search for: `repobrain` (or `RepoBrain`).
     - Check **Require branches to be up to date before merging** (guarantees that the base branch against which RepoBrain evaluated policy is current).
   - Check **Block force pushes**.
   - Check **Restrict deletions**.

### Why This Is Tamper-Proof
1. **Policy from Base**: RepoBrain reads `repobrain.yml` from `origin/$BASE_REF` (the protected default branch). Any edits to `repobrain.yml` inside the PR are completely ignored by the evaluator.
2. **Workflow from Base**: GitHub Actions evaluates required checks defined on the default branch. Even if a PR modifies `.github/workflows/repobrain.yml`, the required status check must still pass.

---

## 3. Audit Anchoring in CI: What Is and Is Not Detectable

The RepoBrain audit trail is a cryptographically hash-chained append-only JSONL log where each entry contains `hash = SHA256(seq + ts + event + actor + decision + detail + prev_hash)`.

### How CI Anchoring Works
1. When RepoBrain runs on CI, it appends review and optimization records to the local audit log.
2. The workflow downloads the previous run's anchor artifact via `actions/download-artifact`.
3. It executes `python -m repobrain audit --anchor-file <prev_anchor> --write-anchor <new_anchor>`.
4. The new head hash is uploaded as a workflow artifact (`repobrain-anchor`) that subsequent runs download.
5. Because GitHub Actions artifacts from prior runs cannot be overwritten or altered by a PR branch without repository admin privileges, the audit chain is securely anchored across PR runs.

### What Is Detectable
- **In-place record tampering**: Modifying any field (timestamp, actor, decision, detail) in any historical log entry breaks the entry's own SHA-256 hash. `broken_at = #N` is immediately identified.
- **Entry deletion**: Removing an entry from the middle breaks the `prev` link of the next entry.
- **Entry insertion or reordering**: Inserting or swapping records invalidates the `prev` pointers.
- **Log truncation**: Deleting entries from the tail produces a valid internal sub-chain, but the head hash differs from the anchored head hash recorded in CI. `--anchor-file` detects this immediately with `reason: head hash differs from the anchored value`.

### What Is NOT Detectable
- **Out-of-band bypasses**: Actions taken directly against git (e.g., an administrator pushing directly to `main` with bypass rights or disabling GitHub Actions) never invoke RepoBrain and produce no audit entries. This is why GitHub Branch Rulesets must disable bypass permissions.
- **Unanchored log substitution**: If an attacker completely deletes the audit log and writes a completely new, internally-valid log starting from `0000...0000`, a standalone `repobrain audit` *without* `--expect` or `--anchor-file` cannot tell it is a substitution. Checking against an externally stored anchor (CI artifact or release tag) is required to detect full rewrites.
3. **Protected Paths**: Changes to `.github/workflows/` made by AI agents are flagged as `blocked-path` by Shield, automatically failing the required check.

