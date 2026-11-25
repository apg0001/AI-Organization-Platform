"""런타임 계약. 오케스트레이터는 이 인터페이스만 안다(Claude Code 외 런타임 추가 시 구현체만 늘린다)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from ai_org.schemas import RuntimeInfo

RuntimeEventType = Literal[
    "session.started",  # 런타임 세션 ID 확보
    "message.delta",  # 부분 텍스트(스트리밍)
    "message",  # 완성된 어시스턴트 텍스트 블록
    "tool.started",
    "tool.completed",
    "tool.failed",
    "turn.completed",  # 결과·비용·소요 시간
    "error",
]


@dataclass(frozen=True)
class RunRequest:
    """에이전트 한 번의 실행 요청. 조직·정책에서 계산한 값만 담는다(런타임은 정책을 해석하지 않는다)."""

    agent_id: str
    prompt: str
    cwd: Path
    system_prompt_append: str = ""
    model: str | None = None
    allowed_tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    permission_mode: Literal["default", "acceptEdits", "plan"] = "default"
    add_dirs: tuple[Path, ...] = ()
    skills: tuple[str, ...] = ()
    resume_session_id: str | None = None
    max_turns: int | None = None
    approval_timeout_s: float = 900
    # None이면 Claude Code 기본 도구, ()이면 도구 없음(조직 설계 담당자처럼 대화만 하는 실행).
    tools: tuple[str, ...] | None = None
    # 구조화 출력(JSON 스키마). 결과는 turn.completed의 structured_output으로 온다.
    output_schema: dict[str, Any] | None = None
    system_prompt: str | None = None  # 지정하면 Claude Code 기본 프롬프트 대신 이것만 쓴다.
    # 읽을 Claude Code 설정 범위. 기본은 프로젝트 설정만(사용자 전역 allow 규칙이 승인을 건너뛰지 않게).
    setting_sources: tuple[str, ...] = ("project",)
    # 허용된 MCP 서버 설정({이름: 설정}). strict 모드라 여기 없는 서버는 붙지 않는다.
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    plugin_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeEvent:
    type: RuntimeEventType
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PermissionDecision:
    allow: bool
    message: str = ""


# 도구 이름과 입력을 받아 허용 여부를 돌려준다. 사용자 승인을 기다리는 동안 await가 끝나지 않는다.
PermissionCallback = Callable[[str, dict[str, Any]], Awaitable[PermissionDecision]]


class RunHandle(Protocol):
    def events(self) -> AsyncIterator[RuntimeEvent]: ...

    async def interrupt(self) -> None: ...


class AgentRuntime(Protocol):
    id: str
    name: str

    def detect(self) -> RuntimeInfo:
        """설치·버전 확인. 부작용이 없어야 한다."""
        ...

    def start(self, request: RunRequest, on_permission: PermissionCallback) -> RunHandle:
        """실행 핸들을 만든다. 실제 프로세스는 events()를 순회할 때 시작된다."""
        ...
