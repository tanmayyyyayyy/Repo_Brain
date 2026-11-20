# RepoBrain Final Demo Video Script

**Target runtime:** about 4 minutes 05 seconds (within the required 3–5 minutes).
**Rendered file:** [`docs/demo/repobrain_demo_edited.mp4`](demo/repobrain_demo_edited.mp4)
**Build command:** `.venv/bin/python scripts/produce_submission_video.py`

The producer creates a narrated 1080p video with on-screen captions. Demo metrics are from seeded local runs; they are not general benchmarks. The GitHub PR shot is a captured run from the public repository. If the hosted service is slow, record against the local seeded server.

## Team Credits (CodeQuest 2026)
- **Tanmay Jain** — Systems & Security Architect (Core Engine, Taint Analysis, Prover & Merkle Audit)
- **Saanchi Jain** — AI Governance & Product Lead (Policy Models, Mission Control UI/UX, Compliance)

## Timeline and narration

### 0:00–0:26 — Team & Project Introduction (CodeQuest 2026)

**Show:** Branded CodeQuest 2026 title card with team members Tanmay Jain and Saanchi Jain and their respective roles.

> Welcome to the final build showcase for RepoBrain, built for CodeQuest 2026 by Tanmay Jain, Systems and Security Architect, and Saanchi Jain, AI Governance and Product Lead. RepoBrain is a vendor-neutral governance platform that stops autonomous AI agents from introducing silent vulnerabilities, complexity debt, or untracked changes into production repositories.

### 0:26–0:58 — Problem and solution

**Show:** Branded problem and solution card.

> AI coding agents can open useful pull requests quickly. They can also expose credentials, alter the workflow meant to review them, or add code that humans struggle to maintain. Linters often report problems without enforcing a merge decision. RepoBrain applies repository policy from the trusted base, reviews proposed changes, helps simplify supported Python code, and records human approval and audit evidence. I will show a blocked change, a tested rewrite, and how the seeded demo detects tampering.

### 0:58–1:25 — Preflight refusal

**Show:** CLI and MCP preflight responses for a protected workflow edit and unsafe shell command.

> Before a write reaches disk, an agent can ask RepoBrain's preflight interface to check the target path and proposed content. The CLI and MCP server use the same policy decisions. Here, an agent attempts to modify the protected CI workflow and request an unsafe shell command. RepoBrain rejects the requests before the write. The demo uses a placeholder payload; it does not execute a real credential or shell command.

### 1:25–1:59 — Scenario A: blocked risky pull request

**Show:** Seeded blocked verdict, findings list, and annotated workflow diff.

> Scenario A is a seeded risky pull request. RepoBrain blocks three findings: a credential in shop slash config dot py, an edit to the protected CI workflow, and prompt injection hidden in an HTML comment. The finding list gives the rule and file location, while the diff inspector shows the changed lines. These are repeatable demo fixtures, not a claim that every secret scanner or repository will behave the same way.

### 1:59–2:25 — GitHub Actions integration

**Show:** Captured public-repository pull request with the RepoBrain check and findings comment.

> This captured pull request shows the GitHub Actions integration on RepoBrain's public repository. The check reports a blocked verdict and places the findings in the pull request conversation. In deployment, keep the policy on the trusted base branch and require the RepoBrain status check through branch protection. The screenshot is evidence from that run; the local seeded demo remains the fallback if the network is slow.

### 2:25–3:15 — Scenario B: optimizer and human approval

**Show:** Complexity gate, optimizer output, test and fuzz results, complexity deltas, named approval, and allowed review.

> Scenario B is a separate seeded pull request with a Python function that exceeds the configured complexity limits. RepoBrain proposes deterministic AST rewrites, then runs the repository's targeted tests on a scratch copy and differentially checks one thousand generated inputs with zero divergences in this run. Cognitive complexity moves from fifteen to ten, nesting depth from four to three, and the function from sixty nine lines to forty seven. The symbolic prover covers only supported pure control flow, so we present its proof evidence together with tests and fuzzing rather than claim a proof of arbitrary Python behavior. The optimizer waits for Priya Sharma's named approval, recorded in the commit trailer.

### 3:15–3:49 — Audit tamper detection

**Show:** Verified audit status, then simulate an edit to a historical entry and show the invalidated records.

> RepoBrain records decisions in an append-only ledger. In this seeded demo, the HMAC key is local and ephemeral. The verifier reports the chain as valid before the change. We then edit a historical entry in memory. The audit check detects the changed content and invalidates the affected downstream records. For a receipt to establish authenticity outside this local run, the verifier needs a root or HMAC key supplied through a separately trusted channel; the receipt alone is not its own trust anchor.

### 3:49–4:08 — Team Wrap-Up & Closing

**Show:** Closing card with team members Tanmay Jain and Saanchi Jain, verification stats, open-source MIT license, and repository URL.

> RepoBrain bridges the critical gap between fast autonomous coding agents and rigorous enterprise compliance. On behalf of team members Tanmay Jain and Saanchi Jain, thank you for evaluating RepoBrain for the CodeQuest 2026 Final Build Showcase. The full open-source repository, technical documentation, and test suite are available on GitHub.

## Demo fallback

```bash
python -m pip install -r requirements.txt
python -m repobrain serve --demo --port 8765
```

Open `http://127.0.0.1:8765/` and use the seeded scenarios. Do not use real credentials in the demo.
