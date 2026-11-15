"""Role-Based Access Control (RBAC) & Enterprise Authentication for RepoBrain.

Provides:
- Company email domain verification (enforcing corporate domains, rejecting public webmail).
- FIPS-grade PBKDF2-HMAC-SHA256 password hashing (600,000 iterations, 16-byte cryptographically secure salt).
- Cryptographic session management (32-byte urlsafe tokens, 7-day TTL, thread-safe).
- 4-Tier Enterprise RBAC Matrix:
    * admin: Full governance authority, approve and apply commits, waivers, user management, policy editor.
    * security: Shield policy tuning, secret leak analysis, prompt injection defense, HMAC audit ledger verification, security waivers.
    * tester: Test suite runner, differential fuzzing inspector, function coverage gates, failure log explainer.
    * developer: AST complexity optimizer, PR diff inspector, preflight hook, approval requests.
- Integrated HMAC-SHA256 audit ledger logging for all authentication & authorization events.
- Evaluator persona switcher for seamless 1-click role testing in demos and evaluation environments.
"""

import hashlib
import json
import os
import re
import secrets
import threading
import time

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

# Common public webmail / free email providers that do NOT qualify as company/corporate domains
PUBLIC_WEBMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "ymail.com",
    "hotmail.com", "outlook.com", "live.com", "msn.com",
    "icloud.com", "me.com", "mac.com",
    "aol.com", "mail.com", "zoho.com", "protonmail.com",
    "proton.me", "tutanota.com", "yandex.com", "gmx.com", "fastmail.com"
}

ROLES = {
    "admin": {
        "id": "admin",
        "name": "Admin / Release Manager",
        "badge": "ADMIN",
        "color": "#ef4444",
        "description": "Full administrative authority: approve code merges, grant waivers, manage team roles and security policies.",
        "permissions": [
            "view_pr", "run_optimizer", "run_tests", "request_review",
            "inspect_fuzzing", "inspect_coverage", "run_explainer",
            "configure_shield", "inspect_secrets", "verify_audit", "simulate_tamper",
            "apply_approval", "grant_waiver", "manage_users", "manage_policy"
        ]
    },
    "security": {
        "id": "security",
        "name": "DevSecOps / Security Lead",
        "badge": "SECURITY",
        "color": "#a855f7",
        "description": "Security governance: configure Shield rules, inspect secret patterns, analyze prompt injection telemetry, verify HMAC audit chain, issue security waivers.",
        "permissions": [
            "view_pr", "request_review",
            "configure_shield", "inspect_secrets", "verify_audit", "simulate_tamper",
            "grant_waiver"
        ]
    },
    "tester": {
        "id": "tester",
        "name": "QA / Test Engineer",
        "badge": "TESTER",
        "color": "#eab308",
        "description": "Quality assurance: inspect differential fuzzing invariants, verify test coverage gates, run Failure Explainer on CI crash logs.",
        "permissions": [
            "view_pr", "run_tests", "request_review",
            "inspect_fuzzing", "inspect_coverage", "run_explainer"
        ]
    },
    "developer": {
        "id": "developer",
        "name": "Software Engineer / Developer",
        "badge": "DEV",
        "color": "#38bdf8",
        "description": "Software authoring: run AST optimizer, view PR diffs, execute preflight safety checks, submit human review requests.",
        "permissions": [
            "view_pr", "run_optimizer", "run_tests", "request_review"
        ]
    }
}

DEFAULT_DEMO_USERS = [
    {
        "id": "usr-alex-admin",
        "email": "alex.mercer@acmeworks.internal",
        "name": "Alex Mercer",
        "role": "admin",
        "company": "Acme Corp",
        "title": "Principal Release Manager"
    },
    {
        "id": "usr-sam-sec",
        "email": "samira.patel@acmeworks.internal",
        "name": "Samira Patel",
        "role": "security",
        "company": "Acme Corp",
        "title": "Lead DevSecOps Engineer"
    },
    {
        "id": "usr-quinn-qa",
        "email": "quinn.vance@acmeworks.internal",
        "name": "Quinn Vance",
        "role": "tester",
        "company": "Acme Corp",
        "title": "Staff QA & Reliability Engineer"
    },
    {
        "id": "usr-alice-dev",
        "email": "alice.chen@acmeworks.internal",
        "name": "Alice Chen",
        "role": "developer",
        "company": "Acme Corp",
        "title": "Senior Backend Developer"
    }
]

SESSION_TTL_SECONDS = 7 * 24 * 3600  # 7 days


def validate_company_email(email: str, allowed_domains=None):
    """Validate corporate email address:
    - Must be a syntactically valid email address.
    - Must NOT be from a generic free webmail provider (e.g. Gmail, Yahoo, Outlook).
    - If allowed_domains is specified, must match one of the allowed corporate domains.
    Returns (is_valid: bool, reason: str, domain: str).
    """
    if not email or not isinstance(email, str):
        return False, "Email address is required", ""
    email = email.strip().lower()
    if not EMAIL_REGEX.match(email):
        return False, "Invalid email format", ""
    domain = email.split("@", 1)[1].lower()
    if domain in PUBLIC_WEBMAIL_DOMAINS:
        return False, f"Personal email domain '@{domain}' is not allowed. Please register with your corporate company email.", domain
    if allowed_domains:
        norm_allowed = {d.strip().lower().lstrip("@") for d in allowed_domains if d.strip()}
        if norm_allowed and domain not in norm_allowed:
            return False, f"Domain '@{domain}' is not in the allowed corporate domain list: {', '.join(sorted(norm_allowed))}", domain
    return True, "", domain


