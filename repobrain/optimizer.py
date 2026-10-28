"""Optimizer: rule-based rewrite (+ optional LLM) -> run tests on a copy -> proposal -> human apply."""
import ast
import difflib
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

from . import gitutil, llm, metrics, rewrite
from .shield import SECRET_PATTERNS

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache", ".mypy_cache"}
SECRET_ENV = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.I)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def has_tests(root, policy):
    if policy.get("test_command"):
        return True
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        if any(f.startswith("test_") and f.endswith(".py") or f.endswith("_test.py") for f in fn):
            return True
    return False


def run_tests(root, overrides, policy):
    """Copy the repo, apply `overrides` ({relpath: text}), run the test command. -> dict"""
    if not has_tests(root, policy):
        return {"ran": False, "ok": None, "output": "no tests found", "cmd": ""}
    cmd = policy.get("test_command") or [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"]
    cmd = shlex.split(cmd) if isinstance(cmd, str) else cmd
    tmp = tempfile.mkdtemp(prefix="repobrain-")
    try:
        work = os.path.join(tmp, "repo")
        shutil.copytree(root, work, ignore=shutil.ignore_patterns(*SKIP_DIRS))
        for rel, text in overrides.items():
            with open(os.path.join(work, rel), "w", encoding="utf-8", newline="") as f:
                f.write(text)
        env = {k: v for k, v in os.environ.items() if not SECRET_ENV.search(k)}   # tests never see secrets
        env.update(PYTHONDONTWRITEBYTECODE="1", HOME=tmp)
        try:
            r = subprocess.run(cmd, cwd=work, capture_output=True, text=True, env=env,
                               timeout=policy.get("test_timeout", 180))
            out = (r.stdout + r.stderr)[-4000:]
            return {"ran": True, "ok": r.returncode == 0, "output": out, "cmd": " ".join(cmd)}
        except subprocess.TimeoutExpired:
            return {"ran": True, "ok": False, "output": "test run timed out", "cmd": " ".join(cmd)}
        except FileNotFoundError as e:
            return {"ran": True, "ok": False, "output": f"test command not found: {e}", "cmd": " ".join(cmd)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _diff(path, a, b):
    return "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True),
                                        f"a/{path}", f"b/{path}", n=2))


def _llm_refine(src, policy, funcs, ask, feedback=""):
    """Ask the LLM to rewrite individual over-threshold functions. Returns (new_src, [names])."""
    lines, names, edits = src.splitlines(), [], []
    tree = ast.parse(src)
    by_name = {}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            by_name.setdefault(n.name, n)
    for f in funcs:
        node = by_name.get(f["name"].split(".")[-1])
        if node is None:
            continue
        seg = "\n".join(lines[node.lineno - 1:node.end_lineno])
        prompt = (f"Refactor this Python function to reduce complexity (target: cyclomatic <= "
                  f"{policy['complexity_threshold']}, nesting depth <= {policy['max_depth']}, cognitive <= "
                  f"{policy['max_cognitive']}) WITHOUT changing behaviour. Keep the name and signature, "
                  "keep comments. You may add small private helper functions after it. Reply with ONE "
                  "```python block containing only the code.\n" + (f"\nPrevious attempt failed tests:\n{feedback}\n"
                  if feedback else "") + f"\n```python\n{textwrap_dedent(seg)}\n```")
        reply = ask(prompt, "You are a careful refactoring tool. Output code only.")
        m = re.search(r"```(?:python)?\n(.*?)```", reply, re.S)
        if not m:
            continue
        try:
            ast.parse(m.group(1))
        except SyntaxError:
            continue
        indent = lines[node.lineno - 1][:node.col_offset]
        new = [(indent + l if l.strip() else l) for l in m.group(1).rstrip().split("\n")]
        edits.append((node.lineno, node.end_lineno, new))
        names.append(f["name"])
    for s, e, new in sorted(edits, key=lambda x: -x[0]):
        lines[s - 1:e] = new
    return "\n".join(lines) + ("\n" if src.endswith("\n") else ""), names


def textwrap_dedent(s):
    import textwrap
    return textwrap.dedent(s)


