import json
import os
import subprocess
import sys

import pytest

from repobrain import agent, audit, demo, diagnose, explainer, incident, policy, server, testing, triage

SECRET = "AKIAIOSFODNN7EXAMPLE"


def _rev(decision="BLOCKED", rules=("secret",), files=("shop/api.py",), score=82):
    return {
        "head": "abc123",
        "decision": decision,
        "reason": "1 blocking finding(s) - not waivable, fix and push",
        "risk": {"score": score, "level": "high" if score >= 70 else "low"},
        "files": [{"path": p, "ai": True, "status": "M", "findings": [], "violations": []} for p in files],
        "findings": [{"severity": "block", "rule": r, "file": f, "evidence": ""}
                     for r in rules for f in files],
        "gate": [],
    }


def _repo(tmp_path):
    root = str(tmp_path / "repo")
    os.makedirs(root)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    with open(os.path.join(root, "app.py"), "w", encoding="utf-8") as f:
        f.write("def add(a, b):\n    return a + b\n")
    os.makedirs(os.path.join(root, "tests"))
    with open(os.path.join(root, "tests", "test_app.py"), "w", encoding="utf-8") as f:
        f.write("from app import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    subprocess.run(["git", "-C", root, "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", root, "-c", "user.name=T", "-c", "user.email=t@e.com",
                    "commit", "-qm", "initial"], check=True, capture_output=True)
    return root


def test_triage_priority_labels_owners_and_markdown():
    t = triage.run(_rev())
    assert t["priority"] == "P0" and t["queue"] == "security-review"
    assert "priority:p0" in t["labels"] and "security" in t["labels"] and "ai-authored" in t["labels"]
    assert t["sla_hours"] == 1 and t["suggested_reviewers"] == ["backend"]
    assert "Do not merge" in t["next_actions"][0]
    assert "PR triage — P0" in triage.to_markdown(t)

    clean_rev = _rev("ALLOWED", rules=(), files=("app.py",), score=10)
    clean_rev["files"][0]["ai"] = False
    clean = triage.run(clean_rev, policy={"triage": {"code_owners": {"apps": ["app\\.py"]}}})
    assert clean["priority"] == "P3" and clean["queue"] == "fast-track"
    assert "clean" in clean["labels"] and clean["suggested_reviewers"] == ["apps"]


def test_diagnose_correlates_changes_and_redacts_secrets():
    log = ("ModuleNotFoundError: No module named 'requests'\n"
           "FAILED tests/test_api.py::test_fetch\n"
           'File "shop/api.py", line 7, in fetch\n'
           f"token = {SECRET}\n")
    res = diagnose.run(log, rev=_rev("ALLOWED", rules=(), files=("shop/api.py", "tests/test_api.py")))
    assert res["status"] == "diagnosed" and res["confidence"] == "high"
    assert any(s["file"] == "shop/api.py" for s in res["suspect_files"])
    assert any(s["file"] == "tests/test_api.py" for s in res["suspect_files"])
    assert SECRET not in json.dumps(res)
    assert "Missing Python package" in diagnose.to_markdown(res)
    assert diagnose.run("all good")["status"] == "needs-more-data"


def test_testing_plan_and_real_suite(tmp_path):
    root = _repo(tmp_path)
    pol = dict(policy.DEFAULT)
    pol["test_command"] = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    planned = testing.plan(root, paths=["app.py"])
    assert planned and planned[0]["tests"] == ["tests/test_app.py"]
    res = testing.run(root, pol, repeats=2, log=audit.AuditLog(str(tmp_path / "home")))
    assert res["status"] == "passed" and res["counts"]["passed"] >= 1
    assert "Testing workflow" in testing.to_markdown(res)


def test_testing_detects_flaky_runs(monkeypatch, tmp_path):
    root = _repo(tmp_path)
    calls = []

    def fake(root_, overrides, pol, cov_funcs=None):
        calls.append(1)
        return {"ran": True, "ok": len(calls) > 1, "output": "1 failed, 1 passed\nFAILED tests/test_app.py::test_add",
                "cmd": "pytest", "coverage": {}, "sandbox": {}}

    monkeypatch.setattr(testing.optimizer, "run_tests", fake)
    res = testing.run(root, policy.DEFAULT, repeats=2)
    assert res["status"] == "flaky" and res["flaky"] and res["runs"] == 2


