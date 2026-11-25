"""도메인 모델(SQLite).

조직 관리(우리 시스템)와 실행(Claude Code 런타임)을 분리한다:
- Organization / Department / Agent / Collaboration: 사용자가 설계하는 조직. 런타임과 무관하다.
- Project / ProjectRoot: 로컬 프로젝트 레지스트리.
- Task / Approval / ActivityEvent / RuntimeSession: 오케스트레이션·런타임이 채우는 실행 기록(Phase 3·5).

JSON 열은 구조가 아직 바뀌는 정책 값에만 쓴다. 관계·조회 기준이 되는 값은 열로 둔다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_org.db import Base, UTCDateTime


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    mission: Mapped[str] = mapped_column(Text, default="")
    base_instructions: Mapped[str] = mapped_column(Text, default="")
    # 업무 정책(예: 승인 필요 작업, 최대 동시 실행 수). 스키마는 schemas.OrgPolicy.
    policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    template_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    default_project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )

    departments: Mapped[list[Department]] = relationship(
        back_populates="organization", cascade="all, delete-orphan", order_by="Department.sort_order"
    )
    agents: Mapped[list[Agent]] = relationship(
        back_populates="organization", cascade="all, delete-orphan", foreign_keys="Agent.organization_id"
    )
    collaborations: Mapped[list[Collaboration]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class Department(TimestampMixin, Base):
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    # 디자인 토큰 이름(dept-1 … dept-8). 화면은 토큰을 색으로 바꾼다.
    color: Mapped[str] = mapped_column(String(20), default="dept-1")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    organization: Mapped[Organization] = relationship(back_populates="departments")


class Agent(TimestampMixin, Base):
    """조직의 구성원. 실행 세션이 아니라 '직원' 정의다.

    reports_to_id는 조직도상의 상하 관계다. 실제 업무 전달 관계는 Collaboration과 Task가 기록한다.
    """

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    reports_to_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(80), default="")
    role: Mapped[str] = mapped_column(Text, default="")
    responsibilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    expertise: Mapped[list[str]] = mapped_column(JSON, default=list)
    instructions: Mapped[str] = mapped_column(Text, default="")
    is_lead: Mapped[bool] = mapped_column(Boolean, default=False)  # 조직의 CEO(업무 접수 창구)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # 실행 설정. runtime은 확장 지점(현재 claude-code만).
    runtime: Mapped[str] = mapped_column(String(40), default="claude-code")
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # 허용 목록(Capability ID). 자동 선택은 이 목록 안에서만 일어난다.
    allowed_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_mcp_servers: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_plugins: Mapped[list[str]] = mapped_column(JSON, default=list)
    # 권한 정책. 스키마는 schemas.AgentPermissions.
    permissions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # 관측 상태(런타임이 갱신). Phase 3 전에는 항상 idle.
    status: Mapped[str] = mapped_column(String(20), default="idle")

    # 조직도 캔버스 위치.
    pos_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    pos_y: Mapped[float | None] = mapped_column(Float, nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="agents", foreign_keys=[organization_id])


class Collaboration(TimestampMixin, Base):
    """조직도 상하 관계와 별개인 협업 관계(예: 시장 조사 → 사업 모델 '결과 전달')."""

    __tablename__ = "collaborations"
    __table_args__ = (UniqueConstraint("source_agent_id", "target_agent_id", "kind"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    source_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    target_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    # handoff(결과 전달) | review(검토 요청) | consult(자문)
    kind: Mapped[str] = mapped_column(String(20), default="handoff")
    label: Mapped[str] = mapped_column(String(120), default="")

    organization: Mapped[Organization] = relationship(back_populates="collaborations")


class ProjectRoot(TimestampMixin, Base):
    """사용자가 등록한 탐색 경로. 백엔드는 등록된 경로 아래만 탐색·접근한다."""

    __tablename__ = "project_roots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    path: Mapped[str] = mapped_column(Text, unique=True)
    max_depth: Mapped[int] = mapped_column(Integer, default=2)


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    path: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(40), default="unknown")  # 감지한 유형(node, python, go …)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    last_opened_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Task(TimestampMixin, Base):
    """업무 단위(Phase 5). 위임은 parent_id 트리로, 담당은 assignee_id로 기록한다."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    assignee_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    requested_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )  # None = 사용자
    title: Mapped[str] = mapped_column(String(200))
    brief: Mapped[str] = mapped_column(Text, default="")
    # queued | running | waiting | review | done | failed | cancelled
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=2)
    result: Mapped[str] = mapped_column(Text, default="")
    depends_on: Mapped[list[str]] = mapped_column(JSON, default=list)


