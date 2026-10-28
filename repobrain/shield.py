"""Shield: policy enforcement over paths and content. Pure functions, no I/O."""
import re

from . import policy as P

SECRET_PATTERNS = [
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("stripe-live-key", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{16,}\b")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    # GCP / Firebase service-account key JSON fragments
    ("gcp-service-account", re.compile(r'"private_key"\s*:\s*"-----BEGIN')),
    # Azure SAS / storage connection strings
    ("azure-storage", re.compile(r"\bDefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[A-Za-z0-9+/=]{50,}")),
    # Twilio auth tokens / SIDs
    ("twilio-token", re.compile(r"\bAC[0-9a-fA-F]{32}\b|\bSK[0-9a-fA-F]{32}\b")),
    # SendGrid / Mailgun / generic bearer tokens
    ("sendgrid-key", re.compile(r"\bSG\.[A-Za-z0-9_-]{22,}\.[A-Za-z0-9_-]{43,}\b")),
    # Generic high-entropy secrets (≥16-char base64-ish strings assigned to a secret-looking var).
    # Use word boundary on variable name so parser enums like token_type = '...' don't match.
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
               r"(?:instructions|prompts?|rules)"),
    re.compile(r"(?i)\bdisregard (?:all |any |the )?(?:previous|prior|above|system) "
               r"(?:instructions|prompts?|rules)"),
    re.compile(r"(?i)\byou are now (?:a|an|in)\b"),
    re.compile(r"(?i)\b(?:system|developer) prompt\b.{0,40}\b(?:reveal|print|show|leak|ignore)"),
    re.compile(r"(?i)\b(?:exfiltrate|send|post|upload)\b.{0,40}\b(?:secrets?|tokens?|api[_ -]?keys?"
               r"|credentials?|env(?:ironment)? variables?)\b"),
    re.compile(r"(?i)\bdo not (?:tell|inform|alert|notify) (?:the )?(?:user|human|reviewer|developer)"),
    re.compile(r"(?i)\b(?:AI|assistant|agent|copilot|claude)\b.{0,30}\b(?:must|should)\b.{0,30}"
               r"\b(?:disable|bypass|skip|turn off)\b.{0,30}\b(?:checks?|review|tests?|security|policy)"),
    # Multi-word injections that span line boundaries (e.g., split across comment continuation)
    re.compile(r"(?i)\bact as (?:a |an )?(?:different|new|unrestricted|jailbroken)\b"),
    re.compile(r"(?i)\b(?:override|overwrite|replace) (?:your |all )?(?:previous |system |default )?"
               r"(?:instructions|prompt|rules|guidelines|constraints)\b"),
    re.compile(r"(?i)\bpretend (?:you are|to be) (?:a |an )?(?!a programming|an algorithm|a function)\w"),
]
HIDDEN_CHARS = re.compile("[\u202a-\u202e\u2066-\u2069\u200b-\u200d\u2060\ufeff]")
MAX_BYTES = 1_000_000


def mask(s):
    return s[:4] + "…" + "*" * 6 if len(s) > 8 else "*" * len(s)


def finding(sev, rule, path, msg, line=None, evidence=None):
    f = {"severity": sev, "rule": rule, "file": path, "message": msg}
    if line:
        f["line"] = line
    if evidence:
        f["evidence"] = evidence
    return f


def scan_path(path, status, ai, policy):
    out = []
    pat = P.match_path(path, policy["blocked"])
    if pat:
        enforced = ai or policy["blocked_for"] == "all"
        who = "AI-authored change" if ai else "change"
        out.append(finding("block" if enforced else "warn", "blocked-path", path,
                           f"{who} touches protected path (matches '{pat}')"
                           + ("" if enforced else " - human author, flagged only")))
    pat = P.match_path(path, policy["review_required"])
    if pat and not P.match_path(path, policy["blocked"]):
        out.append(finding("warn", "review-required", path,
                           f"'{pat}' changes need explicit human review (dependency / build surface)"))
    if status == "D" and re.search(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$|[^/]*\.test\.[jt]sx?$)", path):
        out.append(finding("warn", "test-deleted", path, "test file deleted in this change"))
    return out


def scan_text(path, text, policy, only_lines=None):
    """Content rules. `only_lines`: iterable of line numbers to inspect (None = whole text).

    Multi-line injection detection: joins pairs of consecutive *added* lines and rescans
    the concatenation so injections split across comments/strings are caught.
    """
    if len(text.encode("utf-8", "ignore")) > MAX_BYTES or "\x00" in text[:4096]:
        return []
    only = set(only_lines) if only_lines is not None else None
    lines = text.splitlines()
    out = []
    reported_lines: set = set()  # avoid double-reporting same line
    for n, line in enumerate(lines, 1):
        if only is not None and n not in only:
            continue
        for rule, rx in SECRET_PATTERNS:
            m = rx.search(line)
            if m:
                out.append(finding("block", "secret", path,
                                   f"possible hardcoded credential ({rule})", n, mask(m.group(0))))
                reported_lines.add(n)
                break
        if n not in reported_lines:
            for rx in INJECTION_PATTERNS:
                if rx.search(line):
                    out.append(finding("block", "prompt-injection", path,
                                       "text that tries to instruct an AI agent (possible injection)", n,
                                       line.strip()[:80]))
                    reported_lines.add(n)
                    break
        if HIDDEN_CHARS.search(line):
            out.append(finding("block", "hidden-unicode", path,
                               "invisible / bidirectional control characters (Trojan Source style)", n))

    # Multi-line injection pass: join adjacent line pairs and scan the combined text.
    # This catches injections deliberately split across two lines (e.g. across comments).
    # Leading comment markers (#, //, *, /*) are stripped from the second line before joining.
    for i in range(len(lines) - 1):
        n1, n2 = i + 1, i + 2
        if only is not None and n1 not in only and n2 not in only:
            continue
        if n1 in reported_lines or n2 in reported_lines:
            continue  # already flagged
        next_clean = re.sub(r"^\s*(?:#|//|/\*|\*)\s*", "", lines[i + 1])
        combined = lines[i].rstrip() + " " + next_clean.lstrip()
        for rx in INJECTION_PATTERNS:
            if rx.search(combined):
                out.append(finding("block", "prompt-injection", path,
                                   "multi-line text that tries to instruct an AI agent (possible injection)",
                                   n1, combined.strip()[:120]))
                reported_lines.add(n1)
                break

    return out


def check_action(action, policy):
    """Playground / agent-hook entry point: one proposed action -> decision."""
    path = action.get("path", "")
    ai = action.get("ai")
    if ai is None:
        ai = P.is_ai(action.get("actor", ""), policy)
    fs = scan_path(path, action.get("status", "M"), ai, policy)
    fs += scan_text(path, action.get("content", ""), policy)
    blocked = any(f["severity"] == "block" for f in fs)
    return {"decision": "BLOCKED" if blocked else "ALLOWED", "ai": ai, "findings": fs}
