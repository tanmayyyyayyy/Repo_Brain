"""Optimizer: rule-based rewrite (+ optional LLM) -> run tests on a copy -> proposal -> human apply."""
import ast
from collections import Counter
import copy
import difflib
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tokenize

from . import fuzz, gitutil, llm, metrics as metrics_mod, rewrite as rewrite_mod
from .shield import SECRET_PATTERNS

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache", ".mypy_cache"}
SECRET_ENV = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.I)
TERM = (ast.Return, ast.Raise)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def has_tests(root, policy):
    if policy.get("test_command"):
        return True
    for dp, dn, fn in os.walk(str(root)):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        if any(f.startswith("test_") and f.endswith(".py") or f.endswith("_test.py") for f in fn):
            return True
    return False


def _analyze_function_coverage(work, overrides, cov_data):
    """Determine line execution per function in overrides using CoverageData.
    Returns (unexecuted_functions, function_coverage_list)."""
    unexecuted = []
    func_cov = []
    measured_map = {}
    for mf in cov_data.measured_files():
        measured_map[os.path.realpath(mf)] = mf
        measured_map[os.path.normpath(mf)] = mf

    for rel, text in overrides.items():
        full_work = os.path.realpath(os.path.join(work, os.path.normpath(rel)))
        cov_key = measured_map.get(full_work)
        if not cov_key:
            for mf in cov_data.measured_files():
                if mf.replace("\\", "/").endswith(rel.replace("\\", "/")):
                    cov_key = mf
                    break
        executed_lines = set(cov_data.lines(cov_key) or []) if cov_key else set()

        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body_lines = set()
                for b in node.body:
                    for sub in ast.walk(b):
                        if hasattr(sub, "lineno") and sub.lineno != node.lineno:
                            body_lines.add(sub.lineno)
                if not body_lines:
                    body_lines = {node.lineno}
                covered = body_lines & executed_lines
                pct = round(len(covered) / max(len(body_lines), 1) * 100, 1)
                entry = {"file": rel, "function": node.name, "coverage_pct": pct,
                         "executed": len(covered), "total_lines": len(body_lines)}
                func_cov.append(entry)
                if not covered:
                    unexecuted.append(entry)
    return unexecuted, func_cov


def run_tests(root, overrides, policy):
    """Copy the repo, apply `overrides` ({relpath: text}), run the test command. -> dict"""
    if not has_tests(root, policy):
        return {"ran": False, "ok": None, "output": "no tests found", "cmd": ""}
    cmd = policy.get("test_command") or [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"]
    posix_mode = (os.name == "posix")
    cmd = shlex.split(cmd, posix=posix_mode) if isinstance(cmd, str) else list(cmd)
    tmp = tempfile.mkdtemp(prefix="repobrain-")
    try:
        work = os.path.join(tmp, "repo")
        shutil.copytree(str(root), work, ignore=shutil.ignore_patterns(*SKIP_DIRS))
        for rel, text in overrides.items():
            dest = os.path.join(work, os.path.normpath(rel))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        env = {k: v for k, v in os.environ.items() if not SECRET_ENV.search(k)}
        env.update(PYTHONDONTWRITEBYTECODE="1", HOME=tmp)
        if os.name == "nt":
            env.update(USERPROFILE=tmp, APPDATA=os.path.join(tmp, "AppData"))

        has_coverage = False
        cov_file = os.path.join(tmp, ".coverage")
        cov_cmd = list(cmd)
        try:
            import coverage
            has_coverage = True
            if len(cmd) >= 3 and cmd[0] == sys.executable and cmd[1] == "-m":
                cov_cmd = [sys.executable, "-m", "coverage", "run", f"--data-file={cov_file}"] + cmd[1:]
            elif "pytest" in cmd[0] or (len(cmd) > 1 and "pytest" in cmd[1]):
                cov_cmd = [sys.executable, "-m", "coverage", "run", f"--data-file={cov_file}"] + cmd
        except (ImportError, Exception):
            has_coverage = False

        try:
            r = subprocess.run(cov_cmd, cwd=work, capture_output=True, text=True, env=env,
                               timeout=policy.get("test_timeout", 180))
            out = (r.stdout + r.stderr)[-4000:]
            cov_info = {"available": False, "unexecuted_functions": [], "function_coverage": []}
            if r.returncode == 0 and has_coverage and os.path.exists(cov_file):
                try:
                    import coverage
                    cov = coverage.Coverage(data_file=cov_file)
                    cov.load()
                    unexec, f_cov = _analyze_function_coverage(work, overrides, cov.get_data())
                    cov_info = {"available": True, "unexecuted_functions": unexec, "function_coverage": f_cov}
                    try:
                        cov_info["percent"] = round(cov.report(file=io.StringIO()), 1)
                    except Exception:
                        pass
                except Exception:
                    pass
            return {"ran": True, "ok": r.returncode == 0, "output": out,
                    "cmd": " ".join(cmd) if isinstance(cmd, list) else str(cmd),
                    "runner": "pytest" if "pytest" in str(cmd) else "custom",
                    "coverage": cov_info}
        except subprocess.TimeoutExpired:
            return {"ran": True, "ok": False, "output": "test run timed out",
                    "cmd": " ".join(cmd) if isinstance(cmd, list) else str(cmd),
                    "coverage": {"available": False}}
        except FileNotFoundError as e:
            return {"ran": True, "ok": False, "output": f"test command not found: {e}",
                    "cmd": " ".join(cmd) if isinstance(cmd, list) else str(cmd),
                    "coverage": {"available": False}}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _diff(path, a, b):
    nl = "\r\n" if "\r\n" in a else "\n"
    al = a.splitlines(keepends=True)
    bl = b.splitlines(keepends=True)
    return "".join(difflib.unified_diff(al, bl, f"a/{path}", f"b/{path}", lineterm=nl))


# ---------- AST metrics and analysis (matching clean engine) ----------
def complexity(fn):
    c = 1
    for n in ast.walk(fn):
        if isinstance(n, (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.With, ast.AsyncWith, ast.Assert)):
            c += 1
        elif isinstance(n, ast.BoolOp):
            c += len(n.values) - 1
    return c


def depth(node, d=0):
    m = d
    for c in ast.iter_child_nodes(node):
        step = 1 if isinstance(c, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)) else 0
        m = max(m, depth(c, d + step))
    return m


