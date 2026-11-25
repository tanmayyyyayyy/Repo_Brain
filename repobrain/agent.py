"""RepoBrain developer agent: five repetitive engineering workflows on one safety layer.

triage · review · diagnose · test · incident

The agent proposes; it never writes files, reverts commits, merges or pages anyone.
Every workflow returns structured evidence and an audit record, and anything that
changes the repository still goes through the existing human-approval path. Rules
decide verdicts; an optional LLM may add prose, never a decision.
"""
import hashlib, json, os, pathlib, re, subprocess, time
from . import audit, explainer, llm, optimizer, policy, risk, shield

WORKFLOWS = ("run", "triage", "review", "diagnose", "test", "incident")
SECURITY_RULES = frozenset({"secret", "high-entropy-string", "prompt-injection", "hidden-unicode",
                            "risky-command", "dependency-risk", "blocked-path"})
SKIP_DIRS = {".git", ".repobrain", "__pycache__", ".pytest_cache", "node_modules", "venv", ".venv"}


def home_for(root):
    base = pathlib.Path(os.environ.get("REPOBRAIN_HOME", pathlib.Path.home() / ".repobrain"))
    return base / hashlib.sha1(str(pathlib.Path(root).resolve()).encode()).hexdigest()[:10]


def _home(root, home):
    return pathlib.Path(home or home_for(root))


def _git(root, *a):
    return subprocess.run(["git", *a], cwd=root, capture_output=True, text=True).stdout.strip()


def _pol(root):
    return policy.load(pathlib.Path(root) / "repobrain.yml")


def _changed(root, base):
    if not base:
        return []
    return [p for p in _git(root, "diff", "--name-only", f"{base}...HEAD").splitlines() if p.strip()]


def _commits(root, base, pol):
    if not base:
        return []
    rows = _git(root, "log", f"{base}..HEAD", "--format=%h|%an|%s").splitlines()
    out = []
    for row in rows:
        sha, author, subject = (row.split("|", 2) + ["", "", ""])[:3]
        out.append({"sha": sha, "author": author, "subject": subject, "ai": shield.is_ai(author, pol)})
    return out


def _files(root, base, pol):
    out = []
    for p in _changed(root, base):
        authors = _git(root, "log", f"{base}..HEAD", "--format=%an", "--", p).splitlines()
        ai = [a for a in authors if shield.is_ai(a, pol)]
        actor = ai[0] if ai else (authors[0] if authors else "unknown")
        added = shield.added_lines(root, base, p)
        fp = pathlib.Path(root) / p
        loc = len(fp.read_text(errors="ignore").splitlines()) if fp.is_file() and fp.stat().st_size < 1_000_000 else 0
        out.append({"path": p, "actor": actor, "ai": bool(ai), "loc": loc, "added": len(added),
                    "findings": shield.check(root, [p], pol, actor, added={p: added})})
    return out


def _record(home, workflow, decision, actor, detail, log=True):
    if log:
        return audit.log(home, "agent:" + workflow, decision, actor, detail)
    return None


def _ai_note(out, prompt, use_ai):
    if use_ai and llm.available():
        try:
            out["ai_summary"] = llm.ask(prompt, system="Summarise the evidence. Never claim an action was taken or approve anything.")
        except Exception as e:
            out["ai_summary"] = f"(AI unavailable: {e})"
    return out


def _priority(files, gate):
    findings = [x for f in files for x in f["findings"]]
    if any(x["severity"] == "block" for x in findings):
        return "P0" if {x["rule"] for x in findings} & SECURITY_RULES else "P1"
    if gate:
        return "P1"
    return "P2" if findings else "P3"


def _route(files, gate):
    rules = {x["rule"] for f in files for x in f["findings"]}
    out = []
    if rules & SECURITY_RULES:
        out.append("security-review")
    if gate:
        out.append("code-owner")
    if "large-change" in rules or (files and max((f["added"] for f in files), default=0) > 200):
        out.append("split-the-change")
    return out or ["routine-review"]


