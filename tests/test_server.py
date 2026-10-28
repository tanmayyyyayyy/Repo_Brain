import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    d = tmp_path_factory.mktemp("demo")
    p = subprocess.Popen([sys.executable, "-m", "repobrain", "serve", "--demo", "--no-browser", "--port", "8793"],
                         cwd=ROOT, env={**os.environ, "REPOBRAIN_DEMO_DIR": str(d)}, stdout=subprocess.PIPE, text=True)
    tok = re.search(r"t=(\S+)", p.stdout.readline() + p.stdout.readline()).group(1)
    yield tok
    p.terminate()


def call(path, tok, body=None, host=None, ctype="application/json"):
    h = {"X-RepoBrain-Token": tok, "Content-Type": ctype}
    if host:
        h["Host"] = host
    req = urllib.request.Request("http://127.0.0.1:8793" + path, None if body is None else json.dumps(body).encode(), h)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_auth_host_and_csrf_guards(srv):
    assert call("/api/state", "wrong")[0] == 401
    assert call("/api/state", srv, host="evil.example")[0] == 403
    assert call("/api/review", srv, {}, ctype="text/plain")[0] == 415
    assert call("/api/state", srv)[0] == 200


def test_review_and_approve_need_a_named_human(srv):
    s, b = call("/api/review", srv, {})
    assert s == 200 and json.loads(b)["decision"] == "BLOCKED"
    call("/api/scenario", srv, {"name": "pricing"})
    s, b = call("/api/optimize", srv, {})
    prop = json.loads(b)
    assert prop["status"] == "verified" and "after" not in prop["files"][0]
    assert call("/api/approve", srv, {"id": prop["id"]})[0] == 400
    assert call("/api/approve", srv, {"id": "../../etc/passwd", "actor": "x"})[0] == 400
    assert call("/api/approve", srv, {"id": prop["id"], "actor": "Priya"})[0] == 200
