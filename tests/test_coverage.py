import os
import sys
import pytest
from repobrain import demo, optimizer, policy


def test_coverage_policy_validation():
    # Valid min_function_coverage
    pol = policy.parse("min_function_coverage: 80\n")
    assert pol["min_function_coverage"] == 80

    pol_null = policy.parse("min_function_coverage: null\n")
    assert pol_null["min_function_coverage"] is None

    # Invalid min_function_coverage type
    with pytest.raises(policy.PolicyError, match="min_function_coverage"):
        policy.parse("min_function_coverage: true\n")

    with pytest.raises(policy.PolicyError, match="min_function_coverage"):
        policy.parse("min_function_coverage: 'eighty'\n")


def test_partial_coverage_flags_unexecuted_functions(tmp_path):
    root = str(tmp_path / "repo")
    home = str(tmp_path / "home")
    demo.seed(root)
    demo.switch(root, "pricing")

    # Add an untested function to shop/pricing.py that gets rewritten (e.g. x == None)
    pricing_file = os.path.join(root, "shop", "pricing.py")
    orig_pricing = open(pricing_file).read()
    untested_code = "\n\ndef untested_helper(val):\n    if val == None:\n        return True\n    return False\n"
    with open(pricing_file, "w") as f:
        f.write(orig_pricing + untested_code)

    pol = policy.load_for(root, "main")
    prop = optimizer.propose(root, pol, ["shop/pricing.py"], home)

    # Since untested_helper was rewritten (is-none rule) and tests never call it:
    assert prop["tests"]["ok"] is True
    if prop["coverage"]["available"]:
        assert prop["status"] == "verified (partial coverage)"
        unexec_names = [u["function"] for u in prop["unexecuted_functions"]]
        assert "untested_helper" in unexec_names
        assert prop["applicable"] is True


def test_strict_min_coverage_blocks_applicable_when_required(tmp_path):
    root = str(tmp_path / "repo")
    home = str(tmp_path / "home")
    demo.seed(root)
    demo.switch(root, "pricing")

    pricing_file = os.path.join(root, "shop", "pricing.py")
    orig_pricing = open(pricing_file).read()
    untested_code = "\n\ndef uncalled_helper(val):\n    if val == None:\n        return True\n    return False\n"
    with open(pricing_file, "w") as f:
        f.write(orig_pricing + untested_code)

    pol = {**policy.load_for(root, "main"), "min_function_coverage": 100, "require_tests": True}
    prop = optimizer.propose(root, pol, ["shop/pricing.py"], home)

    if prop["coverage"]["available"]:
        assert prop["status"] == "verified (partial coverage)"
        assert prop["applicable"] is False


def test_degrades_gracefully_without_coverage(tmp_path, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "coverage":
            raise ImportError("No module named 'coverage'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    root = str(tmp_path / "repo")
    home = str(tmp_path / "home")
    demo.seed(root)
    demo.switch(root, "pricing")

    pol = policy.load_for(root, "main")
    prop = optimizer.propose(root, pol, ["shop/pricing.py"], home)
    assert prop["status"] == "verified"
    assert prop["coverage"]["available"] is False