def triage(root, base="main", actor="dev-agent", use_ai=False, home=None, log=True):
    """Prioritise and route a pull request using the same policy as every other entry point."""
    root = pathlib.Path(root)
    pol = _pol(root)
    files = _files(root, base, pol)
    commits = _commits(root, base, pol)
    gate = optimizer.gate(root, pol, base=base)
    blocks = [x for f in files for x in f["findings"] if x["severity"] == "block"]
    warns = [x for f in files for x in f["findings"] if x["severity"] == "warn"]
    rk = risk.score(files, gate, None, len(blocks), len(warns), len(files) > pol["max_files_changed"])
    verdict = "blocked" if blocks else "changes" if gate else "ready"
    reasons = []
    if blocks:
        reasons.append(f"{len(blocks)} blocking finding(s): " + ", ".join(sorted({x["rule"] for x in blocks})))
    if gate:
        reasons.append(f"{len(gate)} function(s) over the complexity policy")
    if warns:
        reasons.append(f"{len(warns)} warning(s), including learned-guard advice")
    if commits and all(c["ai"] for c in commits):
        reasons.append("every commit in this PR is AI-authored")
    if not reasons:
        reasons.append("no policy or complexity findings in the added lines")
    prio = _priority(files, gate)
    out = {"workflow": "triage", "base": base, "head": _git(root, "rev-parse", "--short", "HEAD"),
           "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"), "commits": commits, "files": files,
           "gate": gate, "risk": rk, "priority": prio, "route": _route(files, gate), "verdict": verdict,
           "reasons": reasons, "actions": ["human review required", "nothing merges without approval"],
           "summary": f"{prio} · {verdict} · risk {rk['score']}/100 · {len(files)} files · "
                      f"{len(blocks)} blocking · {len(gate)} gate · route to {', '.join(_route(files, gate))}"}
    _record(_home(root, home), "triage", verdict, actor, {"priority": prio, "risk": rk["score"], "files": len(files)})
    return _ai_note(out, "Summarise this PR triage for a reviewer:\n" + json.dumps(out["summary"] + "\n" + "\n".join(reasons)), use_ai)


def _has_test(root, path):
    if not path.endswith(".py") or pathlib.Path(path).name.startswith("test_"):
        return True
    stem = pathlib.Path(path).stem
    for pat in ("test_*.py", "*_test.py"):
        for p in pathlib.Path(root).rglob(pat):
            if set(p.relative_to(root).parts) & SKIP_DIRS:
                continue
            if stem in p.read_text(errors="ignore"):
                return True
    return False


def review(root, base="main", actor="dev-agent", use_ai=False, home=None, log=True):
    """Produce line-level review comments from Shield, the complexity gate and the verified proposal."""
    root = pathlib.Path(root)
    home = _home(root, home)
    pol = _pol(root)
    files = _files(root, base, pol)
    gate = optimizer.gate(root, pol, base=base)
    prop = optimizer.run(root, pol, home, base=base, log=False)
    proposals = {f["path"]: f for f in prop["files"] if f["diff"]}
    comments = []
    for f in files:
        for x in f["findings"]:
            comments.append({"file": f["path"], "line": x.get("line") or 1, "severity": x["severity"],
                             "rule": x["rule"], "body": x["msg"], "evidence": x.get("evidence", ""),
                             "suggestion": "Remove the secret and rotate it" if x["rule"] == "secret" else ""})
        for g in [x for x in gate if x["file"] == f["path"]]:
            p = proposals.get(f["path"])
            comments.append({"file": f["path"], "line": g["line"], "severity": "warn",
                             "rule": "complexity-gate", "body": f"{g['name']}(): " + "; ".join(g["why"]),
                             "evidence": "", "suggestion": "Apply the tested, fuzz-verified Optimizer proposal" if p else ""})
        if not _has_test(root, f["path"]) and f["path"].endswith(".py"):
            comments.append({"file": f["path"], "line": 1, "severity": "warn", "rule": "missing-test",
                             "body": "No test file references this module", "evidence": "",
                             "suggestion": "Add a focused test before requesting merge"})
        if f["added"] > 200:
            comments.append({"file": f["path"], "line": 1, "severity": "warn", "rule": "large-diff",
                             "body": f"{f['added']} lines added in one file", "evidence": "",
                             "suggestion": "Split into smaller, independently reviewable changes"})
    verdict = "request-changes" if any(c["severity"] == "block" for c in comments) or gate else \
              ("comment" if comments else "approve")
    out = {"workflow": "review", "base": base, "head": _git(root, "rev-parse", "--short", "HEAD"),
           "verdict": verdict, "comments": comments, "proposal": {"status": prop["status"], "tests": prop["tests"],
           "fuzz": prop["fuzz"], "changed": sum(1 for f in prop["files"] if f["diff"])},
           "approval_required": True,
           "summary": f"{verdict}: {len(comments)} comment(s) across {len(files)} files · "
                      f"optimizer {prop['status']} · nothing pushed without human approval"}
    _record(home, "review", verdict, actor, {"comments": len(comments), "blocking": verdict == "request-changes"})
    return _ai_note(out, "Review these comments and give a short reviewer summary:\n" + json.dumps(comments[:40]), use_ai)


