"""Review console + agent preflight API. Standard library + PyYAML only.
Binds to 127.0.0.1 by default and requires a per-run token or X-RepoBrain header on
/api calls. Set REPOBRAIN_HOST=0.0.0.0 (and REPOBRAIN_OPEN_DEMO=1) to serve the
sandboxed demo publicly. Host header is validated (DNS-rebinding), allowed hosts can
be extended with REPOBRAIN_ALLOWED_HOSTS (`*` for any), and POSTs must be JSON (CSRF)."""
import collections
import contextlib
import hashlib
import ipaddress
import json
import os
import pathlib
import re
import secrets
import shutil
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import audit as A
from . import auth, demo, deps, explainer, export, gitutil, llm, optimizer, report, review, risk, shield
from . import policy as P
from .review import TEST_RX

def find_index_html():
    """Locate the packaged index.html console, checking package directory, importlib.resources, and dev static fallback."""
    pkg_web = pathlib.Path(__file__).resolve().parent / "web" / "index.html"
    if pkg_web.is_file():
        return str(pkg_web)
    try:
        import importlib.resources as pkg_resources
        res = pkg_resources.files("repobrain.web").joinpath("index.html")
        if res.is_file():
            return str(res)
    except Exception:
        pass
    legacy = pathlib.Path(__file__).resolve().parent.parent / "static" / "index.html"
    if legacy.is_file():
        return str(legacy)
    return str(pkg_web)


def find_slides_html():
    """Locate the packaged 5-slide presentation deck for finals judges."""
    p = pathlib.Path(__file__).resolve().parent.parent / "docs" / "slides.html"
    return str(p) if p.is_file() else None


STATIC = find_index_html()
LOCK = threading.RLock()


def parse_trusted_proxies(env_val: str = None):
    val = env_val if env_val is not None else os.environ.get("REPOBRAIN_TRUSTED_PROXIES", "")
    networks = []
    for item in val.split(","):
        s = item.strip()
        if not s:
            continue
        try:
            networks.append(ipaddress.ip_network(s, strict=False))
        except ValueError:
            pass
    return networks


def is_ip_in_networks(ip_str: str, networks: list) -> bool:
    if not ip_str or not networks:
        return False
    try:
        ip = ipaddress.ip_address(ip_str.strip())
        return any(ip in net for net in networks)
    except ValueError:
        return False


def resolve_client_ip(handler) -> str:
    """Resolve the genuine client IP address.
    Forwarded headers (X-Forwarded-For / X-Real-IP) are ONLY trusted when the immediate
    socket peer is within REPOBRAIN_TRUSTED_PROXIES. In that case, the rightmost non-trusted
    IP in the chain is returned. Otherwise, the socket peer address is returned directly.
    """
    peer_ip = "unknown"
    if handler and getattr(handler, "client_address", None) and len(handler.client_address) > 0:
        peer_ip = str(handler.client_address[0]).strip()

    trusted_nets = parse_trusted_proxies()
    # If the direct peer is not in trusted proxies, ignore all forwarded headers completely
    if not is_ip_in_networks(peer_ip, trusted_nets):
        return peer_ip

    headers = getattr(handler, "headers", {}) or {}
    xff = headers.get("X-Forwarded-For", "").strip() if hasattr(headers, "get") else ""
    if xff:
        # Split and inspect right-to-left
        entries = [e.strip() for e in xff.split(",") if e.strip()]
        for entry in reversed(entries):
            # Check valid IP syntax
            try:
                ipaddress.ip_address(entry)
            except ValueError:
                continue
            if not is_ip_in_networks(entry, trusted_nets):
                return entry

    x_real = headers.get("X-Real-IP", "").strip() if hasattr(headers, "get") else ""
    if x_real:
        try:
            ipaddress.ip_address(x_real)
            if not is_ip_in_networks(x_real, trusted_nets):
                return x_real
        except ValueError:
            pass

    return peer_ip


