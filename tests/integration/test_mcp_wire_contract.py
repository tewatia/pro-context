"""Wire-level integration tests for MCP transport contract."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def _run_mcp_exchange(env: dict[str, str], messages: list[dict]) -> list[dict]:

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
    proc.stdin.flush()

    # Read responses line-by-line until every request ID has been answered.
    #
    # The MCP stdio transport uses zero-capacity anyio streams, so the receive
    # loop dispatches async tool handlers (e.g. aiosqlite lookups) via
    # anyio.start_soon() and immediately continues reading the remaining stdin
    # messages.  If we close stdin before those handlers finish, the receive
    # loop exits and tears down the write stream, silently dropping in-flight
    # responses.  Reading first keeps stdin open until the handlers complete.
    expected_ids = frozenset(msg["id"] for msg in messages if "id" in msg)
    responses: list[dict] = []
    seen_ids: set = set()
    while seen_ids < expected_ids:
        line = proc.stdout.readline()
        if not line:  # server exited before answering all requests
            break
        stripped = line.strip()
        if stripped:
            resp = json.loads(stripped)
            responses.append(resp)
            rid = resp.get("id")
            if rid is not None:
                seen_ids.add(rid)

    # Ask the server to shut down gracefully now that we have all responses.
    try:
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 9999, "method": "shutdown"}) + "\n")
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "exit"}) + "\n")
    except OSError:
        pass  # server already exited
    proc.stdin.close()

    proc.stderr.read()  # drain for reliable process shutdown
    proc.wait(timeout=10)
    proc.stdout.close()
    proc.stderr.close()

    return responses


def _seed_toc_cache(
    tmp_path: Path,
    *,
    library_id: str,
    llms_txt_url: str,
    content: str,
) -> None:
    db_path = tmp_path / "cache.db"
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=24)

    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS toc_cache (
                library_id         TEXT PRIMARY KEY,
                llms_txt_url       TEXT NOT NULL,
                content            TEXT NOT NULL,
                discovered_domains TEXT NOT NULL DEFAULT '',
                fetched_at         TEXT NOT NULL,
                expires_at         TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO toc_cache
            (library_id, llms_txt_url, content, fetched_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                library_id,
                llms_txt_url,
                content,
                now.isoformat(),
                expires_at.isoformat(),
            ),
        )
        conn.commit()


def _seed_page_cache(
    tmp_path: Path,
    *,
    url: str,
    content: str,
    headings: str,
) -> None:
    db_path = tmp_path / "cache.db"
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=24)

    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS page_cache (
                url_hash           TEXT PRIMARY KEY,
                url                TEXT NOT NULL UNIQUE,
                content            TEXT NOT NULL,
                headings           TEXT NOT NULL DEFAULT '',
                discovered_domains TEXT NOT NULL DEFAULT '',
                fetched_at         TEXT NOT NULL,
                expires_at         TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO page_cache
            (url_hash, url, content, headings, fetched_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                url_hash,
                url,
                content,
                headings,
                now.isoformat(),
                expires_at.isoformat(),
            ),
        )
        conn.commit()


def test_initialize_and_tools_list_contract(subprocess_env: dict[str, str]) -> None:
    responses = _run_mcp_exchange(
        subprocess_env,
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
    assert "read_page" in tools_by_name

    resolve_schema = tools_by_name["resolve_library"]["inputSchema"]
    assert resolve_schema["type"] == "object"
    assert "query" in resolve_schema["required"]

    get_docs_schema = tools_by_name["get_library_docs"]["inputSchema"]
    assert get_docs_schema["type"] == "object"
    assert "library_id" in get_docs_schema["required"]

    read_page_schema = tools_by_name["read_page"]["inputSchema"]
    assert read_page_schema["type"] == "object"
    assert "url" in read_page_schema["required"]
    assert read_page_schema["properties"]["offset"]["type"] == "integer"
    assert read_page_schema["properties"]["limit"]["type"] == "integer"


def test_resolve_library_wire_success(subprocess_env: dict[str, str]) -> None:
    responses = _run_mcp_exchange(
        subprocess_env,
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


def test_read_page_wire_success_from_cache(tmp_path: Path, subprocess_env: dict[str, str]) -> None:
    url = "https://python.langchain.com/docs/concepts/cached.md"
    content = "# Title\n\n## Section\nLine A\nLine B"
    headings = "1: # Title\n3: ## Section"
    _seed_page_cache(tmp_path, url=url, content=content, headings=headings)

    responses = _run_mcp_exchange(
        subprocess_env,
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
                    "name": "read_page",
                    "arguments": {"url": url, "offset": 3, "limit": 2},
                },
            },
        ],
    )

    tool_response = next(response for response in responses if response.get("id") == 2)
    assert tool_response["result"]["isError"] is False

    payload = json.loads(tool_response["result"]["content"][0]["text"])
    assert payload["url"] == url
    assert payload["cached"] is True
    assert payload["stale"] is False
    assert payload["offset"] == 3
    assert payload["limit"] == 2
    assert payload["headings"] == headings
    assert payload["total_lines"] == 5
    assert payload["content"] == "## Section\nLine A"


def test_read_page_wire_error_envelope(subprocess_env: dict[str, str]) -> None:
    responses = _run_mcp_exchange(
        subprocess_env,
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
                    "name": "read_page",
                    "arguments": {"url": "https://evil.example.com/docs.md"},
                },
            },
        ],
    )

    tool_response = next(response for response in responses if response.get("id") == 2)
    assert tool_response["result"]["isError"] is True

    payload = json.loads(tool_response["result"]["content"][0]["text"])
    assert payload["error"]["code"] == "URL_NOT_ALLOWED"
    assert payload["error"]["recoverable"] is False


def test_get_library_docs_wire_success_from_cache(
    tmp_path: Path, subprocess_env: dict[str, str]
) -> None:
    _seed_toc_cache(
        tmp_path,
        library_id="langchain",
        llms_txt_url="https://python.langchain.com/llms.txt",
        content="# LangChain\n\n## Concepts\n\n- [Chat Models](https://python.langchain.com/docs/concepts/chat_models.md)",
    )

    responses = _run_mcp_exchange(
        subprocess_env,
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
                    "name": "get_library_docs",
                    "arguments": {"library_id": "langchain"},
                },
            },
        ],
    )

    tool_response = next(response for response in responses if response.get("id") == 2)
    assert tool_response["result"]["isError"] is False

    payload = json.loads(tool_response["result"]["content"][0]["text"])
    assert payload["library_id"] == "langchain"
    assert payload["name"] == "LangChain"
    assert payload["cached"] is True
    assert payload["stale"] is False
    assert "# LangChain" in payload["content"]
    assert set(payload.keys()) == {
        "library_id",
        "name",
        "content",
        "cached",
        "cached_at",
        "stale",
    }


def test_get_library_docs_wire_error_envelope(subprocess_env: dict[str, str]) -> None:
    responses = _run_mcp_exchange(
        subprocess_env,
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
                    "name": "get_library_docs",
                    "arguments": {"library_id": "nonexistent-lib"},
                },
            },
        ],
    )

    tool_response = next(response for response in responses if response.get("id") == 2)
    assert tool_response["result"]["isError"] is True

    payload = json.loads(tool_response["result"]["content"][0]["text"])
    assert payload["error"]["code"] == "LIBRARY_NOT_FOUND"
    assert payload["error"]["recoverable"] is False
