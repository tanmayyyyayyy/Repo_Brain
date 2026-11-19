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


def test_cli_receipt_and_verify(seeded_repo, tmp_path, capsys):
    """Verifies CLI subcommands 'repobrain receipt' and 'repobrain verify-receipt'."""
    out_file = str(tmp_path / "test-receipt.json")

    # 1. Run 'repobrain receipt'
    rc_receipt = cli_main(["--repo", seeded_repo, "receipt", "--base", "main", "--out", out_file])
    assert rc_receipt == 0
    assert os.path.exists(out_file)

    # 2. Run 'repobrain verify-receipt'
    rc_verify = cli_main(["verify-receipt", out_file])
    assert rc_verify == 0
    captured = capsys.readouterr()
    assert "VALID & UNTAMPERED" in captured.out

    # 3. Tamper with output file and verify non-zero exit code
    with open(out_file, "r") as f:
        data = json.load(f)
    data["review"]["decision"] = "FORGED_ALLOWED"
    with open(out_file, "w") as f:
        json.dump(data, f)

    rc_verify_tampered = cli_main(["verify-receipt", out_file])
    assert rc_verify_tampered == 1
    captured_tampered = capsys.readouterr()
    assert "TAMPERED / VERIFICATION FAILED" in captured_tampered.out

