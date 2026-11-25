# RepoBrain Demo Guide

Use the [3–5 minute video script](VIDEO_SCRIPT.md) for the judging walkthrough. This guide covers the local fallback and the evidence each scenario should show.

## Start the seeded demo

```bash
python -m pip install -r requirements.txt
python -m repobrain serve --demo --no-browser --port 8765
```

Open `http://127.0.0.1:8765/`. The demo creates a disposable workspace and an ephemeral audit key. Use only the provided fixtures; do not paste real credentials.

## Scenario A — block the risky pull request

Select **A · risky AI PR**. Show the blocked verdict and these findings:

- `shop/config.py:1`: secret
- `.github/workflows/ci.yml`: protected path
- `docs/AGENT_NOTES.md:5`: prompt injection

The exact rule result depends on the seeded fixture and policy. Point to the file and line in the findings panel rather than claiming a universal scanner result.

## Scenario B — check a proposed rewrite

Select **B · messy AI PR**, then run the optimizer. The seeded run shown in the current demo reports 26 passing tests, 1,000 fuzz inputs across 4 functions, and 0 divergences. It reduces cognitive complexity from 15 to 10, nesting depth from 4 to 3, and source lines from 69 to 47.

The symbolic prover covers supported pure control-flow rewrites. Other safeguards include scratch-copy tests and differential fuzzing; these checks do not prove arbitrary Python behavior. Enter `Priya Sharma`, apply the proposal, and show the `Approved-by:` trailer and the rerun verdict.

## Golden path — allow a clean change

Select **D · clean PR**. Show **ALLOWED** with 0 blocking findings. This seeded example demonstrates the clean-change path; it is not a general false-positive benchmark.

## Audit and receipt

Open **Audit & report** and show the verified chain. Use **Simulate tampering** to edit a historical entry and show the resulting invalidation.

For offline receipt verification, supply a previously saved root or HMAC key separately from the receipt:

```bash
python -m repobrain verify-receipt repobrain-receipt.json --anchor-file trusted-root.txt
```

The root file must be stored through a trusted channel, such as CI artifacts protected by repository permissions. If the root is taken from the receipt being checked, the check only establishes internal consistency. The local video demo labels its root as local and does not claim it is a CI trust anchor.

## Checks

Run the automated suite with `python -m pytest -q`. The most recent verified local run completed with **237 passed, 1 skipped**. `scripts/demo_check.py` exercises the seeded block, optimizer, human approval, receipt, and ledger tamper path in a browser.
