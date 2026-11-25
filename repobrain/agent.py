"""Developer Workflow agent: triage, review, diagnose, test and initial incident response in one entry point."""
import json
import os
import re
import time

from . import audit as A
from . import diagnose as D
from . import gitutil, incident, llm, review, testing, triage
from . import policy as P

TASKS = ("triage", "review", "diagnose", "test", "incident", "workflow")


def write_artifact(result, home, name=None):
    if not home:
        return None
    folder = os.path.join(home, "agent")
    os.makedirs(folder, exist_ok=True)
    token = re.sub(r"[^A-Za-z0-9_.-]", "_", str(name or result.get("task") or "result"))[:80]
    path = os.path.join(folder, token + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return path


def run(task="workflow", root=".", base=None, policy=None, home=None, actor=None,
        log_text="", alert=None, pr=None, repeats=1, ai=False, with_tests=False, log=None):
    """Run one workflow task (or all of them) with shared policy and audit trail."""
    task = str(task or "workflow").lower()
    if task not in TASKS:
        raise ValueError("unknown task: " + task + " (choose from " + ", ".join(TASKS) + ")")
    root = os.path.abspath(str(root))
    home = os.path.abspath(home) if home else A.home_for(root)
    pol = policy if policy is not None else P.load_for(root, base)
    log = log if log is not None else A.AuditLog(home)
    actor = str(actor or "repobrain-agent")[:80]

    if task == "incident":
        result = incident.run(alert, root=root, policy=pol, base=base, home=home, log=log)
        result["artifact"] = result.get("brief_path")
        return result

    if task == "test":
        result = testing.run(root, pol, base=base, repeats=repeats, log=log)
    else:
        rev = None
        if task in ("triage", "review", "diagnose", "workflow"):
            rev = review.run(root, pol, base, home)
            review.log_review(log, rev)
        if task == "review":
            result = dict(rev)
            result["task"] = "review"
            result["next_actions"] = triage.run(rev, pol, pr)["next_actions"]
        elif task == "triage":
            result = triage.run(rev, pol, pr)
        elif task == "diagnose":
            ask = llm.ask if (ai and pol.get("allow_llm") and llm.available()) else None
            result = D.run(log_text, rev=rev, ask=ask, log=log)
        else:
            t = triage.run(rev, pol, pr)
            result = {
                "task": "workflow",
                "status": "triaged",
                "head": rev.get("head"),
                "decision": rev.get("decision"),
                "priority": t["priority"],
                "queue": t["queue"],
                "triage": t,
                "review": {"decision": rev.get("decision"), "reason": rev.get("reason"),
                           "counts": rev.get("counts"), "risk": rev.get("risk")},
                "testing": None,
                "diagnosis": None,
                "incident": None,
                "next_actions": t["next_actions"],
            }
            if with_tests:
                result["testing"] = testing.run(root, pol, base=base, repeats=repeats, log=log)
            if log_text:
                ask = llm.ask if (ai and pol.get("allow_llm") and llm.available()) else None
                result["diagnosis"] = D.run(log_text, rev=rev, ask=ask, log=log)
                result["next_actions"] = result["diagnosis"]["next_actions"]
            if alert:
                result["incident"] = incident.run(alert, root=root, policy=pol, base=base, home=home, log=log)
                result["next_actions"] = result["incident"]["playbook"][:5]
            log.append("agent-workflow", actor, t["priority"],
                       f"{task} complete: {rev.get('decision')} / {t['priority']} / {t['queue']}",
                       head=rev.get("head"))

    result["actor"] = actor
    result["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    result["artifact"] = result.get("artifact") or write_artifact(result, home,
        f"{result.get('incident_id') or result.get('head') or task}-{task}")
    return result


def to_markdown(result):
    task = result.get("task")
    if task == "triage":
        return triage.to_markdown(result)
    if task == "diagnose":
        return D.to_markdown(result)
    if task == "test":
        return testing.to_markdown(result)
    if task == "incident":
        return incident.to_markdown(result)
    if task == "review":
        lines = [f"## Developer Workflow agent — code review",
                 f"- Verdict: **{result.get('decision')}** — {result.get('reason', '')}",
                 f"- Counts: {result.get('counts', {})}", ""]
        lines.append("Next actions:")
        lines += [f"  1. {a}" for a in result.get("next_actions", [])]
        return "\n".join(lines)
    lines = [f"## Developer Workflow agent — {result.get('priority')} / {result.get('queue')}",
             f"- Verdict: {result.get('decision')} · head: {str(result.get('head'))[:12]}", ""]
    lines.append(triage.to_markdown(result["triage"]))
    if result.get("testing"):
        lines.append("")
        lines.append(testing.to_markdown(result["testing"]))
    if result.get("diagnosis"):
        lines.append("")
        lines.append(D.to_markdown(result["diagnosis"]))
    if result.get("incident"):
        lines.append("")
        lines.append(incident.to_markdown(result["incident"]))
    return "\n".join(lines)
