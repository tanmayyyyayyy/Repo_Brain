# RepoBrain — Final Pitch Deck (5 Slides)

**One-line pitch:** RepoBrain puts a trusted, human-controlled safety gate between AI coding agents and production repositories, then records evidence for each decision.

## Slide 1 — Problem

### AI agents can change code faster than teams can review it

- A risky change can hide a split secret, prompt injection, or unsafe data flow.
- A technically passing PR can still add hard-to-maintain complexity.
- Policy stored in the PR branch can be changed by the same agent it is meant to govern.
- After approval, teams need a clear record of what was checked and who approved it.

**Speaker note:** “Teams want the speed of coding agents, but need control over what they can change and evidence that a human reviewed risky changes.”

## Slide 2 — Proposed Solution & Key Features

### One trusted policy. A clear path from block to approval.

1. **Prevent risky changes:** Shield scans proposed changes for secrets, protected paths, injection patterns, and unsafe flows.
2. **Gate complexity:** RepoBrain checks functions changed by the PR against policy read from the trusted base branch.
3. **Support safe cleanup:** For supported Python changes, the optimizer runs project tests and differential fuzzing; a symbolic prover covers supported pure control-flow rewrites.
4. **Keep a human in control:** A named reviewer must approve and apply a rewrite.
5. **Record the decision:** The audit ledger and downloadable receipt capture the review evidence.

**Speaker note:** “The key is the full workflow: block a risky change, help improve a safe but complex one, require human approval, and preserve evidence.”

## Slide 3 — Technical Approach

### Deterministic checks, scoped verification, verifiable records

- **Policy provenance:** Read policy from the trusted base branch so a PR cannot weaken its own gate.
- **Python verification:** Run the repository’s tests in a scratch copy and compare original and rewritten functions with differential fuzzing. The symbolic prover supports a bounded set of pure control-flow transformations; it does not prove arbitrary Python behavior.
- **Audit evidence:** Hash-chain audit entries, RFC-6962 Merkle inclusion proofs, and decision receipts. Offline receipt verification checks integrity and binding; authenticity requires a separately trusted CI root or HMAC key.
- **Integration:** CLI, GitHub Actions, pre-commit hook, and agent preflight API. Runtime uses Python’s standard library plus PyYAML.

**Speaker note:** “We are explicit about the boundary of each check: tests and fuzzing are evidence, the symbolic prover has a limited domain, and a receipt needs an independent trust anchor to establish authenticity.”

## Slide 4 — Working Proof & Measured Result

### See the complete decision lifecycle

Show one risky PR blocked with its findings, then a safe but complex PR optimized and tested, approved by a named human, and allowed on re-review. Briefly show a clean PR allowed with no findings. Finish by verifying the receipt against a CI-saved root, then changing the receipt verdict and showing verification fail.

**Evidence to show on screen:**

- Risky scenario: blocked verdict and annotated finding locations.
- Remediation: test result, fuzz input count and divergence count, complexity before and after, and the human approval commit.
- Golden path: clean PR allowed with zero blocking findings.
- Receipt: successful verification with the trusted anchor, followed by failure after tampering.

Use only evaluation metrics that match the current benchmark reports; name the dataset and conditions when presenting false-positive results.

**Speaker note:** “This is the product in operation: a risky change is stopped, a safe change gets help, a human approves it, and the evidence can be checked independently.”

## Slide 5 — Future Scope

### Extend the same governance workflow

- Add AST optimization and scoped verification for TypeScript and Go.
- Turn the GitHub webhook prototype into a hosted GitHub App with installation-level policy and check runs.
- Support longer-term public transparency anchoring for audit roots.

**Speaker note:** “The next step is expanding language coverage and deployment options while keeping the same policy provenance, human approval, and verifiable audit model.”

---

**Demo fallback:** If the hosted demo is slow, launch `python -m repobrain server --demo --port 8765` and use the seeded local scenarios. See [the click-by-click demo guide](DEMO.md).