def cognitive(fn):
    total = 0
    def expr_cost(n, nest):
        nonlocal total
        if n is None: return 0
        for sub in ast.walk(n):
            if isinstance(sub, ast.BoolOp):
                total += len(sub.values) - 1
            elif isinstance(sub, ast.IfExp):
                total += 1 + nest
        return 0

    def stmts(lst, nest):
        for s in lst: stmt(s, nest)

    def stmt(st, nest, elif_=False):
        nonlocal total
        if isinstance(st, ast.If):
            total += 1 + (0 if elif_ else nest) + expr_cost(st.test, nest)
            stmts(st.body, nest + 1)
            if len(st.orelse) == 1 and isinstance(st.orelse[0], ast.If):
                stmt(st.orelse[0], nest, True)
            elif st.orelse:
                total += 1; stmts(st.orelse, nest + 1)
        elif isinstance(st, (ast.For, ast.AsyncFor, ast.While)):
            total += 1 + nest + expr_cost(getattr(st, "test", None) or st.iter, nest)
            stmts(st.body, nest + 1); stmts(st.orelse, nest + 1)
        elif isinstance(st, ast.Try):
            stmts(st.body, nest)
            for h in st.handlers:
                total += 1 + nest; stmts(h.body, nest + 1)
            stmts(st.orelse, nest); stmts(st.finalbody, nest)
        elif isinstance(st, (ast.With, ast.AsyncWith)):
            stmts(st.body, nest)
        elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            stmts(st.body, nest + 1)
        else:
            total += expr_cost(st, nest)

    stmts(fn.body, 0)
    return total


def analyze(src):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    return [{"name": n.name, "line": n.lineno, "complexity": complexity(n), "cognitive": cognitive(n),
             "depth": depth(n), "lines": getattr(n, "end_lineno", n.lineno) - n.lineno + 1}
            for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def metrics(src):
    rows = analyze(src)
    return {"functions": len(rows),
            "max_complexity": max([r["complexity"] for r in rows], default=0),
            "total_complexity": sum(r["complexity"] for r in rows),
            "max_cognitive": max([r["cognitive"] for r in rows], default=0),
            "total_cognitive": sum(r["cognitive"] for r in rows),
            "max_depth": max([r["depth"] for r in rows], default=0),
            "loc": sum(1 for l in src.splitlines() if l.strip())}


def violations(rows, policy):
    thresh = policy.get("max_complexity", policy.get("complexity_threshold", 10))
    max_d = policy.get("max_depth", 3)
    max_c = policy.get("max_cognitive", 15)
    out = []
    for r in rows:
        why = []
        cc = r.get("complexity", r.get("cc", 0))
        depth_val = r.get("depth", 0)
        cog = r.get("cognitive", r.get("cog", 0))
        if cc > thresh: why.append(f"complexity {cc} > {thresh}")
        if depth_val > max_d: why.append(f"nesting {depth_val} > {max_d}")
        if max_c and cog > max_c: why.append(f"cognitive {cog} > {max_c}")
        if why:
            out.append({**r, "why": why})
    return out


# ---------- rewrite helpers (matching clean engine) ----------
def _terminates(b):
    if not b: return False
    last = b[-1]
    if isinstance(last, TERM): return True
    return isinstance(last, ast.If) and bool(last.orelse) and _terminates(last.body) and _terminates(last.orelse)


def _is_bool(n, v=None):
    return isinstance(n, ast.Return) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, bool) \
        and (v is None or n.value.value is v)


