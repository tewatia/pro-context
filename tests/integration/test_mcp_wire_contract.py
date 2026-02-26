"""Wire-level integration tests for MCP transport contract."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def _run_mcp_exchange(tmp_path: Path, messages: list[dict]) -> list[dict]:
    env = os.environ.copy()
    env["PROCONTEXT__CACHE__DB_PATH"] = str(tmp_path / "cache.db")
    # Point to an unlistened port so the first-run blocking fetch fails immediately
    env["PROCONTEXT__REGISTRY__METADATA_URL"] = "http://127.0.0.1:1/registry_metadata.json"

    proc = subprocess.Popen(
        [sys.executable, "-m", "procontext.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    assert proc.stdin is not None
    assert proc.stdout is not None
    assert proc.stderr is not None

    for message in messages:
        proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.close()

    stdout_lines = [line for line in proc.stdout.read().splitlines() if line.strip()]
    proc.stderr.read()  # drain for reliable process shutdown
    proc.wait(timeout=10)

    return [json.loads(line) for line in stdout_lines]


def test_initialize_and_tools_list_contract(tmp_path: Path) -> None:
    responses = _run_mcp_exchange(
        tmp_path,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "0"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ],
    )

    init_response = next(response for response in responses if response.get("id") == 1)
    init_result = init_response["result"]
    assert init_result["protocolVersion"] in {"2025-11-25", "2025-03-26"}
    assert init_result["serverInfo"]["name"] == "procontext"
    assert "tools" in init_result["capabilities"]

    tools_response = next(response for response in responses if response.get("id") == 2)
    tools = tools_response["result"]["tools"]
    tools_by_name = {tool["name"]: tool for tool in tools}

    assert "resolve_library" in tools_by_name
    assert "get_library_docs" in tools_by_name

    resolve_schema = tools_by_name["resolve_library"]["inputSchema"]
    assert resolve_schema["type"] == "object"
    assert "query" in resolve_schema["required"]

    get_docs_schema = tools_by_name["get_library_docs"]["inputSchema"]
    assert get_docs_schema["type"] == "object"
    assert "library_id" in get_docs_schema["required"]


def test_resolve_library_wire_success(tmp_path: Path) -> None:
    responses = _run_mcp_exchange(
        tmp_path,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "0"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "resolve_library",
                    "arguments": {"query": "langchain-openai"},
                },
            },
        ],
    )

    tool_response = next(response for response in responses if response.get("id") == 2)
    assert tool_response["result"]["isError"] is False

    payload = json.loads(tool_response["result"]["content"][0]["text"])
    assert "matches" in payload
    assert payload["matches"][0]["library_id"] == "langchain"
