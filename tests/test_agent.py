import json, os, pathlib, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from repobrain import agent, audit

POLICY = """version: 1
optimize: required
approval: human
max_complexity: 3
max_depth: 2
max_cognitive: 3
blocked:
  - .github/workflows/
"""
SERVICE = '''def classify(n):
    if n > 10:
        if n > 20:
            if n > 30:
                return 3
            else:
                return 2
        else:
            return 1
    else:
        return 0
'''
TEST = 'from service import classify\n\ndef test_classify():\n    assert classify(5) == 0 and classify(25) == 2\n'
LOG = "Traceback (most recent call last):\n  File \"service.py\", line 3\nModuleNotFoundError: No module named 'yaml'\nFAILED test_service.py::test_classify\n"
ALERT = {"title": "checkout is down", "service": "payments", "severity": "SEV1",
         "text": "error rate high\nFile \"service.py\", line 3"}


def _git(root, *a, env=None):
    return subprocess.run(["git", *a], cwd=root, capture_output=True, text=True, env=env).stdout.strip()


def _commit(root, msg, who):
    mail = who.split()[0].lower() + "@example.com"
    env = {**os.environ, "GIT_AUTHOR_NAME": who, "GIT_AUTHOR_EMAIL": mail,
           "GIT_COMMITTER_NAME": who, "GIT_COMMITTER_EMAIL": mail}
    _git(root, "add", "-A"); _git(root, "commit", "-qm", msg, env=env)


def _repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "repobrain.yml").write_text(POLICY)
    (root / "service.py").write_text("def classify(n):\n    return 0 if n <= 10 else 1\n")
    (root / "test_service.py").write_text(TEST)
    (root / "test_other.py").write_text("def test_nothing():\n    assert True\n")
    _commit(root, "initial", "Priya")
    _git(root, "checkout", "-q", "-b", "ai/feature")
    (root / "service.py").write_text(SERVICE)
    (root / "config.py").write_text("AWS = '" + "AKIA" + "IOSFODNN7EXAMPLE" + "'\n")
    _commit(root, "add shipping rules", "copilot-agent[bot]")
    return root, tmp_path / "home"


def test_triage_prioritises_routes_and_audits(tmp_path):
    root, home = _repo(tmp_path)
    r = agent.triage(root, "main", "dev-agent", home=home)
    assert r["verdict"] == "blocked" and r["priority"] in ("P0", "P1")
    assert "security-review" in r["route"] and "code-owner" in r["route"]
    assert r["risk"]["score"] > 0 and r["head"]
    assert audit.read(home)[-1]["event"] == "agent:triage"


def test_review_emits_line_comments_and_keeps_approval(tmp_path):
    root, home = _repo(tmp_path)
    before = {p.name: p.read_text() for p in root.glob("*.py")}
    r = agent.review(root, "main", "dev-agent", home=home)
    rules = {c["rule"] for c in r["comments"]}
    assert {"secret", "complexity-gate"} <= rules
    assert r["verdict"] == "request-changes" and r["approval_required"] is True
    assert before == {p.name: p.read_text() for p in root.glob("*.py")}


def test_diagnose_correlates_the_log_with_changed_files(tmp_path):
    root, home = _repo(tmp_path)
    r = agent.diagnose(root, LOG, "main", "dev-agent", home=home)
    assert r["diagnosis"]["patches"][0]["line"] == "pyyaml"
    assert any(s["path"] == "service.py" and "named in the log" in s["why"] for s in r["suspects"])
    assert r["confidence"] == "high"


def test_test_runs_the_project_tests(tmp_path):
    root, home = _repo(tmp_path)
    r = agent.test(root, "main", "dev-agent", home=home)
    assert r["status"] == "passed" and r["passed"] >= 2 and r["failed"] == 0
    assert r["runner"] in ("pytest", "builtin")


def test_incident_triages_an_alert_without_taking_action(tmp_path):
    root, home = _repo(tmp_path)
    before = _git(root, "status", "--porcelain")
    r = agent.incident(root, ALERT, "main", "dev-agent", home=home)
    assert r["severity"] == "SEV1" and r["page"] is True
    assert r["suspects"] and any(a["automated"] is False for a in r["actions"])
    assert r["approval_required"] is True and "no action taken" in r["summary"]
    assert _git(root, "status", "--porcelain") == before


def test_run_all_five_writes_a_brief_and_changes_nothing(tmp_path):
    root, home = _repo(tmp_path)
    before = _git(root, "status", "--porcelain")
    r = agent.run(root, "main", ALERT, LOG, "dev-agent", home=home)
    assert set(r["workflows_run"]) == {"triage", "review", "diagnose", "test", "incident"}
    assert r["verdict"] == "blocked"
    assert (home / "agent" / "latest.md").is_file() and (home / "agent" / "latest.json").is_file()
    assert "# RepoBrain developer agent" in r["markdown"]
    assert agent.latest(home)["head"] == r["head"]
    assert _git(root, "status", "--porcelain") == before
    assert audit.read(home)[-1]["event"] == "agent:run"
    assert agent.exit_code(r) == 1
