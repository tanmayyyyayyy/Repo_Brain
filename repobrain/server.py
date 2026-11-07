"""Local review console + agent preflight API. Standard library + PyYAML only.
Binds to 127.0.0.1, requires a per-run token or X-RepoBrain header on /api calls,
validates the Host header (DNS-rebinding) and only accepts JSON POSTs (CSRF)."""
import json
import os
import pathlib
import secrets
import shutil
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import audit as A
from . import demo, deps, explainer, export, gitutil, llm, optimizer, report, review, risk, shield
from . import policy as P
from .review import TEST_RX

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "index.html")
LOCK = threading.RLock()


class Ctx:
    def __init__(self, root, base, home, is_demo):
        self.root, self.base, self.home, self.demo = root, base, home, is_demo
        self.log = A.AuditLog(home)
        self.last_proposal = None

    def policy(self):
        return P.load_for(self.root, self.base)


def strip(prop):
    if not prop:
        return prop
    p = dict(prop)
    p["files"] = [{k: v for k, v in f.items() if k not in ("before", "after")} for f in prop["files"]]
    return p


def preflight(root, actor, files):
    """Vendor-neutral agent hook: ask BEFORE writing. files: [{path, content}]. Returns a decision."""
    root_path = pathlib.Path(root)
    pol = P.load_for(str(root_path))
    findings, gate, ai = [], [], shield.is_ai(actor, pol)
    for f in files[:50]:
        if isinstance(f, str):
            f = {"path": f}
        path = str(f.get("path", ""))[:300]
        content = f.get("content")
        if content is None:
            disk_p = root_path / path
            if disk_p.is_file():
                try:
                    content = disk_p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    content = ""
            else:
                content = ""
        content = str(content)[:400_000]
        if not path or path.startswith("/") or ".." in pathlib.PurePath(path).parts:
            findings.append(dict(severity="block", rule="blocked-path", file=path or "?", line=0, evidence="",
                                 msg="path escapes the repository", message="path escapes the repository"))
            continue
        if shield.ignored(path, pol):
            continue
        hit = shield.blocked_by(path, pol)
        if hit:
            findings.append(dict(severity="block" if ai else "warn", rule="blocked-path", file=path, line=0, evidence=hit,
                                 msg=f"{'AI actor' if ai else 'Change'} touches protected path '{hit}'",
                                 message=f"{'AI actor' if ai else 'Change'} touches protected path '{hit}'"))
        findings += shield.scan_text(path, content, pol, actor)
        if pol.get("dependency_guard", True) and deps.is_manifest(path):
            ls = [(n, t) for n, t in enumerate(content.split("\n"), 1)]
            for d in deps.check_added(path, ls, pol):
                findings.append(dict(severity="block" if ai else "warn", rule="dependency-risk", file=path, line=d["line"],
                                     msg=d["msg"], message=d["msg"], evidence=d["evidence"]))
        if path.endswith(".py"):
            try:
                gate += [{"file": path, **v} for v in optimizer.violations(optimizer.analyze(content), pol)]
            except SyntaxError:
                findings.append(dict(severity="warn", rule="syntax", file=path, line=0, evidence="",
                                     msg="file does not parse as Python", message="file does not parse as Python"))
    decision = "block" if any(f["severity"] == "block" for f in findings) else ("warn" if findings or gate else "allow")
    A.AuditLog(A.home_for(str(root_path))).append("preflight", actor, decision.upper(),
                                                 f"{len(files)} files checked: " + (", ".join(f['rule'] for f in findings[:5]) or "clean"))
    return {"decision": decision, "findings": findings, "gate": gate, "actor": actor, "ai_actor": ai}