class BoundedRateLimiter:
    """Thread-safe bounded in-memory sliding-window rate limiter with LRU key eviction."""

    def __init__(self, max_keys: int = 10000, window: int = 60, max_attempts: int = 5):
        self.max_keys = max_keys
        self.window = window
        self.max_attempts = max_attempts
        self._items = collections.OrderedDict()
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        if not key:
            return True
        now = time.time()
        with self._lock:
            # Get existing attempts or initialize
            attempts = [t for t in self._items.get(key, []) if now - t < self.window]
            if len(attempts) >= self.max_attempts:
                self._items[key] = attempts
                self._items.move_to_end(key)
                return False

            attempts.append(now)
            self._items[key] = attempts
            self._items.move_to_end(key)

            # Evict oldest key if exceeding capacity
            while len(self._items) > self.max_keys:
                self._items.popitem(last=False)
            return True

    def record_success(self, key: str):
        if not key:
            return
        with self._lock:
            self._items.pop(key, None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


LOGIN_LIMITER = BoundedRateLimiter(max_keys=10000, window=60, max_attempts=5)
PREFLIGHT_LIMITER = BoundedRateLimiter(max_keys=10000, window=60, max_attempts=60)


def check_login_rate(identifier: str) -> bool:
    return LOGIN_LIMITER.check(identifier)


def record_login_success(identifier: str):
    LOGIN_LIMITER.record_success(identifier)


class Ctx:
    MAX_DEMO_WORKSPACES = 50
    DEMO_WORKSPACE_TTL = 3600  # 1 hour

    def __init__(self, root, base, home, is_demo):
        self.root, self.base, self.home, self.demo = root, base, home, is_demo
        self.log = A.AuditLog(home)
        self.auth = auth.AuthManager(home, is_demo=is_demo)
        self.last_proposal = None
        self._session_roots = {}
        self._workspace_access = {}
        self._valid_demo_wids = set()
        self._workspace_refcounts = collections.defaultdict(int)
        self._lock = threading.RLock()

        # One-time bootstrap administrator from startup environment variables
        boot_email = os.environ.pop("REPOBRAIN_BOOTSTRAP_ADMIN_EMAIL", None)
        boot_pw = os.environ.pop("REPOBRAIN_BOOTSTRAP_ADMIN_PASSWORD", None)
        if boot_email and boot_pw:
            boot_email = boot_email.strip()
            has_admin = any(u.get("role") == "admin" for u in self.auth.list_users())
            if not has_admin and len(boot_pw) >= 12:
                try:
                    self.auth.bootstrap_admin(boot_email, boot_pw, name="Bootstrap Administrator", audit_log=self.log)
                except Exception:
                    pass

    def create_valid_wid(self) -> str:
        with self._lock:
            wid = secrets.token_hex(16)
            self._valid_demo_wids.add(wid)
            return wid

    def is_valid_wid(self, wid: str) -> bool:
        if not wid or not isinstance(wid, str):
            return False
        wid = wid.strip().lower()
        if not re.match(r"^[0-9a-f]{32}$", wid):
            return False
        with self._lock:
            return wid in self._valid_demo_wids

    def resolve_or_create_wid(self, candidate_wid: str = None) -> str:
        if candidate_wid and self.is_valid_wid(candidate_wid):
            return candidate_wid.strip().lower()
        return self.create_valid_wid()

    @contextlib.contextmanager
    def acquire_workspace(self, wid: str):
        if not wid:
            yield
            return
        with self._lock:
            self._workspace_refcounts[wid] += 1
        try:
            yield
        finally:
            with self._lock:
                self._workspace_refcounts[wid] = max(0, self._workspace_refcounts[wid] - 1)

    def _delete_workspace(self, k: str):
        dir_to_remove = os.path.join(self.home, "demo_sessions", k)
        shutil.rmtree(dir_to_remove, ignore_errors=True)
        self._workspace_access.pop(k, None)
        self._session_roots.pop(k, None)
        self._valid_demo_wids.discard(k)

    def _cleanup_workspaces(self):
        """Prune expired and excess demo workspaces to prevent disk filling on hosted free tiers.
        Never prunes workspaces currently marked in-use by an active request.
        """
        now = time.time()
        with self._lock:
            expired = [k for k, last_ts in list(self._workspace_access.items())
                       if now - last_ts > self.DEMO_WORKSPACE_TTL and self._workspace_refcounts.get(k, 0) == 0]
            for k in expired:
                self._delete_workspace(k)

            if len(self._workspace_access) > self.MAX_DEMO_WORKSPACES:
                sorted_keys = sorted(self._workspace_access.keys(), key=lambda k: self._workspace_access[k])
                for k in sorted_keys:
                    if len(self._workspace_access) <= self.MAX_DEMO_WORKSPACES:
                        break
                    if self._workspace_refcounts.get(k, 0) == 0:
                        self._delete_workspace(k)

    def get_workspace_root(self, wid: str):
        if not self.demo or not wid:
            return self.root
        with self._lock:
            self._workspace_access[wid] = time.time()
            if wid in self._session_roots and os.path.isdir(self._session_roots[wid]):
                return self._session_roots[wid]
            self._cleanup_workspaces()
            session_repo_dir = os.path.join(self.home, "demo_sessions", wid, "repo")
            if not os.path.isdir(session_repo_dir):
                os.makedirs(os.path.dirname(session_repo_dir), exist_ok=True)
                try:
                    demo.seed(session_repo_dir)
                except Exception:
                    return self.root
            self._session_roots[wid] = session_repo_dir
            return session_repo_dir

    def get_root_for_user(self, user=None, wid=None):
        """In demo mode, isolate working git repository per user session to prevent race conditions across concurrent evaluators."""
        if not self.demo:
            return self.root
        if wid:
            return self.get_workspace_root(wid)
        ident = (user and user.get("id")) or (user and user.get("email"))
        if not ident:
            return self.root
        key = hashlib.sha256(str(ident).encode()).hexdigest()[:12]
        return self.get_workspace_root(key)

    def get_base_for_root(self, root=None):
        r = root or self.root
        if not self.demo or not gitutil.is_repo(r):
            return self.base
        branch = gitutil.branch(r)
        if branch == "ai/orders":
            return "orders-base"
        return "main"

    def policy(self, root=None):
        r = root or self.root
        return P.load_for(r, self.get_base_for_root(r))


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
        # Path safety check must execute before any disk access
        if not path or path.startswith("/") or path.startswith("\\") or ".." in pathlib.PurePath(path).parts:
            findings.append(dict(severity="block", rule="blocked-path", file=path or "?", line=0, evidence="",
                                 msg="path escapes the repository", message="path escapes the repository"))
            continue
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


def _env_allowed_hosts(port):
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
    raw = os.environ.get("REPOBRAIN_ALLOWED_HOSTS", "").strip()
    if raw:
        hosts.update(h.strip() for h in raw.split(",") if h.strip())
    return hosts


def make_handler(ctx, token, port, host="127.0.0.1", open_demo=False, allowed_hosts=None):
    allowed_hosts = set(allowed_hosts or _env_allowed_hosts(port))
    if host and host not in ("0.0.0.0", "::", ""):
        allowed_hosts.add(f"{host}:{port}")

    def host_ok(value):
        if "*" in allowed_hosts:
            return True
        if not value:
            return False
        if value in allowed_hosts:
            return True
        # Behind a proxy the port may be omitted from the Host header.
        bare = value.rsplit(":", 1)[0] if value.count(":") == 1 else value
        return any(h.rsplit(":", 1)[0] == bare for h in allowed_hosts if not h.startswith("["))

    class H(BaseHTTPRequestHandler):
        server_version = "RepoBrain"
        timeout = 10.0

        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json", headers=None):
            data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body)).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if getattr(self, "_new_demo_wid", None):
                self.send_header("Set-Cookie", f"repobrain_demo_wid={self._new_demo_wid}; HttpOnly; SameSite=Strict; Path=/")
            if self.path.startswith("/api/"):
                self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; sandbox")
            else:
                self.send_header("Content-Security-Policy",
                                 "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'")
            if headers:
                for k, v in headers.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _get_demo_wid(self):
            if not (ctx.demo or open_demo):
                return None
            cookie_hdr = self.headers.get("Cookie", "") if hasattr(self, "headers") and self.headers else ""
            wid = None
            if cookie_hdr:
                match = re.search(r'(?:^|;\s*)repobrain_demo_wid=([a-fA-F0-9]{32})(?:;|$)', cookie_hdr)
                if match:
                    candidate = match.group(1).lower()
                    if ctx.is_valid_wid(candidate):
                        wid = candidate
            if wid:
                return wid

            # If no valid cookie, check if request is authenticated by per-run token (CLI)
            tok_hdr = self.headers.get("X-RepoBrain-Token", "").strip() if hasattr(self, "headers") and self.headers else ""
            if not tok_hdr:
                tok_hdr = parse_qs(urlparse(self.path).query).get("t", [""])[0].strip()
            if tok_hdr and token and secrets.compare_digest(tok_hdr, token) and not open_demo:
                cli_wid = hashlib.sha256(f"cli:{token}".encode()).hexdigest()[:32]
                with ctx._lock:
                    ctx._valid_demo_wids.add(cli_wid)
                return cli_wid

            # Otherwise, anonymous / browser visitor: issue fresh random 128-bit hex cookie
            wid = ctx.create_valid_wid()
            self._new_demo_wid = wid
            return wid

        def _guard(self):
            host_hdr = self.headers.get("X-Forwarded-Host") or self.headers.get("Host", "")
            if not host_ok(host_hdr):
                self._send(403, {"error": "bad host"}); return False
            if open_demo:
                return True
            tok_hdr = self.headers.get("X-RepoBrain-Token", "").strip()
            if not tok_hdr:
                tok_hdr = parse_qs(urlparse(self.path).query).get("t", [""])[0].strip()
            has_valid_tok = bool(tok_hdr) and secrets.compare_digest(tok_hdr, token)
            if self.path.startswith("/api/"):
                if not has_valid_tok:
                    self._send(401, {"error": "missing or wrong token - open the URL printed by `repobrain serve`"})
                    return False
            return True

        def _get_user(self):
            tok = self.headers.get("X-RepoBrain-Session", "").strip()
            if not tok:
                auth_hdr = self.headers.get("Authorization", "").strip()
                if auth_hdr.lower().startswith("bearer "):
                    tok = auth_hdr[7:].strip()
            u = ctx.auth.get_user_by_token(tok) if tok else None
            if not u and (open_demo or ctx.demo):
                for p in ctx.auth.list_users():
                    if p.get("role") == "admin":
                        return p
            return u

        def do_GET(self):
            wid = self._get_demo_wid()
            u = urlparse(self.path)
            if u.path == "/healthz":
                return self._send(200, {"ok": True})
            if not self._guard():
                return
            with ctx.acquire_workspace(wid):
                try:
                    if u.path == "/":
                        with open(find_index_html(), "rb") as f:
                            return self._send(200, f.read(), "text/html")
                    if u.path in ("/slides", "/docs/slides.html"):
                        sl = find_slides_html()
                        if sl and os.path.exists(sl):
                            with open(sl, "rb") as f:
                                return self._send(200, f.read(), "text/html")
                    if u.path == "/api/auth/me":
                        usr = self._get_user()
                        return self._send(200, {
                            "user": usr,
                            "roles": auth.ROLES,
                            "demo_personas": auth.DEFAULT_DEMO_USERS,
                            "users": ctx.auth.list_users()
                        })
                    if u.path == "/api/auth/users":
                        return self._send(200, {"users": ctx.auth.list_users()})
                    if u.path == "/api/state":
                        return self._send(200, state(ctx, user=self._get_user(), wid=wid))
                    if u.path == "/api/audit":
                        es = ctx.log.entries()
                        return self._send(200, {"entries": es, "chain": A.verify_entries(es)})
                    if u.path == "/api/report.md":
                        with LOCK:
                            usr = self._get_user()
                            active_root = ctx.get_workspace_root(wid) if wid else ctx.get_root_for_user(usr)
                            active_base = ctx.get_base_for_root(active_root)
                            pol = ctx.policy(active_root)
                            rev = review.run(active_root, pol, active_base, ctx.home)
                            return self._send(200, report.compliance(rev, ctx.log.entries(), ctx.log.verify(), pol),
                                              "text/markdown")
                    if u.path == "/api/export":
                        qs = parse_qs(u.query)
                        fmt = qs.get("fmt", ["json"])[0]
                        with LOCK:
                            usr = self._get_user()
                            active_root = ctx.get_workspace_root(wid) if wid else ctx.get_root_for_user(usr)
                            active_base = ctx.get_base_for_root(active_root)
                            pol = ctx.policy(active_root)
                            rev = review.run(active_root, pol, active_base, ctx.home)
                            finds = rev["findings"]
                            gate = rev["gate"]
                            if fmt == "sarif":
                                return self._send(200, export.sarif(finds, gate), "application/json",
                                                  {"content-disposition": "attachment; filename=repobrain.sarif"})
                            if fmt == "md":
                                st = state(ctx, user=usr, wid=wid)
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
                        usr = self._get_user()
                        active_root = ctx.get_workspace_root(wid) if wid else ctx.get_root_for_user(usr)
                        active_base = ctx.get_base_for_root(active_root)
                        target = os.path.realpath(os.path.join(active_root, norm))
                        real_root = os.path.realpath(active_root)
                        if os.path.commonpath([real_root, target]) != real_root:
                            return self._send(403, {"error": "path escapes repository"})
                        changed = {p: s for s, p in gitutil.changed_files(active_root, active_base)}
                        if norm not in changed:
                            return self._send(404, {"error": f"file '{norm}' not in current change set"})
                        status = changed[norm]
                        diff_text = gitutil.git(active_root, "diff", "-u", f"{active_base}...HEAD", "--", norm, check=False)
                        if len(diff_text) > 500_000:
                            diff_text = diff_text[:500_000] + "\n... [diff truncated at 500KB limit]"
                        pol = ctx.policy(active_root)
                        rev = review.run(active_root, pol, active_base, ctx.home)
                        file_findings = [f for f in rev["findings"] if f["file"] == norm]
                        file_gate = [g for g in rev["gate"] if g["file"] == norm]
                        return self._send(200, {
                            "path": norm,
                            "status": status,
                            "diff": diff_text,
                            "findings": file_findings,
                            "gate": file_gate,
                            "base": active_base,
                            "head": gitutil.head(active_root),
                        })
                    self._send(404, {"error": "not found"})
                except Exception as e:
                    self._send(500, {"error": str(e)})

        def _client_ip(self):
            return resolve_client_ip(self)

        def do_POST(self):
            wid = self._get_demo_wid()
            if not self._guard():
                return
            if "application/json" not in self.headers.get("Content-Type", ""):
                return self._send(415, {"error": "JSON only"})
            cl_raw = self.headers.get("Content-Length")
            if cl_raw is None:
                return self._send(411, {"error": "Content-Length required"})
            try:
                n = int(cl_raw.strip())
            except (ValueError, TypeError):
                return self._send(400, {"error": "invalid Content-Length header"})
            if n < 0:
                return self._send(400, {"error": "negative Content-Length refused"})
            if n > 2_000_000:
                return self._send(413, {"error": "body too large (max 2MB)"})

            try:
                raw_bytes = self.rfile.read(n) if n > 0 else b"{}"
                body = json.loads(raw_bytes.decode("utf-8") if raw_bytes else "{}")
            except Exception as e:
                return self._send(400, {"error": f"Invalid JSON payload: {e}"})

            req_path = urlparse(self.path).path
            user = self._get_user()

            with ctx.acquire_workspace(wid):
                if req_path == "/api/preflight":
                    client_ip = self._client_ip()
                    if not PREFLIGHT_LIMITER.check(f"ip:{client_ip}"):
                        return self._send(429, {"error": "Rate limit exceeded for preflight requests. Please slow down."})
                if req_path == "/api/shield" and not user:
                    client_ip = self._client_ip()
                    if not PREFLIGHT_LIMITER.check(f"ip:{client_ip}"):
                        return self._send(429, {"error": "Rate limit exceeded for unauthenticated shield requests."})

                # Webhook HMAC-SHA256 signature verification
                if req_path == "/api/webhook":
                    secret = os.environ.get("GITHUB_WEBHOOK_SECRET") or os.environ.get("REPOBRAIN_WEBHOOK_SECRET")
                    sig_header = self.headers.get("X-Hub-Signature-256", "").strip()
                    if secret:
                        from . import webhook
                        if not webhook.verify_signature(raw_bytes, secret, sig_header):
                            return self._send(401, {"error": "invalid webhook HMAC-SHA256 signature"})
                    elif sig_header:
                        return self._send(401, {"error": "webhook secret not configured on server"})

                # Auth endpoints run outside global LOCK for concurrency & non-blocking PBKDF2
                if req_path == "/api/auth/login":
                    client_ip = self._client_ip()
                    login_email = str(body.get("email", "")).strip().lower()
                    ip_key = f"ip:{client_ip}"
                    email_key = f"email:{login_email}" if login_email else None
                    if not LOGIN_LIMITER.check(ip_key) or (email_key and not LOGIN_LIMITER.check(email_key)):
                        return self._send(429, {"error": "Too many failed login attempts. Please wait 60 seconds before trying again."})
                    try:
                        res = route(ctx, req_path, body, user=user, wid=wid)
                        LOGIN_LIMITER.record_success(ip_key)
                        if email_key:
                            LOGIN_LIMITER.record_success(email_key)
                        return self._send(200, res)
                    except ValueError as e:
                        return self._send(400, {"error": str(e)})
                    except Exception as e:
                        return self._send(500, {"error": f"{type(e).__name__}: {e}"})

                if req_path.startswith("/api/auth/"):
                    try:
                        return self._send(200, route(ctx, req_path, body, user=user, wid=wid))
                    except PermissionError as e:
                        return self._send(403, {"error": str(e), "code": "FORBIDDEN"})
                    except ValueError as e:
                        return self._send(400, {"error": str(e)})
                    except Exception as e:
                        return self._send(500, {"error": f"{type(e).__name__}: {e}"})

                try:
                    with LOCK:
                        self._send(200, route(ctx, req_path, body, user=user, wid=wid))
                except PermissionError as e:
                    self._send(403, {"error": str(e), "code": "FORBIDDEN"})
                except (ValueError, gitutil.GitError, P.PolicyError, KeyError) as e:
                    self._send(400, {"error": str(e)})
                except Exception as e:
                    self._send(500, {"error": f"{type(e).__name__}: {e}"})

    return H