class RuntimeSession(TimestampMixin, Base):
    """에이전트 한 명의 Claude Code 세션(Phase 3). session_id는 Claude Code가 발급한 값이다."""

    __tablename__ = "runtime_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    runtime: Mapped[str] = mapped_column(String(40), default="claude-code")
    external_session_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cwd: Mapped[str] = mapped_column(Text, default="")
    # starting | running | waiting_approval | ended | failed | interrupted
    state: Mapped[str] = mapped_column(String(20), default="starting", index=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Approval(TimestampMixin, Base):
    """사용자 승인 요청(Phase 3). 도구 사용 권한·위험 작업·계획 확인."""

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("runtime_sessions.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(20), default="tool")  # tool | plan | question
    summary: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # pending | approved | denied | expired
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class ActivityEvent(Base):
    """조직 활동 기록(감사 로그 겸 타임라인). 조직 설계 변경도 기록한다."""

    __tablename__ = "activity_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))  # org.created, agent.updated, task.delegated …
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)


class Conversation(TimestampMixin, Base):
    """채팅 대화. 대상(target)은 에이전트·팀(부서)·조직(CEO) 중 하나다.

    context: 사용자가 첨부한 컨텍스트 항목 목록(schemas.ContextItem). 전송 시 서버가 다시 검증한다.
    """

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    target_kind: Mapped[str] = mapped_column(String(10), default="org")  # org | team | agent
    target_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), default="새 대화")
    context: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class ChatMessage(Base):
    """대화 메시지. role=command는 슬래시 명령 결과(구조화 데이터)다.

    activity: 이 응답을 만드는 동안의 도구 사용 요약(도구 이름·짧은 대상). 원문 출력은 저장하지 않는다.
    """

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(12))  # user | assistant | command | system
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    content: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # command 결과·첨부·멘션
    activity: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # pending | streaming | done | error | interrupted
    status: Mapped[str] = mapped_column(String(12), default="done")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(80), nullable=True)  # Claude Code 세션 ID
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)


class AgentThread(Base):
    """(대화, 에이전트)별 Claude Code 세션 ID. 다음 턴에 resume으로 이어 간다."""

    __tablename__ = "agent_threads"
    __table_args__ = (UniqueConstraint("conversation_id", "agent_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    session_id: Mapped[str] = mapped_column(String(80))
    cwd: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class Attachment(Base):
    """업로드 파일. 실제 파일은 <home>/uploads/<id>/ 에 0600으로 저장한다."""

    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    stored_path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class OrgDesign(TimestampMixin, Base):
    """조직 설계 초안(설계 모드). spec이 대화·조직도·검토 화면이 공유하는 단일 상태다.

    organization_id가 없으면 새 조직 설계, 있으면 기존 조직 변경안이다.
    status: draft | applied | discarded
    """

    __tablename__ = "org_designs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    origin: Mapped[str] = mapped_column(
        String(40), default="blank"
    )  # blank | template:<id> | org | revision:<id>
    spec: Mapped[dict[str, Any]] = mapped_column(JSON)
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    notes: Mapped[list[str]] = mapped_column(JSON, default=list)
    designer_session_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="draft")
    busy: Mapped[bool] = mapped_column(Boolean, default=False)


class OrgRevision(Base):
    """적용된 조직 구성 스냅샷(변경 이력·복원용)."""

    __tablename__ = "org_revisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    spec: Mapped[dict[str, Any]] = mapped_column(JSON)
    summary: Mapped[list[str]] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(60), default="design")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)


class User(Base):
    """앱 로그인 계정(로컬). Claude Code 인증과 무관하다. 비밀번호는 scrypt 해시만 저장한다."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(40), unique=True)
    display_name: Mapped[str] = mapped_column(String(80), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class AuthSession(Base):
    """로그인 세션. 쿠키의 토큰 원문은 저장하지 않고 SHA-256 해시만 저장한다."""

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
