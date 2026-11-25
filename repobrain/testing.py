"""Testing workflow: map changed code to tests, run them safely and flag flaky failures."""
import json
import os
import re

from . import optimizer

PASSED_RX = re.compile(r"(\d+)\s+passed")
FAILED_RX = re.compile(r"(\d+)\s+failed")
ERROR_RX = re.compile(r"(\d+)\s+error")
SKIPPED_RX = re.compile(r"(\d+)\s+skipped")
FAILED_TEST_RX = re.compile(r"^(?:FAILED|FAIL|--- FAIL:)\s*([^\s\[]+)", re.M)
MAVEN_RX = re.compile(r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+)", re.I)


TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs"}
TEST_NAME_RX = re.compile(r"(^test_|_test\.|\.test\.|\.spec\.|^test-|_spec\.|Test\.java$|Tests\.java$|_test\.go$)", re.I)


def _names_for(source):
    base = os.path.basename(str(source))
    stem, ext = os.path.splitext(base)
    ext = ext.lower()
    if ext == ".py":
        parent = os.path.dirname(str(source)).replace("/", "_")
        return {f"test_{stem}.py", f"{stem}_test.py", f"test_{parent}_{stem}.py"}
    if ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
        return {f"{stem}.test{ext}", f"{stem}.spec{ext}", f"{stem}.test.js", f"{stem}.spec.js",
                f"test_{stem}{ext}", f"{stem}-test{ext}"}
    if ext == ".go":
        return {f"{stem}_test.go"}
    if ext == ".java":
        return {f"{stem}Test.java", f"{stem}Tests.java", f"{stem}IT.java"}
    if ext == ".rs":
        return {f"{stem}.rs", f"{stem}_test.rs"}
    if ext == ".cs":
        return {f"{stem}Tests.cs", f"{stem}Test.cs"}
    if ext == ".rb":
        return {f"{stem}_spec.rb", f"{stem}_test.rb"}
    if ext == ".php":
        return {f"{stem}Test.php", f"{stem}Tests.php"}
    return set()


def _is_test_path(path):
    parts = [p.lower() for p in str(path).replace("\\", "/").split("/")]
    return any(p in TEST_DIRS for p in parts[:-1]) or bool(TEST_NAME_RX.search(parts[-1]))


