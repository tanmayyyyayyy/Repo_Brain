"""Tests for RepoBrain Innovation Layer:
1. Symbolic AST Formal Equivalence Prover (repobrain.prover)
2. Symbolic AST Data-Flow Taint & Exfiltration Engine (repobrain.taint)
3. RFC-6962 Cryptographic Merkle Audit Tree & Zero-Knowledge Inclusion Proofs (repobrain.merkle)
"""

import hashlib
import json
import os
import pytest

from repobrain import audit, merkle, optimizer, prover, taint


# ─────────────────────────────────────────────────────────────
# 1. SYMBOLIC AST FORMAL EQUIVALENCE PROVER TESTS
# ─────────────────────────────────────────────────────────────

def test_symbolic_prover_proves_guard_clause_hoisting_and_path_equivalence():
    orig_code = """
def discount_for(user, total, coupon):
    if user is not None:
        if user.get("tier") == "gold":
            if total > 100:
                if coupon == "SAVE10":
                    return round(total * 0.25, 2)
                else:
                    return round(total * 0.20, 2)
            else:
                return round(total * 0.10, 2)
        else:
            if coupon == "SAVE10":
                return round(total * 0.05, 2)
            else:
                return 0
    else:
        return 0
"""

    opt_code = """
def discount_for(user, total, coupon):
    if user is None:
        return 0
    if user.get("tier") == "gold":
        if total <= 100:
            return round(total * 0.1, 2)
        if coupon == "SAVE10":
            return round(total * 0.25, 2)
        return round(total * 0.2, 2)
    if coupon != "SAVE10":
        return 0
    return round(total * 0.05, 2)
"""

    res = prover.prove_function_equivalence(orig_code, opt_code, "discount_for")
    assert res["proven"] is True
    assert res["paths_verified"] == 6
    assert "discount_for_original(input) ≡ discount_for_optimized(input)" in res["theorem"]
    assert res["domain_coverage"] == "100.0%"
    assert res["proof_hash"].startswith("0x")


def test_symbolic_prover_rejects_divergent_behavior():
    orig_code = """
def calculate_tax(amount, is_exempt):
    if is_exempt:
        return 0
    if amount > 1000:
        return amount * 0.15
    return amount * 0.05
"""

    # Flawed rewrite with changed threshold (500 instead of 1000)
    buggy_opt_code = """
def calculate_tax(amount, is_exempt):
    if is_exempt:
        return 0
    if amount > 500:
        return amount * 0.15
    return amount * 0.05
"""

    res = prover.prove_function_equivalence(orig_code, buggy_opt_code, "calculate_tax")
    assert res["proven"] is False
    assert "Original path" in res["reason"] or "unmatched" in res["reason"]


def test_symbolic_prover_handles_nested_boolean_and_de_morgan_laws():
    orig = """
def check_access(user, is_admin, has_mfa):
    if not (is_admin and has_mfa):
        return False
    return True
"""
    # De Morgan rewritten: if not is_admin or not has_mfa
    opt = """
def check_access(user, is_admin, has_mfa):
    if not is_admin:
        return False
    if not has_mfa:
        return False
    return True
"""
    res = prover.prove_function_equivalence(orig, opt, "check_access")
    assert res["proven"] is True
    assert res["paths_verified"] >= 2


# ─────────────────────────────────────────────────────────────
# 2. SYMBOLIC AST DATA-FLOW TAINT ENGINE TESTS
# ─────────────────────────────────────────────────────────────

def test_taint_engine_detects_untrusted_command_injection_chain():
    vulnerable_code = """
import os

def execute_agent_command(cmd_payload):
    stripped = cmd_payload.strip()
    formatted = f"run --opt {stripped}"
    os.system(formatted)
"""
    findings = taint.scan_source(vulnerable_code)
    assert len(findings) == 1
    f = findings[0]
    assert f["rule"] == "taint-analysis"
    assert f["cwe"] == "CWE-78"
    assert f["severity"] == "block"
    assert len(f["taint_chain"]) == 4
    assert "parameter 'cmd_payload'" in f["taint_chain"][0]
    assert "assigned to 'stripped'" in f["taint_chain"][1]
    assert "assigned to 'formatted'" in f["taint_chain"][2]
    assert "sink 'os.system()'" in f["taint_chain"][3]


def test_taint_engine_allows_sanitized_inputs():
    safe_code = """
import subprocess, shlex

def safe_execution(user_input):
    safe_arg = shlex.quote(user_input)
    subprocess.run(["echo", safe_arg])

def safe_numeric(count_arg):
    n = int(count_arg)
    subprocess.run(["seq", str(n)])
"""
    findings = taint.scan_source(safe_code)
    assert len(findings) == 0


def test_taint_engine_detects_code_injection_eval_sink():
    eval_code = """
def dynamic_calculator(expr_input):
    tokens = expr_input.split()
    joined = " ".join(tokens)
    return eval(joined)
"""
    findings = taint.scan_source(eval_code)
    assert len(findings) == 1
    assert findings[0]["cwe"] == "CWE-95"
    assert "eval()" in findings[0]["sink"]


def test_taint_engine_detects_arbitrary_file_write_path_traversal():
    write_code = """
def save_agent_artifact(file_path, data):
    with open(file_path, "w") as f:
        f.write(data)
"""
    findings = taint.scan_source(write_code)
    assert any(f["cwe"] == "CWE-22" for f in findings)


# ─────────────────────────────────────────────────────────────
# 3. RFC-6962 CRYPTOGRAPHIC MERKLE TREE & PROOF TESTS
# ─────────────────────────────────────────────────────────────

def test_merkle_tree_construction_and_logarithmic_proof_verification():
    records = [
        {"seq": i, "event": f"event_{i}", "actor": f"agent_{i}", "decision": "ALLOWED"}
        for i in range(1, 17)  # 16 records
    ]

    tree = merkle.MerkleTree(records)
    assert tree.root is not None
    assert len(tree.root) == 64  # Hex SHA-256

    # Test audit inclusion proof for record #5 (index 4)
    target_idx = 4
    proof = tree.audit_proof(target_idx)
    assert proof["index"] == target_idx
    assert proof["record_seq"] == 5
    assert proof["tree_size"] == 16
    assert len(proof["proof_path"]) == 4  # log2(16) = 4 steps!

    # Mathematical verification must succeed on untampered record
    assert merkle.verify_inclusion_proof(records[target_idx], proof) is True

    # Tampered record must fail mathematical proof
    tampered_record = dict(records[target_idx], decision="BLOCKED")
    assert merkle.verify_inclusion_proof(tampered_record, proof) is False

    # Swapped proof path must fail
    fake_proof = dict(proof, merkle_root=hashlib.sha256(b"fake").hexdigest())
    assert merkle.verify_inclusion_proof(records[target_idx], fake_proof) is False


def test_audit_log_merkle_methods(tmp_path):
    log = audit.AuditLog(str(tmp_path))
    for i in range(1, 6):
        log.append(f"event-{i}", "developer", "ALLOWED", f"detail {i}")

    # Merkle root should be accessible
    root = log.merkle_root()
    assert root is not None
    assert len(root) == 64

    # Generate proof by sequence
    proof = log.merkle_proof(3)
    assert proof["record_seq"] == 3
    assert len(proof["proof_path"]) > 0

    entries = log.entries()
    rec3 = next(e for e in entries if e["seq"] == 3)
    assert merkle.verify_inclusion_proof(rec3, proof) is True

    # Verify detail includes merkle_root
    v = log.verify()
    assert "merkle_root" in v
    assert v["merkle_root"] == root

