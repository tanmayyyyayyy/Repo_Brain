"""RepoBrain CLI.  python -m repobrain <command>"""
import argparse
import json
import os
import pathlib
import sys

from . import audit as A
from . import demo, explainer, export, gitutil, hooks, llm, metrics, mlguard, optimizer, report, review, server, shield
from . import policy as P

TEST_RX = review.TEST_RX


def _root(a):
    return os.path.abspath(getattr(a, "repo", None) or ".")


def _ctx(a):
    root = _root(a)
    base = None
    if gitutil.is_repo(root):
        try:
            base = gitutil.resolve_base(root, getattr(a, "base", None))
        except gitutil.GitError:
            base = None
    pol = P.load_for(root, base)
    home = os.path.abspath(a.home) if getattr(a, "home", None) else A.home_for(root)
    return root, base, pol, home, A.AuditLog(home)


def _py_files(root):
    out = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in optimizer.SKIP_DIRS]
        for f in fn:
            rel = os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/")
            if f.endswith(".py") and not TEST_RX.search(rel) and f != "__init__.py" and f != "conftest.py":
                out.append(rel)
    return sorted(out)


def cmd_init(a):
    dst = os.path.join(a.repo, "repobrain.yml")
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "repobrain.yml")
    if os.path.exists(dst):
        print("repobrain.yml already exists"); return 1
    with open(src, encoding="utf-8") as f, open(dst, "w", encoding="utf-8") as g:
        g.write(f.read())
    print("wrote repobrain.yml - commit it to your default branch so PRs cannot change it")
    return 0


def cmd_review(a):
    root, base, pol, home, log = _ctx(a)
    rev = review.run(root, pol, base, home, a.actor)
    review.log_review(log, rev)
    md = report.pr_comment(rev)
    if a.comment:
        with open(a.comment, "w", encoding="utf-8") as f:
            f.write(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md + "\n")
    print(json.dumps(rev, indent=2) if a.json else md)
    return 0 if rev["decision"] == "ALLOWED" else 1


def cmd_scan(a):
    root, _, pol, _, _ = _ctx(a)
    rows = []
    for rel in _py_files(root):
        try:
            src = open(os.path.join(root, rel), encoding="utf-8").read()
            rows += [dict(f, file=rel) for f in metrics.violations(metrics.analyze(src), pol)]
        except (SyntaxError, UnicodeDecodeError):
            pass
    rows.sort(key=lambda r: -r["cog"])
    print(f"{len(rows)} function(s) over policy limits")
    for r in rows:
        print(f"  {r['file']}::{r['name']:<28} cc={r['cc']:<3} cog={r['cog']:<3} depth={r['depth']}  ({'; '.join(r['why'])})")
    return 0


def cmd_shield(a):
    root, base, pol, home, log = _ctx(a)
    if getattr(a, "path", None):
        content = open(a.file, encoding="utf-8").read() if getattr(a, "file", None) else ""
        res = shield.check_action({"actor": a.actor, "path": a.path, "content": content}, pol)
        log.append("shield-check", a.actor, res["decision"], f"{a.path}: " + (", ".join(f["rule"] for f in res["findings"]) or "clean"))
        print(json.dumps(res, indent=2))
        return 0 if res["decision"] == "ALLOWED" else 1

    files = getattr(a, "files", []) or []
    if base and not files:
        files = [p for s, p in gitutil.changed_files(root, base)]
    added = gitutil.added_lines(root, base) if base else None
    finds = shield.check(root, files, pol, a.actor, added=added)
    A.log(home, "shield", "block" if any(f["severity"] == "block" for f in finds) else "pass", a.actor, {"findings": len(finds)})
    if getattr(a, "sarif", None):
        pathlib.Path(a.sarif).write_text(json.dumps(export.sarif(finds, []), indent=1))
    for f in finds:
        print(f"{f['severity'].upper():5} {f['rule']:18} {f['file']}:{f.get('line') or ''}  {f.get('msg', f.get('message', ''))}")
    return 1 if any(f["severity"] == "block" for f in finds) else 0


