"""Append-only, hash-chained audit log (JSONL) with verification, export and tamper detection."""
import hashlib
import hmac
import json
import os
import pathlib
import shutil
import threading
import time

GENESIS = "0" * 64
_lock = threading.Lock()


def home_for(root):
    env = os.environ.get("REPOBRAIN_HOME")
    if env:
        return os.path.abspath(env)
    h = hashlib.sha1(os.path.abspath(str(root)).encode()).hexdigest()[:10]
    return os.path.join(os.path.expanduser("~"), ".repobrain", h)


def _key():
    return (os.environ.get("REPOBRAIN_AUDIT_KEY") or "").encode()


def _sig(h):
    return hmac.new(_key(), h.encode(), hashlib.sha256).hexdigest()


def _hash(rec):
    body = {k: v for k, v in rec.items() if k not in ("hash", "sig")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


class AuditCorruptionError(ValueError):
    """Raised when the audit log tail or structure is malformed or corrupt."""
    pass


def _tail_last_record(path: str):
    """Return (seq, hash) of the trailing record in O(1) time by seeking backwards from EOF.
    Refuses to append if the trailing record is corrupt or malformed.
    """
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return 0, GENESIS

    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            chunk_size = 4096
            buffer = bytearray()
            pos = size
            found_line = None

            while pos > 0:
                read_size = min(chunk_size, pos)
                pos -= read_size
                f.seek(pos, os.SEEK_SET)
                chunk = f.read(read_size)
                buffer = chunk + buffer

                # Split on newlines to extract candidate trailing line
                lines = buffer.split(b"\n")
                while lines and not lines[-1].strip():
                    lines.pop()

                if not lines:
                    continue

                # If pos > 0 and only 1 element, we haven't seen the start of this line yet
                if pos > 0 and len(lines) == 1:
                    continue

                found_line = lines[-1].strip()
                break

            if not found_line:
                raise AuditCorruptionError(f"Audit log at '{path}' is non-empty but contains no records.")

            try:
                text = found_line.decode("utf-8")
                rec = json.loads(text)
            except Exception as e:
                raise AuditCorruptionError(f"Audit log at '{path}' has malformed trailing record JSON: {e}") from e

            if not isinstance(rec, dict) or "seq" not in rec or "hash" not in rec or "prev" not in rec:
                raise AuditCorruptionError(f"Audit log at '{path}' has missing cryptographic fields in trailing record.")

            expected_hash = _hash(rec)
            if rec.get("hash") != expected_hash:
                raise AuditCorruptionError(
                    f"Audit log at '{path}' has tampered or corrupt hash in trailing record (seq {rec.get('seq')}). "
                    f"Expected {expected_hash[:16]}..., got {str(rec.get('hash'))[:16]}..."
                )

            seq = int(rec.get("seq", 0))
            h = str(rec.get("hash", GENESIS))
            return seq, h
    except OSError as e:
        raise AuditCorruptionError(f"Cannot read audit log at '{path}': {e}") from e


class AuditLog:
    def __init__(self, home):
        self.home = str(home)
        self.path = os.path.join(self.home, "audit.jsonl")
        self.recovery_file = os.path.join(self.home, "recovery_pending.json")
        self._verify_cache = None
        os.makedirs(self.home, exist_ok=True)

    def is_recovery_pending(self) -> bool:
        if not os.path.exists(self.recovery_file):
            return False
        try:
            with open(self.recovery_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return bool(data.get("recovery_pending", False))
        except Exception:
            return False

    def get_recovery_info(self) -> dict:
        if not os.path.exists(self.recovery_file):
            return {}
        try:
            with open(self.recovery_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def set_recovery_pending(self, pending: bool, quarantined_file: str = "", error: str = ""):
        if not pending:
            if os.path.exists(self.recovery_file):
                try:
                    os.remove(self.recovery_file)
                except OSError:
                    pass
        else:
            with open(self.recovery_file, "w", encoding="utf-8") as f:
                json.dump({
                    "recovery_pending": True,
                    "quarantined_file": quarantined_file,
                    "timestamp": time.time(),
                    "error": str(error)
                }, f)

    def ack_recovery(self, actor: str) -> dict:
        info = self.get_recovery_info()
        quarantined = info.get("quarantined_file", "unknown")
        self.set_recovery_pending(False)
        self.append("audit-recovery-ack", actor, "ACKNOWLEDGED",
                    f"Administrator acknowledged recovery for {quarantined}")
        return {"ok": True, "quarantined_file": quarantined, "acknowledged_by": actor}

    def _quarantine_and_start_recovery(self, err: Exception):
        now_ts = int(time.time() * 1000)
        quarantine_fn = f"audit.corrupt.{now_ts}"
        quarantine_target = os.path.join(self.home, quarantine_fn)
        if os.path.exists(self.path):
            shutil.move(self.path, quarantine_target)
        self.set_recovery_pending(True, quarantine_fn, str(err))

        rec = {
            "seq": 1,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "event": "audit-recovery",
            "actor": "system",
            "decision": "RECOVERY",
            "detail": f"Corrupt tail quarantined to {quarantine_fn}: {err}",
            "prev": GENESIS,
            "quarantined_file": quarantine_fn
        }
        rec["hash"] = _hash(rec)
        if _key():
            rec["sig"] = _sig(rec["hash"])
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def entries(self):
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path, encoding="utf-8") as f:
            for ln in f:
                if ln.strip():
                    try:
                        out.append(json.loads(ln))
                    except json.JSONDecodeError:
                        out.append({"_corrupt": ln[:80]})
        return out

    def append(self, event, actor, decision, detail="", **extra):
        lock_path = self.path + ".lock"
        with _lock:
            lock_fd = None
            try:
                try:
                    import fcntl
                    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
                    fcntl.flock(lock_fd, fcntl.LOCK_EX)
                except ImportError:
                    try:
                        import msvcrt
                        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
                        msvcrt.locking(lock_fd, msvcrt.LK_LOCK, 1)
                    except (ImportError, OSError):
                        pass
                except OSError:
                    pass
                try:
                    last_seq, prev = _tail_last_record(self.path)
                except AuditCorruptionError as err:
                    recovery_rec = self._quarantine_and_start_recovery(err)
                    last_seq = recovery_rec["seq"]
                    prev = recovery_rec["hash"]

                rec = {"seq": last_seq + 1, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event,
                       "actor": actor, "decision": decision, "detail": detail, "prev": prev, **extra}
                rec["hash"] = _hash(rec)
                if _key():
                    rec["sig"] = _sig(rec["hash"])
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                return rec
            finally:
                if lock_fd is not None:
                    try:
                        try:
                            import fcntl
                            fcntl.flock(lock_fd, fcntl.LOCK_UN)
                        except ImportError:
                            try:
                                import msvcrt
                                msvcrt.locking(lock_fd, msvcrt.LK_UNLCK, 1)
                            except (ImportError, OSError):
                                pass
                        os.close(lock_fd)
                    except (ImportError, OSError):
                        pass

    def verify(self, expect_head=None, cached=False):
        if self.is_recovery_pending():
            info = self.get_recovery_info()
            quarantined = info.get("quarantined_file", "corrupt file")
            return {
                "ok": False,
                "count": len(self.entries()),
                "head": None,
                "broken_at": 1,
                "reason": f"Audit ledger recovery pending acknowledgment (quarantined: {quarantined})",
                "recovery_pending": True,
                "quarantined_file": quarantined
            }
        es = self.entries()
        stat = os.stat(self.path) if os.path.exists(self.path) else None
        mtime = getattr(stat, "st_mtime_ns", getattr(stat, "st_mtime", 0)) if stat else 0
        size = getattr(stat, "st_size", 0) if stat else 0
        key = _key()
        if cached and not expect_head and self._verify_cache:
            c = self._verify_cache
            if c.get("mtime") == mtime and c.get("size") == size and c.get("key") == key:
                cached_res = dict(c["result"])
                cached_res["cached"] = True
                return cached_res

        res = verify_entries(es, expect_head)
        if cached and not expect_head and res.get("ok"):
            self._verify_cache = {
                "mtime": mtime,
                "size": size,
                "key": key,
                "result": res
            }
        return res

    def merkle_tree(self):
        from . import merkle
        return merkle.MerkleTree(self.entries())

    def merkle_root(self):
        return self.merkle_tree().root

    def merkle_proof(self, seq_or_index):
        from . import merkle
        entries = self.entries()
        idx = None
        for i, e in enumerate(entries):
            if e.get("seq") == seq_or_index or i == seq_or_index:
                idx = i
                break
        if idx is None:
            raise KeyError(f"No audit entry with sequence/index {seq_or_index}")
        return self.merkle_tree().audit_proof(idx)


def verify_entries(es, expect_head=None):
    prev = GENESIS
    key = _key()
    has_key = bool(key)
    has_sig = any("sig" in e for e in es)
    hmac_signed = has_key and (has_sig or len(es) == 0)

    if not has_key and has_sig:
        return {"ok": False, "count": len(es), "broken_at": None,
                "reason": "audit entries carry HMAC signatures but REPOBRAIN_AUDIT_KEY is not configured",
                "signed": False, "hmac_signed": False}

    for i, e in enumerate(es):
        if "_corrupt" in e:
            return {"ok": False, "count": len(es), "broken_at": i + 1, "reason": "unparseable line",
                    "signed": hmac_signed, "hmac_signed": hmac_signed}
        if e.get("prev") != prev:
            return {"ok": False, "count": len(es), "broken_at": e.get("seq", i + 1),
                    "reason": "chain link broken (entry removed, inserted or reordered)",
                    "signed": hmac_signed, "hmac_signed": hmac_signed}
        h = e.get("hash")
        if _hash(e) != h:
            return {"ok": False, "count": len(es), "broken_at": e.get("seq", i + 1),
                    "reason": "entry content was modified after being written",
                    "signed": hmac_signed, "hmac_signed": hmac_signed}
        sig = e.get("sig")
        if has_key:
            if sig is None or not hmac.compare_digest(sig, _sig(h)):
                return {"ok": False, "count": len(es), "broken_at": e.get("seq", i + 1),
                        "reason": "signature missing or invalid (wrong key, or chain was rewritten)",
                        "signed": hmac_signed, "hmac_signed": hmac_signed}
        prev = h

    if expect_head is not None:
        exp_str = str(expect_head).strip()
        if exp_str.isdigit():
            exp_seq = int(exp_str)
            actual_seq = es[-1].get("seq", len(es)) if es else 0
            if actual_seq != exp_seq or len(es) != exp_seq:
                return {"ok": False, "count": len(es), "broken_at": None, "head": prev,
                        "reason": f"expected sequence #{exp_seq}, found #{actual_seq} (log truncated or entries dropped)",
                        "signed": hmac_signed, "hmac_signed": hmac_signed}
        elif exp_str:
            if prev != exp_str:
                return {"ok": False, "count": len(es), "broken_at": None, "head": prev,
                        "reason": "head hash differs from the anchored value (log truncated or rewritten)",
                        "signed": hmac_signed, "hmac_signed": hmac_signed}

    from . import merkle
    tree = merkle.MerkleTree(es)
    return {"ok": True, "count": len(es), "head": prev, "broken_at": None, "reason": "",
            "signed": hmac_signed, "hmac_signed": hmac_signed, "merkle_root": tree.root}


def simulate_tamper(es):
    """Demo helper: edit one entry in memory (never on disk) and re-verify."""
    if not es:
        return {"ok": True, "note": "log is empty"}
    t = [dict(e) for e in es]
    i = len(t) // 2
    t[i]["decision"] = "ALLOWED" if t[i].get("decision") != "ALLOWED" else "BLOCKED"
    res = verify_entries(t)
    tampered_seq = t[i].get("seq")
    downstream = [e.get("seq") for e in t[i + 1:]]
    res["tampered_seq"] = tampered_seq
    res["downstream_seqs"] = downstream
    res["invalidated_seqs"] = [tampered_seq] + downstream
    return res


# Functional API for compatibility with engine / CLI / tests
def read(home):
    return AuditLog(home).entries()


def log(home, event, decision, actor, detail):
    return AuditLog(home).append(event, actor, decision, detail)


def verify_detail(home):
    """Return {ok, bad_index, reason, signed, records}."""
    entries = read(home)
    v = verify_entries(entries)
    bad_index = None
    if not v["ok"]:
        b = v.get("broken_at")
        bad_index = b - 1 if isinstance(b, int) else None
    return {"ok": v["ok"], "bad_index": bad_index, "reason": v.get("reason", ""),
            "signed": bool(_key()), "records": len(entries), "head": v.get("head")}


def verify(home):
    d = verify_detail(home)
    return d["ok"], d["bad_index"]
