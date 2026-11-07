"""Failure Explainer: logs -> plain-language cause + fix. Deterministic rules first, optional LLM second."""
import re

from . import deps, llm
from .shield import SECRET_PATTERNS

# import name -> PyPI package name, for the cases where they differ
PIP = {
    "yaml": "pyyaml", "cv2": "opencv-python", "PIL": "pillow", "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4", "dateutil": "python-dateutil", "jwt": "pyjwt",
    "dotenv": "python-dotenv", "OpenSSL": "pyopenssl", "Crypto": "pycryptodome",
    "MySQLdb": "mysqlclient", "serial": "pyserial", "git": "gitpython",
    "magic": "python-magic", "skimage": "scikit-image"
}

RULES = [
    (r"ModuleNotFoundError: No module named ['\"]?([\w.\-]+)", "Missing Python package",
     "The code imports '{0}' but it is not installed in this environment.",
     "Add '{0}' to requirements.txt (or pyproject) and reinstall.", "dependency"),
    (r"ImportError: cannot import name ['\"]?(\w+)", "Wrong or missing import",
     "'{0}' does not exist in the module being imported (renamed, removed, or circular import).",
     "Check the module for '{0}', fix the name, or break the import cycle.", "dependency"),
    (r"Cannot find module ['\"]([^'\"]+)", "Missing Node module",
     "Node cannot resolve '{0}'.", "Run `npm install {0}` (or fix the relative path).", "dependency"),
    (r"npm ERR! (?:code )?ERESOLVE", "npm dependency conflict",
     "Two packages need incompatible versions of the same dependency.",
     "Align versions, or as a last resort use `npm install --legacy-peer-deps`.", "dependency"),
    (r"AttributeError: 'NoneType' object has no attribute ['\"]?(\w+)", "Value was None",
     "Something returned None and the code then used '.{0}' on it.",
     "Find the call that returned None; add a None check or fix the missing return.", "code"),
    (r"AttributeError: (.+)", "Missing attribute",
     "Code used something that does not exist: {0}.",
     "Check for a None value or a renamed attribute.", "code"),
    (r"KeyError: ['\"]?([^'\"\n]+)", "Missing dictionary key",
     "The code read key '{0}' that is not in the dict.", "Use .get('{0}') or validate the input first.", "code"),
    (r"NameError: name ['\"]?(\w+)['\"]? is not defined", "Undefined name",
     "'{0}' is used before it is defined or never imported.", "Define or import '{0}'; check for typos.", "code"),
    (r"(?:Indentation|Syntax)Error: ([^\n]+)", "Syntax problem",
     "Python could not parse the file: {0}.", "Fix the line shown above (brackets, colons, indentation).", "code"),
    (r"TypeError: ([^\n]+)", "Wrong type or arguments", "A value had the wrong type: {0}.",
     "Check argument counts/types at the call site shown in the traceback.", "code"),
    (r"ZeroDivisionError", "Division by zero", "A denominator was 0.", "Guard the division or validate input.", "code"),
    (r"FileNotFoundError: .*?['\"]([^'\"]+)['\"]", "File not found",
     "'{0}' does not exist where the code looks for it.", "Check the path / working directory / that the file is committed.", "infra"),
    (r"PermissionError|Permission denied", "Permission denied", "The process may not read/write that path.",
     "Fix file permissions or run as the right user.", "infra"),
    (r"(?:ConnectionRefusedError|ECONNREFUSED|Connection (?:refused|timed out|reset)|Name or service not known)", "Service not reachable",
     "Nothing is listening at the address (service down, wrong host/port, not started in CI).",
     "Start the dependency (docker service / mock) or fix host and port.", "infra"),
    (r"(?:Timeout|timed out|ETIMEDOUT|TimeoutError|deadline exceeded)", "Timeout", "An operation took longer than its limit.",
     "Check network/service health; raise the timeout only after finding the slow step.", "infra"),
    (r"(?:Process completed with exit code 137|Killed|OOMKilled|out of memory|MemoryError|JavaScript heap out of memory)", "Out of memory",
     "The process was killed for using too much memory.", "Reduce memory use (batching) or give the job more memory.", "infra"),
    (r"no space left on device", "Disk full", "The runner/container ran out of disk.", "Clean caches/artifacts or use a larger runner.", "infra"),
    (r"CONFLICT \(content\)|<<<<<<< ", "Merge conflict", "Unresolved merge conflict markers are in the code.",
     "Resolve the conflict markers, then commit.", "code"),
    (r"AssertionError", "Test assertion failed", "A test's expected value did not match the actual value.",
     "Compare 'expected' vs 'actual' in the output; fix the code or the stale test (not both blindly).", "code"),
    (r"(?:fatal: )?[Aa]uthentication failed|401 Unauthorized|403 Forbidden", "Authentication failed",
     "Credentials were rejected.", "Refresh the token/secret and confirm it has the right scopes.", "infra"),
]

