# Changelog

All notable changes to the RepoBrain console and governance platform.

## [UI/UX Mission Control Overhaul] - 2026-10-29

### Added
- **Design System ("Flight Recorder / Mission Control")**:
  - Full design tokens with dark/light theme support (`data-theme="dark"` / `"light"`), CSS variables for cool slate ramp, precision cyan/cobalt brand accent, and 4 high-contrast semantic signals (pass/warn/block/ai).
  - Clean system monospace & sans typography with tabular numerals for hashes and metrics.
  - Zero external CDN fonts, scripts, or styles to maintain strict zero-dependency CSP compliance.
- **Asymmetric Layout & Telemetry Rail**:
  - Persistent 290px left telemetry rail with live 5-stage pipeline stepper (Shield → Complexity Gate → Optimizer → Human Approval → Merge Gate).
  - Diagnostic tools navigation in the rail (PR Review, Optimizer, Shield, Explainer, Audit, Policy).
  - Responsive mobile slide-over drawer and compact layouts down to 360px viewport.
- **Verdict Hero**:
  - Dominant merge-gate state (`ALLOWED` / `CHANGES REQUIRED` / `BLOCKED`) with color-coded status badges and prominent primary next action.
  - 4-gate status checklist (Shield & Secrets, Complexity Gate, Safety Net Tests, Human Approval) with single-line diagnostic reasons.
- **PR Map & Interactive File Diff Inspector**:
  - PR files map with AI-authorship badges (robot vs human icon), status chips (`ADD`, `MOD`, `DEL`), and risk level indicator.
  - Click-to-inspect unified diff viewer with line numbers and hand-written syntax highlighting for Python/YAML/Markdown.
  - Inline Shield rule annotations (`blocked-path`, `secret`, `prompt-injection`) directly beneath offending lines with masked evidence.
  - Token-protected read-only `/api/diff?path=...` endpoint with path traversal defense (`normpath`, `commonpath`, bounds checks) and size capping.
- **Complexity Visualization**:
  - Function complexity rendered as horizontal progress bars with policy threshold marker lines for Cyclomatic (limit 10), Cognitive (limit 15), and Depth (limit 3).
  - Optimizer view with before/after paired bars and large monospace delta values (`Δ -5`).
- **Cryptographic Audit Chain**:
  - Vertical timeline visualizing SHA-256 hash chaining between consecutive blocks (`prev_hash` → `hash`).
  - Animated sweep verification of block integrity.
  - Visual demonstration of tamper detection with broken downstream link highlighting.
- **Command Palette & Keyboard Shortcuts**:
  - `Cmd+K` / `Ctrl+K` command palette for instant scenario switching, reviews, optimizer runs, and audits.
  - Keyboard navigation (`1-6` for tabs, `O` for optimizer, `A` for approver input, `Esc` for modals, `?` for shortcuts sheet).
- **Interactive Guided Tour (Presenter Mode)**:
  - Step-by-step walkthrough covering Risky AI PR, annotated diffs, Complexity Gate, AST rewrite, human sign-off, and cryptographic audit.
- **Testing & Security**:
  - New pytest for `/api/diff` path-traversal attacks and boundary cases (`tests/test_server.py`).
  - New Playwright automated XSS safety verification test (`tests/test_xss_safety.py`).
  - Automated screenshot capture suite (`scripts/capture_ui_screenshots.py`) for desktop (1440x900) and mobile (390x844).
