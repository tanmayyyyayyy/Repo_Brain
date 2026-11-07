import os
import pytest
from repobrain import audit, cli

# ───── Audit: anchor-file verification via CLI
def test_audit_anchor_file_cli(tmp_path):
    home = str(tmp_path / "home")
    anchor_file = str(tmp_path / "anchor.txt")
    log = audit.AuditLog(home)
    log.append("test_event", "actor1", "ALLOWED", "detail 1")
    log.append("test_event", "actor2", "ALLOWED", "detail 2")

    # Step 1: Write anchor using --write-anchor
    rc = cli.main(["--home", home, "audit", "--write-anchor", anchor_file])
    assert rc == 0
    assert os.path.isfile(anchor_file)
    anchored_head = open(anchor_file).read().strip()
    assert len(anchored_head) == 64

    # Step 2: Verify against anchor file (should succeed)
    rc = cli.main(["--home", home, "audit", "--anchor-file", anchor_file])
    assert rc == 0

    # Step 3: Tamper with log by truncating or changing entries
    lines = open(log.path).read().splitlines()
    open(log.path, "w").write(lines[0] + "\n")  # delete second entry

    # Step 4: Verify against anchor file (should detect mismatch)
    rc = cli.main(["--home", home, "audit", "--anchor-file", anchor_file])
    assert rc == 1


def test_signed_chain_verification_succeeds(tmp_path, monkeypatch):
    key = "test-hmac-secret-key-38291"
    monkeypatch.setenv("REPOBRAIN_AUDIT_KEY", key)
    home = str(tmp_path / "home_signed")
    log = audit.AuditLog(home)
    log.append("review", "claude-bot", "ALLOWED", "all clean")
    log.append("optimize", "human", "APPLIED", "reduced complexity")

    res = log.verify()
    assert res["ok"] is True
    assert res["count"] == 2
    assert res["signed"] is True
    assert res["hmac_signed"] is True

    # CLI verification
    assert cli.main(["--home", home, "audit"]) == 0


def test_tamper_detection_on_signed_chain_with_recomputed_sha256(tmp_path, monkeypatch):
    import json
    key = "secret-signing-key-999"
    monkeypatch.setenv("REPOBRAIN_AUDIT_KEY", key)
    home = str(tmp_path / "home_tamper")
    log = audit.AuditLog(home)
    log.append("review", "bot", "BLOCKED", "entry 1")
    log.append("review", "bot", "BLOCKED", "entry 2")
    log.append("review", "bot", "ALLOWED", "entry 3")

    entries = log.entries()
    assert len(entries) == 3

    # Attacker tampers entry #2 and recomputes all SHA-256 hashes downstream
    # but cannot forge the HMAC signature
    entries[1]["decision"] = "ALLOWED"
    entries[1]["detail"] = "tampered detail"
    entries[1]["hash"] = audit._hash(entries[1])  # legitimate SHA-256 hash of modified content

    # Propagate prev hash into entry #3
    entries[2]["prev"] = entries[1]["hash"]
    entries[2]["hash"] = audit._hash(entries[2])

    # Write tampered log back to disk
    with open(log.path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")

    # Verification must catch the tampering at entry #2 because the signature is invalid
    v = log.verify()
    assert v["ok"] is False
    assert v["broken_at"] == 2
    assert "signature" in v["reason"]


def test_truncation_detection_with_expect(tmp_path):
    home = str(tmp_path / "home_trunc")
    log = audit.AuditLog(home)
    for i in range(1, 5):
        log.append("event", "actor", "ALLOWED", f"entry {i}")

    # Expecting 4 entries passes
    v4 = log.verify(expect_head=4)
    assert v4["ok"] is True
    assert cli.main(["--home", home, "audit", "--expect", "4"]) == 0

    # Truncate the last entry
    entries = log.entries()[:3]
    import json
    with open(log.path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")

    # Expecting 4 entries now fails due to truncation
    v_trunc = log.verify(expect_head=4)
    assert v_trunc["ok"] is False
    assert "truncated" in v_trunc["reason"] or "entries dropped" in v_trunc["reason"]
    assert cli.main(["--home", home, "audit", "--expect", "4"]) == 1

    # Expecting 3 entries passes for the 3-entry chain
    assert cli.main(["--home", home, "audit", "--expect", "3"]) == 0
