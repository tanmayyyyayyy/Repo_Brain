import json
import os
import subprocess
import sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_mcp_server_protocol_lifecycle():
    script_path = os.path.join(ROOT, "integrations", "mcp_server.py")
    req1 = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    req2 = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    req3 = json.dumps({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "repobrain_preflight",
            "arguments": {
                "path": ".github/workflows/deploy.yml",
                "content": "name: hack",
                "actor": "claude"
            }
        }
    })
    req4 = json.dumps({"jsonrpc": "2.0", "id": 4, "method": "ping", "params": {}})

    input_payload = f"{req1}\n{req2}\n{req3}\n{req4}\n"
    proc = subprocess.run([sys.executable, script_path], input=input_payload, text=True, capture_output=True, cwd=ROOT)
    assert proc.returncode == 0

    lines = [ln for ln in proc.stdout.strip().split("\n") if ln.strip()]
    assert len(lines) == 4

    # 1. Initialize response
    r1 = json.loads(lines[0])
    assert r1["id"] == 1
    assert r1["result"]["serverInfo"]["name"] == "repobrain-mcp"

    # 2. Tools list response
    r2 = json.loads(lines[1])
    assert r2["id"] == 2
    tools = r2["result"]["tools"]
    assert any(t["name"] == "repobrain_preflight" for t in tools)

    # 3. Tool execution (blocked path .github/workflows/)
    r3 = json.loads(lines[2])
    assert r3["id"] == 3
    assert r3["result"]["isError"] is True
    assert "BLOCK" in r3["result"]["content"][0]["text"]

    # 4. Ping response
    r4 = json.loads(lines[3])
    assert r4["id"] == 4
    assert r4["result"] == {}
