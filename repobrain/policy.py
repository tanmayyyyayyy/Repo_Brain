"""Policy loading and validation. The policy is read from the TRUSTED base ref
when possible, so an AI-authored PR cannot loosen its own rules."""
import fnmatch
import pathlib
import re
import subprocess

import yaml

DEFAULT = {
    "version": 1,
    "optimize": "required",          # required | advisory | off
    "approval": "human",
    "ai_changes": "log_all",
    "complexity_threshold": 10,      # cyclomatic, per touched function
    "max_complexity": 10,            # alias for complexity_threshold
    "max_depth": 3,                  # nesting depth
    "max_cognitive": 15,             # cognitive complexity
    "max_files_per_run": 15,
    "max_files_changed": 25,         # alias for max_files_per_run
    "require_tests": True,           # optimizer output must pass tests to be applicable
    "test_command": None,            # default: python -m pytest -q -x
    "test_timeout": 180,
    "blocked": [".github/workflows/", "secrets/", "credentials/", ".env", ".env.*",
                "*.pem", "id_rsa", "repobrain.yml"],
    "blocked_for": "ai",             # ai | all  (humans get a warning when "ai")
    "review_required": ["requirements.txt", "package.json", "pyproject.toml",
                        "Dockerfile", "package-lock.json"],
    "ai_actors": ["copilot", "claude", "codex", "cursor", "devin", "gemini", "aider",
                  "openai", "chatgpt", "antigravity", "bot", "agent"],
    "allow_llm": False,              # optimizer may send function code to an LLM API
    "min_function_coverage": None,   # optional % threshold for test execution of rewritten functions
    "format_command": None,          # optional command to format rewritten code (e.g. "black -q -")
    "remove_unused_imports": True,
    "allow_comment_loss": False,
    "preserve_comments": True,       # never rewrite a function that contains comments
    "languages": ["python"],
    "fuzz": True,                    # differential fuzzing of rewritten functions
    "ml_guard": True,                # learned prompt-injection classifier
    "dependency_guard": True,        # typosquat / dependency-confusion checks
    "ignore": [],                    # paths Shield will not scan
}

_TYPES = {
    "version": int, "optimize": str, "approval": str, "ai_changes": str,
    "complexity_threshold": int, "max_complexity": int, "max_depth": int,
    "max_cognitive": int, "max_files_per_run": int, "max_files_changed": int,
    "require_tests": bool, "test_timeout": int, "blocked": list, "blocked_for": str,
    "review_required": list, "ai_actors": list, "allow_llm": bool,
    "remove_unused_imports": bool, "allow_comment_loss": bool, "preserve_comments": bool,
    "languages": list, "fuzz": bool, "ml_guard": bool, "dependency_guard": bool, "ignore": list,
}

_ENUMS = {
    "optimize": {"required", "advisory", "off"},
    "approval": {"human"},
    "blocked_for": {"ai", "all"},
    "ai_changes": {"log_all"},
}


class PolicyError(ValueError):
    pass


class PolicyResult(dict):
    """A dictionary that can also be unpacked as (policy_dict, problems_list)."""
    def __iter__(self):
        yield self
        yield self.get("_problems", [])


