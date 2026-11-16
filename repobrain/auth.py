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
import hmac
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


DUMMY_PBKDF2_HASH = "pbkdf2_sha256$600000$e3b0c44298fc1c149afbf4c8996fb924$e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

COMMON_PASSWORDS = {
    "password", "password123", "password1234", "12345678", "123456789", "1234567890",
    "qwerty123456", "admin123456", "welcome1234", "letmein1234", "repobrain1234",
    "iloveyou1234", "secret123456", "changeme1234", "monkey123456", "dragon123456",
    "master123456", "sunshine1234", "princess1234", "football1234"
}


def validate_password_complexity(password: str, is_demo: bool = True):
    if is_demo:
        return
    if not password or len(password) < 12:
        raise ValueError("Password must be at least 12 characters long outside demo mode")
    p_low = password.strip().lower()
    if p_low in COMMON_PASSWORDS:
        raise ValueError("Password is too common or easily guessable; please choose a stronger corporate password")


def hash_password(password: str) -> str:
    """Hash password with PBKDF2-HMAC-SHA256, 600,000 iterations and a 16-byte random salt."""
    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters")
    salt = secrets.token_bytes(16)
    iterations = 600_000
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${derived.hex()}"


def hash_session_token(token: str) -> str:
    """Compute SHA-256 hash of a bearer session token for secure persistence."""
    return hashlib.sha256((token or "").strip().encode("utf-8")).hexdigest()


def get_server_secret(home_dir: str = None) -> bytes:
    sec = os.environ.get("REPOBRAIN_SECRET", "").strip()
    if sec:
        return sec.encode("utf-8")
    if not home_dir:
        home_dir = os.environ.get("REPOBRAIN_HOME", os.path.expanduser("~/.repobrain"))
    sec_file = os.path.join(home_dir, "secret.key")
    if os.path.isfile(sec_file):
        try:
            with open(sec_file, "rb") as f:
                data = f.read().strip()
                if data:
                    return data
        except Exception:
            pass
    os.makedirs(home_dir, exist_ok=True)
    new_secret = secrets.token_bytes(32)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    mode = 0o600
    try:
        fd = os.open(sec_file, flags, mode)
        with os.fdopen(fd, "wb") as f:
            f.write(new_secret)
    except Exception:
        with open(sec_file, "wb") as f:
            f.write(new_secret)
        try:
            os.chmod(sec_file, 0o600)
        except Exception:
            pass
    return new_secret