def make_handler(ctx, token, port):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class H(BaseHTTPRequestHandler):
        server_version = "RepoBrain"

        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json", headers=None):
            data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body)).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'; connect-src 'self'")
            if headers:
                for k, v in headers.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _guard(self):
            if self.headers.get("Host", "") not in allowed_hosts:
                self._send(403, {"error": "bad host"}); return False
            tok_hdr = self.headers.get("X-RepoBrain-Token", "")
            has_valid_tok = bool(tok_hdr) and secrets.compare_digest(tok_hdr, token)
            has_x_hdr = (self.headers.get("X-RepoBrain") == "1")
            if self.path.startswith("/api/") and not (has_valid_tok or has_x_hdr):
                self._send(401, {"error": "missing or wrong token - open the URL printed by `repobrain serve`"}); return False
            return True

        def do_GET(self):
            if not self._guard():
                return
            u = urlparse(self.path)
            try:
                if u.path == "/":
                    with open(STATIC, "rb") as f:
                        return self._send(200, f.read(), "text/html")
                if u.path == "/api/state":
                    return self._send(200, state(ctx))
                if u.path == "/api/audit":
                    es = ctx.log.entries()
                    return self._send(200, {"entries": es, "chain": A.verify_entries(es)})
                if u.path == "/api/report.md":
                    with LOCK:
                        pol = ctx.policy()
                        rev = review.run(ctx.root, pol, ctx.base, ctx.home)
                        return self._send(200, report.compliance(rev, ctx.log.entries(), ctx.log.verify(), pol),
                                          "text/markdown")
                if u.path == "/api/export":
                    qs = parse_qs(u.query)
                    fmt = qs.get("fmt", ["json"])[0]
                    with LOCK:
                        pol = ctx.policy()
                        rev = review.run(ctx.root, pol, ctx.base, ctx.home)
                        finds = rev["findings"]
                        gate = rev["gate"]
                        if fmt == "sarif":
                            return self._send(200, export.sarif(finds, gate), "application/json",
                                              {"content-disposition": "attachment; filename=repobrain.sarif"})
                        if fmt == "md":
                            st = state(ctx)
                            st["files"] = rev["files"]
                            st["findings"] = finds
                            st["gate"] = gate
                            st["verdict"] = rev.get("verdict", "ready")
                            st["risk"] = rev.get("risk", {"score": 0, "level": "low", "factors": []})
                            st["proposal"] = ctx.last_proposal or {"changed": 0}
                            st["chain"] = ctx.log.verify()
                            return self._send(200, export.markdown(st).encode(), "text/markdown; charset=utf-8")
                        if fmt == "csv":
                            return self._send(200, export.audit_csv(list(reversed(ctx.log.entries()))).encode(), "text/csv; charset=utf-8",
                                              {"content-disposition": "attachment; filename=repobrain-audit.csv"})
                        if fmt == "html":
                            report_path = report.build(ctx.home)
                            return self._send(200, report_path.read_bytes(), "text/html; charset=utf-8")
                        return self._send(200, {"audit": list(reversed(ctx.log.entries())), "chain": ctx.log.verify()},
                                          "application/json", {"content-disposition": "attachment; filename=repobrain-audit.json"})
                if u.path == "/api/diff":
                    qs = parse_qs(u.query)
                    req_path = qs.get("path", [""])[0].strip()
                    if not req_path:
                        return self._send(400, {"error": "path parameter required"})
                    norm = os.path.normpath(req_path).replace("\\", "/")
                    if norm.startswith("..") or os.path.isabs(req_path) or req_path.startswith("/") or req_path.startswith("\\"):
                        return self._send(400, {"error": "path traversal refused"})
                    target = os.path.realpath(os.path.join(ctx.root, norm))
                    real_root = os.path.realpath(ctx.root)
                    if os.path.commonpath([real_root, target]) != real_root:
                        return self._send(403, {"error": "path escapes repository"})
                    changed = {p: s for s, p in gitutil.changed_files(ctx.root, ctx.base)}
                    if norm not in changed:
                        return self._send(404, {"error": f"file '{norm}' not in current change set"})
                    status = changed[norm]
                    diff_text = gitutil.git(ctx.root, "diff", "-u", f"{ctx.base}...HEAD", "--", norm, check=False)
                    if len(diff_text) > 500_000:
                        diff_text = diff_text[:500_000] + "\n... [diff truncated at 500KB limit]"
                    pol = ctx.policy()
                    rev = review.run(ctx.root, pol, ctx.base, ctx.home)
                    file_findings = [f for f in rev["findings"] if f["file"] == norm]
                    file_gate = [g for g in rev["gate"] if g["file"] == norm]
                    return self._send(200, {
                        "path": norm,
                        "status": status,
                        "diff": diff_text,
                        "findings": file_findings,
                        "gate": file_gate,
                        "base": ctx.base,
                        "head": gitutil.head(ctx.root),
                    })
                self._send(404, {"error": "not found"})
            except Exception as e:
                self._send(500, {"error": str(e)})

        def do_POST(self):
            if not self._guard():
                return
            if "application/json" not in self.headers.get("Content-Type", ""):
                return self._send(415, {"error": "JSON only"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > 2_000_000:
                return self._send(413, {"error": "body too large"})
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
                with LOCK:
                    self._send(200, route(ctx, urlparse(self.path).path, body))
            except (ValueError, gitutil.GitError, P.PolicyError, KeyError) as e:
                self._send(400, {"error": str(e)})
            except Exception as e:
                self._send(500, {"error": f"{type(e).__name__}: {e}"})

    return H


def state(ctx_or_root, base="main"):
    if isinstance(ctx_or_root, Ctx):
        ctx = ctx_or_root
    else:
        root = os.path.abspath(str(ctx_or_root))
        home = A.home_for(root)
        ctx = Ctx(root, base, home, False)

    pol = ctx.policy()
    try:
        yml = gitutil.show(ctx.root, ctx.base, "repobrain.yml") or open(os.path.join(ctx.root, "repobrain.yml")).read()
    except OSError:
        yml = ""

    rev = review.run(ctx.root, pol, ctx.base, ctx.home)
    head_sha = gitutil.head(ctx.root) if gitutil.is_repo(ctx.root) else ""
    branch_name = gitutil.branch(ctx.root) if gitutil.is_repo(ctx.root) else ""

    return {
        "root": ctx.root,
        "base": ctx.base,
        "branch": branch_name,
        "head": head_sha,
        "repo": {
            "path": ctx.root, "branch": branch_name, "head": head_sha,
            "base": ctx.base, "demo": ctx.demo, "scenarios": list(demo.SCENARIOS) if ctx.demo else []
        },
        "policy": {k: v for k, v in pol.items() if not k.startswith("_")},
        "policy_source": pol.get("_source"),
        "policy_yaml": yml,
        "llm": {**llm.describe(), "allowed": pol.get("allow_llm", False)},
        "files": rev["files"],
        "findings": rev["findings"],
        "gate": rev["gate"],
        "verdict": rev["verdict"],
        "risk": rev["risk"],
        "blocking": rev["counts"]["blocks"],
        "proposal": ctx.last_proposal or {"changed": 0},
        "chain": ctx.log.verify()
    }


def route(ctx, path, body):
    actor = str(body.get("actor", "")).strip()[:80]
    if path == "/api/review":
        pol = ctx.policy()
        rev = review.run(ctx.root, pol, ctx.base, ctx.home, body.get("pr_author"))
        review.log_review(ctx.log, rev)
        return rev
    if path == "/api/optimize":
        pol, rev = ctx.policy(), None
        rev = review.run(ctx.root, pol, ctx.base, ctx.home)
        files = [f["path"] for f in rev["files"] if f["status"] != "D" and f["path"].endswith(".py")
                 and not TEST_RX.search(f["path"]) and not f["path"].endswith("__init__.py")]
        prop = optimizer.propose(ctx.root, pol, files, ctx.home, use_llm=bool(body.get("ai")))
        ctx.log.append("optimize", "repobrain", prop["status"], f"{len(prop['files'])} file(s) proposed, id {prop['id']}",
                       head=prop["head"])
        ctx.last_proposal = prop["id"]
        return strip(prop)
    if path == "/api/approve":
        if not actor:
            raise ValueError("approver name is required (a human approves)")
        res = optimizer.apply(ctx.root, ctx.home, body["id"], actor)
        ctx.log.append("approve", actor, "APPLIED", f"{', '.join(res['applied'])} -> {str(res['commit'])[:8]}", head=res["commit"])
        return res
    if path == "/api/waive":
        if not actor:
            raise ValueError("waiver name is required")
        w = review.waive(ctx.home, gitutil.head(ctx.root), actor, str(body.get("reason", "")))
        ctx.log.append("waive", actor, "WAIVED", w["reason"], head=gitutil.head(ctx.root))
        return w
    if path == "/api/shield":
        res = shield.check_action({"actor": str(body.get("actor", "")), "path": str(body.get("path", "")),
                                   "content": str(body.get("content", ""))}, ctx.policy())
        ctx.log.append("shield-check", str(body.get("actor", "") or "unknown")[:60], res["decision"],
                       f"{body.get('path', '')}: " + (", ".join(f['rule'] for f in res['findings']) or "clean"))
        return res
    if path == "/api/explain":
        pol = ctx.policy()
        ask = llm.ask if body.get("ai") and pol.get("allow_llm") and llm.available() else None
        res = explainer.explain(str(body.get("log", ""))[:200_000], ask)
        ctx.log.append("explain", "repobrain", "EXPLAINED", res["summary"])
        return res
    if path == "/api/preflight":
        actor_name = str(body.get("actor", "unknown-agent"))[:80]
        files = body.get("files", [])
        return preflight(ctx.root, actor_name, files)
    if path == "/api/audit/tamper":
        return A.simulate_tamper(ctx.log.entries())
    if path == "/api/scenario" and ctx.demo:
        demo.switch(ctx.root, body["name"])
        ctx.base = demo.SCENARIO_BASES.get(body["name"], "main")
        return {"branch": gitutil.branch(ctx.root), "base": ctx.base}
    if path == "/api/reset" and ctx.demo:
        demo.seed(ctx.root)
        shutil.rmtree(ctx.home, ignore_errors=True)
        ctx.log = A.AuditLog(ctx.home)
        return {"ok": True}
    if path == "/api/webhook":
        from . import webhook
        return webhook.handle_event(body.get("event", "ping"), body)
    raise KeyError("unknown endpoint")


def serve(a_or_repo=None, base="main", port=8765, open_browser=False, demo_mode=False):
    if hasattr(a_or_repo, "repo"):
        a = a_or_repo
        root = os.path.abspath(a.repo)
        is_demo = getattr(a, "demo", False)
        port = a.port
        open_browser = not getattr(a, "no_browser", False)
        base = getattr(a, "base", None)
        home = getattr(a, "home", None)
    else:
        root = os.path.abspath(a_or_repo or ".")
        is_demo = demo_mode
        home = None

    if is_demo:
        base_dir = os.environ.get("REPOBRAIN_DEMO_DIR") or os.path.join(os.path.expanduser("~"), ".repobrain", "demo")
        root, home = os.path.join(base_dir, "repo"), os.path.join(base_dir, "home")
        demo.seed(root)
        shutil.rmtree(home, ignore_errors=True)
        base = "main"
    else:
        base = gitutil.resolve_base(root, base) if gitutil.is_repo(root) else (base or "main")
        home = os.path.abspath(home) if home else A.home_for(root)

    ctx = Ctx(root, base, home, is_demo)
    token = secrets.token_urlsafe(24)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(ctx, token, port))
    url = f"http://127.0.0.1:{port}/?t={token}"
    print(f"RepoBrain console  ({'demo repo' if is_demo else root})\n  {url}\n  Ctrl+C to stop", flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
