# Security Policy

RepoBrain is a security and governance layer, so its own attack surface is intentionally kept minimal (zero runtime dependencies beyond PyYAML, no native extensions, strict localhost binding for the review console).

Report vulnerabilities privately through GitHub Security Advisories on this repository. Please do not open public issues for security bugs.

## Execution Model & Optimizer Safety

The Optimizer runs the project's test suite on a temporary scratch copy with a timeout, and the differential fuzzer executes rewritten pure functions in a subprocess with CPU, memory, and file-size resource limits (`rlimit`).

**Important:** There is NO operating-system-level network or filesystem isolation. The Optimizer executes code from the target repository directly in the Python runtime. Therefore, **the Optimizer must only be run on code and tests you would trust to execute in your CI environment.**

## Governance Boundaries (Known Limits)

RepoBrain only governs changes that pass through its entry points:
- CI workflows (e.g. GitHub Actions `repobrain ci`),
- Local pre-commit hooks (`repobrain install-hook`), or
- The agent preflight API (`/api/preflight`).

It does not provide an OS sandbox for an agent that bypasses all three. Direct un-gated pushes to protected branches must be prevented at the repository host level via GitHub branch rulesets.