def _suspect_files(text, files, location, failed_tests):
    names = {pathlib.Path(m).name for m in re.findall(r"([\w./-]+\.(?:py|js|ts|tsx|rs|go))(?::\d+)?", text)}
    if location:
        names.add(pathlib.Path(location.rsplit(":", 1)[0]).name)
    for t in failed_tests:
        names.add(pathlib.Path(t.split("::")[0]).stem + ".py")
    out = []
    for f in files:
        why = []
        if pathlib.Path(f["path"]).name in names:
            why.append("named in the log")
        if any(x["severity"] == "block" for x in f["findings"]):
            why.append("has a blocking finding")
        if why:
            out.append({"path": f["path"], "actor": f["actor"], "why": why})
    return out


def diagnose(root, log_text, base="main", actor="dev-agent", use_ai=False, home=None, log=True):
    """Turn a failed build/test log into cause, fix, patch and suspect changed files."""
    root = pathlib.Path(root)
    text = str(log_text)[:200_000]
    d = explainer.explain(text, use_ai=use_ai)
    files = _files(root, base, _pol(root)) if base else []
    suspects = _suspect_files(text, files, d["location"], d["failed_tests"])
    actions = [{"kind": "patch", "file": p["file"], "line": p["line"], "warning": p.get("warning", "")} for p in d["patches"]]
    if d["failed_tests"]:
        actions.append({"kind": "run-tests", "targets": d["failed_tests"][:10]})
    if d["confidence"] == "low":
        actions.append({"kind": "collect-more-log", "reason": "no known pattern matched"})
    out = {"workflow": "diagnose", "diagnosis": d, "suspects": suspects, "actions": actions,
           "confidence": d["confidence"], "approval_required": True,
           "summary": f"{d['confidence']} confidence · {len(d['findings'])} cause(s) · "
                      f"{len(d['patches'])} patch(es) · {len(suspects)} suspect file(s)"}
    _record(_home(root, home), "diagnose", d["confidence"], actor,
            {"findings": len(d["findings"]), "patches": len(d["patches"]), "suspects": [s["path"] for s in suspects]})
    return out


def _test_failures(output):
    names = re.findall(r"FAILED ([\w/\.:\-\[\]]+)", output)
    return [{"test": n, "file": n.split("::")[0].replace(".py", "") + ".py"} for n in dict.fromkeys(names)]


def test(root, base="main", actor="dev-agent", home=None, log=True):
    """Run the repository's own tests on a scratch copy and correlate failures with the PR."""
    root = pathlib.Path(root)
    ok, info = optimizer.verify(root, {})
    status = "passed" if ok else "failed" if ok is False else "unverified"
    failures = _test_failures(info["output"])
    changed = _changed(root, base)
    related = []
    for f in failures:
        hits = [p for p in changed if pathlib.Path(p).name == pathlib.Path(f["file"]).name
                or pathlib.Path(p).stem == pathlib.Path(f["file"]).stem]
        related.append({"test": f["test"], "changed_files": hits})
    out = {"workflow": "test", "status": status, "runner": info["runner"], "passed": info["passed"],
           "failed": info["failed"], "skipped": info["skipped"], "failures": failures, "related": related,
           "changed_files": changed, "output": info["output"], "approval_required": False,
           "summary": f"{status} · {info['passed']} passed, {info['failed']} failed, {info['skipped']} skipped "
                      f"({info['runner'] or 'no runner'}) · {len(failures)} failed test id(s)"}
    _record(_home(root, home), "test", status, actor,
            {"passed": info["passed"], "failed": info["failed"], "skipped": info["skipped"]})
    return out


