import os
import sys
import pytest

from repobrain import optimizer, policy


def test_policy_format_command_validation():
    p = policy.parse("format_command: 'black -q -'")
    assert p["format_command"] == "black -q -"
    p_none = policy.parse("format_command: null")
    assert p_none["format_command"] is None
    with pytest.raises(policy.PolicyError, match="format_command must be a string or null"):
        policy.parse("format_command: 12345")


def test_format_source_graceful_fallback_on_missing_command():
    src = "def foo():\n    return 42\n"
    pol = dict(policy.DEFAULT, format_command="this_command_definitely_does_not_exist_xyz_123")
    # Should not throw exception; returns src unchanged
    formatted = optimizer.format_source(src, pol)
    assert formatted == src


def test_format_source_graceful_fallback_on_failing_command():
    src = "def foo():\n    return 42\n"
    pol = dict(policy.DEFAULT, format_command=f"{sys.executable} -c 'import sys; sys.exit(1)'")
    formatted = optimizer.format_source(src, pol)
    assert formatted == src


def test_format_source_applies_formatter_and_preserves_crlf():
    # Use python as an in-process mock formatter that normalizes comments/spacing
    formatter_script = (
        f"{sys.executable} -c \"import sys; text = sys.stdin.read(); "
        f"sys.stdout.write(text.replace('pass', '# formatted\\n    pass'))\""
    )
    src = "def foo():\r\n    pass\r\n"
    pol = dict(policy.DEFAULT, format_command=formatter_script)
    formatted = optimizer.format_source(src, pol)
    assert "# formatted" in formatted
    # Crucial: verify CRLF was preserved
    assert "\r\n" in formatted
    assert "\r\r\n" not in formatted