def state(ctx_or_root, base=None, user=None, wid=None):
    if isinstance(ctx_or_root, Ctx):
        ctx = ctx_or_root
    else:
        root = os.path.abspath(str(ctx_or_root))
        home = A.home_for(root)
        ctx = Ctx(root, base or "main", home, False)

    if user is None and (ctx.demo or getattr(ctx, "open_demo", False)):
        for p in ctx.auth.list_users():
            if p.get("role") == "admin":
                user = p
                break

    active_root = ctx.get_workspace_root(wid) if wid else ctx.get_root_for_user(user)
    active_base = ctx.get_base_for_root(active_root)
    pol = ctx.policy(active_root)
    try:
        yml = gitutil.show(active_root, active_base, "repobrain.yml") or open(os.path.join(active_root, "repobrain.yml")).read()
    except OSError:
        yml = ""

    rev = review.run(active_root, pol, active_base, ctx.home)
    head_sha = gitutil.head(active_root) if gitutil.is_repo(active_root) else ""
    branch_name = gitutil.branch(active_root) if gitutil.is_repo(active_root) else ""

    return {
        "root": active_root,
        "base": active_base,
        "branch": branch_name,
        "head": head_sha,
        "repo": {
            "path": active_root, "branch": branch_name, "head": head_sha,
            "base": active_base, "demo": ctx.demo, "scenarios": list(demo.SCENARIOS) if ctx.demo else []
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
        "chain": ctx.log.verify(),
        "auth": {
            "current_user": user,
            "roles": auth.ROLES,
            "demo_personas": auth.DEFAULT_DEMO_USERS,
            "company": user.get("company", "Acme Corp") if user else "Acme Corp",
            "users": ctx.auth.list_users()
        }
    }


def route(ctx, path, body, user=None, wid=None):
    actor = str(body.get("actor", "")).strip()[:80]
    active_root = ctx.get_workspace_root(wid) if wid else ctx.get_root_for_user(user)
    active_base = ctx.get_base_for_root(active_root)
    if path == "/api/auth/register":
        u, tok = ctx.auth.register(
            email=body.get("email", ""),
            password=body.get("password", ""),
            name=body.get("name", ""),
            role=body.get("role", "developer"),
            company=body.get("company", ""),
            audit_log=ctx.log
        )
        return {"user": u, "token": tok}
    if path == "/api/auth/login":
        u, tok = ctx.auth.login(
            email=body.get("email", ""),
            password=body.get("password", ""),
            audit_log=ctx.log
        )
        return {"user": u, "token": tok}
    if path == "/api/auth/logout":
        tok = body.get("token") or ""
        return ctx.auth.logout(tok, ctx.log)
    if path == "/api/auth/switch-demo-role":
        if not (ctx.demo or getattr(ctx, "open_demo", False)):
            raise PermissionError("Demo persona switching is restricted to demo mode (--demo)")
        u, tok = ctx.auth.switch_demo_persona(body.get("role", "admin"), ctx.log)
        return {"user": u, "token": tok}
    if path == "/api/auth/verify-email":
        email = str(body.get("email", "")).strip().lower()
        code = str(body.get("code", "")).strip()
        u = ctx.auth.verify_email(email, code, ctx.log)
        return {"user": u, "verified": True}
    if path == "/api/auth/resend-code":
        email = str(body.get("email", "")).strip().lower()
        return ctx.auth.resend_verification_code(email, ctx.log)
    if path == "/api/auth/update-role":
        if not user or not auth.check_permission(user, "manage_users"):
            raise PermissionError("Permission Denied: Authentication required. Only Admin / Release Manager can change user roles.")
        actor_email = user.get("email", "admin")
        u = ctx.auth.update_role(body.get("email", ""), body.get("role", "developer"), actor_email, ctx.log)
        return {"user": u}
    if path == "/api/review":
        pol = ctx.policy(active_root)
        rev = review.run(active_root, pol, active_base, ctx.home, body.get("pr_author"))
        review.log_review(ctx.log, rev)
        return rev
    if path == "/api/optimize":
        pol = ctx.policy(active_root)
        rev = review.run(active_root, pol, active_base, ctx.home)
        files = [f["path"] for f in rev["files"] if f["status"] != "D" and f["path"].endswith(".py")
                 and not TEST_RX.search(f["path"]) and not f["path"].endswith("__init__.py")]
        prop = optimizer.propose(active_root, pol, files, ctx.home, use_llm=bool(body.get("ai")))
        ctx.log.append("optimize", "repobrain", prop["status"], f"{len(prop['files'])} file(s) proposed, id {prop['id']}",
                       head=prop["head"])
        ctx.last_proposal = prop["id"]
        return strip(prop)
    if path == "/api/approve":
        if ctx.log.is_recovery_pending():
            raise PermissionError("Audit ledger is in recovery state. Human administrator must acknowledge recovery before approvals can be processed.")
        if not actor:
            raise ValueError("approver name is required (a human approves)")
        if not user or not auth.check_permission(user, "apply_approval"):
            role_title = user.get("role_title", user.get("role", "Developer")) if user else "Unauthenticated"
            raise PermissionError(
                f"Permission Denied: User '{user.get('name', 'Anonymous') if user else 'Unauthenticated'}' ({role_title}) cannot approve code. "
                "Only Admin / Release Manager can approve and apply code merges. Please switch to Admin persona."
            )
        approved_by = user.get("name") if (user and user.get("name")) else actor
        approved_by = re.sub(r"[\r\n]+", " ", str(approved_by)).strip()
        res = optimizer.apply(active_root, ctx.home, body["id"], approved_by)
        ctx.log.append("approve", approved_by, "APPLIED", f"{', '.join(res['applied'])} -> {str(res['commit'])[:8]}", head=res["commit"])
        return res
    if path == "/api/waive":
        if not actor:
            raise ValueError("waiver name is required")
        if not user or not auth.check_permission(user, "grant_waiver"):
            role_title = user.get("role_title", user.get("role", "Developer")) if user else "Unauthenticated"
            raise PermissionError(
                f"Permission Denied: User '{user.get('name', 'Anonymous') if user else 'Unauthenticated'}' ({role_title}) cannot grant policy waivers. "
                "Waivers require Security Lead or Admin authority."
            )
        waived_by = user.get("name") if (user and user.get("name")) else actor
        waived_by = re.sub(r"[\r\n]+", " ", str(waived_by)).strip()
        w = review.waive(ctx.home, gitutil.head(active_root), waived_by, str(body.get("reason", "")))
        ctx.log.append("waive", waived_by, "WAIVED", w["reason"], head=gitutil.head(active_root))
        return w
    if path == "/api/shield":
        res = shield.check_action({"actor": str(body.get("actor", "")), "path": str(body.get("path", "")),
                                   "content": str(body.get("content", ""))}, ctx.policy(active_root))
        ctx.log.append("shield-check", str(body.get("actor", "") or "unknown")[:60], res["decision"],
                       f"{body.get('path', '')}: " + (", ".join(f['rule'] for f in res['findings']) or "clean"))
        return res
    if path == "/api/explain":
        pol = ctx.policy(active_root)
        ask = llm.ask if body.get("ai") and pol.get("allow_llm") and llm.available() else None
        res = explainer.explain(str(body.get("log", ""))[:200_000], ask)
        ctx.log.append("explain", "repobrain", "EXPLAINED", res["summary"])
        return res
    if path == "/api/preflight":
        actor_name = str(body.get("actor", "unknown-agent"))[:80]
        files = body.get("files", [])
        return preflight(active_root, actor_name, files)
    if path == "/api/audit/tamper":
        if not (ctx.demo or getattr(ctx, "open_demo", False)):
            if not user or not auth.check_permission(user, "simulate_tamper"):
                raise PermissionError("Permission Denied: simulate_tamper requires security or admin privileges outside demo mode.")
        return A.simulate_tamper(ctx.log.entries())
    if path == "/api/audit/ack-recovery":
        if not user or not auth.check_permission(user, "manage_policy"):
            raise PermissionError("Permission Denied: Only Admin can acknowledge audit ledger recovery.")
        return ctx.log.ack_recovery(user.get("email", actor or "admin"))
    if path == "/api/scenario" and ctx.demo:
        demo.switch(active_root, body["name"])
        active_base = ctx.get_base_for_root(active_root)
        ctx.base = active_base
        return {"branch": gitutil.branch(active_root), "base": active_base}
    if path == "/api/reset" and ctx.demo:
        demo.seed(active_root)
        if active_root != ctx.root:
            pass
        else:
            shutil.rmtree(ctx.home, ignore_errors=True)
            ctx.log = A.AuditLog(ctx.home)
        return {"ok": True}
    if path == "/api/webhook":
        from . import webhook
        return webhook.handle_event(body.get("event", "ping"), body)
    raise KeyError("unknown endpoint")


def serve(a_or_repo=None, base="main", port=8765, open_browser=False, demo_mode=False):
    env_port = os.environ.get("REPOBRAIN_PORT") or os.environ.get("PORT")
    host = os.environ.get("REPOBRAIN_HOST") or ("0.0.0.0" if env_port else "127.0.0.1")
    open_demo = os.environ.get("REPOBRAIN_OPEN_DEMO", "").strip().lower() in ("1", "true", "yes", "on")
    if hasattr(a_or_repo, "repo"):
        a = a_or_repo
        root = os.path.abspath(a.repo)
        is_demo = getattr(a, "demo", False)
        port = getattr(a, "port", None) or int(env_port or port or 8765)
        host = getattr(a, "host", None) or host
        open_demo = open_demo or bool(getattr(a, "open", False))
        open_browser = not getattr(a, "no_browser", False)
        base = getattr(a, "base", None)
        home = getattr(a, "home", None)
    else:
        root = os.path.abspath(a_or_repo or ".")
        is_demo = demo_mode
        home = None
        port = int(env_port or port or 8765)

    if is_demo:
        if not os.environ.get("REPOBRAIN_AUDIT_KEY"):
            # Use an ephemeral key in demo mode so the audit chain demonstrates HMAC-SHA256 signing.
            os.environ["REPOBRAIN_AUDIT_KEY"] = "repobrain-demo-" + secrets.token_hex(8)
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
    srv = ThreadingHTTPServer((host, port), make_handler(ctx, token, port, host, open_demo))
    display = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    url = f"http://{display}:{port}/?t={token}"
    mode = "open demo - no token required" if open_demo else "token required"
    print(f"RepoBrain console  ({'demo repo' if is_demo else root}; {mode})\n"
          f"  {url}\n  listening on {host}:{port}\n  Ctrl+C to stop", flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