LOC_PY = re.compile(r'File "([^"]+)", line (\d+)')
LOC_PYTEST = re.compile(r"^([\w./\\-]+\.py):(\d+): ", re.M)
LOC_JS = re.compile(r"at (?:.*? \()?([\w./\\-]+\.[jt]sx?):(\d+):\d+")
FAILED = re.compile(r"^FAILED ([\w./\\:\[\]-]+)(?: - (.*))?$", re.M)


def redact(text):
    for _, rx in SECRET_PATTERNS:
        text = rx.sub("[REDACTED]", text)
    return text


def _confidence(n_matches, has_loc):
    return "high" if n_matches and has_loc else ("medium" if n_matches else "low")


def explain(log, ask=None):
    text = redact(log)
    matches = []
    mods = []

    for item in RULES:
        rx, title, cause, fix = item[0], item[1], item[2], item[3]
        cat = item[4] if len(item) > 4 else "general"
        m = re.search(rx, log)
        if m:
            g = m.groups() or ("",)
            g_padded = list(g) + [""] * 4
            m_dict = {
                "title": title,
                "category": title,
                "cause": cause.format(*g_padded).replace(" .", "."),
                "fix": fix.format(*g_padded),
                "evidence": m.group(0)[:160],
                "kind": cat
            }
            matches.append(m_dict)
            if "ModuleNotFoundError" in rx:
                mods.append(m.group(1).split(".")[0])

    loc = None
    loc_str = None
    for rx in (LOC_PYTEST, LOC_PY, LOC_JS):
        found = rx.findall(log)
        if found:
            loc = {"file": found[-1][0], "line": int(found[-1][1])}
            loc_str = f"{found[-1][0]}:{found[-1][1]}"
            break

    failed = [{"test": a, "message": (b or "")[:160]} for a, b in FAILED.findall(log)]
    patches = []
    for mod in dict.fromkeys(mods):
        pkg = PIP.get(mod, mod.replace("_", "-"))
        patch = {
            "file": "requirements.txt",
            "kind": "append-line",
            "line": pkg,
            "diff": f"--- a/requirements.txt\n+++ b/requirements.txt\n@@\n+{pkg}\n",
            "note": f"import '{mod}' -> PyPI package '{pkg}'"
        }
        t = deps.typosquat_of(pkg, deps.PY_POPULAR)
        if t:
            patch["warning"] = f"'{pkg}' resembles the popular package '{t[0]}': verify it exists and is the one you intend before installing"
        patches.append(patch)

    confidence = _confidence(len(matches), bool(loc))
    res = {
        "matches": matches,
        "findings": matches,
        "location": loc,
        "location_str": loc_str,
        "loc": loc,
        "failed_tests": [f["test"] for f in failed] if failed else [],
        "failures": failed,
        "patches": patches,
        "confidence": confidence,
        "summary": matches[0]["title"] if matches else "No known failure pattern matched",
        "lines": len(log.splitlines()),
        "llm": None,
        "ai_explanation": None
    }

    if ask is True:
        if llm.available():
            try:
                explanation = llm.ask("Explain this CI failure in 3 short sentences and give the fix:\n" + text[-6000:],
                                      system="You are a clear build failure explainer.")
                res["llm"] = explanation
                res["ai_explanation"] = explanation
            except Exception as e:
                res["llm"] = f"(LLM unavailable: {e})"
                res["ai_explanation"] = res["llm"]
    elif callable(ask):
        try:
            explanation = ask("Explain this CI failure in 3 short sentences for a developer, then give the one "
                              "most likely fix:\n\n" + text[-6000:], "Be concrete. No preamble.")
            res["llm"] = explanation
            res["ai_explanation"] = explanation
        except Exception as e:
            res["llm"] = f"(LLM unavailable: {e})"
            res["ai_explanation"] = res["llm"]

    return res
