#!/usr/bin/env python3
"""
integrations/mcp_server.py
Model Context Protocol (MCP) stdio server for RepoBrain.
Exposes RepoBrain's preflight governance check as an MCP tool.
Zero external dependencies (standard library only).
"""
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repobrain import server


def handle_initialize(req_id, params):
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": "repobrain-mcp",
                "version": "1.0.0"
            },
            "capabilities": {
                "tools": {}
            }
        }
    }


def handle_tools_list(req_id):
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "tools": [
                {
                    "name": "repobrain_preflight",
                    "description": (
                        "Governance preflight check: validate a proposed file edit before writing to disk. "
                        "Checks repository policy, protected paths (.github/workflows, secrets), hardcoded "
                        "credentials, prompt injections, and risky shell commands."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Repository-relative file path intended to be written or modified"
                            },
                            "content": {
                                "type": "string",
                                "description": "Proposed file text content"
                            },
                            "actor": {
                                "type": "string",
                                "description": "Identifier of the agent or contributor",
                                "default": "ai-agent"
                            }
                        },
                        "required": ["path"]
                    }
                }
            ]
        }
    }


def handle_tools_call(req_id, params):
    name = params.get("name")
    arguments = params.get("arguments", {})

    if name != "repobrain_preflight":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {name}"
            }
        }

    path = arguments.get("path", "")
    content = arguments.get("content", "")
    actor = arguments.get("actor", "ai-agent")
    cwd = os.getcwd()

    res = server.preflight(cwd, actor, [{"path": path, "content": content}])

    is_block = res.get("decision") == "block"
    summary_text = (
        f"RepoBrain Preflight Decision: {res.get('decision', 'allowed').upper()}\n"
        f"Findings ({len(res.get('findings', []))}): {json.dumps(res.get('findings', []), indent=2)}"
    )

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": summary_text
                }
            ],
            "isError": is_block
        }
    }


def process_message(line):
    line = line.strip()
    if not line:
        return None
    try:
        msg = json.loads(line)
    except Exception:
        return None

    req_id = msg.get("id")
    method = msg.get("method")
    params = msg.get("params", {})

    if method == "initialize":
        return handle_initialize(req_id, params)
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        return handle_tools_list(req_id)
    elif method == "tools/call":
        return handle_tools_call(req_id, params)
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    elif req_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Unhandled method: {method}"
            }
        }
    return None


def main():
    """Stdio loop for MCP JSON-RPC messages."""
    for line in sys.stdin:
        resp = process_message(line)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
