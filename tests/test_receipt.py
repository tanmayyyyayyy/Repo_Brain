"""Unit and integration tests for the Verifiable PR Decision Receipt Engine."""

import json
import os
import shutil
import tempfile
import pytest

from repobrain import audit, demo, optimizer, policy, receipt, review
from repobrain.cli import main as cli_main


@pytest.fixture
def seeded_repo(tmp_path):
    root = str(tmp_path / "repo")
    demo.seed(root)
    return root


def test_receipt_scenario_a_blocked(seeded_repo):
    """Scenario A: Risky AI PR produces a verifiable BLOCKED receipt."""
    demo.switch(seeded_repo, "risky")
    pol = policy.load_for(seeded_repo, "main")
    rev = review.run(seeded_repo, pol, base="main")
    home = os.path.join(seeded_repo, ".repobrain")
    log = audit.AuditLog(home)

    rcpt = receipt.generate_receipt(seeded_repo, rev, log, base="main")

    assert rcpt["receipt_version"] == "1.0"
    assert rcpt["review"]["decision"] == "BLOCKED"
    assert rcpt["review"]["verdict"] == "blocked"
    assert rcpt["review"]["findings_count"]["blocking"] >= 1
    assert "receipt_hash" in rcpt
    assert "merkle_proof" in rcpt["audit"]

    # Verify receipt integrity
    ver = receipt.verify_receipt(rcpt)
    assert ver["valid"] is True
    assert ver["errors"] == []
    assert ver["checks"]["receipt_hash"]["valid"] is True
    assert ver["checks"]["merkle_proof"]["valid"] is True


def test_receipt_scenario_b_remediated_and_approved(seeded_repo):
    """Scenario B: Messy AI PR remediated by optimizer produces an approved receipt with formal proof."""
    demo.switch(seeded_repo, "pricing")
    pol = policy.load_for(seeded_repo, "main")
    home = os.path.join(seeded_repo, ".repobrain")
    log = audit.AuditLog(home)

    # 1. Propose refactor
    prop = optimizer.propose(seeded_repo, pol, ["shop/pricing.py"], home)
    assert len(prop["formal_proofs"]) > 0

    # 2. Apply proposal with named human
    approver = "Priya Sharma <priya@example.com>"
    optimizer.apply(seeded_repo, home, prop["id"], approver)

    # 3. Re-evaluate review
    rev = review.run(seeded_repo, pol, base="main")
    assert rev["decision"] == "ALLOWED"

    # 4. Generate receipt
    rcpt = receipt.generate_receipt(seeded_repo, rev, log, proposal=prop, approver=approver, base="main")

    assert rcpt["review"]["decision"] == "ALLOWED"
    assert rcpt["remediation"]["remediated"] is True
    assert rcpt["remediation"]["formal_proof"]["proven"] is True
    assert rcpt["remediation"]["human_approver"] == approver
    assert "active_prices" in rcpt["remediation"]["formal_proof"]["theorem"]

    # 5. Verify receipt
    ver = receipt.verify_receipt(rcpt)
    assert ver["valid"] is True
    assert ver["checks"]["formal_proof"]["valid"] is True
    assert ver["checks"]["merkle_proof"]["valid"] is True


def test_receipt_scenario_d_clean_golden_path(seeded_repo):
    """Scenario D: Clean AI PR produces an ALLOWED receipt with zero findings."""
    demo.switch(seeded_repo, "clean")
    pol = policy.load_for(seeded_repo, "main")
    rev = review.run(seeded_repo, pol, base="main")
    home = os.path.join(seeded_repo, ".repobrain")
    log = audit.AuditLog(home)

    rcpt = receipt.generate_receipt(seeded_repo, rev, log, base="main")

    assert rcpt["review"]["decision"] == "ALLOWED"
    assert rcpt["review"]["verdict"] == "ready"
    assert rcpt["review"]["findings_count"]["total"] == 0
    assert rcpt["review"]["findings_count"]["blocking"] == 0

    ver = receipt.verify_receipt(rcpt)
    assert ver["valid"] is True