def _bool_return(test, val):
    if val:
        plain = isinstance(test, ast.Compare) or (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not))
        return ast.Return(test if plain else ast.Call(ast.Name("bool", ast.Load()), [test], []))
    return ast.Return(ast.UnaryOp(ast.Not(), test))


def _is_append(st, r):
    return (isinstance(st, ast.Expr) and isinstance(st.value, ast.Call)
            and isinstance(st.value.func, ast.Attribute) and st.value.func.attr == "append"
            and isinstance(st.value.func.value, ast.Name) and st.value.func.value.id == r
            and len(st.value.args) == 1 and not st.value.keywords)


def _append_comp(f, r):
    body, ifs = f.body, []
    if len(body) == 1 and isinstance(body[0], ast.If) and not body[0].orelse:
        ifs, body = [body[0].test], body[0].body
    if len(body) == 1 and _is_append(body[0], r):
        elt = body[0].value.args[0]
        if not any(isinstance(n, ast.Name) and n.id == r for n in ast.walk(elt)) \
                and not any(isinstance(n, ast.Name) and n.id == r for t in ifs for n in ast.walk(t)):
            return ast.ListComp(elt, [ast.comprehension(f.target, f.iter, ifs, 0)])
    return None


class Rewriter(ast.NodeTransformer):
    def __init__(self):
        self.notes = []

    def visit_Compare(self, n):
        self.generic_visit(n)
        if len(n.ops) == 1 and isinstance(n.ops[0], (ast.Eq, ast.NotEq)) \
                and isinstance(n.comparators[0], ast.Constant) and n.comparators[0].value is None:
            n.ops = [ast.Is() if isinstance(n.ops[0], ast.Eq) else ast.IsNot()]
            self.notes.append("== None -> is None")
        return n

    def generic_visit(self, node):
        super().generic_visit(node)
        for f in ("body", "orelse", "finalbody"):
            b = getattr(node, f, None)
            if isinstance(b, list) and b and isinstance(b[0], ast.stmt):
                setattr(node, f, self.block(b))
        return node

    def block(self, b):
        changed = True
        while changed:
            changed, out = False, []
            for st in b:
                if isinstance(st, ast.If) and st.orelse and _terminates(st.body):
                    out += [ast.If(st.test, st.body, [])] + st.orelse
                    changed = True
                    self.notes.append("flattened else-after-return")
                else:
                    out.append(st)
            b = out
        out, i = [], 0
        while i < len(b):
            st, nxt = b[i], (b[i + 1] if i + 1 < len(b) else None)
            if isinstance(st, ast.If) and not st.orelse and len(st.body) == 1 and _is_bool(st.body[0]) \
                    and nxt is not None and _is_bool(nxt) and st.body[0].value.value is not nxt.value.value:
                out.append(_bool_return(st.test, st.body[0].value.value)); i += 2
                self.notes.append("collapsed boolean return"); continue
            if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name) \
                    and isinstance(st.value, ast.List) and not st.value.elts \
                    and isinstance(nxt, ast.For) and not nxt.orelse:
                comp = _append_comp(nxt, st.targets[0].id)
                if comp is not None:
                    out.append(ast.Assign([ast.Name(st.targets[0].id, ast.Store())], comp)); i += 2
                    self.notes.append("loop + append -> list comprehension"); continue
            if isinstance(st, ast.If) and not st.orelse and len(st.body) == 1 \
                    and isinstance(st.body[0], ast.If) and not st.body[0].orelse:
                inner = st.body[0]
                st = ast.If(ast.BoolOp(ast.And(), [st.test, inner.test]), inner.body, [])
                self.notes.append("merged nested ifs")
            out.append(st); i += 1
        return out


