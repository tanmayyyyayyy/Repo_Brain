# RepoBrain Video Demo Script (2:30 Exact Presentation)

> **Theme**: Flight recorder & mission control for repositories touched by AI coding agents.
> **Length**: ~2 minutes 05 seconds (`docs/demo/repobrain_demo_edited.mp4`).
> **Screen Setup**: Full-frame 1600×900 dark mode scaled cleanly to 1920×1080 60fps with narrated AAC audio and large lower-third captions.

---

## ⏱️ Video Timeline & Cues

### [0:00 - 0:30] Hook & Mission Control
- **On Screen**: Show RepoBrain web console hero section. Point to persistent left rail with 5-stage pipeline stepper (Shield -> Gate -> Optimizer -> Human -> Audit).
- **Spoken Audio**:
  > "Autonomous coding agents like Claude Code, Cursor, and Devin are generating massive pull requests. But engineering teams face a dilemma: either spend hours reviewing AI spaghetti code, or risk accidental credential leaks, corrupted CI workflows, and prompt injection attacks.
  >
  > This is **RepoBrain**: an open-source, vendor-neutral governance, cleanup, and audit layer for repositories that AI agents write to. It doesn't write code—it decides what agents may touch, cleans up what they write using your existing tests as the judge, and keeps cryptographic proof of every decision."

---

### [0:30 - 1:10] Scenario A: The Risky AI PR (Shield Defense)
- **Action**: Click `Scenario A` button (or press `1`). Verdict hero updates to **BLOCKED**. Click `.github/workflows/ci.yml` in the PR map to open the unified diff with red inline annotations.
- **Spoken Audio**:
  > "Here in Scenario A, an AI agent attempted to update configuration. Shield immediately flags three blocking violations:
  > First, a hardcoded AWS key in `shop/config.py`, automatically masked.
  > Second, an unauthorized modification to our protected deployment workflow in `.github/workflows/ci.yml`.
  > And third, an indirect prompt injection hidden in markdown instructing future agents to exfiltrate secrets.
  >
  > Notice the policy source: `origin/main`. Even if an AI agent edits `repobrain.yml` in its PR branch, RepoBrain reads policy strictly from the trusted base ref. The agent cannot loosen its own rules."

---

### [1:10 - 1:55] Scenario B: The Messy AI PR & Verified AST Optimizer
- **Action**: Click `Scenario B` (or press `2`). Verdict updates to yellow **CHANGES REQUIRED**. Point out `discount_for` exceeding nesting depth (4 > 3) and cognitive complexity (15 > 10). Click **Optimize** button.
- **Spoken Audio**:
  > "Now let's switch to Scenario B. The code is secure, but it's classic AI slop: deep nesting, redundant else-branches, and high cognitive complexity.
  >
  > Instead of sending code back for another hallucinatory review loop, we click **Optimize**.
  > On a temporary scratch copy with resource limits, RepoBrain applies semantic-preserving AST rewrites, runs our unit tests (`26 passed`), and verifies behavior using differential fuzzing.
  >
  > Cognitive complexity drops from 15 to 10; nesting depth drops from 4 to 3. Inline comments and line endings are strictly preserved.
  > RepoBrain never merges on its own: a named human, Priya Sharma, approves the proposal, committing it with an `Approved-by:` trailer. Re-running the review now flips the verdict to **ALLOWED**."

---

### [1:55 - 2:30] Cryptographic Audit Trail & Tamper Detection
- **Action**: Click **Audit** tab (or press `5`). Point out the vertical timeline blockchain ledger and the `HMAC-signed` status pill. Click **Simulate tampering**.
- **Spoken Audio**:
  > "Underneath every check is an append-only JSONL audit ledger. Every review, waiver, and human approval is anchored in a SHA-256 hash chain and HMAC-signed with `REPOBRAIN_AUDIT_KEY`.
  >
  > If someone tampers with historical block #8 in memory—even if they recompute the SHA-256 hashes—the cryptographic HMAC signature fails immediately, invalidating every downstream block in the chain.
  >
  > With zero heavy runtime dependencies, 124 passing automated tests, and a measured 0.03% false-positive rate across 4,000 stdlib prose samples, RepoBrain gives engineering leaders complete confidence to adopt AI coding agents at scale. Thank you."

---

## 🎤 Judge Q&A Cheat Sheet

1. **"How accurate is your prompt injection detector?"**
   > *Answer*: "We believe in honest metrics: our zero-dependency Naive Bayes classifier was evaluated on a 242-sample team-written corpus via 5-fold cross-validation, achieving 0.938 precision, 0.625 recall, and 0.75 F1 (0.77 hybrid). On 4,000 benign Python standard library comments, its measured false-positive rate is 0.03%. Crucially, rigid deterministic rules can block; the ML model only warns and elevates risk—it never blocks on its own."

2. **"Does the optimizer send my proprietary code to OpenAI or Anthropic?"**
   > *Answer*: "No. By default, RepoBrain's AST optimizer runs 100% locally on your machine or CI runner using standard library Python AST rules. External LLM APIs are only engaged if you explicitly set `allow_llm: true` and configure `GROQ_API_KEY` or `ANTHROPIC_API_KEY` for high-complexity Scenario C function refactoring."

3. **"Can an attacker bypass the audit log by rewriting historical entries?"**
   > *Answer*: "In an unsigned chain, an attacker could recompute SHA-256 hashes. That's why RepoBrain supports HMAC-SHA256 signing (`REPOBRAIN_AUDIT_KEY`) and CI head anchoring (`--anchor-file` and `--expect <seq>`). Modifying an entry invalidates the HMAC signature, and truncating tail entries fails the anchored head check in GitHub Actions."

4. **"How does this integrate into our workflow today?"**
   > *Answer*: "RepoBrain runs as a GitHub Action (`action.yml`), a CLI tool (`repobrain review`), a pre-commit hook (`.pre-commit-hooks.yaml`), an MCP server for any agent (`integrations/mcp_server.py`), and a Claude Code pre-execution tool hook (`integrations/claude-code/`)."
