"""Shield: policy enforcement over paths and content. Pure functions, no I/O."""
import base64
import fnmatch
import json
import math
import pathlib
import re
import unicodedata

from . import deps, mlguard
from . import policy as P

SECRET_PATTERNS = [
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("stripe-live-key", re.compile(r"\b[sr]k_live_[0-9A-Za-z]{16,}\b")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    # GCP / Firebase service-account key JSON fragments
    ("gcp-service-account", re.compile(r'"private_key"\s*:\s*"-----BEGIN')),
    # Azure SAS / storage connection strings
    ("azure-storage", re.compile(r"\bDefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[A-Za-z0-9+/=]{50,}")),
    # Twilio auth tokens / SIDs
    ("twilio-token", re.compile(r"\bAC[0-9a-fA-F]{32}\b|\bSK[0-9a-fA-F]{32}\b")),
    # SendGrid / Mailgun / generic bearer tokens
    ("sendgrid-key", re.compile(r"\bSG\.[A-Za-z0-9_-]{22,}\.[A-Za-z0-9_-]{43,}\b")),
    ("jwt-token", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    # Generic high-entropy secrets (≥16-char base64-ish strings assigned to a secret-looking var).
    ("generic-secret", re.compile(
        r"""(?ix)\b(?:
            api[_-]?key |
            (?:client|app|user|access|auth|jwt|bearer)[_-]?(?:secret|token|key) |
            secret(?:[_-]?(?:key|token|val|value))? |
            pass(?:wd|word) |
            auth[_-]?token |
            credentials? |
            token
        )\b\s*[:=]\s*['"][A-Za-z0-9/+_\-=]{16,}['"]""")),
]

INJECTION_PATTERNS = [
    re.compile(r"(?i)\bignore (?:all |any )?(?:the )?(?:previous|prior|above|earlier) "
               r"(?:instructions|prompts?|rules|directives|guidelines)"),
    re.compile(r"(?i)\bdisregard (?:all |any |the )?(?:previous|prior|above|system) "
               r"(?:instructions|prompts?|rules|polic|guidelines)"),
    re.compile(r"(?i)\byou are now (?:a|an|in)\b"),
    re.compile(r"(?i)\b(?:system|developer) prompt\b.{0,40}\b(?:reveal|print|show|leak|ignore)"),
    re.compile(r"(?i)\b(?:exfiltrate|send|post|upload)\b.{0,40}\b(?:secrets?|tokens?|api[_ -]?keys?"
               r"|credentials?|env(?:ironment)? variables?)\b"),
    re.compile(r"(?i)\bdo not (?:tell|inform|alert|notify|mention) (?:the )?(?:user|human|reviewer|maintainers?|developer|anyone)"),
    re.compile(r"(?i)\b(?:AI|assistant|agent|copilot|claude|language model|bot)s?\b.{0,30}\b(?:must|should|please)\b.{0,40}"
               r"\b(?:disable|bypass|skip|turn off|ignore|approve|execute|run)\b"),
    re.compile(r"(?i)\bact as (?:a |an )?(?:different|new|unrestricted|jailbroken)\b"),
    re.compile(r"(?i)\b(?:override|overwrite|replace|circumvent) (?:your |all |any |the )?(?:previous |system |default |safety |security |repository )?"
               r"(?:instructions|prompt|rules|guidelines|constraints|policy|guardrails)\b"),
    re.compile(r"(?i)\bpretend (?:you are|to be) (?:a |an )?(?!a programming|an algorithm|a function)\w"),
    re.compile(r"(?i)\bforget (?:everything|all|what) (?:you|that)\b"),
    re.compile(r"(?i)\b(?:new|updated) (?:system )?(?:instructions|prompt)\s*:"),
]

RISKY_COMMANDS = [
    ("pipes a download straight into a shell", re.compile(r"(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba|z)?sh\b")),
    ("executes unverified PowerShell command or download", re.compile(r"(?i)\b(?:Invoke-Expression\b|iex\b.*?(?:iwr|Invoke-WebRequest|DownloadString|Net\.WebClient|\()|(?:iwr|Invoke-WebRequest)\b[^\n|]*\|\s*iex\b)")),
    ("grants workflow write-all permissions", re.compile(r"permissions:\s*write-all")),
    ("uses pull_request_target (runs untrusted code with secrets)", re.compile(r"\bpull_request_target\b")),
    ("makes files world-writable", re.compile(r"chmod\s+(?:-R\s+)?777")),
    ("executes obfuscated/decoded code", re.compile(r"\b(?:exec|eval)\s*\(\s*(?:base64\.b64decode|bytes\.fromhex|codecs\.decode|atob)")),
]

HIDDEN_CHARS = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\U000e0000-\U000e007f]")
SKIP_ENTROPY = re.compile(r"(?:\.lock|package-lock\.json|yarn\.lock|\.svg|\.min\.js|\.map)$")
MAX_BYTES = 1_000_000


def mask(s):
    if len(s) > 8:
        return s[:4] + "…[" + str(len(s)) + " chars redacted]"
    return "[redacted]"


def _normalize_concat(line):
    prev = None
    cur = line
    while cur != prev:
        prev = cur
        cur = re.sub(r"""['"]\s*(?:\+\s*)?['"]""", "", cur)
    return cur


def _scan_base64_secret(line):
    for m in re.finditer(r"""['"]([A-Za-z0-9+/=_-]{16,})['"]""", line):
        raw = m.group(1)
        clean = raw.replace("-", "+").replace("_", "/").rstrip("=")
        pad = (4 - len(clean) % 4) % 4
        padded = clean + ("=" * pad)
        try:
            decoded = base64.b64decode(padded).decode("utf-8", "ignore")
        except Exception:
            continue
        if decoded and len(decoded) >= 8:
            for rule, rx in SECRET_PATTERNS:
                m_dec = rx.search(decoded)
                if m_dec:
                    return rule, raw, m_dec.group(0)
    return None


def entropy(s):
    if not s:
        return 0.0
    return -sum(c / len(s) * math.log2(c / len(s)) for c in (s.count(ch) for ch in set(s)))


def is_ai(actor, policy):
    if not actor:
        return False
    return P.is_ai(actor, policy)


def _glob(path, pat):
    if pat.endswith("/"):
        return ("/" + path).find("/" + pat) != -1
    base = pathlib.PurePath(path).name
    return fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(base, pat)


def blocked_by(path, policy):
    return next((p for p in policy.get("blocked", []) if _glob(path, p)), None)


def ignored(path, policy):
    return any(_glob(path, p) for p in policy.get("ignore", []))


def injection_rule_hit(text):
    return any(rx.search(text) for rx in INJECTION_PATTERNS)


def _sentences(line):
    s = re.sub(r"^\s*(?:#+|//+|/\*+|\*+|<!--|-|>|\d+\.)\s*", "", line).replace("-->", "").strip()
    return [x for x in re.split(r"(?<=[.!?])\s+", s) if len(x.split()) >= 4]


def finding(sev, rule, path, msg, line=None, evidence=None, **extra):
    f = {"severity": sev, "rule": rule, "file": path, "msg": msg, "message": msg, **extra}
    if line is not None:
        f["line"] = line
    if evidence is not None:
        f["evidence"] = evidence
    return f


def scan_path(path, status, ai, policy):
    out = []
    pat = P.match_path(path, policy.get("blocked", []))
    if pat:
        enforced = ai or policy.get("blocked_for", "ai") == "all"
        who = "AI-authored change" if ai else "change"
        out.append(finding("block" if enforced else "warn", "blocked-path", path,
                           f"{who} touches protected path (matches '{pat}')"
                           + ("" if enforced else " - human author, flagged only"), evidence=pat))
    pat = P.match_path(path, policy.get("review_required", []))
    if pat and not P.match_path(path, policy.get("blocked", [])):
        out.append(finding("warn", "review-required", path,
                           f"'{pat}' changes need explicit human review (dependency / build surface)"))
    if status == "D" and re.search(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$|[^/]*\.test\.[jt]sx?$)", path):
        out.append(finding("warn", "test-deleted", path, "test file deleted in this change"))
    return out


def scan_text(path, text, policy, actor=None, only_lines=None):
    """Scan file content. Accepts either (path, text, policy, only_lines)
    or (path, text, policy, actor, only_lines)."""
    if isinstance(actor, (set, list, tuple, dict)) or (hasattr(actor, "__iter__") and not isinstance(actor, str)):
        only_lines = actor
        actor = "unknown"

    actor_str = str(actor or "unknown")
    ai = is_ai(actor_str, policy)

    if len(text.encode("utf-8", "ignore")) > MAX_BYTES or "\x00" in text[:4096]:
        return []

    only = set(only_lines) if only_lines is not None else None
    lines = text.splitlines()
    out = []
    reported_lines = set()

    for n, line in enumerate(lines, 1):
        if only is not None and n not in only:
            continue
        if len(line) > 4000:
            continue

        # 1. Known secret patterns (direct or normalized string concatenation)
        matched_rule = None
        for rule, rx in SECRET_PATTERNS:
            m = rx.search(line)
            if m:
                matched_rule = (rule, m.group(0))
                break
        if not matched_rule and ("+" in line or re.search(r"""['"]\s+['"]""", line)):
            norm_line = _normalize_concat(line)
            for rule, rx in SECRET_PATTERNS:
                m = rx.search(norm_line)
                if m:
                    matched_rule = (rule, m.group(0))
                    break
        if matched_rule:
            out.append(finding("block", "secret", path,
                               f"possible hardcoded credential ({matched_rule[0]})", n, mask(matched_rule[1])))
            reported_lines.add(n)

        # 1b. Base64-encoded secret literals (len >= 16)
        if n not in reported_lines:
            b64_hit = _scan_base64_secret(line)
            if b64_hit:
                rule, raw, _ = b64_hit
                out.append(finding("block", "secret", path,
                                   f"possible hardcoded credential (base64-encoded {rule})", n, mask(raw)))
                reported_lines.add(n)

        # 2. Entropy fallback for keyword-less secrets
        if n not in reported_lines and not SKIP_ENTROPY.search(path):
            for m in re.finditer(r"['\"]([A-Za-z0-9+/_=\-]{24,})['\"]", line):
                tok = m.group(1)
                if entropy(tok) >= 4.2 and re.search(r"\d", tok) and re.search(r"[A-Za-z]", tok) and not re.fullmatch(r"[0-9a-f]{32,64}", tok):
                    out.append(finding("block" if ai else "warn", "high-entropy-string", path,
                                       "High-entropy string that looks like a secret", n, mask(tok)))
                    reported_lines.add(n)
                    break

        # 3. Invisible / Trojan source Unicode
        if HIDDEN_CHARS.search(line) and not (n == 1 and line.startswith("\ufeff") and not HIDDEN_CHARS.search(line[1:])):
            out.append(finding("block", "hidden-unicode", path,
                               "invisible / bidirectional control characters (Trojan Source style)", n))
            reported_lines.add(n)

        # 4. Risky commands / dangerous configurations (only for files not already blocked by path)
        if not blocked_by(path, policy):
            for desc, rx in RISKY_COMMANDS:
                if rx.search(line):
                    out.append(finding("block" if ai else "warn", "risky-command", path,
                                       f"Change {desc}", n, line.strip()[:90]))
                    reported_lines.add(n)
                    break

        # 5. Single-line Prompt injection rules
        if n not in reported_lines:
            for rx in INJECTION_PATTERNS:
                if rx.search(line):
                    hid = "<!--" in line or (n > 1 and "<!--" in lines[n - 2] and "-->" not in lines[n - 2])
                    msg = "text that tries to instruct an AI agent (possible injection)"
                    if hid:
                        msg += " (hidden in an HTML comment)"
                    out.append(finding("block", "prompt-injection", path, msg, n, line.strip()[:80], source="rules"))
                    reported_lines.add(n)
                    break

    # Multi-line injection pass: join adjacent line windows (2, 3, 4 lines)
    for w in (2, 3, 4):
        for i in range(len(lines) - w + 1):
            window_lines = [i + k + 1 for k in range(w)]
            if only is not None and not any(n_w in only for n_w in window_lines):
                continue
            if any(n_w in reported_lines for n_w in window_lines):
                continue
            cleaned = []
            for k in range(w):
                raw_l = lines[i + k]
                c_l = re.sub(r"^\s*(?:#+|//+|/\*+|\*+|<!--)\s*", "", raw_l).rstrip()
                c_l = re.sub(r"\s*(?:-->|\*/)\s*$", "", c_l)
                cleaned.append(c_l)
            combined = " ".join(c for c in cleaned if c)
            for rx in INJECTION_PATTERNS:
                if rx.search(combined):
                    out.append(finding("block", "prompt-injection", path,
                                       "multi-line text that tries to instruct an AI agent (possible injection)",
                                       window_lines[0], combined.strip()[:120], source="rules"))
                    for n_w in window_lines:
                        reported_lines.add(n_w)
                    break

    # Machine-learning prompt-injection guard (model only warns, never blocks)
    if policy.get("ml_guard", True):
        for i, line in enumerate(lines, 1):
            if only is not None and i not in only:
                continue
            if i in reported_lines or len(line) > 2000:
                continue
            best = 0.0
            for s in _sentences(line):
                if len(re.findall(r"[A-Za-z ,']", s)) / max(len(s), 1) < 0.85 or not mlguard.directive(s):
                    continue
                best = max(best, mlguard.score(s))
            if best >= mlguard.WARN_AT:
                out.append(finding("warn", "prompt-injection", path,
                                   f"Learned classifier: wording resembles an instruction aimed at AI agents (p={best:.2f})",
                                   i, re.sub(r"\s+", " ", line.strip())[:90], source="model", score=round(best, 3),
                                   terms=mlguard.model().top_terms(line)))

    return out


def check(root, files, policy, actor, added=None, base=None):
    """Check `files` (paths relative to root). `added`: {path: {lineno: text}} limits content scans to new lines."""
    findings, ai = [], is_ai(actor, policy)
    max_files = policy.get("max_files_changed", policy.get("max_files_per_run", 25))
    if len(files) > max_files:
        findings.append(finding("warn", "large-change", "*", f"{len(files)} files changed (limit {max_files})", line=0))
    for path in files:
        if ignored(path, policy):
            continue
        hit = blocked_by(path, policy)
        if hit:
            findings.append(finding("block" if ai else "warn", "blocked-path", path,
                                    f"{'AI actor' if ai else 'Change'} touches protected path '{hit}'", line=0, evidence=hit))
        fp = pathlib.Path(root) / path
        if not fp.is_file() or fp.stat().st_size > MAX_BYTES:
            continue
        try:
            text = fp.read_text(errors="ignore")
        except OSError:
            continue
        only = set(added[path]) if added and path in added else None
        findings += scan_text(path, text, policy, actor, only)
        if policy.get("dependency_guard", True) and deps.is_manifest(path):
            ls = [(n, t) for n, t in enumerate(text.split("\n"), 1) if only is None or n in only]
            for d in deps.check_added(path, ls, policy):
                findings.append(finding("block" if ai else "warn", "dependency-risk", path,
                                        d["msg"], line=d["line"], evidence=d["evidence"], kind=d.get("kind")))
    return findings


def check_action(action, policy):
    """Playground / agent-hook entry point: one proposed action -> decision."""
    path = action.get("path", "")
    ai = action.get("ai")
    actor = action.get("actor", "")
    if ai is None:
        ai = is_ai(actor, policy)
    fs = scan_path(path, action.get("status", "M"), ai, policy)
    fs += scan_text(path, action.get("content", ""), policy, actor)
    blocked = any(f["severity"] == "block" for f in fs)
    return {"decision": "BLOCKED" if blocked else "ALLOWED", "ai": ai, "findings": fs}