def hash_otp(code: str, salt: str, secret: bytes = None) -> str:
    """Compute HMAC-SHA256(server_secret, salt+code) for corporate email verification OTP."""
    if secret is None:
        secret = get_server_secret()
    elif isinstance(secret, str):
        secret = secret.encode("utf-8")
    msg = f"{salt}:{str(code).strip()}".encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


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
        self.server_secret = get_server_secret(self.home)
        self.users_file = os.path.join(self.home, "users.json")
        self.sessions_file = os.path.join(self.home, "sessions.json")
        self._lock = threading.RLock()
        self._users = {}
        self._sessions = {}
        self._last_test_otp = {}
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
                "is_demo_seed": True,
                "email_verified": True,
                "verification_code": None
            }
            self._users[p["email"]] = user_rec
        self._save_users()

    def register(self, email: str, password: str, name: str, role="developer",
                 company=None, allowed_domains=None, audit_log=None):
        """Register a new user with company email, password, and enterprise role."""
        smtp_host = os.environ.get("REPOBRAIN_SMTP_HOST") or os.environ.get("SMTP_HOST")
        if not self.is_demo and not smtp_host:
            raise ValueError("Registration unavailable: SMTP service is not configured. Email verification is required in production.")

        ok, reason, domain = validate_company_email(email, allowed_domains)
        if not ok:
            raise ValueError(reason)

        validate_password_complexity(password, self.is_demo)

        email_norm = email.strip().lower()

        # Compute PBKDF2 hash outside lock to prevent blocking concurrent sessions
        pw_hash = hash_password(password)

        # Generate 6-digit verification code and HMAC-SHA256 hash
        now = time.time()
        raw_code = f"{secrets.randbelow(900000) + 100000}"
        salt = secrets.token_hex(16)
        code_hash = hash_otp(raw_code, salt, self.server_secret)
        expires_at = now + 900  # 15 minutes

        with self._lock:
            if email_norm in self._users:
                raise ValueError(f"User with email '{email_norm}' is already registered")

            # Force all public self-registrations to developer tier to prevent self-privilege escalation.
            # Initial administrator must be provisioned via bootstrap_admin().
            assigned_role = "developer"

            comp_name = (company or "").strip() or domain_to_company_name(domain)
            usr_name = (name or "").strip() or email_norm.split("@")[0].replace(".", " ").title()

            user_id = f"usr-{secrets.token_hex(6)}"
            user_rec = {
                "id": user_id,
                "email": email_norm,
                "name": usr_name,
                "role": assigned_role,
                "company": comp_name,
                "title": ROLES[assigned_role]["name"],
                "password_hash": pw_hash,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "is_demo_seed": False,
                "email_verified": False,
                "otp_hash": code_hash,
                "otp_salt": salt,
                "otp_expires_at": expires_at,
                "otp_window_expires_at": expires_at,
                "otp_attempts": 0,
                "resend_timestamps": [],
            }
            self._users[email_norm] = user_rec
            self._last_test_otp[email_norm] = raw_code
            self._save_users()

            session_tok = self._create_session(user_rec)

            if self.is_demo and os.environ.get("REPOBRAIN_DEMO_PRINT_OTP") == "1":
                print(f"[RepoBrain Demo Auth] Corporate verification code for {email_norm}: {raw_code} (expires in 15m)")

            if audit_log:
                audit_log.append("auth-register", email_norm, "SUCCESS",
                                 f"New user registered as {ROLES[assigned_role]['badge']} for {comp_name} (pending verification)")

            return self._strip_user(user_rec), session_tok

    def bootstrap_admin(self, email: str, password: str, name: str, company=None, audit_log=None):
        """Bootstrap the first system administrator account outside demo mode."""
        if not password or len(password) < 12:
            raise ValueError("Administrator password must be at least 12 characters")
        with self._lock:
            has_admin = any(u.get("role") == "admin" for u in self._users.values())
            if has_admin:
                raise PermissionError("An administrator already exists. Role changes must be performed by an existing admin.")

            ok, reason, domain = validate_company_email(email)
            if not ok:
                raise ValueError(reason)

            email_norm = email.strip().lower()
            if email_norm in self._users:
                raise ValueError(f"User with email '{email_norm}' is already registered")

            comp_name = (company or "").strip() or domain_to_company_name(domain)
            usr_name = (name or "").strip() or email_norm.split("@")[0].replace(".", " ").title()

            pw_hash = hash_password(password)
            user_id = f"usr-{secrets.token_hex(6)}"
            user_rec = {
                "id": user_id,
                "email": email_norm,
                "name": usr_name,
                "role": "admin",
                "company": comp_name,
                "title": ROLES["admin"]["name"],
                "password_hash": pw_hash,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "is_demo_seed": False,
                "email_verified": True,
            }
            self._users[email_norm] = user_rec
            self._save_users()
            session_tok = self._create_session(user_rec)

            if audit_log:
                audit_log.append("auth-bootstrap-admin", email_norm, "SUCCESS",
                                 f"First administrator account bootstrapped for {comp_name}")

            return self._strip_user(user_rec), session_tok

    def get_last_otp_for_test(self, email: str) -> str:
        """Testing helper to inspect the last generated OTP in memory without leaking via API."""
        return self._last_test_otp.get((email or "").strip().lower(), "")

    def verify_email(self, email: str, code: str, audit_log=None):
        """Verify corporate email address using 6-digit OTP."""
        with self._lock:
            email_norm = (email or "").strip().lower()
            u = self._users.get(email_norm)
            if not u:
                raise ValueError(f"User with email '{email}' not found")
            if u.get("email_verified", False):
                return self._strip_user(u)

            otp_hash = u.get("otp_hash")
            otp_salt = u.get("otp_salt")
            legacy_code = u.get("verification_code")

            if not otp_hash and not legacy_code:
                raise ValueError("No active verification code for this account. Please request a new code.")

            attempts = int(u.get("otp_attempts", 0))
            if attempts >= 5:
                if audit_log:
                    audit_log.append("auth-verify-locked", email_norm, "REJECTED", "OTP attempts exceeded max limit (5)")
                raise ValueError("Verification code has exceeded maximum attempt limit (5 attempts). Please request a new code.")

            expires_at = float(u.get("otp_expires_at", 0))
            if expires_at and time.time() > expires_at:
                if audit_log:
                    audit_log.append("auth-verify-expired", email_norm, "REJECTED", "OTP code expired (> 15 mins)")
                raise ValueError("Verification code has expired (valid for 15 minutes). Please request a new code.")

            code_clean = str(code).strip()
            match = False
            if otp_hash and otp_salt:
                expected_hash = hash_otp(code_clean, otp_salt, self.server_secret)
                match = secrets.compare_digest(expected_hash, otp_hash)
            elif legacy_code:
                match = secrets.compare_digest(code_clean, str(legacy_code).strip())

            if not match:
                u["otp_attempts"] = attempts + 1
                self._save_users()
                remaining = max(0, 5 - (attempts + 1))
                if audit_log:
                    audit_log.append("auth-verify-failed", email_norm, "REJECTED", f"Invalid OTP code ({remaining} attempts remaining)")
                raise ValueError(f"Invalid verification code. {remaining} attempt(s) remaining before code is invalidated.")

            u["email_verified"] = True
            u.pop("otp_hash", None)
            u.pop("otp_salt", None)
            u.pop("otp_expires_at", None)
            u.pop("otp_window_expires_at", None)
            u.pop("otp_attempts", None)
            u.pop("resend_timestamps", None)
            u.pop("verification_code", None)
            self._save_users()
            if audit_log:
                audit_log.append("auth-verify-success", email_norm, "VERIFIED", "Corporate email verified with OTP")
            return self._strip_user(u)

    def resend_verification_code(self, email: str, audit_log=None):
        """Resend a new 6-digit corporate verification OTP."""
        email_norm = (email or "").strip().lower()
        now = time.time()

        smtp_host = os.environ.get("REPOBRAIN_SMTP_HOST") or os.environ.get("SMTP_HOST")
        if not self.is_demo and not smtp_host:
            raise ValueError("Resend unavailable: SMTP service is not configured. Email verification is required in production.")

        with self._lock:
            u = self._users.get(email_norm)
            if not u:
                raise ValueError(f"User with email '{email}' not found")
            if u.get("email_verified", False):
                return {"email": email_norm, "status": "already_verified", "email_verified": True}

            # Rate limit resends: 3 per hour max
            resends = [t for t in u.get("resend_timestamps", []) if now - t < 3600]
            if len(resends) >= 3:
                raise ValueError("Too many resend requests. Maximum 3 resends per hour allowed.")
            resends.append(now)
            u["resend_timestamps"] = resends

            # Window check: 15-minute window
            window_exp = float(u.get("otp_window_expires_at", 0))
            if now < window_exp:
                # Window still active: do NOT reset attempt counter!
                current_attempts = int(u.get("otp_attempts", 0))
                if current_attempts >= 5:
                    raise ValueError("Verification code has exceeded maximum attempt limit (5 attempts). Please wait until the 15-minute window expires.")
                u["otp_attempts"] = current_attempts
            else:
                # Window expired, start new window
                u["otp_window_expires_at"] = now + 900
                u["otp_attempts"] = 0

            raw_code = f"{secrets.randbelow(900000) + 100000}"
            salt = secrets.token_hex(16)
            code_hash = hash_otp(raw_code, salt, self.server_secret)
            u["otp_hash"] = code_hash
            u["otp_salt"] = salt
            u["otp_expires_at"] = u["otp_window_expires_at"]
            u.pop("verification_code", None)
            self._last_test_otp[email_norm] = raw_code
            self._save_users()

            if self.is_demo and os.environ.get("REPOBRAIN_DEMO_PRINT_OTP") == "1":
                print(f"[RepoBrain Demo Auth] Resent verification code for {email_norm}: {raw_code} (expires in 15m)")

            mode = "smtp" if smtp_host else "demo_simulation"
            if audit_log:
                audit_log.append("auth-resend-code", email_norm, "SENT", f"Resent OTP verification code (mode: {mode})")
            return {"email": email_norm, "status": "sent", "mode": mode, "expires_in": int(round(max(0, u["otp_expires_at"] - now)))}

    def login(self, email: str, password: str, audit_log=None):
        """Authenticate user with corporate credentials and issue session token."""
        email_norm = (email or "").strip().lower()
        with self._lock:
            user_rec = self._users.get(email_norm)
            stored_hash = user_rec.get("password_hash", "") if user_rec else DUMMY_PBKDF2_HASH

        # Compute password verification outside self._lock so 600,000 PBKDF2 iterations
        # never block concurrent get_user_by_token requests.
        # Constant-time: always executes PBKDF2 even if user does not exist.
        valid = verify_password(password or "dummy", stored_hash)

        if not user_rec or not valid:
            if audit_log:
                audit_log.append("auth-login-failed", email_norm or "unknown", "REJECTED", "Invalid credentials")
            raise ValueError("Invalid corporate email or password")

        with self._lock:
            user_rec = self._users.get(email_norm)
            if not user_rec:
                raise ValueError("User deleted during authentication")
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
        h = hash_session_token(tok)
        now = time.time()

        # Purge expired sessions on write
        expired = [k for k, s in self._sessions.items() if now > s.get("expires_at", 0)]
        for k in expired:
            self._sessions.pop(k, None)

        # Cap active sessions per user to 5 (evict oldest)
        user_email = user_rec["email"]
        user_sessions = [(k, s.get("created_at", 0)) for k, s in self._sessions.items() if s.get("email") == user_email]
        user_sessions.sort(key=lambda x: x[1])
        while len(user_sessions) >= 5:
            oldest_k, _ = user_sessions.pop(0)
            self._sessions.pop(oldest_k, None)

        self._sessions[h] = {
            "token_hash": h,
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

    def invalidate_user_sessions(self, email_norm: str):
        """Invalidate all active sessions for a user (on role change, password change, etc)."""
        with self._lock:
            to_del = [k for k, s in self._sessions.items() if s.get("email") == email_norm]
            for k in to_del:
                self._sessions.pop(k, None)
            self._save_sessions()

    def change_password(self, email: str, old_password: str, new_password: str, audit_log=None):
        """Change user password, verifying complexity outside demo mode, and invalidating existing sessions."""
        email_norm = email.strip().lower()
        validate_password_complexity(new_password, self.is_demo)
        with self._lock:
            u = self._users.get(email_norm)
            if not u:
                raise ValueError("User not found")
            if not verify_password(old_password, u.get("password_hash", "")):
                raise ValueError("Invalid current password")
            u["password_hash"] = hash_password(new_password)
            self._save_users()
            self.invalidate_user_sessions(email_norm)
            if audit_log:
                audit_log.append("auth-password-change", email_norm, "SUCCESS", "Password updated; all existing sessions invalidated")
            return {"ok": True}

    def get_user_by_token(self, token: str):
        """Retrieve user profile for session token. Returns None if invalid or expired."""
        if not token:
            return None
        h = hash_session_token(token)
        with self._lock:
            s = self._sessions.get(h)
            # Compatibility migration for any pre-existing plaintext token entries
            if not s and token in self._sessions:
                s = self._sessions.pop(token)
                self._sessions[h] = s
                self._save_sessions()
            if not s:
                return None
            if time.time() > s.get("expires_at", 0):
                self._sessions.pop(h, None)
                self._save_sessions()
                return None
            u = self._users.get(s.get("email", ""))
            if not u:
                return None
            res = self._strip_user(u)
            res["session_hash"] = h
            return res

    def logout(self, token: str, audit_log=None):
        """Invalidate session token."""
        if not token:
            return {"ok": True}
        h = hash_session_token(token)
        with self._lock:
            s = self._sessions.pop(h, None) or self._sessions.pop(token, None)
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

            # Invalidate all active sessions on role change (security requirement)
            self.invalidate_user_sessions(email_norm)

            if audit_log:
                audit_log.append("auth-role-change", actor_email, "UPDATED",
                                 f"Changed {email_norm} role from {old_role} to {new_role}")

            return self._strip_user(self._users[email_norm])

    def _strip_user(self, u: dict) -> dict:
        role_info = ROLES.get(u.get("role", "developer"), ROLES["developer"])
        is_verified = bool(u.get("email_verified", True if u.get("is_demo_seed") else False))
        smtp_configured = bool(os.environ.get("REPOBRAIN_SMTP_HOST") or os.environ.get("SMTP_HOST"))
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
            "is_demo_seed": u.get("is_demo_seed", False),
            "email_verified": is_verified,
            "verification_mode": "smtp" if smtp_configured else "demo_simulation"
        }


def check_permission(user: dict, permission: str) -> bool:
    """Check if user role grants the specified permission.
    Unverified users have NO permissions until their email is verified.
    """
    if not user:
        return False
    if not user.get("email_verified", False):
        return False
    role = user.get("role", "developer")
    role_def = ROLES.get(role)
    if not role_def:
        return False
    return permission in role_def["permissions"]