def _comment_rows(src):
    rows = set()
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type == tokenize.COMMENT:
                rows.add(t.start[0])
    except (tokenize.TokenError, IndentationError):
        pass
    return rows


def _unparse_indented(node, col):
    text = ast.unparse(node)
    skip = set()
    try:
        for t in tokenize.generate_tokens(io.StringIO(text).readline):
            if t.type == tokenize.STRING and t.end[0] > t.start[0]:
                skip.update(range(t.start[0] + 1, t.end[0] + 1))
    except (tokenize.TokenError, IndentationError):
        pass
    pad = " " * col
    return "\n".join(l if (i + 1 in skip or not l) else pad + l for i, l in enumerate(text.split("\n"))) + "\n"


def _outer_functions(body):
    for n in body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield n
        elif isinstance(n, ast.ClassDef):
            yield from _outer_functions(n.body)


def _unused_import_edits(tree, lines, notes):
    if any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets) for n in tree.body):
        return []
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.isidentifier()}
    edits = []
    for st in tree.body:
        if not isinstance(st, (ast.Import, ast.ImportFrom)) or (isinstance(st, ast.ImportFrom) and (st.module == "__future__" or st.level)):
            continue
        seg = "".join(lines[st.lineno - 1: st.end_lineno])
        if "noqa" in seg or "type:" in seg:
            continue
        keep = [a for a in st.names if a.name == "*" or (a.asname or a.name.split(".")[0]) in used]
        if len(keep) == len(st.names):
            continue
        notes.append("removed unused import")
        if keep:
            clone = copy.copy(st); clone.names = keep
            edits.append((st.lineno, st.end_lineno, ast.unparse(clone) + "\n"))
        else:
            edits.append((st.lineno, st.end_lineno, ""))
    return edits


def rewrite(src, preserve_comments=True):
    """Returns (new_src, notes, details). details: per-function {name, line, notes|skipped}."""
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    crows = _comment_rows(src)
    edits, notes, details = [], [], []
    for fn in _outer_functions(tree.body):
        rw = Rewriter()
        new_fn = ast.fix_missing_locations(rw.visit(copy.deepcopy(fn)))
        if not rw.notes:
            continue
        start = min([fn.lineno] + [d.lineno for d in fn.decorator_list])
        if preserve_comments and any(start <= r <= fn.end_lineno for r in crows):
            details.append({"name": fn.name, "line": fn.lineno, "skipped": "contains comments; left untouched so none are lost"})
            continue
        edits.append((start, fn.end_lineno, _unparse_indented(new_fn, fn.col_offset)))
        notes += rw.notes
        details.append({"name": fn.name, "line": fn.lineno, "notes": dict(Counter(rw.notes))})
    edits += _unused_import_edits(tree, lines, notes)
    if not edits:
        return src, [], details
    for s, e, text in sorted(edits, reverse=True):
        lines[s - 1:e] = [text] if text else []
    new = "".join(lines)
    if not src.startswith("\n"):
        new = new.lstrip("\n")
    try:
        ast.parse(new)
    except SyntaxError:
        return src, [], details + [{"name": "*", "line": 0, "skipped": "rewrite produced invalid syntax; discarded"}]
    return new, notes, details


def changed_functions(old, new):
    """Names of top-level functions whose AST differs between two versions of a file."""
    def table(s):
        try:
            return {n.name: ast.dump(n) for n in ast.parse(s).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        except SyntaxError:
            return {}
    o, n = table(old), table(new)
    return [k for k in n if k in o and o[k] != n[k]]


def ai_refine(src, policy):
    """Optional: ask an LLM to further simplify functions that still break policy."""
    if not violations(analyze(src), policy):
        return None
    try:
        reply = llm.ask("Simplify this Python for readability and lower complexity WITHOUT changing behaviour. "
                        "Keep comments and public names. Return only the full file in one ```python block.\n\n" + src,
                        system="You are a careful refactoring tool.")
        m = re.search(r"```python\n(.*?)```", reply, re.S)
        if m:
            ast.parse(m.group(1))
            return m.group(1)
    except Exception:
        pass
    return None


def gate(root, policy, files=None, base=None):
    root = pathlib.Path(root)
    if files:
        cand = list(files)
    elif base:
        out = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=str(root), capture_output=True, text=True)
        cand = out.stdout.splitlines()
    else:
        cand = [str(p.relative_to(root)) for p in root.rglob("*.py") if not (set(p.relative_to(root).parts) & SKIP_DIRS)]
    bad = []
    for rel in cand:
        if not rel.endswith(".py") or not (root / rel).is_file():
            continue
        try:
            src = (root / rel).read_text(encoding="utf-8")
            rows = analyze(src)
            for v in violations(rows, policy):
                bad.append({"file": rel, **v})
        except (SyntaxError, UnicodeDecodeError):
            pass
    return bad