def hash_password(password: str) -> str:
    """Hash password with PBKDF2-HMAC-SHA256, 600,000 iterations and a 16-byte random salt."""
    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters")
    salt = secrets.token_bytes(16)
    iterations = 600_000
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${derived.hex()}"


def verify_password(password: str, hashed_str: str) -> bool:
    """Verify password against stored PBKDF2 hash using constant-time comparison."""
    if not password or not hashed_str:
        return False
    try:
        parts = hashed_str.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected = bytes.fromhex(parts[3])
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return secrets.compare_digest(actual, expected)
    except Exception:
        return False


def domain_to_company_name(domain: str) -> str:
    """Infer a friendly company name from an email domain (e.g. acme-corp.com -> Acme Corp)."""
    if not domain:
        return "Enterprise Org"
    base = domain.split(".")[0]
    words = re.split(r"[-_]", base)
    return " ".join(w.capitalize() for w in words if w) or domain


class AuthManager:
    """Thread-safe user, role, and session manager backed by JSON files in REPOBRAIN_HOME."""

    def __init__(self, home_dir: str, is_demo: bool = True):
        self.home = str(home_dir)
        self.is_demo = bool(is_demo)
        self.users_file = os.path.join(self.home, "users.json")
        self.sessions_file = os.path.join(self.home, "sessions.json")
        self._lock = threading.RLock()
        self._users = {}
        self._sessions = {}
        os.makedirs(self.home, exist_ok=True)
        self._load()

    def _load(self):
        with self._lock:
            if os.path.isfile(self.users_file):
                try:
                    with open(self.users_file, "r", encoding="utf-8") as f:
                        self._users = json.load(f)
                except Exception:
                    self._users = {}
            if os.path.isfile(self.sessions_file):
                try:
                    with open(self.sessions_file, "r", encoding="utf-8") as f:
                        self._sessions = json.load(f)
                except Exception:
                    self._sessions = {}

            # Seed default demo enterprise personas if users database is empty AND in demo mode
            if not self._users and self.is_demo:
                self._seed_default_personas()

    def _save_users(self):
        tmp = self.users_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._users, f, indent=2)
        os.replace(tmp, self.users_file)

    def _save_sessions(self):
        tmp = self.sessions_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._sessions, f, indent=2)
        os.replace(tmp, self.sessions_file)

    def _seed_default_personas(self):
        default_pw_hash = hash_password("RepoBrainEnterprise2026!")
        for p in DEFAULT_DEMO_USERS:
            user_rec = {
                "id": p["id"],
                "email": p["email"],
                "name": p["name"],
                "role": p["role"],
                "company": p["company"],
                "title": p["title"],
                "password_hash": default_pw_hash,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "is_demo_seed": True
            }
            self._users[p["email"]] = user_rec
        self._save_users()

    def register(self, email: str, password: str, name: str, role="developer",
                 company=None, allowed_domains=None, audit_log=None):
        """Register a new user with company email, password, and enterprise role."""
        with self._lock:
            ok, reason, domain = validate_company_email(email, allowed_domains)
            if not ok:
                raise ValueError(reason)

            email_norm = email.strip().lower()
            if email_norm in self._users:
                raise ValueError(f"User with email '{email_norm}' is already registered")

            # Force all new registrations to developer tier to prevent self-privilege escalation to admin
            role = "developer"

            comp_name = (company or "").strip() or domain_to_company_name(domain)
            usr_name = (name or "").strip() or email_norm.split("@")[0].replace(".", " ").title()

            pw_hash = hash_password(password)
            user_id = f"usr-{secrets.token_hex(6)}"
            user_rec = {
                "id": user_id,
                "email": email_norm,
                "name": usr_name,
                "role": role,
                "company": comp_name,
                "title": ROLES[role]["name"],
                "password_hash": pw_hash,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "is_demo_seed": False
            }
            self._users[email_norm] = user_rec
            self._save_users()

            session_tok = self._create_session(user_rec)

            if audit_log:
                audit_log.append("auth-register", email_norm, "SUCCESS",
                                 f"New user registered as {ROLES[role]['badge']} for {comp_name}")

            return self._strip_user(user_rec), session_tok

    def login(self, email: str, password: str, audit_log=None):
        """Authenticate user with corporate credentials and issue session token."""
        with self._lock:
            email_norm = (email or "").strip().lower()
            user_rec = self._users.get(email_norm)
            if not user_rec:
                if audit_log:
                    audit_log.append("auth-login-failed", email_norm or "unknown", "REJECTED",
                                     "User not found")
                raise ValueError("Invalid corporate email or password")

            if not verify_password(password, user_rec.get("password_hash", "")):
                if audit_log:
                    audit_log.append("auth-login-failed", email_norm, "REJECTED",
                                     "Invalid password credentials")
                raise ValueError("Invalid corporate email or password")

            session_tok = self._create_session(user_rec)
            if audit_log:
                audit_log.append("auth-login", email_norm, "SUCCESS",
                                 f"Logged in as {ROLES.get(user_rec.get('role', 'developer'), {}).get('badge', 'USER')}")

            return self._strip_user(user_rec), session_tok

    def switch_demo_persona(self, role: str, audit_log=None):
        """Evaluator / Demo quick-switch: instantiates or finds persona for role and returns valid session."""
        if not self.is_demo:
            raise PermissionError("Demo persona switching is restricted to demo mode (--demo)")
        with self._lock:
            target_role = role.lower() if role in ROLES else "admin"
            match = None
            for u in self._users.values():
                if u.get("role") == target_role and u.get("is_demo_seed"):
                    match = u
                    break
            if not match:
                for u in self._users.values():
                    if u.get("role") == target_role:
                        match = u
                        break
            if not match:
                # Fallback to creating a seeded persona
                for p in DEFAULT_DEMO_USERS:
                    if p["role"] == target_role:
                        match = {
                            "id": p["id"],
                            "email": p["email"],
                            "name": p["name"],
                            "role": p["role"],
                            "company": p["company"],
                            "title": p["title"],
                            "password_hash": hash_password("RepoBrainEnterprise2026!"),
                            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "is_demo_seed": True
                        }
                        self._users[p["email"]] = match
                        self._save_users()
                        break
            if not match:
                raise ValueError(f"Unknown role '{role}'")

            session_tok = self._create_session(match)
            if audit_log:
                audit_log.append("auth-persona-switch", match["email"], "SUCCESS",
                                 f"Evaluator switched active persona to {ROLES[target_role]['badge']}")

            return self._strip_user(match), session_tok

    def _create_session(self, user_rec: dict) -> str:
        tok = secrets.token_urlsafe(32)
        now = time.time()
        self._sessions[tok] = {
            "token": tok,
            "user_id": user_rec["id"],
            "email": user_rec["email"],
            "name": user_rec["name"],
            "role": user_rec["role"],
            "company": user_rec["company"],
            "created_at": now,
            "expires_at": now + SESSION_TTL_SECONDS
        }
        self._save_sessions()
        return tok

    def get_user_by_token(self, token: str):
        """Retrieve user profile for session token. Returns None if invalid or expired."""
        if not token:
            return None
        with self._lock:
            s = self._sessions.get(token)
            if not s:
                return None
            if time.time() > s.get("expires_at", 0):
                self._sessions.pop(token, None)
                self._save_sessions()
                return None
            u = self._users.get(s.get("email", ""))
            if not u:
                return None
            return self._strip_user(u)

    def logout(self, token: str, audit_log=None):
        """Invalidate session token."""
        with self._lock:
            s = self._sessions.pop(token, None)
            self._save_sessions()
            if s and audit_log:
                audit_log.append("auth-logout", s.get("email", "unknown"), "LOGOUT", "Session invalidated")
            return {"ok": True}

    def list_users(self):
        """List team users without sensitive credentials."""
        with self._lock:
            return [self._strip_user(u) for u in self._users.values()]

    def update_role(self, target_email: str, new_role: str, actor_email: str, audit_log=None):
        """Update role for target user (requires admin authority)."""
        with self._lock:
            if new_role not in ROLES:
                raise ValueError(f"Invalid role '{new_role}'. Must be one of: {list(ROLES.keys())}")
            email_norm = target_email.strip().lower()
            if email_norm not in self._users:
                raise ValueError(f"User '{target_email}' not found")
            old_role = self._users[email_norm].get("role", "developer")
            self._users[email_norm]["role"] = new_role
            self._users[email_norm]["title"] = ROLES[new_role]["name"]
            self._save_users()

            # Update active sessions for this user
            for s in self._sessions.values():
                if s.get("email") == email_norm:
                    s["role"] = new_role
            self._save_sessions()

            if audit_log:
                audit_log.append("auth-role-change", actor_email, "UPDATED",
                                 f"Changed {email_norm} role from {old_role} to {new_role}")

            return self._strip_user(self._users[email_norm])

    def _strip_user(self, u: dict) -> dict:
        role_info = ROLES.get(u.get("role", "developer"), ROLES["developer"])
        return {
            "id": u.get("id"),
            "email": u.get("email"),
            "name": u.get("name"),
            "role": u.get("role"),
            "role_badge": role_info["badge"],
            "role_title": role_info["name"],
            "role_description": role_info["description"],
            "permissions": list(role_info["permissions"]),
            "company": u.get("company"),
            "title": u.get("title"),
            "created_at": u.get("created_at"),
            "is_demo_seed": u.get("is_demo_seed", False)
        }


def check_permission(user: dict, permission: str) -> bool:
    """Check if user role grants the specified permission."""
    if not user:
        return False
    role = user.get("role", "developer")
    role_def = ROLES.get(role)
    if not role_def:
        return False
    return permission in role_def["permissions"]