def test_incident_classification_brief_and_human_ack(tmp_path):
    home = str(tmp_path / "home")
    log = audit.AuditLog(home)
    res = incident.run({"severity": "SEV1", "service": "payments", "message": "Production outage: 5xx error rate"},
                       home=home, log=log)
    assert res["severity"] == "SEV1" and res["status"] == "triaged"
    assert res["incident_id"].startswith("INC-") and os.path.isfile(res["brief_path"])
    assert any("Page" in step for step in res["playbook"])
    assert res["acknowledged_by"] is None
    acked = incident.acknowledge(res, "Priya Sharma", log)
    assert acked["acknowledged_by"] == "Priya Sharma" and acked["acknowledged_at"]
    assert json.load(open(acked["brief_path"], encoding="utf-8"))["acknowledged_by"] == "Priya Sharma"
    with pytest.raises(ValueError):
        incident.acknowledge(res, "")
    assert any(e["event"] == "incident-ack" for e in log.entries())


def test_incident_never_mutates_the_repository(tmp_path):
    root = _repo(tmp_path)
    before = subprocess.run(["git", "-C", root, "status", "--porcelain"], capture_output=True, text=True).stdout
    incident.run("p2 elevated latency on checkout", root=root, home=str(tmp_path / "home"))
    after = subprocess.run(["git", "-C", root, "status", "--porcelain"], capture_output=True, text=True).stdout
    assert before == after == ""


def test_agent_workflow_runs_all_five_tasks(tmp_path):
    root = str(tmp_path / "repo")
    demo.seed(root)
    home = str(tmp_path / "home")
    log = audit.AuditLog(home)
    res = agent.run("workflow", root=root, base="main", home=home, log=log, actor="oncall",
                    log_text="ModuleNotFoundError: No module named 'requests'",
                    alert={"severity": "critical", "service": "payments", "message": "production outage"})
    assert res["task"] == "workflow" and res["decision"] in ("ALLOWED", "BLOCKED", "CHANGES_REQUIRED")
    assert res["triage"]["priority"] and res["diagnosis"]["status"] == "diagnosed"
    assert res["incident"]["severity"] == "SEV1" and res["testing"] is None
    assert os.path.isfile(res["artifact"])
    md = agent.to_markdown(res)
    assert "Developer Workflow agent" in md and "Failed-build diagnosis" in md and "on-call" in md
    events = {e["event"] for e in log.entries()}
    assert {"review", "diagnose", "incident", "agent-workflow"} <= events

    with pytest.raises(ValueError):
        agent.run("unknown", root=root, home=home, log=log)


def test_agent_cli_triage_command(tmp_path, capsys):
    root = str(tmp_path / "repo")
    demo.seed(root)
    rc = agent_cli_main(["--repo", root, "--home", str(tmp_path / "home"), "triage", "--base", "main", "--json"])
    out = capsys.readouterr().out
    assert rc in (0, 1) and '"priority"' in out and '"task": "triage"' in out


def test_test_command_detection_is_ecosystem_agnostic(tmp_path):
    cases = [
        ({"package.json": '{"scripts":{"test":"jest"}}'}, "npm test", "package.json"),
        ({"package.json": '{"scripts":{"test":"jest"}}', "pnpm-lock.yaml": ""}, "pnpm test", "package.json"),
        ({"package.json": '{"scripts":{"test":"vitest"}}', "yarn.lock": ""}, "yarn test", "package.json"),
        ({"go.mod": "module example.com/x"}, "go test ./...", "go.mod"),
        ({"Cargo.toml": "[package]\nname = 'x'"}, "cargo test", "Cargo.toml"),
        ({"pom.xml": "<project/>"}, "mvn -q test", "pom.xml"),
        ({"gradlew": ""}, "./gradlew test", "gradlew"),
        ({"Makefile": "test:\n\techo ok\n"}, "make test", "Makefile"),
    ]
    for n, (files, expected, source) in enumerate(cases):
        root = tmp_path / f"eco{n}"
        root.mkdir()
        for name, text in files.items():
            (root / name).write_text(text, encoding="utf-8")
        assert testing.detect_command(str(root)) == (expected, source)
    assert testing.detect_command(str(tmp_path / "eco0"), {"test_command": "custom"}) == ("custom", "policy")