def _all_files(root):
    out = set()
    for dp, dn, fn in os.walk(str(root)):
        dn[:] = [d for d in dn if d not in optimizer.SKIP_DIRS and not d.startswith(".")]
        for f in fn:
            out.add(os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/"))
    return out


def _candidate_tests(root, source, files=None):
    files = files if files is not None else _all_files(root)
    names = _names_for(source)
    folder = os.path.dirname(str(source)).replace("\\", "/")
    matched = []
    for path in files:
        if os.path.basename(path) not in names:
            continue
        parent = os.path.dirname(path)
        if parent and parent not in (folder, "tests", "test", "__tests__") and not parent.startswith(folder + "/"):
            continue
        matched.append(path)
    return sorted(matched)


def detect_command(root, policy=None):
    """Find the natural test command for Python, JS/TS, Go, Rust, JVM or Make projects."""
    configured = (policy or {}).get("test_command")
    if configured:
        return configured, "policy"
    root = str(root)
    if os.path.isfile(os.path.join(root, "package.json")):
        try:
            with open(os.path.join(root, "package.json"), encoding="utf-8") as f:
                script = (json.load(f).get("scripts") or {}).get("test")
        except (OSError, ValueError):
            script = None
        if script:
            if os.path.exists(os.path.join(root, "pnpm-lock.yaml")):
                return "pnpm test", "package.json"
            if os.path.exists(os.path.join(root, "yarn.lock")):
                return "yarn test", "package.json"
            return "npm test", "package.json"
    if os.path.isfile(os.path.join(root, "go.mod")):
        return "go test ./...", "go.mod"
    if os.path.isfile(os.path.join(root, "Cargo.toml")):
        return "cargo test", "Cargo.toml"
    if os.path.isfile(os.path.join(root, "pom.xml")):
        return "mvn -q test", "pom.xml"
    if os.path.isfile(os.path.join(root, "gradlew")):
        return "./gradlew test", "gradlew"
    if any(os.path.isfile(os.path.join(root, name)) for name in ("build.gradle", "build.gradle.kts")):
        return "gradle test", "gradle"
    if os.path.isfile(os.path.join(root, "Makefile")):
        try:
            with open(os.path.join(root, "Makefile"), encoding="utf-8") as f:
                if re.search(r"^test\s*:", f.read(), re.M):
                    return "make test", "Makefile"
        except OSError:
            pass
    return None, "python-default"


def plan(root, base=None, paths=None):
    """Suggest tests for changed files in any supported language (no execution, no writes)."""
    if paths is None:
        from . import gitutil
        paths = [p for status, p in gitutil.changed_files(root, base) if status != "D"] if base else []
    files = _all_files(root)
    rows = []
    for src in paths:
        src = str(src).replace("\\", "/")
        if _is_test_path(src):
            rows.append({"source": src, "tests": [src], "coverage": "direct"})
            continue
        if not _names_for(src):
            continue
        tests = _candidate_tests(root, src, files)
        rows.append({"source": src, "tests": tests, "coverage": "targeted" if tests else "suite-only"})
    return rows


def _parse(output):
    output = output or ""

    def number(rx):
        m = rx.search(output)
        return int(m.group(1)) if m else 0

    maven = MAVEN_RX.search(output)
    return {
        "passed": number(PASSED_RX) or (int(maven.group(1)) if maven else 0),
        "failed": number(FAILED_RX) or (int(maven.group(2)) if maven else 0),
        "errors": number(ERROR_RX) or (int(maven.group(3)) if maven else 0),
        "skipped": number(SKIPPED_RX),
        "failed_tests": FAILED_TEST_RX.findall(output)[:50],
    }


def run(root, policy, base=None, repeats=1, log=None):
    """Run the repository suite on a scratch copy; repeat failures to detect flakiness."""
    repeats = max(1, min(int(repeats or 1), 5))
    command, source = detect_command(root, policy)
    effective_policy = dict(policy or {})
    if command:
        effective_policy["test_command"] = command
    first = optimizer.run_tests(root, {}, effective_policy)
    runs = [first]
    counts = _parse(str(first.get("output", "")))
    flaky = False
    if not first.get("ok") and repeats > 1 and (counts["failed"] or counts["errors"]):
        for _ in range(repeats - 1):
            again = optimizer.run_tests(root, {}, effective_policy)
            runs.append(again)
            if again.get("ok"):
                flaky = True
                break
    if not first.get("ran"):
        status = "no-tests"
    elif flaky:
        status = "flaky"
    elif first.get("ok"):
        status = "passed"
    else:
        status = "failed"

    actions = []
    if status == "passed":
        actions.append("Suite is green on a scratch copy; proceed to review and merge.")
    elif status == "flaky":
        actions.append("Failure did not reproduce: quarantine the flaky test and add a deterministic fixture.")
    elif status == "failed":
        if counts["failed_tests"]:
            actions.append("Start with: " + ", ".join(counts["failed_tests"][:5]))
        actions.append("Run `repobrain agent --task diagnose --log <ci-log>` to map failures to causes.")
        actions.append("Re-run `repobrain agent --task test` after the fix.")
    elif status == "no-tests":
        actions.append("Add a test suite or configure `test_command` in repobrain.yml.")

    result = {
        "task": "test",
        "status": status,
        "ran": bool(first.get("ran")),
        "ok": bool(first.get("ok")),
        "flaky": flaky,
        "counts": counts,
        "runs": len(runs),
        "command": first.get("cmd", ""),
        "command_source": source,
        "runner": first.get("runner", ""),
        "sandbox": first.get("sandbox", {}),
        "coverage": first.get("coverage", {}),
        "targeted": plan(root, base),
        "output": str(first.get("output", ""))[-4000:],
        "next_actions": actions,
    }
    if log is not None:
        log.append("test-run", "repobrain", status.upper(), f"{counts['passed']} passed, {counts['failed']} failed, flaky={flaky}")
    return result


def to_markdown(t):
    c = t["counts"]
    lines = [f"## Testing workflow — {t['status']}",
             f"- Command: `{t['command']}` · runs: {t['runs']} · sandbox: {t['sandbox'].get('type', 'none')}",
             f"- Results: {c['passed']} passed, {c['failed']} failed, {c['errors']} errors, {c['skipped']} skipped",
             f"- Flaky: {t['flaky']}"]
    if t["targeted"]:
        lines.append("- Targeted tests: " + ", ".join(
            f"{r['source']} -> {', '.join(r['tests']) or 'suite only'}" for r in t["targeted"][:10]))
    lines.append("")
    lines.append("Next actions:")
    lines += [f"  1. {a}" for a in t["next_actions"]]
    return "\n".join(lines)
