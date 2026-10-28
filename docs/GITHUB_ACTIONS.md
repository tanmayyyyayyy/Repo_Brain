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
3. **Protected Paths**: Changes to `.github/workflows/` made by AI agents are flagged as `blocked-path` by Shield, automatically failing the required check.