def cmd_gate(a):
    root, base, pol, _, _ = _ctx(a)
    bad = optimizer.gate(root, pol, base=getattr(a, "base", None))
    for b in bad:
        print(f"GATE  {b['file']}::{b['name']}()  {', '.join(b['why'])}")
    return 1 if bad else 0


def cmd_optimize(a):
    root, base, pol, home, log = _ctx(a)
    if a.all or not base:
        files = _py_files(root)
    else:
        files = [p for s, p in gitutil.changed_files(root, base)
                 if s != "D" and p.endswith(".py") and not TEST_RX.search(p) and not p.endswith("__init__.py")]
    prop = optimizer.propose(root, pol, files, home, use_llm=a.ai)
    log.append("optimize", "repobrain", prop["status"], f"{len(prop['files'])} file(s) proposed, id {prop['id']}")
    print(f"status: {prop['status']}   tests: {prop['tests'].get('ok')}  ({prop['tests'].get('cmd', '')})")
    if prop["llm"]["requested"]:
        print(f"llm: used={prop['llm']['used']} {prop['llm']['reason']}")
    for f in prop["files"]:
        b, af = f["metrics"]["before"], f["metrics"]["after"]
        print(f"  {f['path']}: cognitive {b['max_cog']}->{af['max_cog']}  depth {b['max_depth']}->{af['max_depth']}  "
              f"lines {b['loc']}->{af['loc']}  rules={f['notes']}")
        if a.diff:
            print(f["diff"])
    for s in prop["skipped"]:
        print(f"  skipped {s.get('file', '')}::{s['function']}: {s['reason']}")
    if a.apply:
        if not a.actor:
            print("--apply needs --actor <your name> (a human approves)"); return 2
        res = optimizer.apply(root, home, prop["id"], a.actor)
        log.append("approve", a.actor, "APPLIED", f"{', '.join(res['applied'])} -> {res['commit']}", head=res["commit"])
        print("applied:", res)
    return 0 if prop["status"] in ("verified", "nothing-to-optimize") else 1


def cmd_explain(a):
    log_file = getattr(a, "log", None)
    if log_file and log_file != "-":
        if os.path.isfile(log_file):
            log_text = open(log_file, encoding="utf-8", errors="replace").read()
        else:
            log_text = log_file
    else:
        log_text = sys.stdin.read()
    ask = None
    _, _, pol, _, _ = _ctx(a)
    if a.ai and pol.get("allow_llm") and llm.available():
        ask = llm.ask
    res = explainer.explain(log_text, ask)
    print(json.dumps(res, indent=2))
    return 0


def cmd_audit(a):
    _, _, _, _, log = _ctx(a)
    expect = getattr(a, "expect", None)
    if not expect and getattr(a, "anchor_file", None) and os.path.isfile(a.anchor_file):
        try:
            expect = open(a.anchor_file, encoding="utf-8").read().strip()
        except OSError as exc:
            print(f"repobrain: cannot read anchor file: {exc}", file=sys.stderr)
            return 2
    v = log.verify(expect)
    if getattr(a, "write_anchor", None):
        head = v.get("head") or ""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(a.write_anchor)), exist_ok=True)
            with open(a.write_anchor, "w", encoding="utf-8") as f:
                f.write(head + "\n")
            print(f"anchor written: {head[:16]}… -> {a.write_anchor}")
        except OSError as exc:
            print(f"repobrain: cannot write anchor file: {exc}", file=sys.stderr)
            return 2
    if getattr(a, "export", False):
        print(json.dumps({"verification": v, "entries": log.entries()}, indent=2))
    else:
        tail_count = getattr(a, "tail", 25)
        for e in log.entries()[-tail_count:]:
            print(f"#{e.get('seq', ''):<4} {e.get('ts', '')}  {e.get('event', ''):<10} {e.get('decision', ''):<17} {str(e.get('actor', ''))[:30]:<30} {str(e.get('detail', ''))[:70]}")
        is_signed = bool(v.get("hmac_signed") or v.get("signed"))
        mode_str = "HMAC-signed" if is_signed else "hash-only (unsigned)"
        print("chain:", "VERIFIED" if v["ok"] else f"BROKEN at #{v.get('broken_at')} - {v.get('reason')}", f"[{mode_str}]", f"head={str(v.get('head'))[:16]}")
        if not is_signed:
            print("note: Chain is hash-linked (SHA-256) but unsigned; an attacker with write access to the log could recompute hashes. Set REPOBRAIN_AUDIT_KEY to sign entries.")
    return 0 if v["ok"] else 1