def test_receipt_tamper_detection(seeded_repo):
    """Verifies that tampering with any field in the receipt causes cryptographic verification failure."""
    demo.switch(seeded_repo, "risky")
    pol = policy.load_for(seeded_repo, "main")
    rev = review.run(seeded_repo, pol, base="main")
    home = os.path.join(seeded_repo, ".repobrain")
    log = audit.AuditLog(home)
    rcpt = receipt.generate_receipt(seeded_repo, rev, log, base="main")

    # Tamper 1: Modify decision without updating hash
    tampered1 = json.loads(json.dumps(rcpt))
    tampered1["review"]["decision"] = "ALLOWED"
    ver1 = receipt.verify_receipt(tampered1)
    assert ver1["valid"] is False
    assert any("integrity mismatch" in err for err in ver1["errors"])

    # Tamper 2: Modify Merkle root and recompute top-level receipt hash
    # Even if attacker rehashes the receipt JSON, the Merkle proof itself fails!
    tampered2 = json.loads(json.dumps(rcpt))
    tampered2["audit"]["merkle_root"] = "0" * 64
    copy_obj = dict(tampered2)
    copy_obj.pop("receipt_hash", None)
    tampered2["receipt_hash"] = receipt._sha256_hex(receipt._canonical_json_bytes(copy_obj))

    ver2 = receipt.verify_receipt(tampered2)
    assert ver2["valid"] is False
    assert any("Merkle proof failed" in err for err in ver2["errors"])

    # Tamper 3: Modify commit SHA
    tampered3 = json.loads(json.dumps(rcpt))
    tampered3["review"]["commit"] = "f" * 40
    ver3 = receipt.verify_receipt(tampered3)
    assert ver3["valid"] is False


def test_receipt_trust_anchor_independent_verification(seeded_repo, tmp_path):
    """Verifies that an internally recomputed fake receipt fails against an independent trusted anchor."""
    demo.switch(seeded_repo, "risky")
    pol = policy.load_for(seeded_repo, "main")
    rev = review.run(seeded_repo, pol, base="main")
    home = os.path.join(seeded_repo, ".repobrain")
    log = audit.AuditLog(home)
    rcpt = receipt.generate_receipt(seeded_repo, rev, log, base="main")

    trusted_merkle_root = rcpt["audit"]["merkle_root"]
    assert len(trusted_merkle_root) == 64

    # 1. Correct trusted root passes
    ver_ok = receipt.verify_receipt(rcpt, trusted_root=trusted_merkle_root)
    assert ver_ok["valid"] is True
    assert ver_ok["checks"]["trust_anchor"]["status"] == "verified"

    # 2. Anchor file verification passes
    anchor_file = str(tmp_path / "ci-audit-anchor.txt")
    with open(anchor_file, "w") as f:
        f.write(trusted_merkle_root + "\n")
    ver_anchor_ok = receipt.verify_receipt(rcpt, anchor_file=anchor_file)
    assert ver_anchor_ok["valid"] is True

    # 3. Attacker fabricates an altered receipt:
    # They change decision to ALLOWED, modify audit entry, rebuild Merkle tree, and re-hash receipt.
    # The receipt is "internally consistent" with its own fake root, BUT fails against the trusted root!
    forged = json.loads(json.dumps(rcpt))
    forged["review"]["decision"] = "ALLOWED"
    forged["audit"]["decision"] = "ALLOWED"
    forged["audit"]["target_record"]["decision"] = "ALLOWED"
    # Recompute entry hash
    from repobrain import audit as A
    forged["audit"]["target_record"]["hash"] = A._hash(forged["audit"]["target_record"])
    forged["audit"]["entry_hash"] = forged["audit"]["target_record"]["hash"]
    # Rebuild a single-entry fake tree
    fake_tree = receipt.merkle.MerkleTree([forged["audit"]["target_record"]])
    forged["audit"]["merkle_root"] = fake_tree.root
    forged["audit"]["merkle_proof"] = fake_tree.audit_proof(0)
    # Recompute receipt hash
    copy_obj = dict(forged)
    copy_obj.pop("receipt_hash", None)
    forged["receipt_hash"] = receipt._sha256_hex(receipt._canonical_json_bytes(copy_obj))

    # Without trusted anchor, it's internally self-consistent:
    ver_self = receipt.verify_receipt(forged)
    assert ver_self["checks"]["trust_anchor"]["status"] == "self-consistent"

    # WITH independent trusted anchor, it is IMMEDIATELY DETECTED AND REJECTED!
    ver_anchor_rejected = receipt.verify_receipt(forged, trusted_root=trusted_merkle_root)
    assert ver_anchor_rejected["valid"] is False
    assert any("Trust anchor mismatch" in err for err in ver_anchor_rejected["errors"])

    # Also fails against the saved CI anchor file:
    ver_file_rejected = receipt.verify_receipt(forged, anchor_file=anchor_file)
    assert ver_file_rejected["valid"] is False
    assert any("Trust anchor mismatch" in err for err in ver_file_rejected["errors"])


