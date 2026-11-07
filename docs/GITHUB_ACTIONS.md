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

---

## 3. Audit Anchoring in CI & HMAC Signing

The RepoBrain audit trail is a cryptographically hash-chained append-only JSONL log where each entry contains:
```json
{
  "seq": 1,
  "ts": "2026-11-07T12:00:00+0000",
  "event": "review",
  "actor": "claude-bot",
  "decision": "BLOCKED",
  "detail": "3 blocking violations",
  "prev": "0000000000000000000000000000000000000000000000000000000000000000",
  "hash": "c1a4...",
  "sig": "f89d..."
}
```

### HMAC Signing vs Hash-Only Logging
- **Unsigned (hash-only)**: When `REPOBRAIN_AUDIT_KEY` is absent, entries are hash-chained via SHA-256 (`prev -> hash`). Any modification to an existing entry breaks hashes downstream. However, an attacker with write access to the filesystem could recompute SHA-256 hashes for all downstream blocks.
- **HMAC-signed**: When `REPOBRAIN_AUDIT_KEY` is configured as a GitHub Actions secret (`${{ secrets.REPOBRAIN_AUDIT_KEY }}`), every entry receives an HMAC-SHA256 signature (`sig = HMAC_SHA256(key, hash)`). An attacker without the key cannot forge valid signatures, preventing full-chain recomputation.
- **Action input `require_audit_key`**: `action.yml` defaults `require_audit_key: "true"`, causing CI to fail if the signing key is missing. Set to `"false"` only if evaluating unsigned logs in local demo environments.

### Complete Anchored CI Workflow (`.github/workflows/repobrain-audit.yml`)

The anchored head verification flow links each CI run to the cryptographic state of the prior run:

```yaml
name: RepoBrain Audit & Anchoring
on:
  pull_request:
    branches: [main]

jobs:
  audit-verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e .

      # 1. Download previous head anchor from the default branch
      - name: Download prior audit anchor
        uses: dawidd6/action-download-artifact@v3
        continue-on-error: true
        with:
          workflow: repobrain-audit.yml
          branch: main
          name: repobrain-anchor
          path: /tmp/repobrain-anchor

      # 2. Verify chain against previous anchor and write new anchor
      - name: Verify audit chain & anchor new head
        env:
          REPOBRAIN_AUDIT_KEY: ${{ secrets.REPOBRAIN_AUDIT_KEY }}
          REPOBRAIN_HOME: ${{ runner.temp }}/repobrain
        run: |
          if [ -f /tmp/repobrain-anchor/head.sha256 ]; then
            echo "Verifying chain against previous anchor..."
            python -m repobrain audit --anchor-file /tmp/repobrain-anchor/head.sha256 --write-anchor /tmp/new_anchor/head.sha256
          else
            echo "First run; writing genesis anchor..."
            python -m repobrain audit --write-anchor /tmp/new_anchor/head.sha256
          fi

      # 3. Upload updated anchor for future runs
      - name: Upload new head anchor
        uses: actions/upload-artifact@v4
        with:
          name: repobrain-anchor
          path: /tmp/new_anchor/head.sha256
          retention-days: 90
```

### Catching Silent Truncation with `--expect <seq>`

If an attacker truncates the tail of the audit log (e.g., dropping the last 3 entries to erase a blocked review record), the remaining sub-chain is internally valid (all `prev` hashes match).

1. **Anchored head verification (`--anchor-file`)**: Catches truncation because the resulting head hash does not match the expected 64-character hash of the true head.
2. **Sequence expectation (`--expect <seq>`)**: By passing an expected entry count or sequence index (e.g., stored in CI state as `14`), `repobrain audit --expect 14` checks `len(entries)` and `entries[-1]["seq"]`. If tail entries are removed, verification immediately fails with:
   ```
   chain: BROKEN at #None - expected sequence #14, found #11 (log truncated or entries dropped)
   ```

### What Is Detectable vs NOT Detectable

#### What Is Detectable
- **In-place record tampering**: Modifying any field (timestamp, actor, decision, detail) in any historical log entry breaks the entry's own SHA-256 hash. `broken_at = #N` is immediately identified.
- **Entry deletion**: Removing an entry from the middle breaks the `prev` link of the next entry.
- **Entry insertion or reordering**: Inserting or swapping records invalidates the `prev` pointers.
- **Log truncation**: Deleting entries from the tail produces a valid internal sub-chain, but `--anchor-file` or `--expect <seq>` flags the missing entries immediately.
- **Recomputed hashes on HMAC chains**: An attacker who rewrites content and updates all SHA-256 hashes still fails verification because `sig` fails without `REPOBRAIN_AUDIT_KEY`.

#### What Is NOT Detectable
- **Out-of-band bypasses**: Actions taken directly against git (e.g., an administrator pushing directly to `main` with bypass rights or disabling GitHub Actions) never invoke RepoBrain and produce no audit entries. Branch rulesets must disallow admin bypasses.
- **Unanchored log substitution without signing key**: If an unsigned log is replaced entirely and checked without `--expect` or `--anchor-file`, a standalone `audit` command has no anchor to compare against. Always use HMAC signing and CI artifact anchors in production.

