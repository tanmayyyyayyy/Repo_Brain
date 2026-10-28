"""The optimizer's core promise: behaviour is preserved. Proven by running old vs new code."""
import itertools
import textwrap

import pytest

from repobrain import metrics, rewrite
from repobrain.policy import DEFAULT


def opt(src, **pol):
    return rewrite.optimize_source(textwrap.dedent(src), {**DEFAULT, **pol})


def load(src, name):
    ns = {}
    exec(compile(src, "<t>", "exec"), ns)
    return ns[name]


def same_behaviour(src, name, grids):
    new, _, _ = opt(src)
    old_f, new_f = load(textwrap.dedent(src), name), load(new, name)
    for args in itertools.product(*grids):
        try:
            a = ("ok", old_f(*args))
        except Exception as e:
            a = ("err", type(e).__name__)
        try:
            b = ("ok", new_f(*args))
        except Exception as e:
            b = ("err", type(e).__name__)
        assert a == b, (args, a, b)
    return new


NESTED = """
def f(user, total, coupon, express):
    if user is not None:
        if user.get("tier") == "gold":
            if total > 100:
                if coupon == "X":
                    return 1
                else:
                    return 2
            else:
                return 3
        else:
            if express:
                return 4
            else:
                return 5
    else:
        return 0
"""


def test_nested_returns_equivalent_and_flatter():
    new = same_behaviour(NESTED, "f", [[None, {"tier": "gold"}, {"tier": "x"}, {}], [5, 150], ["X", None], [True, False]])
    a, b = metrics.analyze(textwrap.dedent(NESTED))[0], metrics.analyze(new)[0]
    assert b["depth"] < a["depth"] and b["cog"] < a["cog"]


def test_loop_guard_and_continue_equivalent():
    src = """
    def f(xs):
        out = []
        total = 0
        for x in xs:
            if x % 2 == 0:
                total += x
                out.append(total)
                if total > 10:
                    out.append("big")
        return out
    """
    new = same_behaviour(src, "f", [[[], [1, 2, 3, 4, 8, 10], [2, 2, 2, 2, 2, 2, 2]]])
    assert "continue" in new


def test_boolean_return_and_comprehension():
    src = """
    def g(xs):
        r = []
        for x in xs:
            if x > 1:
                r.append(x * 2)
        return r

    def h(v):
        if v in (1, 2):
            return True
        return False

    def k(v):
        if v:
            return False
        return True
    """
    new, notes, _ = opt(src)
    assert "loop-to-comprehension" in notes and "bool-return" in notes
    ns = {}
    exec(new, ns)
    assert ns["g"]([0, 2, 3]) == [4, 6]
    assert [ns["h"](v) for v in (1, 3)] == [True, False]
    assert [ns["k"](v) for v in (0, "a", [], [1])] == [True, False, True, False]


def test_loop_variable_used_after_loop_is_NOT_converted():
    src = """
    def f(xs):
        r = []
        for x in xs:
            r.append(x)
        return r, x
    """
    new, notes, _ = opt(src)
    assert "loop-to-comprehension" not in notes
    assert load(new, "f")([1, 2]) == ([1, 2], 2)


def test_accumulator_used_in_expression_is_not_converted():
    src = """
    def f(xs):
        r = []
        for x in xs:
            r.append(len(r) + x)
        return r
    """
    _, notes, _ = opt(src)
    assert "loop-to-comprehension" not in notes


def test_generator_and_async_untouched_semantics():
    src = """
    def gen(xs):
        for x in xs:
            if x > 0:
                yield x
                yield -x
    """
    new, _, _ = opt(src)
    assert list(load(new, "gen")([1, -1, 2])) == [1, -1, 2, -2]


def test_comments_and_untouched_code_preserved():
    src = '''
    import os

    # module comment stays
    CONST = {
        "a": 1,   # inline in untouched code
    }


    def f(x):
        # leading comment survives
        if x:
            return 1
        else:
            # comment inside the else survives too?
            return 2


    class K:
        def untouched(self):
            return   1   # odd spacing is kept because nothing changed here
    '''
    new, notes, skipped = opt(src)
    assert "# module comment stays" in new and '"a": 1,   # inline in untouched code' in new
    assert "return   1   # odd spacing" in new
    assert "# leading comment survives" in new
    assert "unused-import" in notes


def test_function_with_inline_comment_is_skipped_not_mangled():
    src = """
    def f(x):
        if x:
            return 1  # keep me
        else:
            return 2
    """
    new, notes, skipped = opt(src)
    assert "# keep me" in new and skipped and "inline comments" in skipped[0]["reason"]
    new2, notes2, _ = opt(src, allow_comment_loss=True)
    assert "else" not in new2


def test_unused_import_removal_is_conservative():
    src = """
    from __future__ import annotations
    import os
    import json  # noqa
    from typing import List, Dict
    import re

    def f(x: "Dict") -> int:
        return re.compile("a")
    """
    new, _, _ = opt(src)
    assert "import os" not in new and "import json  # noqa" in new
    assert "Dict" in new and "List" not in new and "import re" in new and "__future__" in new
    new2, _, _ = opt("__all__ = ['os']\nimport os\n")
    assert "import os" in new2


def test_syntax_error_input_raises_not_silently_rewritten():
    with pytest.raises(SyntaxError):
        opt("def f(:\n  pass")


def test_quote_style_follows_the_file():
    new, _, _ = opt('def f(x):\n    if x == None:\n        return "a"\n    else:\n        return "b"\n')
    assert '"a"' in new and "'a'" not in new
