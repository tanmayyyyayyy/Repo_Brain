"""Initial on-call response: alert -> severity, hypotheses, evidence and a safe first-hour playbook."""
import hashlib
import json
import os
import re
import time

from . import audit as A
from . import explainer, gitutil

SEVERITY_ORDER = ["SEV4", "SEV3", "SEV2", "SEV1"]
KEYWORDS = [
    ("SEV1", r"\b(sev-?1|p0|critical|outage|production down|data loss|payment failure|complete failure)\b"),
    ("SEV2", r"\b(sev-?2|p1|high error rate|5xx|unavailable|major degraded|severe latency)\b"),
    ("SEV3", r"\b(sev-?3|p2|degraded|elevated|intermittent|warning)\b"),
]


def _as_dict(alert):
    if isinstance(alert, dict):
        return alert
    text = str(alert or "")
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except (ValueError, TypeError):
        pass
    return {"message": text[:2000]}


def _clean(value, limit=200):
    return explainer.redact(re.sub(r"[\r\n]+", " ", str(value or "")))[:limit]


def _flatten(alert):
    """Adapt Alertmanager, PagerDuty, Datadog, Opsgenie, Grafana and generic JSON to one shape."""
    data = _as_dict(alert)
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    inner = data.get("alert") if isinstance(data.get("alert"), dict) else {}
    labels = data.get("labels") if isinstance(data.get("labels"), dict) else {}
    annotations = data.get("annotations") if isinstance(data.get("annotations"), dict) else {}
    tags = []
    raw_tags = data.get("tags", [])
    if isinstance(raw_tags, list):
        for tag in raw_tags:
            tags.append(str(tag.get("value") or tag.get("name", "")) if isinstance(tag, dict) else str(tag))
    elif raw_tags:
        tags.append(str(raw_tags))

    def get(*keys):
        for scope in (data, payload, inner, labels, annotations):
            for key in keys:
                value = scope.get(key)
                if value not in (None, ""):
                    return value
        return None

    severity = get("severity", "priority", "sev", "urgency", "alert_type")
    signal = get("message", "summary", "description", "title", "text", "alert_name")
    service = get("service", "service_name", "job", "team", "monitor")
    if not service:
        for tag in tags:
            if ":" in tag and tag.split(":", 1)[0].strip().lower() == "service":
                service = tag.split(":", 1)[1].strip()
                break
    ident = get("id", "incident_id", "dedup_key", "alert_id", "uid")
    started = get("started_at", "startsAt", "timestamp", "created_at")
    source = get("provider", "source", "source_type") or (
        "alertmanager" if labels or annotations else "pagerduty" if payload else "generic")
    raw = " ".join(str(x) for x in [severity, signal] + tags +
                   [str(v) for v in annotations.values() if isinstance(v, (str, int, float))])
    if not raw.strip():
        raw = json.dumps(data, sort_keys=True)[:1000]
    return {"severity": severity, "signal": signal, "service": service, "id": ident,
            "started": started, "source": source, "raw": raw}


def classify(alert):
    """Normalise any alert payload into a severity, service and redacted signal."""
    data = _flatten(alert)
    raw = data["raw"]
    sev = None
    for name, rx in KEYWORDS:
        if re.search(rx, raw, re.I):
            sev = name
            break
    match = re.search(r"\b(sev-?[1-4]|p[0-3])\b", raw, re.I)
    if match:
        explicit = match.group(1).lower().replace("-", "").replace("sev", "SEV")
        explicit = explicit.upper() if explicit.lower().startswith("p") else explicit
        mapping = {"P0": "SEV1", "P1": "SEV2", "P2": "SEV3", "P3": "SEV4"}
        sev = mapping.get(explicit, explicit)
    if sev not in SEVERITY_ORDER:
        sev = "SEV3"
    service = data["service"] or "unknown-service"
    signal = data["signal"] or raw[:500]
    canonical = json.dumps({"service": str(service), "signal": str(signal)[:500]}, sort_keys=True)
    incident_id = _clean(data["id"] or "INC-" + hashlib.sha256(canonical.encode()).hexdigest()[:10].upper(), 80)
    return {
        "task": "incident",
        "incident_id": incident_id,
        "severity": sev,
        "service": _clean(service, 80),
        "signal": _clean(signal, 500),
        "source": _clean(data["source"], 60),
        "started_at": _clean(data["started"] or time.strftime("%Y-%m-%dT%H:%M:%S%z"), 60),
    }


def _recent_commits(root, count=5):
    if not root or not gitutil.is_repo(root):
        return []
    out = gitutil.git(root, "log", f"-n {count}", "--format=%h%x1f%an%x1f%s", check=False)
    rows = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            rows.append({"commit": parts[0], "author": _clean(parts[1], 60), "subject": _clean(parts[2], 160)})
    return rows


