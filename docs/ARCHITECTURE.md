# Architecture

## Flow of a change
1. **Entry points** (all share one engine and one policy): GitHub Action (`repobrain ci`), local pre-commit hook, the console, and the agent **preflight** API.
2. **Shield** scans only the *lines a change added* (git hunks) so old debt does not drown new risk. Layers: protected paths → secret formats + Shannon entropy → injection rules → learned guard (warn-only, needs directive wording) → hidden Unicode → risky commands → dependency typosquats (Damerau-Levenshtein vs popular package lists, homoglyphs, URL/VCS installs, custom indexes).
3. **Optimizer** measures cyclomatic and cognitive complexity and nesting, applies behaviour-preserving rewrites **per function** (flatten else-after-return across all-terminating branches, collapse boolean returns, loop+append → comprehension, merge nested ifs, `== None` → `is None`, remove unused imports), then:
   * runs the project's tests on a scratch copy (pytest if installed, else the built-in runner; unsupported fixtures are *skipped*, never counted as passes);
   * **differentially fuzzes** each rewritten pure-looking function in a resource-limited subprocess (inputs mined from the function's own constants, plus type-confused values; compares results, exception types and argument mutation).
   Any failure discards the proposal. Nothing is pushed; a human approves.
4. **Audit** appends a record whose hash commits to the previous one (optional HMAC with `REPOBRAIN_AUDIT_KEY`). Approvals are bound to a commit SHA.
5. **Merge Risk Index** (0–100) is a transparent weighted sum with its factors shown, deliberately *not* a trained model.

## Developer agent
`repobrain/agent.py` orchestrates five repetitive workflows: **triage** (priority P0–P3, routing, risk factors), **review** (Shield findings + complexity gate + missing-test/large-diff comments + the verified Optimizer proposal), **diagnose** (the Failure Explainer correlated with changed files), **test** (the project's tests in a scratch copy, with failures mapped to changed files) and **incident** (severity, commit timeline, suspect change, containment and escalation from an alert). `run` executes all five and writes `agent/latest.json` + `agent/latest.md` under the audit home. The CLI is `python -m repobrain agent`, the console has a Developer agent tab, and the API is `POST /api/agent` / `GET /api/agent?fmt=md`.

The agent is read-only by construction: no workflow writes, reverts, merges or pages. Each appends an `agent:<workflow>` record to the same hash chain, and anything that would change the repository still requires human approval. Rules produce verdicts; an optional LLM only adds prose, never a decision.

## Optional LLM (vendor-neutral)
`REPOBRAIN_LLM=anthropic|openai|ollama` (+ `REPOBRAIN_LLM_URL`, `REPOBRAIN_LLM_MODEL`). Used to refine functions that still break policy and to explain unknown logs. Ollama keeps everything local. AI output goes through the same tests + fuzzing.

## The 3D scene
`web/scene.js` renders ~90k points (adaptive down on slow GPUs) in one fixed canvas, drawing into the *current stage rectangle* via `gl.viewport`, so the stage can shrink from full-screen to a framed window to the console slot with no re-allocation. Per-particle morph between a procedural brain (`aA`) and a constellation built from live file data (`aB`); the vertex shader adds flow-field turbulence (driven by repo complexity), cursor swirl, a dissolve for the dive, and shock-wave pulses on events.
