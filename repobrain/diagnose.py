"""Failed-build diagnosis: CI log -> ranked causes, likely changed files and an action plan."""
import os
import re

from . import explainer

MAX_LOG_CHARS = 200_000


def _redact(value):
    return explainer.redact(str(value or ""))[:300]


def _suspects(exp, changed):
    found = []
    loc = exp.get("location") or {}
    loc_file = str(loc.get("file", ""))
    for path in changed:
        if not path:
            continue
        if loc_file and (loc_file == path or os.path.basename(loc_file) == os.path.basename(path)):
            found.append({"file": path, "line": loc.get("line"), "why": "failure location matches a changed file", "score": 3})
        elif loc_file and path in loc_file:
            found.append({"file": path, "line": loc.get("line"), "why": "failure location is inside a changed path", "score": 2})
    for test in exp.get("failed_tests", []) or []:
        base = os.path.basename(str(test).split("::")[0])
        for path in changed:
            if base and base == os.path.basename(path):
                found.append({"file": path, "line": None, "why": f"failed test '{test}' matches a changed file", "score": 3})
    evidence = " ".join(_redact(m.get("evidence", "")) for m in exp.get("findings", []))
    for path in changed:
        if path and re.search(re.escape(os.path.basename(path)), evidence):
            found.append({"file": path, "line": None, "why": "changed file appears in failure evidence", "score": 1})
    best = {}
    for item in found:
        key = (item["file"], item["line"])
        if key not in best or item["score"] > best[key]["score"]:
            best[key] = item
    ranked = sorted(best.values(), key=lambda x: -x["score"])
    return ranked[:10]


def run(log_text, rev=None, ask=None, log=None):
    """Explain a build log and correlate it with an optional PR review result."""
    text = str(log_text or "")[:MAX_LOG_CHARS]
    exp = explainer.explain(text, ask)
    changed = [str(f.get("path", "")) for f in ((rev or {}).get("files", []) or [])]
    causes = []
    for m in exp.get("findings", []):
        causes.append({
            "title": _redact(m.get("title")),
            "cause": _redact(m.get("cause")),
            "fix": _redact(m.get("fix")),
            "kind": str(m.get("kind", "general")),
            "evidence": _redact(m.get("evidence")),
        })
    suspects = _suspects(exp, changed)
    failed = [_redact(t) for t in exp.get("failed_tests", [])][:50]
    patches = [{"file": _redact(p.get("file")), "note": _redact(p.get("note")), "warning": _redact(p.get("warning"))}
               for p in exp.get("patches", [])]

    steps = ["Preserve the raw CI log as an audit artifact (secrets are redacted here)."]
    if causes:
        steps.append("Apply the highest-ranked fix: " + causes[0]["fix"])
    else:
        steps.append("No known pattern matched: capture a verbose run and compare the last green build.")
    if suspects:
        steps.append("Inspect " + ", ".join(s["file"] + (f":{s['line']}" if s["line"] else "") for s in suspects[:3]))
    if failed:
        steps.append("Re-run the failed tests locally: " + ", ".join(failed[:5]))
    steps += ["Run `repobrain agent --task test` to verify on a scratch copy.",
              "Re-run CI and `repobrain review` before requesting re-review."]

    result = {
        "task": "diagnose",
        "status": "diagnosed" if causes else "needs-more-data",
        "summary": _redact(exp.get("summary")),
        "confidence": exp.get("confidence", "low"),
        "causes": causes,
        "failed_tests": failed,
        "suspect_files": suspects,
        "suggested_patches": patches,
        "location": {"file": _redact((exp.get("location") or {}).get("file")),
                     "line": (exp.get("location") or {}).get("line")},
        "ai_explanation": _redact(exp.get("ai_explanation")),
        "next_actions": steps,
        "log_lines": exp.get("lines", 0),
    }
    if log is not None:
        log.append("diagnose", "repobrain", result["status"].upper(), result["summary"])
    return result


def to_markdown(d):
    lines = [f"## Failed-build diagnosis — {d['summary']}",
             f"- Confidence: {d['confidence']} · status: {d['status']}"]
    if d["location"]["file"]:
        lines.append(f"- Location: {d['location']['file']}:{d['location'].get('line') or ''}")
    if d["failed_tests"]:
        lines.append("- Failed tests: " + ", ".join(d["failed_tests"][:10]))
    if d["suspect_files"]:
        lines.append("- Likely changed files: " + ", ".join(s["file"] for s in d["suspect_files"][:5]))
    lines.append("")
    lines.append("Causes:")
    for c in d["causes"][:8]:
        lines.append(f"  - **{c['title']}** — {c['cause']} Fix: {c['fix']}")
    lines.append("")
    lines.append("Action plan:")
    lines += [f"  1. {s}" for s in d["next_actions"]]
    return "\n".join(lines)
