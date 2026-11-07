"""Markdown output: PR comment, compliance report, and HTML audit report."""
import html
import json
import pathlib
from . import audit

ICON = {"BLOCKED": "⛔", "CHANGES_REQUIRED": "🟠", "ALLOWED": "✅"}


def pr_comment(rev, prop=None):
    c = rev["counts"]
    L = [f"## {ICON.get(rev['decision'], '')} RepoBrain: {rev['decision'].replace('_', ' ')}",
         f"_{rev['reason']}_", "",
         f"`{rev['base']}` → `{rev['head'][:8]}` · {c['files']} files ({c['ai_files']} AI-authored) · "
         f"{c['blocks']} blocking · {c['warnings']} warnings · {c['gate']} complexity violations", ""]
    blocks = [f for f in rev["findings"] if f["severity"] == "block"]
    warns = [f for f in rev["findings"] if f["severity"] == "warn"]
    if blocks:
        L += ["### Blocking", "| File | Line | Rule | Detail |", "|---|---|---|---|"]
        L += [f"| `{f['file']}` | {f.get('line', '')} | {f['rule']} | {f.get('msg', f.get('message', ''))} |" for f in blocks]
        L.append("")
    if rev["gate"]:
        L += ["### Complexity gate", "| Function | cyclomatic | cognitive | depth | Why |", "|---|---|---|---|---|"]
        L += [f"| `{g['file']}::{g['name']}` | {g.get('cc', g.get('complexity', ''))} | {g.get('cog', g.get('cognitive', ''))} | {g['depth']} | {'; '.join(g.get('why', []))} |"
              for g in rev["gate"]]
        L.append("")
    if warns:
        L += ["### Warnings"] + [f"- `{f['file']}` ({f['rule']}): {f.get('msg', f.get('message', ''))}" for f in warns] + [""]
    if prop and prop.get("files"):
        cov = prop.get("coverage", {})
        cov_note = ""
        if cov.get("available") and cov.get("uncovered_functions"):
            pct = cov.get("percent", 0)
            uncov = ", ".join(f"`{fn}`" for fn in cov["uncovered_functions"])
            cov_note = f" · coverage **{pct:.0f}%** · uncovered rewritten functions: {uncov}"
        elif cov.get("available"):
            pct = cov.get("percent", 0)
            cov_note = f" · coverage **{pct:.0f}%**"
        L += [f"### Proposed cleanup · tests: **{prop['status']}**{cov_note}", "| File | max cognitive | max depth | lines |", "|---|---|---|---|"]
        for f in prop["files"]:
            b, a = f["metrics"]["before"], f["metrics"]["after"]
            L.append(f"| `{f['path']}` | {b.get('max_cog', 0)} → {a.get('max_cog', 0)} | {b.get('max_depth', 0)} → {a.get('max_depth', 0)} | {b.get('loc', 0)} → {a.get('loc', 0)} |")
        L.append("")
    L.append("<sub>Policy is read from the trusted base branch. Merge still requires human approval.</sub>")
    return "\n".join(L)


def compliance(rev, entries, chain, policy):
    L = ["# RepoBrain compliance report", "",
         f"- Branch `{rev['branch']}` @ `{rev['head'][:8]}` vs `{rev['base']}`",
         f"- Decision: **{rev['decision']}** - {rev['reason']}",
         f"- Policy source: {rev.get('policy_source', '')}",
         f"- Audit chain: **{'VERIFIED' if chain['ok'] else 'BROKEN'}** ({chain['count']} entries, head `{str(chain.get('head', ''))[:16]}`)", "",
         "## Policy in force", "```"]
    L += [f"{k}: {v}" for k, v in policy.items() if not k.startswith("_")]
    L += ["```", "", "## Files", "| File | Status | AI-authored | Actors |", "|---|---|---|---|"]
    L += [f"| `{f['path']}` | {f['status']} | {'yes' if f['ai'] else 'no'} | {', '.join(f['actors'])} |" for f in rev["files"]]
    L += ["", "## Audit trail", "| # | Time | Event | Actor | Decision | Detail |", "|---|---|---|---|---|---|"]
    L += [f"| {e.get('seq')} | {e.get('ts')} | {e.get('event')} | {e.get('actor')} | {e.get('decision')} | {str(e.get('detail'))[:90]} |"
          for e in entries]
    return "\n".join(L)


def build(home):
    home = pathlib.Path(home)
    rows, chain = audit.read(home), audit.verify_detail(home)
    status = ("<b style='color:#2e7d32'>Chain verified</b>" + (" (HMAC-signed)" if chain["signed"] else "")) if chain["ok"] else \
        f"<b style='color:#c62828'>TAMPERING DETECTED at record #{chain['bad_index']}: {html.escape(chain['reason'])}</b>"
    body = "".join(
        f"<tr><td>{r.get('seq', '')}</td><td>{html.escape(str(r.get('ts', '')))}</td><td>{html.escape(str(r.get('event', '')))}</td><td class='d-{html.escape(str(r.get('decision', '')).split('+')[0])}'>{html.escape(str(r.get('decision', '')))}</td>"
        f"<td>{html.escape(str(r.get('actor', '')))}</td><td><code>{html.escape(json.dumps(r.get('detail', '')))[:300]}</code></td><td><code>{str(r.get('hash', ''))[:10]}</code></td></tr>"
        for r in reversed(rows))
    page = f"""<!doctype html><meta charset=utf-8><title>RepoBrain audit report</title>
<style>body{{font:14px system-ui;margin:40px auto;max-width:1000px;color:#16161d}}table{{border-collapse:collapse;width:100%}}
td,th{{border-bottom:1px solid #e3e3ea;padding:6px 8px;text-align:left;vertical-align:top}}th{{background:#f4f2fb}}code{{font-size:12px}}
.d-block,.d-rejected,.d-invalidated{{color:#c62828;font-weight:600}}.d-approved,.d-allow{{color:#2e7d32;font-weight:600}}</style>
<h1>RepoBrain audit report</h1><p>{status}. {len(rows)} records. Each record commits to the previous one with SHA-256.</p>
<table><tr><th>#</th><th>Time (UTC)</th><th>Event</th><th>Decision</th><th>Actor</th><th>Detail</th><th>Hash</th></tr>{body}</table>"""
    out = home / "report.html"
    home.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    return out