def _alert(alert):
    if isinstance(alert, dict):
        keys = ("title", "subject", "description", "summary", "body", "message", "log", "logs", "text")
        text = "\n".join(str(alert.get(k, "")) for k in keys if alert.get(k))
        return {"title": str(alert.get("title") or alert.get("subject") or "incident")[:200],
                "service": str(alert.get("service") or alert.get("service_name") or "unknown")[:100],
                "hint": str(alert.get("severity") or "")[:40], "text": text[:200_000]}
    text = str(alert or "")[:200_000]
    return {"title": (text.splitlines() or ["incident"])[0][:200], "service": "unknown", "hint": "", "text": text}


def _severity(text, hint=""):
    h = hint.lower()
    for rx, sev in ((r"sev0|\bp0\b|critical|sev1|\bp1\b", "SEV1"), (r"sev2|\bp2\b|major", "SEV2"),
                    (r"sev3|\bp3\b|degraded", "SEV3")):
        if re.search(rx, h):
            return sev
    t = text.lower()
    if re.search(r"\b(sev0|p0|critical|outage|production is down|total failure)\b", t):
        return "SEV1"
    if re.search(r"\b(sev1|p1|major|error rate|elevated|payment|checkout)\b", t):
        return "SEV2"
    if re.search(r"\b(sev2|p2|degraded|slow|intermittent)\b", t):
        return "SEV3"
    return "SEV4"


def _suspect_commits(root, commits, text):
    names = {pathlib.Path(m).name for m in re.findall(r"([\w./-]+\.(?:py|js|ts|tsx|rs|go|yml|yaml|json))(?::\d+)?", text)}
    out = []
    for c in commits:
        paths = _git(root, "show", "--pretty=", "--name-only", c["sha"]).splitlines()
        hits = [p for p in paths if pathlib.Path(p).name in names]
        why = []
        if hits:
            why.append("touches " + ", ".join(hits[:3]))
        if c["ai"]:
            why.append("AI-authored change")
        if why:
            out.append({**c, "files": paths[:10], "why": why})
    return out


def incident(root, alert, base="main", actor="dev-agent", use_ai=False, home=None, log=True):
    """First on-call response: severity, timeline, suspect change, containment and escalation."""
    root = pathlib.Path(root)
    a = _alert(alert)
    sev = _severity(a["text"], a["hint"])
    pol = _pol(root)
    commits = _commits(root, base, pol)[:12]
    d = diagnose(root, a["text"], base, actor, use_ai=False, home=home, log=False)
    suspects = _suspect_commits(root, commits, a["text"])
    actions = [
        {"step": 1, "action": f"Acknowledge the page and declare {sev} for {a['service']}", "automated": False},
        {"step": 2, "action": "Freeze deploys and preserve the current logs", "automated": False},
        {"step": 3, "action": "Run the RepoBrain test workflow and re-diagnose", "automated": True, "workflow": "test"},
        {"step": 4, "action": "Assign the owner from the routing: " + ("code-owner" if d["diagnosis"]["patches"] else "routine-review"), "automated": False},
    ]
    if suspects:
        actions.append({"step": 5, "action": f"After human approval, consider `git revert {suspects[0]['sha']}`",
                        "automated": False})
    if sev in ("SEV1", "SEV2"):
        actions.append({"step": len(actions) + 1, "action": f"Page the on-call {a['service']} owner and open an incident channel",
                        "automated": False})
    out = {"workflow": "incident", "severity": sev, "service": a["service"], "title": a["title"],
           "alert": a["text"][:4000], "timeline": commits, "suspects": suspects[:5],
           "diagnosis": d["diagnosis"], "suspect_files": d["suspects"], "actions": actions,
           "page": sev in ("SEV1", "SEV2"), "approval_required": True,
           "summary": f"{sev} · {a['service']} · {len(suspects)} suspect commit(s) · "
                      f"{len(actions)} response step(s) · advice only, no action taken"}
    _record(_home(root, home), "incident", sev, actor,
            {"service": a["service"], "suspects": [s["sha"] for s in suspects[:5]], "page": out["page"]})
    return _ai_note(out, "Write a short initial incident brief from this evidence:\n" + json.dumps(out["summary"] + "\n" + a["text"][:2000]), use_ai)


