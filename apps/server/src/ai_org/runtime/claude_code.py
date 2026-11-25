"""Claude Code 런타임. 공식 Claude Agent SDK(Python)로 사용자가 설치한 `claude` CLI를 실행한다.

- 인증: CLI에 로그인된 사용자 자격(구독 또는 API 키)을 그대로 쓴다. 이 앱은 자격증명을 읽거나 저장하지 않는다.
  환경에 ANTHROPIC_API_KEY가 있으면 CLI가 그것을 우선 사용하므로 detect()가 경고한다.
- 권한: 모든 도구 호출은 먼저 PreToolUse 훅에서 우리 정책(on_permission)을 거친다. Claude Code는 읽기 전용
  명령(예: echo) 등을 묻지 않고 허용하므로 can_use_tool만으로는 '항상 승인' 정책을 지킬 수 없다(실측).
  훅은 거부만 하거나 통과시킨다(allow를 반환해 Claude Code 확인을 건너뛰지 않는다 = 권한을 넓히지 않음).
  그다음 Claude Code가 확인을 요청하면 can_use_tool이 호출되고, 훅에서 이미 승인한 호출이면 허용한다.
  Claude Code의 deny 규칙·permission mode는 그대로 적용된다. bypassPermissions는 쓰지 않는다.
- 한 턴마다 프로세스를 띄우고 끝나면 닫는다. 다음 턴은 resume으로 이어 간다(라즈베리 파이 메모리 고려).
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from ai_org.runtime.base import PermissionCallback, RunRequest, RuntimeEvent
from ai_org.schemas import RuntimeInfo

ORG_SERVER = "org"  # 도구 이름은 mcp__org__<도구>가 된다(policy·activity가 이 접두사를 안다).


class ClaudeCodeRuntime:
    id = "claude-code"
    name = "Claude Code"

    def __init__(self, binary: str = "claude") -> None:
        self.binary = binary

    def cli_path(self) -> str | None:
        return shutil.which(self.binary)

    def detect(self) -> RuntimeInfo:
        path = self.cli_path()
        if path is None:
            return RuntimeInfo(
                id=self.id,
                name=self.name,
                available=False,
                detail="`claude` 실행 파일을 PATH에서 찾지 못했습니다.",
            )
        try:
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return RuntimeInfo(id=self.id, name=self.name, available=False, path=path, detail=str(exc))
        version = out.stdout.strip().split(" ")[0] if out.returncode == 0 else None
        detail = None if out.returncode == 0 else out.stderr.strip()[:200]
        if out.returncode == 0 and os.environ.get("ANTHROPIC_API_KEY"):
            detail = "ANTHROPIC_API_KEY가 설정되어 있어 CLI 로그인 대신 API 키 과금이 사용됩니다."
        return RuntimeInfo(
            id=self.id,
            name=self.name,
            available=out.returncode == 0,
            version=version,
            path=path,
            detail=detail,
        )

    def start(self, request: RunRequest, on_permission: PermissionCallback) -> ClaudeCodeRun:
        return ClaudeCodeRun(self, request, on_permission)


class ClaudeCodeRun:
    def __init__(
        self, runtime: ClaudeCodeRuntime, request: RunRequest, on_permission: PermissionCallback
    ) -> None:
        self.runtime = runtime
        self.request = request
        self.on_permission = on_permission
        self._client: Any = None
        self._interrupted = False

    def _options(self) -> Any:
        from claude_agent_sdk import ClaudeAgentOptions, HookMatcher
        from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny

        approved: set[str] = set()

        async def pre_tool_use(hook_input: Any, tool_use_id: str | None, _ctx: Any) -> Any:
            decision = await self.on_permission(
                hook_input.get("tool_name", ""), hook_input.get("tool_input") or {}
            )
            if not decision.allow:
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": decision.message or "정책에 의해 거부되었습니다.",
                    }
                }
            if tool_use_id:
                approved.add(tool_use_id)
            return {"continue_": True}

        async def can_use_tool(tool_name: str, tool_input: dict[str, Any], ctx: Any) -> Any:
            if getattr(ctx, "tool_use_id", None) in approved:
                return PermissionResultAllow(updated_input=tool_input)
            decision = await self.on_permission(tool_name, tool_input)
            if decision.allow:
                return PermissionResultAllow(updated_input=tool_input)
            return PermissionResultDeny(message=decision.message or "정책에 의해 거부되었습니다.")

        req = self.request
        servers: dict[str, Any] = dict(req.mcp_servers)
        if req.org_tools:
            servers[ORG_SERVER] = self._org_server()
        return ClaudeAgentOptions(
            cwd=str(req.cwd),
            cli_path=self.runtime.cli_path(),
            system_prompt=req.system_prompt
            if req.system_prompt is not None
            else {"type": "preset", "preset": "claude_code", "append": req.system_prompt_append},
            tools=list(req.tools) if req.tools is not None else None,
            output_format={"type": "json_schema", "schema": req.output_schema} if req.output_schema else None,
            model=req.model,
            permission_mode=req.permission_mode,
            allowed_tools=list(req.allowed_tools),
            disallowed_tools=list(req.disallowed_tools),
            add_dirs=[str(p) for p in req.add_dirs],
            # 사용자 전역 설정의 allow 규칙이 앱 승인 절차를 건너뛰지 않도록 프로젝트 설정만 읽는다.
            setting_sources=list(req.setting_sources),  # type: ignore[arg-type]
            # 에이전트에게 허용된 MCP 서버만 붙인다(strict: 사용자·프로젝트 설정의 다른 서버는 무시).
            mcp_servers=servers,
            # 위임 도구는 하위 에이전트 작업이 끝날 때까지 기다린다(수 분) → MCP 도구 타임아웃을 늘린다.
            env={"MCP_TOOL_TIMEOUT": str(int((req.approval_timeout_s + 3600) * 1000))}
            if req.org_tools
            else {},
            strict_mcp_config=True,
            plugins=[{"type": "local", "path": p} for p in req.plugin_paths],
            skills=list(req.skills),
            resume=req.resume_session_id,
            max_turns=req.max_turns,
            include_partial_messages=True,
            can_use_tool=can_use_tool,
            # 훅 기본 타임아웃(60초)은 사람 승인보다 짧다. 승인 대기 시간 + 여유로 늘린다.
            hooks={
                "PreToolUse": [
                    HookMatcher(matcher=None, hooks=[pre_tool_use], timeout=req.approval_timeout_s + 30)
                ]
            },
        )

    def _org_server(self) -> Any:
        from claude_agent_sdk import create_sdk_mcp_server, tool

        sdk_tools = []
        for org_tool in self.request.org_tools:

            async def call(args: dict[str, Any], _handler: Any = org_tool.handler) -> dict[str, Any]:
                text = await _handler(args)
                return {"content": [{"type": "text", "text": text}]}

            sdk_tools.append(tool(org_tool.name, org_tool.description, org_tool.input_schema)(call))
        return create_sdk_mcp_server(ORG_SERVER, "1.0.0", sdk_tools)

    async def events(self) -> AsyncIterator[RuntimeEvent]:
        from claude_agent_sdk import ClaudeSDKClient
        from claude_agent_sdk.types import (
            AssistantMessage,
            ResultMessage,
            StreamEvent,
            SystemMessage,
            TextBlock,
            ToolResultBlock,
            ToolUseBlock,
            UserMessage,
        )

        if self.runtime.cli_path() is None:
            yield RuntimeEvent("error", {"message": "Claude Code CLI를 찾을 수 없습니다."})
            return
        if not Path(self.request.cwd).is_dir():
            yield RuntimeEvent("error", {"message": "작업 디렉터리가 없습니다."})
            return

        client = ClaudeSDKClient(self._options())
        self._client = client
        try:
            await client.connect()
            await client.query(self.request.prompt)
            async for msg in client.receive_response():
                if isinstance(msg, SystemMessage):
                    if msg.subtype == "init":
                        data = msg.data
                        yield RuntimeEvent(
                            "session.started",
                            {
                                "session_id": data.get("session_id"),
                                "model": data.get("model"),
                                "tools": len(data.get("tools") or []),
                                "skills": data.get("skills") or [],
                            },
                        )
                elif isinstance(msg, StreamEvent):
                    if msg.parent_tool_use_id is not None:
                        continue
                    event = msg.event
                    delta = event.get("delta") if isinstance(event, dict) else None
                    if (
                        event.get("type") == "content_block_delta"
                        and isinstance(delta, dict)
                        and delta.get("type") == "text_delta"
                    ):
                        yield RuntimeEvent("message.delta", {"text": delta.get("text", "")})
                elif isinstance(msg, AssistantMessage):
                    sub = msg.parent_tool_use_id is not None
                    for block in msg.content:
                        if isinstance(block, TextBlock) and not sub:
                            yield RuntimeEvent("message", {"text": block.text})
                        elif isinstance(block, ToolUseBlock):
                            yield RuntimeEvent(
                                "tool.started",
                                {"id": block.id, "tool": block.name, "input": block.input, "subagent": sub},
                            )
                elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                    for block in msg.content:
                        if isinstance(block, ToolResultBlock):
                            yield RuntimeEvent(
                                "tool.failed" if block.is_error else "tool.completed",
                                {"id": block.tool_use_id},
                            )
                elif isinstance(msg, ResultMessage):
                    yield RuntimeEvent(
                        "turn.completed",
                        {
                            "session_id": msg.session_id,
                            "is_error": msg.is_error,
                            "subtype": msg.subtype,
                            "cost_usd": msg.total_cost_usd,
                            "duration_ms": msg.duration_ms,
                            "num_turns": msg.num_turns,
                            "interrupted": self._interrupted,
                            "structured_output": msg.structured_output,
                            "result": msg.result,
                        },
                    )
        except Exception as exc:  # SDK 오류는 이벤트로 바꿔 대화에 남긴다.
            yield RuntimeEvent("error", {"message": f"{type(exc).__name__}: {exc}"[:500]})
        finally:
            self._client = None
            with contextlib.suppress(Exception):  # 이미 종료된 프로세스
                await client.disconnect()

    async def interrupt(self) -> None:
        self._interrupted = True
        if self._client is not None:
            await self._client.interrupt()