def propose(root, policy, files, home, use_llm=False, ask=None, head=None):
    """Build + verify a proposal for `files` (relative .py paths). Persists it under home/proposals."""
    pid = time.strftime("%Y%m%d-%H%M%S") + "-" + hashlib.sha1(os.urandom(8)).hexdigest()[:6]
    ask = ask or llm.ask
    originals, results, skipped_all = {}, [], []
    for rel in files:
        full = os.path.join(root, rel)
        try:
            src = open(full, encoding="utf-8", newline="").read()
            funcs = metrics.analyze(src)
        except (OSError, SyntaxError, UnicodeDecodeError) as e:
            skipped_all.append({"file": rel, "reason": f"unreadable/invalid python: {e}"})
            continue
        new, notes, skipped = rewrite.optimize_source(src, policy)
        originals[rel] = src
        results.append({"path": rel, "before_sha": sha(src), "before": src, "after": new,
                        "notes": notes, "skipped": skipped, "ai_functions": []})
    llm_info = {"requested": use_llm, "used": False, "reason": ""}
    if use_llm:
        if not policy["allow_llm"]:
            llm_info["reason"] = "disabled by policy (allow_llm: false)"
        elif not (llm.available() or ask is not llm.ask):
            llm_info["reason"] = "ANTHROPIC_API_KEY not set"
        else:
            llm_info["used"] = True
    # tests on rule-based result first
    overrides = {r["path"]: r["after"] for r in results if r["after"] != r["before"]}
    tests = run_tests(root, overrides, policy) if overrides else {"ran": False, "ok": None, "output": "", "cmd": ""}
    if llm_info["used"]:
        remaining = []
        for r in results:
            bad = metrics.violations(metrics.analyze(r["after"]), policy)
            from .shield import scan_text
            if bad and not scan_text(r["path"], r["before"], policy):      # never ship flagged files out
                remaining.append((r, bad))
        if remaining and tests["ok"] is not False:
            trial = dict(overrides)
            feedback, picked = "", {}
            for attempt in range(2):
                picked = {}
                for r, bad in remaining:
                    try:
                        new, names = _llm_refine(r["after"], policy, bad, ask, feedback)
                    except Exception as e:                    # network / API problems must not crash review
                        llm_info["reason"] = f"LLM call failed: {e}"[:200]
                        names, new = [], r["after"]
                    if names:
                        picked[r["path"]] = (r, new, names)
                if not picked:
                    break
                trial = {**overrides, **{p: v[1] for p, v in picked.items()}}
                t2 = run_tests(root, trial, policy)
                if t2["ok"]:
                    for p, (r, new, names) in picked.items():
                        r["after"], r["ai_functions"] = new, names
                    overrides, tests = trial, t2
                    break
                feedback = t2["output"][-1500:]
            else:
                llm_info["reason"] = "LLM refactors failed tests twice - discarded, rule-based result kept"
    out_files = []
    for r in results:
        if r["after"] == r["before"]:
            continue
        b, a = metrics.analyze(r["before"]), metrics.analyze(r["after"])
        r["diff"] = _diff(r["path"], r["before"], r["after"])
        r["metrics"] = {"before": metrics.summarize(b, r["before"].count("\n")),
                        "after": metrics.summarize(a, r["after"].count("\n")),
                        "functions": [{"name": x["name"], "before": {k: x[k] for k in ("cc", "cog", "depth")},
                                       "after": {k: y[k] for k in ("cc", "cog", "depth")}}
                                      for x in b for y in a if x["name"] == y["name"]]}
        r["remaining"] = [{"name": v["name"], "why": v["why"]} for v in metrics.violations(a, policy)]
        out_files.append(r)
    if not out_files:
        status = "nothing-to-optimize"
    elif tests["ok"] is False:
        status = "rejected-tests-failed"
    elif tests["ok"] is None:
        status = "unverified-no-tests"
    else:
        status = "verified"
    prop = {"id": pid, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "status": status, "files": out_files,
            "skipped": skipped_all + [dict(s, file=r["path"]) for r in results for s in r["skipped"]],
            "tests": tests, "llm": llm_info,
            "head": gitutil.head(root) if gitutil.is_repo(root) else None,
            "applicable": status == "verified" or (status == "unverified-no-tests" and not policy["require_tests"])}
    os.makedirs(os.path.join(home, "proposals"), exist_ok=True)
    with open(os.path.join(home, "proposals", pid + ".json"), "w", encoding="utf-8") as f:
        json.dump(prop, f)
    return prop


def load_proposal(home, pid):
    if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{6}", pid or ""):
        raise ValueError("bad proposal id")
    with open(os.path.join(home, "proposals", pid + ".json"), encoding="utf-8") as f:
        return json.load(f)


def apply(root, home, pid, actor):
    """Write an approved proposal to the working tree and commit it. Refuses stale proposals."""
    prop = load_proposal(home, pid)
    if not prop["applicable"]:
        raise ValueError(f"proposal is not applicable (status: {prop['status']})")
    if prop["head"] and gitutil.head(root) != prop["head"]:
        raise ValueError("repository HEAD moved since this proposal was created - re-run the optimizer")
    for r in prop["files"]:
        full = os.path.realpath(os.path.join(root, r["path"]))
        if not full.startswith(os.path.realpath(root) + os.sep):
            raise ValueError("path escapes repository")
        cur = open(full, encoding="utf-8", newline="").read()
        if sha(cur) != r["before_sha"]:
            raise ValueError(f"{r['path']} changed since the proposal was created - re-run the optimizer")
    for r in prop["files"]:
        with open(os.path.join(root, r["path"]), "w", encoding="utf-8", newline="") as f:
            f.write(r["after"])
    sha_new = None
    if gitutil.is_repo(root):
        paths = [r["path"] for r in prop["files"]]
        gitutil.git(root, "add", "--", *paths)
        msg = (f"RepoBrain: simplify {len(paths)} file(s) (tests passed)\n\nApproved-by: {actor}\n"
               f"RepoBrain-proposal: {pid}")
        gitutil.git(root, "-c", "user.name=RepoBrain", "-c", "user.email=repobrain@localhost",
                    "commit", "-m", msg)
        sha_new = gitutil.head(root)
    return {"applied": [r["path"] for r in prop["files"]], "commit": sha_new}
