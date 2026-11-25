"""조직·에이전트·컨텍스트 → 시스템 프롬프트 추가분과 사용자 프롬프트.

시스템 프롬프트는 Claude Code 기본 프롬프트(preset) 뒤에 덧붙인다. 컨텍스트는 내용이 아니라 위치를 알려 주고,
에이전트가 자기 권한 안에서 도구로 읽게 한다(권한 우회 방지).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ai_org.models import Agent, Attachment, Department, Organization


@dataclass
class ContextLines:
    project: str | None = None
    paths: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    tasks: list[tuple[str, str]] = field(default_factory=list)  # (제목, 결과 발췌)
    github: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)


def roster(org: Organization, agents: Sequence[Agent], depts: Sequence[Department]) -> str:
    dept_names = {d.id: d.name for d in depts}
    names = {a.id: a.name for a in agents}
    lines = []
    for a in agents:
        if not a.enabled:
            continue
        parts = [f"- {a.name}"]
        if a.title:
            parts.append(f"({a.title})")
        if a.department_id:
            parts.append(f"[{dept_names.get(a.department_id, '')}]")
        if a.reports_to_id:
            parts.append(f"→ 보고 대상: {names.get(a.reports_to_id, '')}")
        if a.role:
            parts.append(f": {a.role}")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def system_append(
    org: Organization,
    agent: Agent,
    agents: Sequence[Agent],
    depts: Sequence[Department],
    scope: str,
    team: Department | None = None,
) -> str:
    dept = next((d.name for d in depts if d.id == agent.department_id), None)
    out = [
        "# AI 조직 구성원 지침",
        f"당신은 AI 조직 '{org.name}'의 구성원 '{agent.name}'입니다.",
    ]
    if agent.title:
        out.append(f"직책: {agent.title}")
    if dept:
        out.append(f"부서: {dept}")
    if agent.role:
        out.append(f"역할: {agent.role}")
    if agent.responsibilities:
        out.append("책임: " + ", ".join(agent.responsibilities))
    if agent.expertise:
        out.append("전문 분야: " + ", ".join(agent.expertise))
    if org.mission:
        out.append(f"조직 목표: {org.mission}")
    if org.base_instructions:
        out += ["", "## 조직 기본 지침", org.base_instructions]
    if agent.instructions:
        out += ["", "## 개인 지침", agent.instructions]
    if scope == "org":
        out += [
            "",
            "## 조직 전체 대화",
            "사용자는 조직 전체(CEO)에게 말하고 있습니다. 요청을 분석하고,",
            "어떤 구성원이 무엇을 맡으면 좋을지 분배 계획을 제시한 뒤",
            "당신이 직접 할 수 있는 부분을 수행하세요.",
            "다른 구성원에게 업무를 넘기는 자동 위임은 아직 플랫폼이 지원하지 않습니다. 필요한 위임은",
            "사용자에게 `/delegate @이름 업무` 명령으로 제안하세요.",
            "",
            "조직 구성:",
            roster(org, agents, depts),
        ]
    elif scope == "team" and team is not None:
        members = [a for a in agents if a.department_id == team.id]
        out += [
            "",
            f"## 팀 대화: {team.name}",
            "사용자는 이 팀 전체에게 말하고 있고, 당신이 팀을 대표해 답합니다. 팀원:",
            roster(org, members, depts),
        ]
    out += ["", "사용자의 언어로 답하세요. 하지 않은 일을 했다고 말하지 마세요."]
    return "\n".join(out)


def user_prompt(
    message: str, ctx: ContextLines, attachments: Sequence[Attachment], broadcast: bool = False
) -> str:
    pre: list[str] = []
    if broadcast:
        pre.append("[조직 전체 공지] 아래 메시지는 조직 전체(@All)에 보낸 것입니다.")
    if ctx.project:
        pre.append(f"작업 프로젝트: {ctx.project}")
    if ctx.paths:
        pre.append("참고할 경로(필요하면 도구로 읽으세요):\n" + "\n".join(f"- {p}" for p in ctx.paths))
    if attachments:
        pre.append(
            "첨부 파일(Read 도구로 열 수 있습니다):\n"
            + "\n".join(f"- {a.stored_path} ({a.media_type}, {a.size} bytes)" for a in attachments)
        )
    if ctx.agents:
        pre.append("관련 구성원: " + ", ".join(ctx.agents))
    for title, result in ctx.tasks:
        pre.append(f"이전 작업 결과 — {title}:\n{result}")
    if ctx.github:
        pre.append("관련 GitHub 저장소: " + ", ".join(ctx.github))
    if ctx.capabilities:
        pre.append("사용자가 언급한 기능: " + ", ".join(ctx.capabilities))
    if not pre:
        return message
    return "\n\n".join(["<context>", *pre, "</context>", message])