def cmd_waive(a):
    root, base, pol, home, log = _ctx(a)
    w = review.waive(home, gitutil.head(root), a.actor, a.reason)
    log.append("waive", a.actor, "WAIVED", w["reason"], head=gitutil.head(root))
    print("waived:", w)
    return 0


def cmd_report(a):
    root, base, pol, home, log = _ctx(a)
    rev = review.run(root, pol, base, home)
    md = report.compliance(rev, log.entries(), log.verify(), {k: v for k, v in pol.items()})
    if getattr(a, "out", None):
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)
        print("wrote", a.out)
    else:
        print(md)
    return 0


def cmd_serve(a):
    return server.serve(a)


def cmd_demo(a):
    """Run the whole story in the terminal (no browser needed)."""
    base_dir = os.environ.get("REPOBRAIN_DEMO_DIR") or os.path.join(os.path.expanduser("~"), ".repobrain", "demo")
    root, home = os.path.join(base_dir, "repo"), os.path.join(base_dir, "home")
    demo.seed(root)
    base = "main"
    print("== 1. Shield + gate on an AI-authored PR ==")
    st = server.state(root, base)
    for f in st["files"]:
        for x in f["findings"]:
            print(f"  {x['severity'].upper():5} {x['rule']:18} {f['path']}:{x.get('line') or ''}  {x.get('msg', x.get('message', ''))}")
    print(f"  verdict: {st['verdict'].upper()}   merge risk: {st['risk']['score']}/100 ({st['risk']['level']})")
    print("== 2. Optimizer (tests + differential fuzz) ==")
    p = optimizer.propose(root, P.load_for(root, base), [f["path"] for f in st["files"] if f["path"].endswith(".py")], home)
    fuzz_str = str(p.get("fuzz")) if p.get("fuzz") else "none"
    print(f"  {p['status']}  tests={p['tests'] and p['tests']['ok']} runner={p['tests'] and p['tests'].get('runner')}  fuzz={fuzz_str}")
    if getattr(a, "approve", False):
        print("== 3. Human approval applies the verified simplification ==")
        if p["files"]:
            applied = optimizer.apply(root, home, p["id"], "demo-reviewer")
            print(" ", applied)
        print("  gate violations now:", len(optimizer.gate(root, P.load_for(root, base))))
    print("== Audit chain ==", A.verify_detail(home))
    return 0


def cmd_preflight(a):
    content = pathlib.Path(a.content_file).read_text(encoding="utf-8") if getattr(a, "content_file", None) else ""
    r = server.preflight(_root(a), a.actor, [{"path": a.path, "content": content}])
    print(json.dumps(r, indent=2))
    return 1 if r["decision"] == "block" else 0


def cmd_ml_eval(a):
    print(json.dumps(mlguard.evaluate(shield.injection_rule_hit), indent=2))
    return 0


def cmd_hook(a):
    print("installed", hooks.install(_root(a)))
    return 0


def cmd_hook_check(a):
    return hooks.check(_root(a))


def cmd_ci(a):
    """One command for CI: shield + gate + optimizer proposal -> SARIF + Markdown summary + exit code."""
    root = _root(a)
    st = server.state(root, getattr(a, "base", "main"))
    finds = [x for f in st["files"] for x in f["findings"] if not x.get("waived")]
    if getattr(a, "sarif", None):
        pathlib.Path(a.sarif).write_text(json.dumps(export.sarif(finds, st["gate"]), indent=1))
    md = export.markdown(st)
    if getattr(a, "summary", None):
        pathlib.Path(a.summary).write_text(md)
    print(md)
    A.log(A.home_for(root), "ci", st["verdict"], a.actor, {"risk": st["risk"]["score"], "blocking": st["blocking"]})
    return 0 if st["verdict"] == "ready" else 1


