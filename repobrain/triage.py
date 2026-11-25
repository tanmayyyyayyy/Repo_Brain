"""PR triage: turn a review verdict into priority, labels, routing and a reviewer shortlist."""
import re

from . import review as R

SECURITY_RULES = {"secret", "prompt-injection", "taint-flow", "blocked-path", "risky-command", "dependency-risk", "hidden-unicode"}
SLA_HOURS = {"P0": 1, "P1": 4, "P2": 24, "P3": 72}
URGENT_RX = re.compile(r"\b(urgent|hotfix|sev-?[12]|p0|p1|security|cve|incident|production|outage|blocker|emergency)\b", re.I)
DEFAULT_OWNERS = {
    "security": [r"^\.github/workflows/", r"^\.gitlab-ci\.ya?ml$", r"^repobrain\.yml$", r"(^|/)(Dockerfile|Procfile|Jenkinsfile)$", r"(^|/)\.env"],
    "tests": [r"(^|/)tests?/", r"(^|/)__tests__/", r"(^|/)test_[^/]*\.py$", r"(^|/)[^/]*_test\.(py|go)$", r"\.(test|spec)\.[jt]sx?$"],
    "frontend": [r"\.([jt]sx?|css|html|vue|svelte)$"],
    "mobile": [r"\.(kt|kts|swift|m)$"],
    "infra": [r"(^|/)(docker-compose|render|terraform|k8s|helm|charts)", r"\.ya?ml$"],
    "backend": [r"\.(py|go|java|rs|cs|rb|php)$"],
}


def _pr_fields(pr):
    pr = pr if isinstance(pr, dict) else {}
    labels = pr.get("labels")
    if isinstance(labels, list):
        names = [str(x.get("name", x)) if isinstance(x, dict) else str(x) for x in labels]
    else:
        names = [str(labels)] if labels else []
    for key in ("label", "tags"):
        value = pr.get(key)
        if isinstance(value, list):
            names += [str(x) for x in value]
        elif value:
            names.append(str(value))
    return {
        "title": str(pr.get("title", ""))[:300],
        "body": str(pr.get("body") or pr.get("description") or "")[:2000],
        "labels": names[:30],
        "author": str(pr.get("author") or pr.get("actor") or "")[:80],
        "draft": bool(pr.get("draft")),
        "changes": int(pr.get("additions") or 0) + int(pr.get("deletions") or 0),
    }


def _owners(policy):
    configured = (policy or {}).get("triage", {}).get("code_owners", {})
    return configured if isinstance(configured, dict) and configured else DEFAULT_OWNERS


def _matches(path, patterns):
    try:
        return any(re.search(str(p), path) for p in patterns)
    except re.error:
        return False


def suggest_reviewers(paths, policy=None):
    owners = _owners(policy)
    teams = []
    for team, patterns in owners.items():
        if not isinstance(patterns, list):
            continue
        if any(_matches(path, patterns) for path in paths):
            teams.append(str(team))
    return teams or ["maintainers"]


def run(rev, policy=None, pr=None):
    """Rank a review for any forge (GitHub/GitLab/Bitbucket/local git). Pure, no writes."""
    rev = rev or {}
    files = rev.get("files", []) or []
    findings = rev.get("findings", []) or []
    gate = rev.get("gate", []) or []
    blocks = [f for f in findings if f.get("severity") == "block"]
    warns = [f for f in findings if f.get("severity") == "warn"]
    rules = [str(f.get("rule", "")) for f in findings]
    security_hits = [r for r in rules if r in SECURITY_RULES]
    paths = [str(f.get("path", "")) for f in files]
    ai_files = [f for f in files if f.get("ai")]
    score = int((rev.get("risk") or {}).get("score", 0) or 0)
    decision = rev.get("decision", "UNKNOWN")
    meta = _pr_fields(pr)
    urgent = bool(URGENT_RX.search(meta["title"] + " " + meta["body"] + " " + " ".join(meta["labels"])))

    if any(r in rules for r in ("secret", "prompt-injection", "taint-flow")) or (blocks and security_hits):
        priority = "P0"
    elif blocks or score >= 70:
        priority = "P1"
    elif gate or warns or score >= 35:
        priority = "P2"
    else:
        priority = "P3"
    if urgent and priority != "P0":
        priority = "P1"
    if meta["draft"] and not blocks and priority != "P0":
        priority = "P3"

    if priority in ("P0", "P1") and security_hits:
        queue = "security-review"
    elif blocks or gate:
        queue = "code-review"
    elif ai_files:
        queue = "ai-change-review"
    else:
        queue = "fast-track"

    labels = ["priority:" + priority.lower(), "risk:" + str((rev.get("risk") or {}).get("level", "unknown")).lower()]
    if ai_files:
        labels.append("ai-authored")
    if security_hits:
        labels.append("security")
    if gate:
        labels.append("needs-optimizer")
    if any(R.TEST_RX.search(path) for path in paths):
        labels.append("tests-touched")
    if len(files) >= 10 or meta["changes"] >= 1000:
        labels.append("large-change")
    if meta["draft"]:
        labels.append("draft")
    if urgent:
        labels.append("urgent")
    labels += [re.sub(r"[^A-Za-z0-9_:/.-]", "-", x)[:60] for x in meta["labels"]]
    if decision == "ALLOWED" and not blocks and not gate:
        labels.append("clean")

    if priority == "P0" or security_hits:
        next_actions = ["Do not merge", "Rotate or revoke any exposed credential", "Security lead reviews evidence", "Require a fresh PR after remediation"]
    elif blocks:
        next_actions = ["Do not merge", "Fix blocking findings", "Request a targeted re-review"]
    elif gate:
        next_actions = ["Run `repobrain optimize --base <ref>`", "Confirm tests and fuzzing pass", "Human approver applies the proposal"]
    elif decision == "ALLOWED":
        next_actions = ["Confirm required checks are green", "Merge with branch protection enabled"]
        if urgent:
            next_actions.insert(0, "Fast-track: assign a reviewer now")
    else:
        next_actions = ["Review warnings", "Re-run `repobrain review` after changes"]

    return {
        "task": "triage",
        "priority": priority,
        "queue": queue,
        "labels": list(dict.fromkeys(labels)),
        "suggested_reviewers": suggest_reviewers(paths, policy),
        "sla_hours": SLA_HOURS[priority],
        "decision": decision,
        "reason": rev.get("reason", ""),
        "head": rev.get("head"),
        "risk_score": score,
        "security_rules": sorted(set(security_hits)),
        "blocking_rules": sorted(set(rules) & {str(f.get("rule")) for f in blocks}),
        "changed_files": len(files),
        "pr_title": meta["title"],
        "pr_author": meta["author"],
        "pr_labels": meta["labels"],
        "draft": meta["draft"],
        "urgent": urgent,
        "next_actions": next_actions,
    }


def to_markdown(t):
    lines = [
        f"## PR triage — {t['priority']} ({t['queue']})",
    ]
    if t.get("pr_title"):
        lines.append(f"- PR: {t['pr_title']}" + (f" · by {t['pr_author']}" if t.get("pr_author") else ""))
    lines += [
        f"- Verdict: **{t['decision']}** — {t['reason']}",
        f"- Risk: {t['risk_score']}/100 · review within {t['sla_hours']}h · {t['changed_files']} file(s)",
        f"- Labels: {', '.join(t['labels'])}",
        f"- Suggested reviewers: {', '.join(t['suggested_reviewers'])}",
        "",
        "Next actions:",
    ]
    lines += [f"  1. {a}" for a in t["next_actions"]]
    return "\n".join(lines)
