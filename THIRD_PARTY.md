# Third-Party Material & Licenses

RepoBrain is designed to run with minimal dependencies (Python standard library + PyYAML at runtime). Below is a complete inventory of third-party libraries, datasets, and evaluation targets referenced or bundled in this repository.

## 1. Runtime & Development Dependencies

| Component | License | Purpose | Declared In |
|---|---|---|---|
| **Python Standard Library** (`ast`, `hashlib`, `hmac`, `http.server`, `json`, `re`, `subprocess`, `unittest`) | Python Software Foundation License v2 | Core AST metrics, AST rewrites, Shield scanner, HMAC-SHA256 audit log, local HTTP console | Python 3.10+ |
| **PyYAML** (`pyyaml>=6.0`) | MIT License | Policy YAML parsing (`repobrain.yml`) | [`requirements.txt`](requirements.txt), [`pyproject.toml`](pyproject.toml) |
| **pytest** | MIT License | Automated test suite execution | [`requirements-dev.txt`](requirements-dev.txt) |
| **coverage.py** | Apache-2.0 License | Function-level coverage check in optimizer (`min_function_coverage`) | [`requirements-dev.txt`](requirements-dev.txt) |
| **Playwright** | Apache-2.0 License | Headless Chromium UI, accessibility, XSS, and responsive viewport tests | [`requirements-dev.txt`](requirements-dev.txt) |

## 2. Bundled Data Files

| File | Source / License | Usage |
|---|---|---|
| [`repobrain/data/negative_prose.txt`](repobrain/data/negative_prose.txt) | Excerpts from Python Standard Library documentation comments and docstrings (Python Software Foundation License v2) | Used exclusively as negative (benign) prose samples during `repobrain ml-eval` training and false-positive testing |
| [`repobrain/data/injection_corpus.json`](repobrain/data/injection_corpus.json) | Team-written synthetic prompt-injection and benign sample corpus (MIT) | Training and 5-fold cross-validation of the warn-only Naive Bayes guard (`repobrain/mlguard.py`) |
| `PY_POPULAR` & `NPM_POPULAR` in [`repobrain/deps.py`](repobrain/deps.py) | Team-curated list of 289 common package names (198 PyPI, 91 npm) | Baseline for Damerau-Levenshtein typosquatting checks |

## 3. Locally Evaluated Open-Source Targets (`docs/SHIELD_EVAL.md`)

To measure false-positive rates on benign production code (documented in [`docs/SHIELD_EVAL.md`](docs/SHIELD_EVAL.md)), Shield was run locally over 124 files (51,781 LoC) from installed standard library modules and OSS packages (not redistributed in this repository):
- CPython stdlib (`json`, `email`, `http`, `logging`, `urllib`) — PSF License v2
- `PyYAML` — MIT License
- `coverage.py` — Apache-2.0 License
- `pluggy` — MIT License
- `pytest` — MIT License

## 4. Published Placeholder Test Strings

Test fixtures and demo scenarios include AWS's documented example key (`AKIAIOSFODNN7EXAMPLE`) and synthetic format-matching placeholder strings (`ghp_...`, `sk-...`) solely to verify secret masking and Shield rule detection. No live credentials or private keys are present in this repository.