def build():
    ap = argparse.ArgumentParser(prog="repobrain", description=__doc__)
    ap.add_argument("--repo", default=".", help="repository path (default: .)")
    ap.add_argument("--home", help="where audit log/proposals live (default ~/.repobrain/<repo-hash>)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, **kw):
        sp = sub.add_parser(name, **kw)
        sp.set_defaults(fn=fn)
        return sp

    add("init", cmd_init, help="write a starter repobrain.yml")
    sp = add("review", cmd_review, help="Shield + complexity gate on the PR diff (CI entry point)")
    sp.add_argument("--base"); sp.add_argument("--actor", help="extra identity to treat as the author (e.g. PR opener)")
    sp.add_argument("--comment", help="write PR-comment markdown here"); sp.add_argument("--json", action="store_true")
    add("scan", cmd_scan, help="list over-limit functions across the whole repo (tech debt)")

    sp = add("shield", cmd_shield, help="check files or a proposed action")
    sp.add_argument("--path", help="target path for check_action"); sp.add_argument("--actor", default="unknown")
    sp.add_argument("--file", help="file containing content to check"); sp.add_argument("--base", help="base git ref")
    sp.add_argument("--sarif", help="write findings to SARIF file"); sp.add_argument("files", nargs="*", default=[])

    sp = add("gate", cmd_gate, help="check complexity gate violations")
    sp.add_argument("--base")

    sp = add("optimize", cmd_optimize, help="propose a test-verified cleanup")
    sp.add_argument("--base"); sp.add_argument("--all", action="store_true"); sp.add_argument("--ai", action="store_true")
    sp.add_argument("--diff", action="store_true"); sp.add_argument("--apply", action="store_true")
    sp.add_argument("--actor", help="approving human (required with --apply)")

    sp = add("explain", cmd_explain, help="explain a failing log (stdin or --log)")
    sp.add_argument("log", nargs="?", default=None); sp.add_argument("--ai", action="store_true")

    sp = add("audit", cmd_audit, help="show / verify / export the audit log")
    sp.add_argument("--expect", help="anchored head hash to verify against"); sp.add_argument("--export", action="store_true")
    sp.add_argument("--tail", type=int, default=25)
    sp.add_argument("--anchor-file", dest="anchor_file",
                    help="path to a file containing the anchored head hash (written by --write-anchor)")
    sp.add_argument("--write-anchor", dest="write_anchor",
                    help="after verification, write the current head hash to this file")

    sp = add("waive", cmd_waive, help="human override of the complexity gate (logged)")
    sp.add_argument("--actor", required=True); sp.add_argument("--reason", required=True)

    sp = add("report", cmd_report, help="compliance report (markdown)"); sp.add_argument("--base"); sp.add_argument("--out")

    sp = add("serve", cmd_serve, help="review console (localhost by default)")
    sp.add_argument("--base"); sp.add_argument("--port", type=int, default=None)
    sp.add_argument("--host", help="bind address (default 127.0.0.1; use 0.0.0.0 to expose)")
    sp.add_argument("--open", action="store_true", help="open demo mode: no per-run API token")
    sp.add_argument("--demo", action="store_true", help="seed a demo git repo with AI-authored PRs")
    sp.add_argument("--no-browser", action="store_true")

    sp = add("demo", cmd_demo, help="run the full story in the terminal")
    sp.add_argument("--approve", action="store_true")

    sp = add("preflight", cmd_preflight, help="vendor-neutral preflight check")
    sp.add_argument("--actor", required=True); sp.add_argument("--path", required=True); sp.add_argument("--content-file")

    add("ml-eval", cmd_ml_eval, help="evaluate learned prompt injection classifier")
    add("install-hook", cmd_hook, help="install pre-commit hook")
    add("hook-check", cmd_hook_check, help="check staged changes")

    sp = add("ci", cmd_ci, help="one command for CI: shield + gate + optimizer")
    sp.add_argument("--base", default="main"); sp.add_argument("--actor", default="ci")
    sp.add_argument("--sarif"); sp.add_argument("--summary")

    return ap


def main(argv=None):
    a = build().parse_args(argv)
    try:
        rc = a.fn(a)
        return rc if isinstance(rc, int) else 0
    except (gitutil.GitError, P.PolicyError, ValueError) as e:
        print(f"repobrain: {e}", file=sys.stderr)
        return 2