def _map_functions(tree):
    """Map qualified names (e.g. 'Class.method' or 'func') to (node, start_lineno)."""
    mapping = {}

    def visit(node, prefix):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qname = prefix + ch.name
                start = min([d.lineno for d in ch.decorator_list] + [ch.lineno])
                mapping[qname] = (ch, start)
                visit(ch, qname + ".")
            elif isinstance(ch, ast.ClassDef):
                visit(ch, prefix + ch.name + ".")
            else:
                visit(ch, prefix)

    visit(tree, "")
    return mapping


def _llm_refine(src, policy, funcs, ask, feedback="", path="refactor.py"):
    """Ask the LLM to rewrite individual over-threshold functions. Returns (new_src, [names])."""
    from .shield import scan_text
    import textwrap

    lines, names, edits = src.splitlines(), [], []
    tree = ast.parse(src)
    mapping = _map_functions(tree)

    for f in funcs:
        target_qname = f["name"]
        entry = mapping.get(target_qname)
        if entry is None:
            # Fallback to bare-name match only if unambiguous
            bare = target_qname.split(".")[-1]
            bare_matches = [k for k in mapping if k.split(".")[-1] == bare]
            if len(bare_matches) == 1:
                entry = mapping[bare_matches[0]]
                target_qname = bare_matches[0]
            else:
                continue

        node, start_line = entry
        is_method = "." in target_qname
        seg = "\n".join(lines[start_line - 1:node.end_lineno])

        method_hint = ("You are refactoring a class method. Keep 'self' as the first parameter, "
                       "and add helper methods to the class (taking self or decorated with @staticmethod)."
                       if is_method else
                       "You may add small private helper functions after it.")
        prompt = (f"Refactor this Python function to reduce complexity (target: cyclomatic <= "
                  f"{policy.get('complexity_threshold', policy.get('max_complexity', 10))}, nesting depth <= {policy.get('max_depth', 3)}, cognitive <= "
                  f"{policy.get('max_cognitive', 10)}) WITHOUT changing behaviour.\n"
                  f"Keep the function name '{node.name}' and exact parameter signature.\n"
                  f"CRITICAL: Keep all existing comments, docstrings, type annotations, and logic intact.\n"
                  f"{method_hint}\n"
                  "Reply with ONE ```python block containing only the replacement code.\n" +
                  (f"\nPrevious attempt failed tests:\n{feedback}\n" if feedback else "") +
                  f"\n```python\n{textwrap.dedent(seg)}\n```")

        reply = ask(prompt, "You are a careful refactoring tool. Output code only.")
        m = re.search(r"```(?:python)?\s*\n(.*?)\n```", reply, re.S)
        if not m:
            continue
        cleaned_code = textwrap.dedent(m.group(1).rstrip())
        try:
            parsed = ast.parse(cleaned_code)
        except SyntaxError:
            continue

        # Treat model reply as untrusted: run Shield scan to refuse secrets, injection, hidden chars
        shield_findings = scan_text(path, cleaned_code, policy)
        if any(finding.get("severity") == "block" for finding in shield_findings):
            continue

        # Verify target function is present in reply
        parsed_funcs = [n for n in ast.walk(parsed) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if not any(n.name == node.name for n in parsed_funcs):
            continue

        # Preserve indentation
        indent_match = re.match(r"^\s*", lines[start_line - 1])
        indent = indent_match.group(0) if indent_match else ""
        new = [(indent + l if l.strip() else "") for l in cleaned_code.splitlines()]
        edits.append((start_line, node.end_lineno, new))
        names.append(target_qname)

    nl = "\r\n" if "\r\n" in src else "\n"
    for s, e, new in sorted(edits, key=lambda x: -x[0]):
        lines[s - 1:e] = new
    trailing = nl if (src.endswith("\r\n") or src.endswith("\n")) else ""
    return nl.join(lines) + trailing, names


def format_source(src, policy):
    cmd = policy.get("format_command")
    if not cmd:
        return src
    posix_mode = (os.name == "posix")
    cmd_parts = shlex.split(cmd, posix=posix_mode) if isinstance(cmd, str) else list(cmd)
    try:
        p = subprocess.run(cmd_parts, input=src, capture_output=True, text=True, timeout=30)
        if p.returncode == 0 and p.stdout:
            res = p.stdout
            if "\r\n" in src and "\r\n" not in res:
                res = res.replace("\n", "\r\n")
            return res
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return src


def propose(root, policy, files, home, use_llm=False, ask=None, head=None):
    pid = time.strftime("%Y%m%d-%H%M%S-") + secrets_hex(3)
    ask = ask or llm.ask
    originals, results, skipped_all = {}, [], []
    for rel in files:
        full = os.path.join(str(root), rel)
        try:
            src = open(full, encoding="utf-8", newline="").read()
            funcs = metrics_mod.analyze(src)
        except (OSError, SyntaxError, UnicodeDecodeError) as e:
            skipped_all.append({"file": rel, "reason": f"unreadable/invalid python: {e}"})
            continue
        new, notes, skipped = rewrite_mod.optimize_source(src, policy)
        if new != src and policy.get("format_command"):
            new = format_source(new, policy)
        originals[rel] = src
        results.append({"path": rel, "before_sha": sha(src), "before": src, "after": new,
                        "notes": notes, "skipped": skipped, "ai_functions": []})

    llm_info = {"requested": use_llm, "used": False, "reason": ""}
    if use_llm:
        if not policy.get("allow_llm"):
            llm_info["reason"] = "disabled by policy (allow_llm: false)"
        elif not (llm.available() or ask is not llm.ask):
            llm_info["reason"] = llm.missing_key_hint()
        else:
            llm_info["used"] = True

    overrides = {r["path"]: r["after"] for r in results if r["after"] != r["before"]}
    tests = run_tests(root, overrides, policy) if overrides else {"ran": False, "ok": None, "output": "", "cmd": ""}

    if llm_info["used"]:
        remaining = []
        for r in results:
            bad = metrics_mod.violations(metrics_mod.analyze(r["after"]), policy)
            from .shield import scan_text
            if bad and not scan_text(r["path"], r["before"], policy):
                remaining.append((r, bad))
        if remaining and tests["ok"] is not False:
            trial = dict(overrides)
            feedback = ""
            for attempt in range(2):
                picked = {}
                for r, bad in remaining:
                    try:
                        new, names = _llm_refine(r["after"], policy, bad, ask, feedback, path=r["path"])
                    except Exception as e:
                        llm_info["reason"] = f"LLM call failed: {e}"[:200]
                        names, new = [], r["after"]
                    if names:
                        from .shield import scan_text
                        shield_findings = scan_text(r["path"], new, policy)
                        if any(f.get("severity") == "block" for f in shield_findings):
                            llm_info["reason"] = f"Proposed LLM refactor for {r['path']} refused: violates Shield policy"
                        else:
                            if policy.get("format_command"):
                                new = format_source(new, policy)
                            picked[r["path"]] = (r, new, names)
                if not picked:
                    break
                trial = {**overrides, **{p: v[1] for p, v in picked.items()}}
                t2 = run_tests(root, trial, policy)
                if t2["ok"]:
                    for p, (r, new, names) in picked.items():
                        r["after"], r["ai_functions"] = new, names
                    overrides, tests = trial, t2
                    break
                feedback = t2["output"][-1500:]
            else:
                llm_info["reason"] = "LLM refactors failed tests twice - discarded, rule-based result kept"

    out_files = []
    for r in results:
        if r["after"] == r["before"]:
            continue
        b, a = metrics_mod.analyze(r["before"]), metrics_mod.analyze(r["after"])
        r["diff"] = _diff(r["path"], r["before"], r["after"])
        r["metrics"] = {"before": metrics_mod.summarize(b, r["before"].count("\n")),
                        "after": metrics_mod.summarize(a, r["after"].count("\n")),
                        "functions": [{"name": x["name"], "before": {k: x[k] for k in ("cc", "cog", "depth")},
                                       "after": {k: y[k] for k in ("cc", "cog", "depth")}}
                                      for x in b for y in a if x["name"] == y["name"]]}
        r["remaining"] = [{"name": v["name"], "why": v["why"]} for v in metrics_mod.violations(a, policy)]
        out_files.append(r)

    fuzz_total = {"checked_functions": 0, "inputs": 0, "diverged": 0}
    fuzz_diverged = False
    if policy.get("fuzz", True) and out_files:
        for r in out_files:
            ch_names = changed_functions(r["before"], r["after"])
            fz = fuzz.differential(r["before"], r["after"], ch_names)
            r["fuzz"] = fz
            for k in ("checked_functions", "inputs", "diverged"):
                fuzz_total[k] += fz.get(k, 0)
            if fz.get("diverged", 0) > 0:
                fuzz_diverged = True

    cov_info = tests.get("coverage", {})
    unexec = cov_info.get("unexecuted_functions", [])
    min_cov = policy.get("min_function_coverage")

    rewritten_names = set()
    for r in out_files:
        if r.get("ai_functions"):
            rewritten_names.update(r["ai_functions"])
        for f in r.get("metrics", {}).get("functions", []):
            if f["before"] != f["after"]:
                rewritten_names.add(f["name"])

    unexec_rewritten = [u for u in unexec if (not rewritten_names or u["function"] in rewritten_names or any(u["function"] == n.split(".")[-1] for n in rewritten_names))]
    below_threshold = []
    if min_cov is not None and cov_info.get("function_coverage"):
        below_threshold = [f for f in cov_info["function_coverage"]
                           if (not rewritten_names or f["function"] in rewritten_names or any(f["function"] == n.split(".")[-1] for n in rewritten_names))
                           and f["coverage_pct"] < min_cov]

    if not out_files:
        status = "nothing-to-optimize"
    elif tests["ok"] is False:
        status = "rejected-tests-failed"
    elif fuzz_diverged:
        status = "rejected (fuzz found a behaviour change)"
    elif tests["ok"] is None:
        status = "unverified-no-tests"
    elif unexec_rewritten or below_threshold:
        status = "verified (partial coverage)"
    else:
        status = "verified"

    applicable = (not fuzz_diverged) and (
        status in ("verified", "verified (partial coverage)") or (
            status == "unverified-no-tests" and not policy.get("require_tests")
        )
    )
    if min_cov is not None and (unexec_rewritten or below_threshold) and policy.get("require_tests") and min_cov > 0:
        applicable = False

    prop = {"id": pid, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "status": status, "files": out_files,
            "skipped": skipped_all + [dict(s, file=r["path"]) for r in results for s in r["skipped"]],
            "tests": tests, "coverage": cov_info,
            "unexecuted_functions": unexec_rewritten or below_threshold,
            "llm": llm_info,
            "fuzz": fuzz_total if fuzz_total["inputs"] else None,
            "head": gitutil.head(str(root)) if gitutil.is_repo(str(root)) else None,
            "applicable": applicable}
    os.makedirs(os.path.join(str(home), "proposals"), exist_ok=True)
    with open(os.path.join(str(home), "proposals", pid + ".json"), "w", encoding="utf-8") as f:
        json.dump(prop, f)
    return prop


def secrets_hex(nbytes):
    import secrets
    return secrets.token_hex(nbytes)


def load_proposal(home, pid):
    if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{6}", pid or ""):
        raise ValueError("bad proposal id")
    with open(os.path.join(str(home), "proposals", pid + ".json"), encoding="utf-8") as f:
        return json.load(f)


def apply(root, home, pid, actor):
    """Write an approved proposal to the working tree and commit it. Refuses stale proposals."""
    prop = load_proposal(home, pid)
    if not prop["applicable"]:
        raise ValueError(f"proposal is not applicable (status: {prop['status']})")
    if prop["head"] and gitutil.head(str(root)) != prop["head"]:
        raise ValueError("repository HEAD moved since this proposal was created - re-run the optimizer")
    for r in prop["files"]:
        full = os.path.realpath(os.path.join(str(root), os.path.normpath(r["path"])))
        root_real = os.path.realpath(str(root))
        try:
            if os.path.commonpath([root_real, full]) != root_real or full == root_real:
                raise ValueError("path escapes repository")
        except ValueError:
            raise ValueError("path escapes repository")
        cur = open(full, encoding="utf-8", newline="").read()
        if sha(cur) != r["before_sha"]:
            raise ValueError(f"{r['path']} changed since the proposal was created - re-run the optimizer")
    for r in prop["files"]:
        with open(os.path.join(str(root), r["path"]), "w", encoding="utf-8", newline="") as f:
            f.write(r["after"])
    sha_new = None
    if gitutil.is_repo(str(root)):
        paths = [r["path"] for r in prop["files"]]
        gitutil.git(str(root), "add", "--", *paths)
        msg = (f"RepoBrain: simplify {len(paths)} file(s) (tests passed)\n\nApproved-by: {actor}\n"
               f"RepoBrain-proposal: {pid}")
        gitutil.git(str(root), "-c", "user.name=RepoBrain", "-c", "user.email=repobrain@localhost",
                    "commit", "-m", msg)
        sha_new = gitutil.head(str(root))
    return {"applied": [r["path"] for r in prop["files"]], "commit": sha_new}


def run(root, policy, home, files=None, base=None, apply=False, ai=False, allow_unverified=False, log=True):
    from . import audit
    root = pathlib.Path(root)
    res = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "files": [], "tests": None, "fuzz": None, "status": ""}
    new_srcs, fuzz_total = {}, {"checked_functions": 0, "inputs": 0, "diverged": 0}

    if files:
        cand = list(files)
    elif base:
        out = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=str(root), capture_output=True, text=True)
        cand = out.stdout.splitlines()
    else:
        cand = [str(p.relative_to(root)) for p in root.rglob("*.py") if not (set(p.relative_to(root).parts) & SKIP_DIRS)]

    cand = [f for f in cand if f.endswith(".py") and (root / f).is_file()]

    for rel in sorted(cand):
        src = (root / rel).read_text(encoding="utf-8")
        try:
            before = metrics(src)
            new, notes, details = rewrite(src, policy.get("preserve_comments", True))
            if ai and llm.available():
                refined = ai_refine(new, policy)
                if refined:
                    new, notes = refined, notes + ["AI refinement"]
            after = metrics(new)
        except SyntaxError:
            continue
        fz, rejected = None, None
        if new != src and policy.get("fuzz", True):
            fz = fuzz.differential(src, new, changed_functions(src, new))
            for k in ("checked_functions", "inputs", "diverged"):
                fuzz_total[k] += fz.get(k, 0)
            if fz.get("diverged", 0) > 0:
                bad = next((n for n, r in fz["functions"].items() if r["diverged"]), "?")
                rejected = f"differential fuzz: {bad}() behaved differently on {fz['functions'][bad]['example']['input']}"
                new, notes, after = src, [], before
        if new != src:
            new_srcs[rel] = new
        diff = "".join(difflib.unified_diff(src.splitlines(True), new.splitlines(True), f"a/{rel}", f"b/{rel}"))
        old_rows = {r["name"]: r for r in analyze(src)}
        keys = ("complexity", "cognitive", "depth", "lines")
        fn_rows = [{"name": r["name"], "line": r["line"],
                    "before": ({k: old_rows[r["name"]][k] for k in keys} if r["name"] in old_rows else None),
                    "after": {k: r[k] for k in keys}} for r in analyze(new)]
        res["files"].append({"path": rel, "before": before, "after": after, "changes": dict(Counter(notes)), "diff": diff,
                             "functions": fn_rows, "skipped": [d for d in details if "skipped" in d], "fuzz": fz, "rejected": rejected})
    res["fuzz"] = fuzz_total if fuzz_total["inputs"] else None
    if not new_srcs:
        res["status"] = "rejected (fuzz found a behaviour change)" if any(f.get("rejected") for f in res["files"]) else "nothing to optimize"
        if log:
            audit.log(home, "optimize", "rejected" if res["status"].startswith("rejected") else "no-op", "repobrain", {"files": len(res["files"])})
        return res

    t_res = run_tests(str(root), new_srcs, policy)
    ok = t_res.get("ok")
    res["tests"] = {"ok": ok, **t_res}
    if ok is False:
        res["status"] = "rejected (tests failed, nothing proposed)"
        if log:
            audit.log(home, "optimize", "rejected", "repobrain", {"reason": "tests failed", "files": list(new_srcs)})
        return res

    pdir = pathlib.Path(home) / "proposals"
    pdir.mkdir(parents=True, exist_ok=True)
    patch = "".join(l for rel, new in new_srcs.items() for l in difflib.unified_diff(
        (root / rel).read_text().splitlines(True), new.splitlines(True), f"a/{rel}", f"b/{rel}"))
    (pdir / "latest.patch").write_text(patch)
    res["status"] = "proposed (awaiting human review)" if ok else "proposed (UNVERIFIED: no runnable tests)"
    if log:
        audit.log(home, "optimize", "proposed", "repobrain",
                  {"files": list(new_srcs), "tests_passed": ok, "fuzz_inputs": fuzz_total["inputs"], "fuzz_divergences": fuzz_total["diverged"]})
    if apply and (ok or allow_unverified):
        for rel, new in new_srcs.items():
            (root / rel).write_text(new)
        res["status"] = "applied after human approval"
        if log:
            audit.log(home, "optimize", "approved+applied", "human", {"files": list(new_srcs)})
    (pdir / "latest.json").write_text(json.dumps(res, indent=2))
    return res
