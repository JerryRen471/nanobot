import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from nanobot.agent.tools.cursor_agent import CursorAgentTool


@pytest.mark.asyncio
async def test_cursor_agent_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    tool = CursorAgentTool(api_key=None)

    result = await tool.execute(action="list")

    assert result.startswith("Error:")
    assert "CURSOR_API_KEY" in result


@pytest.mark.asyncio
async def test_cursor_launch_builds_expected_payload(monkeypatch) -> None:
    tool = CursorAgentTool(api_key="cursor_test_key")
    seen: dict[str, object] = {}

    async def _fake_request(method: str, path: str, **kwargs):
        seen["method"] = method
        seen["path"] = path
        seen["json_body"] = kwargs.get("json_body")
        return {
            "id": "bc_123",
            "status": "CREATING",
            "name": "Test Task",
            "target": {"url": "https://cursor.com/agents/bc_123", "branchName": "cursor/test", "prUrl": None},
        }

    monkeypatch.setattr(tool, "_request", _fake_request)
    result = await tool.execute(
        action="launch",
        prompt="Fix failing tests",
        repository="https://github.com/acme/repo",
        ref="main",
        autoCreatePr=True,
        branchName="cursor/fix-tests",
    )
    data = json.loads(result)

    assert seen["method"] == "POST"
    assert seen["path"] == "/v0/agents"
    assert data["agentId"] == "bc_123"

    payload = seen["json_body"]
    assert isinstance(payload, dict)
    assert payload["prompt"]["text"] == "Fix failing tests"
    assert payload["source"]["repository"] == "https://github.com/acme/repo"
    assert payload["source"]["ref"] == "main"
    assert payload["target"]["autoCreatePr"] is True
    assert payload["target"]["branchName"] == "cursor/fix-tests"


@pytest.mark.asyncio
async def test_cursor_wait_returns_final_summary(monkeypatch) -> None:
    tool = CursorAgentTool(api_key="cursor_test_key")
    status_calls = {"count": 0}

    async def _fake_request(method: str, path: str, **kwargs):
        if path == "/v0/agents/bc_abc":
            status_calls["count"] += 1
            if status_calls["count"] == 1:
                return {"id": "bc_abc", "status": "RUNNING"}
            return {
                "id": "bc_abc",
                "status": "FINISHED",
                "target": {
                    "url": "https://cursor.com/agents/bc_abc",
                    "branchName": "cursor/fix",
                    "prUrl": "https://github.com/acme/repo/pull/12",
                },
            }
        if path == "/v0/agents/bc_abc/conversation":
            return {
                "id": "bc_abc",
                "messages": [
                    {"id": "1", "type": "user_message", "text": "Please fix it"},
                    {"id": "2", "type": "assistant_message", "text": "Done and pushed commits."},
                ],
            }
        raise AssertionError(f"Unexpected request path: {path}")

    monkeypatch.setattr(tool, "_request", _fake_request)
    monkeypatch.setattr("nanobot.agent.tools.cursor_agent.asyncio.sleep", AsyncMock(return_value=None))

    result = await tool.execute(
        action="wait",
        agentId="bc_abc",
        waitTimeoutSeconds=5,
        pollIntervalSeconds=1,
    )
    data = json.loads(result)

    assert data["agentId"] == "bc_abc"
    assert data["status"] == "FINISHED"
    assert "Done and pushed commits." in data["lastAssistantMessage"]
    assert status_calls["count"] == 2


@pytest.mark.asyncio
async def test_cursor_request_uses_bearer_auth() -> None:
    tool = CursorAgentTool(api_key="cursor_test_key", api_base="https://api.cursor.com", timeout=20)

    with patch("httpx.AsyncClient") as mock_client:
        response = Mock()
        response.status_code = 200
        response.json = Mock(return_value={"ok": True})

        client = AsyncMock()
        client.request = AsyncMock(return_value=response)
        mock_client.return_value.__aenter__.return_value = client

        data = await tool._request("GET", "/v0/agents", params={"limit": 1})
        call = client.request.call_args.kwargs

    assert data == {"ok": True}
    assert call["headers"]["Authorization"] == "Bearer cursor_test_key"
    assert call["url"] == "https://api.cursor.com/v0/agents"
