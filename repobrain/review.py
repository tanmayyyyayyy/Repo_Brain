"""PR review pipeline: git diff -> actors -> Shield -> complexity gate -> decision (+ human waivers)."""
import json
import os
import re
import time

from . import deps, gitutil, metrics, risk, shield
from . import policy as P

TEST_RX = re.compile(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$)")


def _waivers(home, root=None):
    res = {}
    if root:
        try:
            with open(os.path.join(root, ".repobrain", "waivers.json"), encoding="utf-8") as f:
                res.update(json.load(f))
        except (OSError, json.JSONDecodeError):
            pass
    if home:
        try:
            with open(os.path.join(home, "waivers.json"), encoding="utf-8") as f:
                res.update(json.load(f))
        except (OSError, json.JSONDecodeError):
            pass
    return res


def waive(home, head, actor, reason, root=None):
    if len(reason.strip()) < 10:
        raise ValueError("a waiver needs a written reason (min 10 characters)")
    w = _waivers(home, root)
    entry = {"actor": actor, "reason": reason.strip(), "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    w[head] = entry
    if root:
        rdir = os.path.join(root, ".repobrain")
        os.makedirs(rdir, exist_ok=True)
        with open(os.path.join(rdir, "waivers.json"), "w", encoding="utf-8") as f:
            json.dump(w, f, indent=2)
    if home:
        os.makedirs(home, exist_ok=True)
        with open(os.path.join(home, "waivers.json"), "w", encoding="utf-8") as f:
            json.dump(w, f, indent=2)
    return entry


def run(root, policy, base=None, home=None, extra_actor=None):
    base = gitutil.resolve_base(root, base)
    head = gitutil.head(root)
    changes = gitutil.changed_files(root, base)
    added = gitutil.added_lines(root, base)
    actors = gitutil.file_actors(root, base)
    files, findings, gate = [], [], []

    ci_env = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))
    pr_author = os.environ.get("REPOBRAIN_PR_AUTHOR", "").strip()
    pr_author_type = os.environ.get("REPOBRAIN_PR_AUTHOR_TYPE", "").strip()
    ci_bot = bool(ci_env and (pr_author_type.lower() == "bot" or pr_author.lower().endswith("[bot]")))

    if policy.get("require_signed_commits", False) and head:
        sig = gitutil.git(root, "log", "-1", "--format=%G?", head, check=False).strip()
        if sig not in ("G", "U"):
            findings.append(shield.finding("block", "unsigned-commit", "(commit)",
                                           f"commit {head[:7]} is not signed (status %G?='{sig or 'N'}') while policy require_signed_commits is true"))

    for status, path in changes:
        if shield.ignored(path, policy):
            continue
        ids = set(actors.get(path, set()))
        if extra_actor:
            ids.add(extra_actor)
        if pr_author:
            ids.add(pr_author)
        if ci_bot:
            ai = True
            file_ai_source = "ci_metadata"
        else:
            ai = any(P.is_ai(i, policy) for i in ids)
            file_ai_source = "heuristic"
        ff = shield.scan_path(path, status, ai, policy)
        entry = {"path": path, "status": status, "actors": sorted(ids), "ai": ai, "findings": ff,
                 "ai_source": file_ai_source,
                 "violations": [], "added": len(added.get(path, {}))}
        if status != "D":
            text = gitutil.show(root, "HEAD", path)
            actor_name = sorted(ids)[0] if ids else (extra_actor or "unknown")
            ff += shield.scan_text(path, text, policy, actor=actor_name, only_lines=added.get(path, {}).keys())
            if policy.get("dependency_guard", True) and deps.is_manifest(path):
                ls = [(n, t) for n, t in enumerate(text.split("\n"), 1) if not added.get(path) or n in added.get(path, {})]
                for d in deps.check_added(path, ls, policy):
                    ff.append(shield.finding("block" if ai else "warn", "dependency-risk", path,
                                            d["msg"], line=d["line"], evidence=d["evidence"], kind=d.get("kind")))
            if path.endswith(".py") and "python" in policy.get("languages", ["python"]) and not TEST_RX.search(path):
                try:
                    funcs = metrics.analyze(text)
                    entry["metrics"] = metrics.summarize(funcs, text.count("\n"))
                    entry["violations"] = metrics.violations(funcs, policy, set(added.get(path, {})))
                except SyntaxError as e:
                    ff.append(shield.finding("warn", "syntax-error", path, f"cannot parse: {e.msg}", e.lineno))
        findings += ff
        gate += [dict(v, file=path) for v in entry["violations"]]
        files.append(entry)

    ai_files = [f for f in files if f["ai"]]
    max_f = policy.get("max_files_per_run", policy.get("max_files_changed", 15))
    if ai_files and len(files) > max_f:
        findings.append(shield.finding("block", "blast-radius", "(change set)",
                                       f"AI-authored change touches {len(files)} files "
                                       f"(policy max_files_per_run = {max_f})"))
    if gitutil.git(root, "status", "--porcelain", check=False).strip():
        findings.append(shield.finding("warn", "dirty-tree", "(working tree)",
                                       "uncommitted changes present - review covers committed changes only"))

    blocks = [f for f in findings if f["severity"] == "block"]
    warns = [f for f in findings if f["severity"] == "warn"]
    waiver = (_waivers(home, root).get(head) or _waivers(home, root).get("*")) if (home or root) else None
    if not waiver:
        try:
            msg = gitutil.git(root, "log", "-1", "--format=%B", head, check=False)
            for line in msg.splitlines():
                if line.strip().lower().startswith("waived-by:"):
                    parts = line.strip().split(":", 1)[1].strip()
                    if " - " in parts:
                        actor_part, reason_part = parts.split(" - ", 1)
                        if len(reason_part.strip()) >= 10:
                            waiver = {"actor": actor_part.strip(), "reason": reason_part.strip(), "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
                            break
        except Exception:
            pass
    if blocks:
        decision, why = "BLOCKED", f"{len(blocks)} blocking finding(s) - not waivable, fix and push"
        verdict = "blocked"
    elif gate and policy.get("optimize") == "required":
        if waiver:
            decision, why = "ALLOWED", f"complexity gate waived by {waiver['actor']}: {waiver['reason']}"
            verdict = "ready"
        else:
            decision, why = "CHANGES_REQUIRED", f"{len(gate)} function(s) over complexity limits - run the optimizer or waive with a reason"
            verdict = "changes"
    else:
        decision, why = "ALLOWED", "no blocking findings"
        verdict = "ready"

    large = len(files) > max_f
    risk_info = risk.score(files, gate, None, len(blocks), len(warns), large)

    return {"base": base, "head": head, "branch": gitutil.branch(root), "decision": decision,
            "verdict": verdict, "reason": why,
            "ai_detection_source": ("ci_metadata" if ci_bot else "heuristic"),
            "files": files, "findings": findings, "gate": gate, "waiver": waiver,
            "risk": risk_info,
            "counts": {"files": len(files), "ai_files": len(ai_files), "blocks": len(blocks),
                       "warnings": len(warns), "gate": len(gate)},
            "policy_source": policy.get("_source", "")}


def log_review(log, rev, actor="repobrain"):
    """Write one 'ai-change' entry per AI-authored file + one 'review' summary. Idempotent per head+decision."""
    recent = log.entries()[-60:]
    if any(e.get("event") == "review" and e.get("head") == rev["head"] and e.get("decision") == rev["decision"]
           for e in recent):
        return False
    for f in rev["files"]:
        if not f["ai"]:
            continue
        blocked = any(x["severity"] == "block" for x in f["findings"])
        warned = any(x["severity"] == "warn" for x in f["findings"])
        log.append("ai-change", ", ".join(f["actors"])[:120], "BLOCKED" if blocked else ("FLAGGED" if warned else "ALLOWED"),
                   f"{f['status']} {f['path']}: " + ("; ".join(x["rule"] for x in f["findings"]) or "clean"),
                   head=rev["head"])
    log.append("review", actor, rev["decision"], rev["reason"], head=rev["head"])
