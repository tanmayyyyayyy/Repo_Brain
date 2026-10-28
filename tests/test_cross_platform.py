import os
import shlex
import pytest
from repobrain import optimizer, policy, rewrite


def test_crlf_line_endings_preserved_in_rewrite():
    src = "def calculate(x):\r\n    # Check none\r\n    if x == None:\r\n        return True\r\n    else:\r\n        return False\r\n"
    new_src, notes, skipped = rewrite.optimize_source(src, policy.DEFAULT)
    assert "\r\n" in new_src
    assert "\n" not in new_src.replace("\r\n", "")
    assert "return x is None" in new_src


def test_mark_comments_preserves_crlf():
    src = "def greet():\r\n    # hello comment\r\n    msg = 'hi'\r\n    return msg\r\n"
    marked, comments = rewrite.mark_comments(src)
    assert "\r\n" in marked
    assert "\n" not in marked.replace("\r\n", "")
    assert 0 in comments
    assert comments[0] == "# hello comment"


def test_lf_preserved_without_introducing_crlf():
    src = "def foo(x):\n    if x == None:\n        return True\n    return False\n"
    new_src, notes, skipped = rewrite.optimize_source(src, policy.DEFAULT)
    assert "\r\n" not in new_src
    assert "\n" in new_src


def test_crlf_diff_is_minimal():
    src = "def calculate(x):\r\n    y = 1\r\n    if x == None:\r\n        return True\r\n    return False\r\n"
    new_src, _, _ = rewrite.optimize_source(src, policy.DEFAULT)
    d = optimizer._diff("test.py", src, new_src)
    # y = 1 line should be context, not modified
    assert " y = 1" in d
    assert "+y = 1" not in d
    assert "-y = 1" not in d


def test_shlex_cross_platform():
    # Verify posix vs non-posix splitting behaviour for windows paths
    cmd_win = r'"C:\Program Files\Python\python.exe" -m pytest'
    parsed_win = shlex.split(cmd_win, posix=False)
    assert parsed_win[0] == r'"C:\Program Files\Python\python.exe"' or parsed_win[0] == r'C:\Program Files\Python\python.exe'


def test_apply_path_traversal_refused(tmp_path):
    root = str(tmp_path / "repo")
    home = str(tmp_path / "home")
    os.makedirs(root, exist_ok=True)
    os.makedirs(os.path.join(home, "proposals"), exist_ok=True)

    fake_prop = {
        "id": "20261029-010000-abcdef",
        "status": "verified",
        "applicable": True,
        "head": None,
        "files": [{"path": "../../etc/passwd", "before_sha": "abc", "after": "evil"}]
    }
    import json
    with open(os.path.join(home, "proposals", fake_prop["id"] + ".json"), "w") as f:
        json.dump(fake_prop, f)

    with pytest.raises(ValueError, match="path escapes repository"):
        optimizer.apply(root, home, fake_prop["id"], "Tester")
