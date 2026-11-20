# RepoBrain Final Demo Video Script

**Target runtime:** about 3 minutes 43 seconds (within the required 3–5 minutes).
**Rendered file:** [`docs/demo/repobrain_demo_edited.mp4`](demo/repobrain_demo_edited.mp4)
**Build command:** `.venv/bin/python scripts/produce_submission_video.py`

The producer creates a narrated 1080p video with on-screen captions. Demo metrics are from seeded local runs; they are not general benchmarks. The GitHub PR shot is a captured run from the public repository. If the hosted service is slow, record against the local seeded server.

## Timeline and narration

### 0:00–0:30 — Problem and solution

**Show:** Branded problem and solution card.

> AI coding agents can open useful pull requests quickly. They can also expose credentials, alter the workflow meant to review them, or add code that humans struggle to maintain. Linters often report problems without enforcing a merge decision. RepoBrain applies repository policy from the trusted base, reviews proposed changes, helps simplify supported Python code, and records human approval and audit evidence. I will show a blocked change, a tested rewrite, and how the seeded demo detects tampering.

### 0:33–1:00 — Preflight refusal

**Show:** CLI and MCP preflight responses for a protected workflow edit and unsafe shell command.

> Before a write reaches disk, an agent can ask RepoBrain's preflight interface to check the target path and proposed content. The CLI and MCP server use the same policy decisions. Here, an agent attempts to modify the protected CI workflow and request an unsafe shell command. RepoBrain rejects the requests before the write. The demo uses a placeholder payload; it does not execute a real credential or shell command.

### 1:00–1:34 — Scenario A: blocked risky pull request

**Show:** Seeded blocked verdict, findings list, and annotated workflow diff.

> Scenario A is a seeded risky pull request. RepoBrain blocks three findings: a credential in shop slash config dot py, an edit to the protected CI workflow, and prompt injection hidden in an HTML comment. The finding list gives the rule and file location, while the diff inspector shows the changed lines. These are repeatable demo fixtures, not a claim that every secret scanner or repository will behave the same way.

### 1:34–2:00 — GitHub Actions integration

**Show:** Captured public-repository pull request with the RepoBrain check and findings comment.

> This captured pull request shows the GitHub Actions integration on RepoBrain's public repository. The check reports a blocked verdict and places the findings in the pull request conversation. In deployment, keep the policy on the trusted base branch and require the RepoBrain status check through branch protection. The screenshot is evidence from that run; the local seeded demo remains the fallback if the network is slow.

### 2:00–2:44 — Scenario B: optimizer and human approval

**Show:** Complexity gate, optimizer output, test and fuzz results, complexity deltas, named approval, and allowed review.

> Scenario B is a separate seeded pull request with a Python function that exceeds the configured complexity limits. RepoBrain proposes deterministic AST rewrites, then runs the repository's tests on a scratch copy and differentially checks one thousand generated inputs with zero divergences in this run. Cognitive complexity moves from fifteen to ten, nesting depth from four to three, and the function from sixty nine lines to forty seven. The symbolic prover covers only supported pure control flow, so we present its proof evidence together with tests and fuzzing rather than claim a proof of arbitrary Python behavior. The optimizer waits for Priya Sharma's named approval, recorded in the commit trailer.

### 2:44–3:18 — Audit tamper detection

**Show:** Verified audit status, then simulate an edit to a historical entry and show the invalidated records.

> RepoBrain records decisions in an append-only ledger. In this seeded demo, the HMAC key is local and ephemeral. The verifier reports the chain as valid before the change. We then edit a historical entry in memory. The audit check detects the changed content and invalidates the affected downstream records. For a receipt to establish authenticity outside this local run, the verifier needs a root or HMAC key supplied through a separately trusted channel; the receipt alone is not its own trust anchor.

### 3:18–3:43 — Close

**Show:** Setup instructions, repository link, and local test result.

> The current local suite reports two hundred twenty three passed and one skipped. The repository includes setup instructions, technical documentation, CI configuration, and this seeded demo fallback. Clone RepoBrain, install the listed requirements, and run the demo server to try the same scenarios. The displayed scenario metrics are run-specific, not general benchmarks.

## Demo fallback

```bash
python -m pip install -r requirements.txt
python -m repobrain serve --demo --port 8765
```

Open `http://127.0.0.1:8765/` and use the seeded scenarios. Do not use real credentials in the demo.
