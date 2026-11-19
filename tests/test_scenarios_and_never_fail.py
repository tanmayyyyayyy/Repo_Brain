"""Tests for multi-scenario coverage (Scenarios A through E) and zero-failure resilience across all edge cases."""

import pytest
import tempfile
import shutil
import hashlib
from repobrain import demo, review, policy, prover, taint, merkle, metrics, shield, server


def test_all_five_scenarios_seeded_and_switched():
    tmp = tempfile.mkdtemp(prefix="test-5-scenes-")
    try:
        demo.seed(tmp)
        assert set(demo.SCENARIOS.keys()) == {"risky", "pricing", "orders", "clean", "polyglot"}
        
        # Scenario A: Risky AI PR (blocked)
        demo.switch(tmp, "risky")
        pol_a = policy.load_for(tmp, demo.SCENARIO_BASES["risky"])
        rev_a = review.run(tmp, pol_a, base=demo.SCENARIO_BASES["risky"])
        assert rev_a["decision"] == "BLOCKED"
        assert rev_a["verdict"] == "blocked"
        assert len(rev_a["findings"]) > 0

        # Scenario B: Messy AI PR (complexity gate triggered)
        demo.switch(tmp, "pricing")
        pol_b = policy.load_for(tmp, demo.SCENARIO_BASES["pricing"])
        rev_b = review.run(tmp, pol_b, base=demo.SCENARIO_BASES["pricing"])
        assert rev_b["decision"] == "CHANGES_REQUIRED"
        assert rev_b["verdict"] == "changes"

        # Scenario C: Orders base refactor
        demo.switch(tmp, "orders")
        pol_c = policy.load_for(tmp, demo.SCENARIO_BASES["orders"])
        rev_c = review.run(tmp, pol_c, base=demo.SCENARIO_BASES["orders"])
        assert rev_c["decision"] in ("ALLOWED", "CHANGES_REQUIRED")

        # Scenario D: Clean AI PR (The Golden Path)
        demo.switch(tmp, "clean")
        pol_d = policy.load_for(tmp, demo.SCENARIO_BASES["clean"])
        rev_d = review.run(tmp, pol_d, base=demo.SCENARIO_BASES["clean"])
        assert rev_d["decision"] == "ALLOWED"
        assert rev_d["verdict"] == "ready"
        assert len(rev_d["findings"]) == 0
        assert rev_d["counts"]["blocks"] == 0

        # Scenario E: Polyglot Full-Stack PR
        demo.switch(tmp, "polyglot")
        pol_e = policy.load_for(tmp, demo.SCENARIO_BASES["polyglot"])
        rev_e = review.run(tmp, pol_e, base=demo.SCENARIO_BASES["polyglot"])
        assert rev_e["decision"] == "ALLOWED"
        # Verifies Dockerfile advisory or clean review
        assert any(f.get("file") == "Dockerfile" or f.get("path") == "Dockerfile" for f in rev_e["findings"])

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_switch_never_fails_on_dirty_or_unknown_branch():
    tmp = tempfile.mkdtemp(prefix="test-switch-clean-")
    try:
        demo.seed(tmp)
        # Dirty the workspace with uncommitted changes
        with open(f"{tmp}/dirty.txt", "w") as f:
            f.write("untracked debris")
        # Should gracefully switch without raising
        demo.switch(tmp, "clean")
        # Unknown scenario should gracefully fallback to default without raising
        demo.switch(tmp, "nonexistent-scenario-xyz")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_prover_never_fails_on_malformed_syntax_or_missing_functions():
    # 1. Invalid syntax
    res = prover.prove_function_equivalence("def broken(x: if x:", "def broken(x): return x", "broken")
    assert res["proven"] is False
    assert "Syntax error" in res["reason"]

    # 2. Missing function
    res2 = prover.prove_function_equivalence("def foo(): return 1", "def bar(): return 1", "compute")
    assert res2["proven"] is False
    assert "not found" in res2["reason"]

    # 3. Empty input
    res3 = prover.prove_function_equivalence("", "", "anything")
    assert res3["proven"] is False

    # 4. Exotic syntax / unhandled AST
    res4 = prover.prove_function_equivalence("def foo(): yield 1", "def foo(): yield 2", "foo")
    assert isinstance(res4, dict)
    assert "proven" in res4


def test_taint_engine_never_fails_on_malformed_code():
    # 1. Syntax errors
    hits = taint.scan_source("def broken: ((((", "broken.py")
    assert hits == []

    # 2. Empty string
    assert taint.scan_source("", "empty.py") == []

    # 3. Complex expressions and pattern matching
    code = """
def process(match_obj):
    match match_obj:
        case [x, y]:
            return x + y
        case _:
            return 0
"""
    assert isinstance(taint.scan_source(code, "match.py"), list)


def test_merkle_verification_never_fails_on_corrupted_inputs():
    # 1. Non-dict input
    assert merkle.verify_inclusion_proof(None, None) is False
    assert merkle.verify_inclusion_proof({}, "not a dict") is False

    # 2. Non-hex string in sibling hash
    bad_proof = {
        "merkle_root": "0" * 64,
        "leaf_hash": merkle.hash_leaf({"action": "test"}),
        "proof_path": [{"hash": "NOT_A_HEX_STRING!@#$", "position": "left"}]
    }
    assert merkle.verify_inclusion_proof({"action": "test"}, bad_proof) is False

    # 3. Empty proof path
    assert merkle.verify_inclusion_proof({"action": "test"}, {}) is False

    # 4. Hash children with invalid hex degrades gracefully
    h = merkle.hash_children("invalid-hex-1", "invalid-hex-2")
    assert isinstance(h, str) and len(h) == 64


def test_metrics_analyze_never_fails_on_non_python_or_syntax_errors():
    # Non-Python files
    assert metrics.analyze("console.log('hello world');") == []
    assert metrics.analyze("package main; func main() {}") == []
    assert metrics.analyze("SELECT * FROM users WHERE 1=1;") == []
    assert metrics.analyze("--- \n key: value\n") == []
    assert metrics.analyze("def broken(:") == []
    assert metrics.analyze("") == []


def test_shield_scan_never_fails_on_binary_or_extreme_inputs():
    pol = policy.DEFAULT
    # Null bytes (binary file)
    assert shield.scan_text("test.bin", "\x00\x01\x02\x03", pol) == []
    # Huge string (> 1MB)
    huge = "A" * (shield.MAX_BYTES + 100)
    assert shield.scan_text("large.txt", huge, pol) == []
    # Empty string
    assert shield.scan_text("empty.txt", "", pol) == []
    # Extreme line length
    extreme_line = "x = '" + ("A" * 5000) + "'\n"
    assert shield.scan_text("long.py", extreme_line, pol) == []

