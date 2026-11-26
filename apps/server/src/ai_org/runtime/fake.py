"""테스트용 가짜 런타임(`AI_ORG_RUNTIME=fake`). Claude 사용량 없이 E2E·데모를 돌리기 위한 것이다.

실제 런타임과 같은 계약(RunHandle·RuntimeEvent·권한 콜백·OrgTool)을 지키며, 프롬프트 표식으로 동작을 고른다.
- 기본: 마크다운(코드 블록 포함) 응답을 조금씩 스트리밍한다.
- `[승인]`: 작업 폴더에 파일을 쓰는 Write 도구를 요청한다(기본 권한에서 사용자 승인 필요).
- `[위임:이름]`: 위임 도구(delegate_task)로 그 구성원에게 일을 넘기고 보고를 받아 취합한다.
- `[셸:명령]`: 그 셸 명령(Bash)을 요청한다. 실제 런타임의 PreToolUse 훅처럼 출처 "hook"으로 정책에 묻는다.
- `[되묻기:명령]`: 같은 요청을 한 뒤, 실제 Claude Code가 스스로 확인을 요청하는 경우를 흉내 낸다.
  auto 모드에서 정책이 '단순 통과'시킨 호출이면 출처 "runtime"으로 한 번 더 묻는다(→ 승인 배너).
  다른 모드에서는 실제 런타임과 같이 다시 묻지 않는다.
  `[셸:…]`·`[되묻기:…]`는 한 메시지에 여러 개 쓸 수 있고 적힌 순서대로 실행한다. 명령에 `]`는 쓸 수 없다.
  명령은 실제로 실행하지 않는다.
- 설계 담당자 실행(output_schema): 현재 명세에 'E2E팀'과 'E2E 분석가'를 더한 명세를 구조화 출력으로 돌려준다.
절대 운영에 쓰지 않는다. 화면의 런타임 표시가 '가짜 런타임'으로 나온다.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from ai_org.runtime.base import PermissionCallback, RunRequest, RuntimeEvent
from ai_org.schemas import RuntimeInfo

DELEGATE = re.compile(r"\[위임:([^\]]+)\]")
SHELL = re.compile(r"\[(셸|되묻기):([^\]]+)\]")
SPEC = re.compile(r"<current_spec>\s*(\{.*?\})\s*</current_spec>", re.S)


class FakeRuntime:
    id = "claude-code"
    name = "테스트용 가짜 런타임"

    def detect(self) -> RuntimeInfo:
        return RuntimeInfo(
            id=self.id,
            name=self.name,
            available=True,
            version="fake",
            path=None,
            detail="AI_ORG_RUNTIME=fake — 실제 Claude Code를 실행하지 않습니다.",
        )

    def start(self, request: RunRequest, on_permission: PermissionCallback) -> FakeRun:
        return FakeRun(request, on_permission)


class FakeRun:
    def __init__(self, request: RunRequest, on_permission: PermissionCallback) -> None:
        self.request = request
        self.on_permission = on_permission
        self.interrupted = False

    async def _stream(self, text: str) -> AsyncIterator[RuntimeEvent]:
        for i in range(0, len(text), 12):
            if self.interrupted:
                return
            yield RuntimeEvent("message.delta", {"text": text[i : i + 12]})
            await asyncio.sleep(0.03)
        yield RuntimeEvent("message", {"text": text})

    async def events(self) -> AsyncIterator[RuntimeEvent]:
        req = self.request
        session = f"fake-{req.agent_id[:8]}"
        yield RuntimeEvent("session.started", {"session_id": session, "model": "fake"})
        if req.output_schema is not None:
            yield RuntimeEvent("turn.completed", {"session_id": session, "structured_output": self._design()})
            return
        prompt = req.prompt
        if "[승인]" in prompt:
            tool_input = {"file_path": str(req.cwd / "e2e.txt"), "content": "e2e"}
            decision = await self.on_permission("Write", tool_input, "hook")
            yield RuntimeEvent("tool.started", {"id": "fake-write", "tool": "Write", "input": tool_input})
            yield RuntimeEvent("tool.completed" if decision.allow else "tool.failed", {"id": "fake-write"})
            async for ev in self._stream(
                "파일 쓰기가 승인되었습니다." if decision.allow else "파일 쓰기가 거부되었습니다."
            ):
                yield ev
        elif shell_marks := SHELL.findall(prompt):
            lines = []
            for n, (kind, raw) in enumerate(shell_marks):
                command = raw.strip()
                shell_input = {"command": command}
                tool_id = f"fake-shell-{n}"
                decision = await self.on_permission("Bash", shell_input, "hook")
                if (
                    kind == "되묻기"
                    and decision.allow
                    and not decision.explicit
                    and req.permission_mode == "auto"
                ):
                    decision = await self.on_permission("Bash", shell_input, "runtime")
                yield RuntimeEvent("tool.started", {"id": tool_id, "tool": "Bash", "input": shell_input})
                yield RuntimeEvent("tool.completed" if decision.allow else "tool.failed", {"id": tool_id})
                lines.append(f"- `{command}`: {'허용되었습니다' if decision.allow else '거부되었습니다'}")
            async for ev in self._stream("셸 명령 요청 결과입니다.\n\n" + "\n".join(lines)):
                yield ev
        elif (m := DELEGATE.search(prompt)) and req.org_tools:
            name = m.group(1).strip()
            tool = next(t for t in req.org_tools if t.name == "delegate_task")
            args = {"assignee": name, "title": "E2E 위임 작업", "brief": "한 문장으로 보고해 주세요."}
            decision = await self.on_permission("mcp__org__delegate_task", args, "hook")
            yield RuntimeEvent(
                "tool.started", {"id": "fake-delegate", "tool": "mcp__org__delegate_task", "input": args}
            )
            report = await tool.handler(args) if decision.allow else "거부됨"
            yield RuntimeEvent("tool.completed", {"id": "fake-delegate"})
            async for ev in self._stream(f"보고를 취합했습니다.\n\n{report}"):
                yield ev
        else:
            first = prompt.strip().splitlines()[-1][:60] if prompt.strip() else ""
            text = f"가짜 런타임 응답입니다: **{first}**\n\n```python\nprint('hello e2e')\n```"
            async for ev in self._stream(text):
                yield ev
        yield RuntimeEvent(
            "turn.completed",
            {
                "session_id": session,
                "is_error": False,
                "cost_usd": 0.0,
                "duration_ms": 10,
                "interrupted": self.interrupted,
            },
        )

    def _design(self) -> dict[str, Any]:
        m = SPEC.search(self.request.prompt)
        spec = json.loads(m.group(1)) if m else None
        if not isinstance(spec, dict):
            return {"reply": "현재 명세를 읽지 못했습니다.", "spec": None}
        if not any(d.get("key") == "e2e" for d in spec.get("departments", [])):
            spec.setdefault("departments", []).append(
                {"key": "e2e", "name": "E2E팀", "description": "", "color": "dept-5"}
            )
            lead = next(a["key"] for a in spec["agents"] if a.get("is_lead"))
            spec["agents"].append(
                {
                    "key": "e2e_analyst",
                    "name": "E2E 분석가",
                    "title": "애널리스트",
                    "department": "e2e",
                    "reports_to": lead,
                    "role": "E2E 테스트용 구성원",
                    "permissions": {"allow_shell": True},
                }
            )  # 권한 확대 제안 → 사용자 수락 필요
        return {
            "reply": "E2E팀과 E2E 분석가를 추가했습니다.",
            "questions": ["몇 명으로 시작할까요?"],
            "spec": spec,
        }

    async def interrupt(self) -> None:
        self.interrupted = True