def markdown(r):
    """One human-readable brief for the whole run."""
    lines = ["# RepoBrain developer agent", "", r.get("summary", ""), ""]
    t = r.get("triage")
    if t:
        lines += ["## 1. Pull request triage", "",
                  f"- Priority **{t['priority']}** · verdict **{t['verdict']}** · risk **{t['risk']['score']}/100** ({t['risk']['level']})",
                  f"- Route: {', '.join(t['route'])} · {len(t['commits'])} commits · {len(t['files'])} files",
                  *["  - " + x for x in t["reasons"]], ""]
    v = r.get("review")
    if v:
        lines += ["## 2. Code review", "", f"- Verdict **{v['verdict']}** · {len(v['comments'])} comment(s)",
                  f"- Optimizer: {v['proposal']['status']}", ""]
        for c in v["comments"][:30]:
            lines.append(f"- `{c['rule']}` {c['file']}:{c['line']} · {c['severity']} · {c['body']}")
        lines.append("")
    d = r.get("diagnose")
    if d:
        lines += ["## 3. Failed-build diagnosis", "", d["summary"], ""]
        for x in d["diagnosis"]["findings"]:
            lines += [f"- **{x['cause']}** Fix: {x['fix']}"]
        for p in d["diagnosis"]["patches"]:
            lines.append(f"- Patch `{p['file']}` ← `{p['line']}`" + (f" · warning: {p['warning']}" if p.get("warning") else ""))
        lines.append("")
    s = r.get("test")
    if s:
        lines += ["## 4. Testing", "", s["summary"], ""]
        for f in s["related"]:
            lines.append(f"- `{f['test']}`" + (" → changed " + ", ".join(f["changed_files"]) if f["changed_files"] else ""))
        lines.append("")
    i = r.get("incident")
    if i:
        lines += ["## 5. Initial incident response", "",
                  f"- **{i['severity']}** · {i['service']} · {i['title']} · page on-call: {i['page']}",
                  f"- Suspect commits: {', '.join(c['sha'] for c in i['suspects']) or 'none'}", ""]
        for a in i["actions"]:
            lines.append(f"{a['step']}. {a['action']}")
        lines.append("")
    lines += ["<sub>The agent only proposes. Nothing is written, reverted, merged or paged without human approval.</sub>"]
    return "\n".join(lines)


def run(root, base="main", alert=None, log_text="", actor="dev-agent", use_ai=False, home=None, log=True):
    """Run all five workflows and write a reviewable brief to the audit home."""
    root = pathlib.Path(root)
    home = _home(root, home)
    t = triage(root, base, actor, use_ai, home, log=False)
    v = review(root, base, actor, use_ai, home, log=False)
    s = test(root, base, actor, home, log=False)
    d = diagnose(root, log_text, base, actor, use_ai, home, log=False) if str(log_text or "").strip() else None
    i = incident(root, alert, base, actor, use_ai, home, log=False) if alert else None
    verdict = "blocked" if t["verdict"] == "blocked" or s["status"] == "failed" or (i and i["severity"] == "SEV1") else \
              "changes" if t["verdict"] == "changes" or v["verdict"] == "request-changes" else "ready"
    out = {"workflow": "run", "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "root": str(root), "base": base, "head": t["head"], "actor": actor, "verdict": verdict,
           "triage": t, "review": v, "diagnose": d, "test": s, "incident": i,
           "workflows_run": [w for w, x in (("triage", t), ("review", v), ("diagnose", d), ("test", s), ("incident", i)) if x],
           "summary": f"{verdict} · triage {t['priority']} · review {v['verdict']} · tests {s['status']}"}
    _record(home, "run", verdict, actor, {"workflows": out["workflows_run"], "head": t["head"]})
    ddir = home / "agent"
    ddir.mkdir(parents=True, exist_ok=True)
    (ddir / "latest.json").write_text(json.dumps(out, indent=2))
    md = markdown(out)
    (ddir / "latest.md").write_text(md)
    out["markdown"] = md
    out["report"] = str(ddir / "latest.md")
    return out


def latest(home):
    """Last stored run, or None."""
    p = pathlib.Path(home) / "agent" / "latest.json"
    return json.loads(p.read_text()) if p.is_file() else None


def exit_code(out):
    verdict = out.get("verdict") or out.get("triage", {}).get("verdict") or out.get("workflow")
    if verdict in ("blocked", "request-changes", "failed") or out.get("status") == "failed":
        return 1
    return 0
