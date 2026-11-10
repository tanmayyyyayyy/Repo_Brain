# Architecture

## Flow of a change
1. **Entry points** (all share one engine and one policy): GitHub Action (`repobrain ci`), local pre-commit hook (`repobrain hook-check`), local Mission Control console (`repobrain serve`), MCP server (`integrations/mcp_server.py`), and agent **preflight** API (`/api/preflight`, `repobrain preflight`).
2. **Shield** scans only the *lines a change added* (git hunks) so old debt does not drown new risk. Layers: protected paths → secret formats (plus string concatenation normalization and base64 decoding) + Shannon entropy → injection rules → learned Naive Bayes guard (warn-only, needs directive wording) → hidden Unicode → risky commands (shell & PowerShell) → dependency typosquats (Damerau-Levenshtein vs curated 289 popular PyPI/npm packages, homoglyphs, URL/VCS installs).
3. **Optimizer** measures cyclomatic and cognitive complexity and nesting depth on touched Python functions, applies behavior-preserving AST rewrites **per function** (flatten else-after-return across all-terminating branches, collapse boolean returns, loop+append → comprehension, guard clauses, `== None` → `is None`, remove unused imports), then:
   * runs the project's tests on a scratch copy with CPU/memory resource limits (`pytest` if installed, else `repobrain.minitest`, where unsupported fixtures are skipped rather than treated as passing);
   * **differentially fuzzes** each rewritten pure-looking function in a resource-limited subprocess (inputs mined from the function's own constants plus type-confused values; compares results, exception types, and argument mutation).
   Any failure or divergence discards the proposal. Nothing is pushed; a named human approves.
4. **Audit** appends a JSONL record whose SHA-256 hash commits to the previous record (with HMAC-SHA256 signing when `REPOBRAIN_AUDIT_KEY` is set, and CI head anchoring via `--anchor-file` / `--expect`). Approvals are bound to a commit SHA.
5. **Merge Risk Index** (0–100) is a transparent weighted sum with its factors shown, deliberately *not* a trained black-box score.

## Optional LLM Tier (vendor-neutral)
Supports Groq (`GROQ_API_KEY`, default model `openai/gpt-oss-120b`) and Anthropic (`ANTHROPIC_API_KEY`, model `claude-sonnet-5-5`), selectable via `REPOBRAIN_LLM_PROVIDER` in [`repobrain/llm.py`](../repobrain/llm.py). Used only when `allow_llm: true` and explicitly enabled (`--ai`) to refine functions that remain over threshold or summarize unknown CI failure logs. AI outputs are scanned by Shield and must pass the same tests and differential fuzzing.

## Mission Control UI (`repobrain/web/index.html`)
Zero-dependency, strict-CSP single-file Mission Control console served over `127.0.0.1` with per-run bearer token authentication, `Host` allowlisting, CSRF guards, and HTML escaping. Features a persistent 290px 5-stage governance pipeline rail, interactive unified diff viewer with single-pass tokenization and inline Shield annotations, horizontal complexity delta meters, interactive Shield & Explainer playgrounds, HMAC audit chain verifier with dynamic tamper simulation, dark/light WCAG 2.1 AA themes, presenter mode, and a `Cmd+K` command palette.