def validate(raw):
    """Validate policy mapping and return (clean_policy, problems)."""
    problems = []
    pol = PolicyResult(DEFAULT)
    if raw is None:
        return pol, problems
    if not isinstance(raw, dict):
        problems.append({"level": "error", "key": "*", "msg": "policy must be a YAML mapping (key: value)"})
        pol["_problems"] = problems
        return pol, problems

    warnings = []
    for k, v in raw.items():
        if k not in DEFAULT:
            warnings.append(f"unknown key ignored: {k}")
            problems.append({"level": "warn", "key": k, "msg": f"unknown key '{k}' (ignored)"})
            continue

        if k == "test_command":
            if v is not None and not isinstance(v, (str, list)):
                raise PolicyError("test_command must be a string or list")
        elif k == "min_function_coverage":
            if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool)):
                raise PolicyError("min_function_coverage must be a number or null")
        elif k == "format_command":
            if v is not None and not isinstance(v, str):
                raise PolicyError("format_command must be a string or null")
        elif k == "max_complexity":
            if isinstance(v, bool) or not isinstance(v, int) or v < 1:
                problems.append({"level": "error", "key": k, "msg": f"'{k}' must be an integer >= 1"})
                continue
        elif not isinstance(v, _TYPES[k]) or (_TYPES[k] is int and isinstance(v, bool)):
            raise PolicyError(f"{k} must be of type {_TYPES[k].__name__}")

        if k in _ENUMS and v not in _ENUMS[k]:
            raise PolicyError(f"{k} must be one of {sorted(_ENUMS[k])}")
        if _TYPES.get(k) is list and not all(isinstance(x, str) for x in v):
            raise PolicyError(f"{k} must be a list of strings")

        pol[k] = v
        if k == "max_complexity":
            pol["complexity_threshold"] = v
        elif k == "complexity_threshold":
            pol["max_complexity"] = v
        elif k == "max_files_changed":
            pol["max_files_per_run"] = v
        elif k == "max_files_per_run":
            pol["max_files_changed"] = v

    pol["_warnings"] = warnings
    pol["_problems"] = problems
    return pol, problems


def parse(text):
    try:
        raw = yaml.safe_load(text) if text and text.strip() else {}
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" (line {mark.line + 1})" if mark else ""
        raise PolicyError(f"repobrain.yml is not valid YAML{where}: {e}")
    if raw is not None and not isinstance(raw, dict):
        raise PolicyError("repobrain.yml must be a mapping of keys to values")
    pol, _ = validate(raw)
    return pol


def load(path="repobrain.yml"):
    p = pathlib.Path(path)
    if not p.exists():
        pol = PolicyResult(DEFAULT)
        pol["_warnings"] = ["no repobrain.yml found - using defaults"]
        pol["_source"] = "built-in defaults"
        return pol
    try:
        with open(p, encoding="utf-8") as f:
            return parse(f.read())
    except FileNotFoundError:
        pol = PolicyResult(DEFAULT)
        pol["_warnings"] = ["no repobrain.yml found - using defaults"]
        pol["_source"] = "built-in defaults"
        return pol


def load_for(root, base=None):
    """Prefer the policy file as it exists on the trusted base ref."""
    if base:
        r = subprocess.run(["git", "show", f"{base}:repobrain.yml"], cwd=root,
                           capture_output=True, text=True)
        if r.returncode == 0:
            pol = parse(r.stdout)
            pol["_source"] = f"{base}:repobrain.yml (trusted base)"
            return pol
    try:
        pol = load(f"{root}/repobrain.yml")
        pol["_source"] = "working tree repobrain.yml"
        return pol
    except FileNotFoundError:
        pol = PolicyResult(DEFAULT)
        pol["_warnings"] = ["no repobrain.yml found - using defaults"]
        pol["_source"] = "built-in defaults"
        return pol


def is_ai(text, policy):
    low = text.lower()
    toks = set(re.split(r"[^a-z0-9]+", low))
    actors = policy.get("ai_actors") if hasattr(policy, "get") else None
    if actors is None:
        actors = DEFAULT.get("ai_actors", [])
    for frag in actors:
        f = frag.lower()
        if (f.isalnum() and f in toks) or (not f.isalnum() and f in low):
            return True
    return False


def match_path(path, patterns):
    """Return the first pattern that matches, else None."""
    base = path.rsplit("/", 1)[-1]
    for pat in patterns:
        if pat.endswith("/"):
            if path.startswith(pat) or ("/" + pat) in ("/" + path):
                return pat
        elif path == pat or base == pat or fnmatch.fnmatch(base, pat) or fnmatch.fnmatch(path, pat):
            return pat
    return None