def test_receipt_hmac_key_verification(seeded_repo, monkeypatch):
    """Verifies that audit key authentication rejects forged or unsigned receipts."""
    auth_fixture = "mock-key-for-test-suite"
    monkeypatch.setenv("REPOBRAIN_AUDIT_KEY", auth_fixture)

    demo.switch(seeded_repo, "pricing")
    pol = policy.load_for(seeded_repo, "main")
    rev = review.run(seeded_repo, pol, base="main")
    home = os.path.join(seeded_repo, ".repobrain")
    log = audit.AuditLog(home)
    rcpt = receipt.generate_receipt(seeded_repo, rev, log, base="main")

    # Receipt must carry an HMAC signature
    assert rcpt["audit"]["target_record"].get("sig") is not None

    # Verification with correct key passes
    ver_key_ok = receipt.verify_receipt(rcpt, audit_key=auth_fixture)
    assert ver_key_ok["valid"] is True
    assert ver_key_ok["checks"]["trust_anchor"]["status"] == "verified"

    # Verification with attacker's wrong key fails
    ver_wrong_key = receipt.verify_receipt(rcpt, audit_key="untrusted-wrong-key")
    assert ver_wrong_key["valid"] is False
    assert any("HMAC authentication failure" in err for err in ver_wrong_key["errors"])


def test_receipt_audit_commit_and_verdict_binding(seeded_repo):
    """Verifies that an attacker cannot reuse an audit record for a different commit or verdict."""
    demo.switch(seeded_repo, "risky")
    pol = policy.load_for(seeded_repo, "main")
    rev = review.run(seeded_repo, pol, base="main")
    home = os.path.join(seeded_repo, ".repobrain")
    log = audit.AuditLog(home)
    rcpt = receipt.generate_receipt(seeded_repo, rev, log, base="main")

    # Attacker re-points review to a clean commit SHA while keeping original audit record
    forged_commit = json.loads(json.dumps(rcpt))
    forged_commit["review"]["commit"] = "0123456789abcdef0123456789abcdef01234567"
    copy_obj = dict(forged_commit)
    copy_obj.pop("receipt_hash", None)
    forged_commit["receipt_hash"] = receipt._sha256_hex(receipt._canonical_json_bytes(copy_obj))

    ver_commit = receipt.verify_receipt(forged_commit)
    assert ver_commit["valid"] is False
    assert any("Audit entry binding mismatch" in err for err in ver_commit["errors"])


def test_cli_receipt_and_verify(seeded_repo, tmp_path, capsys):
    """Verifies CLI subcommands 'repobrain receipt' and 'repobrain verify-receipt'."""
    out_file = str(tmp_path / "test-receipt.json")
    anchor_file = str(tmp_path / "test-anchor.txt")

    # 1. Run 'repobrain receipt' with --write-anchor
    rc_receipt = cli_main(["--repo", seeded_repo, "receipt", "--base", "main", "--out", out_file, "--write-anchor", anchor_file])
    assert rc_receipt == 0
    assert os.path.exists(out_file)
    assert os.path.exists(anchor_file)

    # 2. Run 'repobrain verify-receipt' with --anchor-file
    rc_verify = cli_main(["verify-receipt", out_file, "--anchor-file", anchor_file])
    assert rc_verify == 0
    captured = capsys.readouterr()
    assert "VALID & UNTAMPERED" in captured.out
    assert "VERIFIED against independent trusted root" in captured.out

    # 3. Tamper with output file and verify non-zero exit code
    with open(out_file, "r") as f:
        data = json.load(f)
    data["review"]["decision"] = "FORGED_ALLOWED"
    with open(out_file, "w") as f:
        json.dump(data, f)

    rc_verify_tampered = cli_main(["verify-receipt", out_file, "--anchor-file", anchor_file])
    assert rc_verify_tampered == 1
    captured_tampered = capsys.readouterr()
    assert "TAMPERED / VERIFICATION FAILED" in captured_tampered.out

