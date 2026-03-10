"""Cursor Cloud Agent API tool."""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any
from urllib.parse import quote

import httpx

from nanobot.agent.tools.base import Tool


class CursorAgentTool(Tool):
    """Launch and manage Cursor cloud agents for coding tasks."""

    TERMINAL_STATUSES = {"FINISHED", "ERROR", "EXPIRED", "STOPPED", "CANCELLED"}

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str = "https://api.cursor.com",
        timeout: int = 30,
    ) -> None:
        self._init_api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "cursor_agent"

    @property
    def description(self) -> str:
        return (
            "Use Cursor Cloud Agent API to run coding tasks on GitHub repositories. "
            "Supports launch, status, wait, conversation, followup, stop, and list."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["launch", "status", "wait", "conversation", "followup", "stop", "list"],
                    "description": "Operation to run on Cursor Agent API.",
                },
                "agentId": {
                    "type": "string",
                    "description": "Cursor agent id (required for status/wait/conversation/followup/stop).",
                },
                "prompt": {
                    "type": "string",
                    "description": "Task description for launch action.",
                },
                "followupPrompt": {
                    "type": "string",
                    "description": "Follow-up instruction for followup action.",
                },
                "repository": {
                    "type": "string",
                    "description": "GitHub repository URL for launch, e.g. https://github.com/org/repo.",
                },
                "ref": {
                    "type": "string",
                    "description": "Git ref (branch/tag) for launch source.",
                },
                "prUrl": {
                    "type": "string",
                    "description": "PR URL. For launch, use this instead of repository/ref to target a PR.",
                },
                "model": {
                    "type": "string",
                    "description": "Optional explicit Cursor model id for launch.",
                },
                "autoCreatePr": {
                    "type": "boolean",
                    "description": "If true, Cursor creates a PR automatically.",
                },
                "openAsCursorGithubApp": {
                    "type": "boolean",
                    "description": "Open PR as Cursor GitHub app (only with autoCreatePr).",
                },
                "skipReviewerRequest": {
                    "type": "boolean",
                    "description": "Skip requesting user as reviewer (only with app-opened PR).",
                },
                "branchName": {
                    "type": "string",
                    "description": "Optional target branch name for launch.",
                },
                "autoBranch": {
                    "type": "boolean",
                    "description": "When launching from prUrl, whether to auto-create a branch.",
                },
                "waitTimeoutSeconds": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 7200,
                    "description": "Max seconds to wait in wait action. Default 900.",
                },
                "pollIntervalSeconds": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 60,
                    "description": "Polling interval seconds for wait action. Default 8.",
                },
                "maxMessages": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "description": "Tail message count for conversation action. Default 30.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "List action page size. Default 20.",
                },
                "cursor": {
                    "type": "string",
                    "description": "Pagination cursor for list action.",
                },
            },
            "required": ["action"],
        }

    @property
    def api_key(self) -> str:
        return self._init_api_key or os.environ.get("CURSOR_API_KEY", "")

    async def execute(
        self,
        action: str,
        agentId: str | None = None,
        prompt: str | None = None,
        followupPrompt: str | None = None,
        repository: str | None = None,
        ref: str | None = None,
        prUrl: str | None = None,
        model: str | None = None,
        autoCreatePr: bool | None = None,
        openAsCursorGithubApp: bool | None = None,
        skipReviewerRequest: bool | None = None,
        branchName: str | None = None,
        autoBranch: bool | None = None,
        waitTimeoutSeconds: int = 900,
        pollIntervalSeconds: int = 8,
        maxMessages: int = 30,
        limit: int = 20,
        cursor: str | None = None,
        **_: Any,
    ) -> str:
        if not self.api_key:
            return (
                "Error: CURSOR_API_KEY is not configured. Set it in ~/.nanobot/config.json under "
                "tools.cursor.apiKey (or export CURSOR_API_KEY), then retry."
            )

        action = action.strip().lower()
        try:
            if action == "launch":
                return await self._launch(
                    prompt=prompt,
                    repository=repository,
                    ref=ref,
                    pr_url=prUrl,
                    model=model,
                    auto_create_pr=autoCreatePr,
                    open_as_cursor_app=openAsCursorGithubApp,
                    skip_reviewer_request=skipReviewerRequest,
                    branch_name=branchName,
                    auto_branch=autoBranch,
                )
            if action == "status":
                return await self._status(agentId)
            if action == "wait":
                return await self._wait(
                    agent_id=agentId,
                    timeout_s=waitTimeoutSeconds,
                    poll_s=pollIntervalSeconds,
                )
            if action == "conversation":
                return await self._conversation(agent_id=agentId, max_messages=maxMessages)
            if action == "followup":
                return await self._followup(agent_id=agentId, prompt=followupPrompt)
            if action == "stop":
                return await self._stop(agent_id=agentId)
            if action == "list":
                return await self._list(limit=limit, cursor=cursor, pr_url=prUrl)
            return f"Error: Unsupported action '{action}'."
        except Exception as e:
            return f"Error: {e}"

    async def _launch(
        self,
        prompt: str | None,
        repository: str | None,
        ref: str | None,
        pr_url: str | None,
        model: str | None,
        auto_create_pr: bool | None,
        open_as_cursor_app: bool | None,
        skip_reviewer_request: bool | None,
        branch_name: str | None,
        auto_branch: bool | None,
    ) -> str:
        if not prompt or not prompt.strip():
            return "Error: 'prompt' is required for launch action."
        if not pr_url and not repository:
            return "Error: For launch action, provide either 'prUrl' or 'repository'."

        body: dict[str, Any] = {
            "prompt": {"text": prompt},
            "source": {},
        }
        if model:
            body["model"] = model

        if pr_url:
            body["source"]["prUrl"] = pr_url
        else:
            body["source"]["repository"] = repository
            if ref:
                body["source"]["ref"] = ref

        target: dict[str, Any] = {}
        if auto_create_pr is not None:
            target["autoCreatePr"] = auto_create_pr
        if open_as_cursor_app is not None:
            target["openAsCursorGithubApp"] = open_as_cursor_app
        if skip_reviewer_request is not None:
            target["skipReviewerRequest"] = skip_reviewer_request
        if branch_name:
            target["branchName"] = branch_name
        if auto_branch is not None:
            target["autoBranch"] = auto_branch
        if target:
            body["target"] = target

        data = await self._request("POST", "/v0/agents", json_body=body)
        return json.dumps(
            {
                "agentId": data.get("id"),
                "status": data.get("status"),
                "name": data.get("name"),
                "targetUrl": (data.get("target") or {}).get("url"),
                "branchName": (data.get("target") or {}).get("branchName"),
                "prUrl": (data.get("target") or {}).get("prUrl"),
            },
            ensure_ascii=False,
        )

    async def _status(self, agent_id: str | None) -> str:
        if not agent_id:
            return "Error: 'agentId' is required for status action."
        data = await self._request("GET", f"/v0/agents/{quote(agent_id, safe='')}")
        return json.dumps(data, ensure_ascii=False)

    async def _wait(self, agent_id: str | None, timeout_s: int, poll_s: int) -> str:
        if not agent_id:
            return "Error: 'agentId' is required for wait action."
        deadline = time.monotonic() + timeout_s
        latest: dict[str, Any] = {}
        status = "UNKNOWN"

        while True:
            latest = await self._request("GET", f"/v0/agents/{quote(agent_id, safe='')}")
            status = str(latest.get("status") or "UNKNOWN").upper()
            if status in self.TERMINAL_STATUSES:
                break
            if time.monotonic() >= deadline:
                return (
                    f"Error: Timed out waiting for Cursor agent '{agent_id}' after {timeout_s}s. "
                    f"Latest status: {status}"
                )
            await asyncio.sleep(poll_s)

        if status != "FINISHED":
            return f"Error: Cursor agent '{agent_id}' ended with status '{status}'."

        last_assistant_message = ""
        try:
            conv = await self._request("GET", f"/v0/agents/{quote(agent_id, safe='')}/conversation")
            messages = conv.get("messages") or []
            for item in reversed(messages):
                if item.get("type") == "assistant_message":
                    last_assistant_message = item.get("text") or ""
                    break
        except Exception:
            last_assistant_message = ""

        target = latest.get("target") or {}
        return json.dumps(
            {
                "agentId": agent_id,
                "status": status,
                "targetUrl": target.get("url"),
                "branchName": target.get("branchName"),
                "prUrl": target.get("prUrl"),
                "lastAssistantMessage": last_assistant_message,
            },
            ensure_ascii=False,
        )

    async def _conversation(self, agent_id: str | None, max_messages: int) -> str:
        if not agent_id:
            return "Error: 'agentId' is required for conversation action."
        data = await self._request("GET", f"/v0/agents/{quote(agent_id, safe='')}/conversation")
        messages = data.get("messages") or []
        trimmed = messages[-max_messages:] if max_messages > 0 else messages
        return json.dumps({"id": data.get("id"), "messages": trimmed}, ensure_ascii=False)

    async def _followup(self, agent_id: str | None, prompt: str | None) -> str:
        if not agent_id:
            return "Error: 'agentId' is required for followup action."
        if not prompt or not prompt.strip():
            return "Error: 'followupPrompt' is required for followup action."
        data = await self._request(
            "POST",
            f"/v0/agents/{quote(agent_id, safe='')}/followup",
            json_body={"prompt": {"text": prompt}},
        )
        return json.dumps(
            {
                "agentId": data.get("id"),
                "status": data.get("status"),
                "targetUrl": (data.get("target") or {}).get("url"),
            },
            ensure_ascii=False,
        )

    async def _stop(self, agent_id: str | None) -> str:
        if not agent_id:
            return "Error: 'agentId' is required for stop action."
        await self._request("POST", f"/v0/agents/{quote(agent_id, safe='')}/stop")
        return json.dumps({"agentId": agent_id, "stopped": True}, ensure_ascii=False)

    async def _list(self, limit: int, cursor: str | None, pr_url: str | None) -> str:
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if pr_url:
            params["prUrl"] = pr_url
        data = await self._request("GET", "/v0/agents", params=params)
        return json.dumps(data, ensure_ascii=False)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.api_base}{path}"

        async with httpx.AsyncClient(timeout=float(self.timeout)) as client:
            resp = await client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_body,
            )

        if resp.status_code >= 400:
            body_text = resp.text[:1200]
            raise RuntimeError(f"Cursor API {method} {path} failed ({resp.status_code}): {body_text}")

        try:
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"Cursor API returned invalid JSON: {e}") from e

        if not isinstance(data, dict):
            raise RuntimeError("Cursor API returned a non-object response.")
        return data