def _recent_decisions(home, count=5):
    if not home:
        return []
    try:
        entries = A.AuditLog(home).entries()
    except Exception:
        return []
    rows = []
    for e in entries[-40:]:
        if e.get("event") in ("review", "ci", "agent-workflow", "optimize", "diagnose"):
            rows.append({"seq": e.get("seq"), "event": e.get("event"),
                         "decision": e.get("decision"), "detail": _clean(e.get("detail"), 120)})
    return rows[-count:]


def _playbook(sev):
    common = [
        "Acknowledge the alert and name an incident commander (human).",
        "Preserve evidence: capture the alert, CI log and current commit SHA in the audit ledger.",
        "Freeze deploys until the likely trigger is identified.",
        "Run `repobrain agent --task diagnose --log <ci-log>` for failed-build signal correlation.",
        "Publish a short status update at the next checkpoint; do not guess root cause.",
    ]
    if sev == "SEV1":
        return ["Page the on-call leads and open a bridge immediately."] + common + [
            "Identify the last deploy and prepare a rollback for human approval.",
            "Do not apply RepoBrain optimizer changes during the incident."]
    if sev == "SEV2":
        return ["Notify the service owner and open an incident thread."] + common + [
            "Compare the failing metrics with the latest merged PR and rollback candidate."]
    return ["Assign an owner and attach the alert to the incident queue."] + common[:4]


def run(alert, root=None, policy=None, base=None, home=None, log=None):
    """Produce a first-response brief. Never pages, rolls back or changes repository code."""
    info = classify(alert)
    hypotheses = []
    exp = explainer.explain(info["signal"] + "\n" + str((_as_dict(alert)).get("log", ""))[:5000])
    for m in exp.get("findings", [])[:3]:
        hypotheses.append({"kind": "log-pattern", "title": _clean(m.get("title"), 120),
                           "cause": _clean(m.get("cause"), 240), "fix": _clean(m.get("fix"), 240)})
    commits = _recent_commits(root)
    if commits:
        hypotheses.append({"kind": "recent-change", "title": "Recent commits are candidate triggers",
                           "cause": "; ".join(f"{c['commit']} {c['subject']}" for c in commits[:3]),
                           "fix": "Compare with the last known-good SHA before any rollback."})
    decisions = _recent_decisions(home)
    result = dict(info)
    result.update({
        "status": "triaged",
        "hypotheses": hypotheses,
        "recent_commits": commits,
        "recent_decisions": decisions,
        "playbook": _playbook(info["severity"]),
        "manual_actions": ["Page / open bridge", "Freeze deploys", "Approve rollback", "External status update"],
        "automations": ["Severity classification", "Redacted evidence capture", "Audit ledger entry", "Incident brief persisted"],
        "acknowledged_by": None,
        "acknowledged_at": None,
        "head": gitutil.head(root) if root and gitutil.is_repo(root) else None,
        "next_actions": _playbook(info["severity"])[:3],
    })

    if home:
        token = re.sub(r"[^A-Za-z0-9_.-]", "_", str(result["incident_id"]))[:80]
        folder = os.path.join(home, "incidents")
        os.makedirs(folder, exist_ok=True)
        brief_path = os.path.join(folder, token + ".json")
        with open(brief_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        result["brief_path"] = brief_path
    if log is not None:
        log.append("incident", "repobrain", info["severity"], f"{info['incident_id']} {info['service']}: {info['signal'][:120]}")
    return result


def acknowledge(brief, actor, log=None):
    """Human acknowledgement is recorded; it does not authorise automated remediation."""
    name = _clean(actor, 80)
    if len(name) < 2:
        raise ValueError("an incident acknowledgement needs a named human actor")
    out = dict(brief)
    out["acknowledged_by"] = name
    out["acknowledged_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    path = out.get("brief_path")
    if path and os.path.isfile(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
    if log is not None:
        log.append("incident-ack", name, "ACKNOWLEDGED", f"{out.get('incident_id')} acknowledged by {name}")
    return out


def to_markdown(i):
    lines = [f"## Initial on-call response — {i['incident_id']} ({i['severity']})",
             f"- Service: {i['service']} · source: {i['source']} · since {i['started_at']}",
             f"- Signal: {i['signal']}",
             f"- Status: {i['status']} · acknowledged by: {i['acknowledged_by'] or 'not yet'}", ""]
    if i["hypotheses"]:
        lines.append("Hypotheses:")
        for h in i["hypotheses"][:5]:
            lines.append(f"  - **{h['title']}** ({h['kind']}) — {h['cause']}")
        lines.append("")
    lines.append("First-hour playbook:")
    lines += [f"  1. {s}" for s in i["playbook"]]
    lines.append("")
    lines.append("Automated: " + ", ".join(i["automations"]))
    lines.append("Human-only: " + ", ".join(i["manual_actions"]))
    return "\n".join(lines)