def test_test_mapping_covers_non_python_languages(tmp_path):
    root = str(tmp_path)
    for name in ("src/handler.go", "src/handler_test.go", "src/service.ts", "tests/service.test.ts",
                 "src/Thing.java", "src/ThingTest.java"):
        path = os.path.join(root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("// test fixture\n")
    rows = testing.plan(root, paths=["src/handler.go", "src/service.ts", "src/Thing.java", "tests/service.test.ts"])
    by_source = {r["source"]: r for r in rows}
    assert by_source["src/handler.go"]["tests"] == ["src/handler_test.go"]
    assert by_source["src/service.ts"]["tests"] == ["tests/service.test.ts"]
    assert by_source["src/Thing.java"]["tests"] == ["src/ThingTest.java"]
    assert by_source["tests/service.test.ts"]["coverage"] == "direct"


def test_triage_accepts_forge_agnostic_pr_metadata():
    rev = _rev("ALLOWED", rules=(), files=("app.py",), score=10)
    rev["files"][0]["ai"] = False
    t = triage.run(rev, pr={"title": "Hotfix: checkout 500s", "labels": [{"name": "urgent"}],
                            "author": "dev@example.com", "additions": 1400})
    assert t["priority"] == "P1" and t["urgent"] and "urgent" in t["labels"]
    assert "large-change" in t["labels"] and t["pr_title"] == "Hotfix: checkout 500s"
    assert t["pr_author"] == "dev@example.com" and "PR: Hotfix" in triage.to_markdown(t)
    assert t["next_actions"][0].startswith("Fast-track") and "Do not merge" not in t["next_actions"]
    draft = triage.run(_rev("ALLOWED", rules=(), score=40), pr={"title": "wip", "draft": True})
    assert draft["priority"] == "P3" and "draft" in draft["labels"]


def test_incident_normalizes_common_alert_providers():
    am = incident.classify({"labels": {"alertname": "HighErrors", "severity": "critical", "service": "checkout"},
                            "annotations": {"summary": "High 5xx error rate"}})
    assert am["severity"] == "SEV1" and am["service"] == "checkout"
    assert am["source"] == "alertmanager" and "5xx" in am["signal"]
    pd = incident.classify({"payload": {"severity": "warning", "summary": "Latency high", "service": "api",
                                        "dedup_key": "PD-42"}})
    assert pd["severity"] == "SEV3" and pd["service"] == "api" and pd["incident_id"] == "PD-42"
    assert pd["source"] == "pagerduty"
    dd = incident.classify({"alert_type": "error", "title": "Elevated errors",
                            "tags": ["service:web", "env:prod"], "provider": "datadog"})
    assert dd["service"] == "web" and dd["source"] == "datadog"


def test_explainer_covers_more_languages():
    go = explainer.explain("main.go:12:3: undefined: helper")
    assert go["summary"] == "Undefined Go identifier" and go["location"]["file"] == "main.go"
    rust = explainer.explain("error[E0308]: mismatched types\n  --> src/main.rs:4:5")
    assert rust["summary"] == "Rust compile error" and rust["location"]["file"] == "src/main.rs"
    java = explainer.explain("[ERROR] BUILD FAILURE\n[ERROR] /app/src/Main.java:10: cannot find symbol")
    assert java["summary"] == "JVM build failed" and java["location"]["file"] == "/app/src/Main.java"


def test_server_agent_route_and_ack_rbac(tmp_path):
    root = _repo(tmp_path)
    ctx = server.Ctx(root, "main", str(tmp_path / "home"), False)
    res = server.route(ctx, "/api/agent", {"task": "incident", "service": "api", "alert": "p1 high error rate"})
    assert res["task"] == "incident" and res["severity"] == "SEV2"
    with pytest.raises(PermissionError):
        server.route(ctx, "/api/agent", {"task": "incident", "alert": "SEV1", "ack": True})
    with pytest.raises(ValueError):
        server.route(ctx, "/api/agent", {"task": "bogus"})


def agent_cli_main(argv):
    from repobrain import cli
    return cli.main(argv)
