from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_org.config import Settings
from ai_org.main import create_app
from tests.test_chat import FakeRuntime, wait_message


@pytest.fixture
def fake() -> FakeRuntime:
    return FakeRuntime()


@pytest.fixture
def api(settings: Settings, fake: FakeRuntime) -> Iterator[TestClient]:
    # 동시 실행 한도 1: 위임자가 슬롯을 내놓지 않으면 교착된다(이 테스트가 그것도 확인한다).
    with TestClient(
        create_app(replace(settings, max_concurrent_runs=1), runtime_for=lambda _id: fake),
        base_url="http://127.0.0.1:8000",
    ) as c:
        yield c


def software_org(api: TestClient) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    org = api.post("/api/v1/organizations/from-template", json={"template_key": "software"}).json()
    return org, {a["name"]: a for a in org["agents"]}


def wait_all_done(api: TestClient, conv_id: str, timeout: float = 8) -> list[dict[str, Any]]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        msgs = api.get(f"/api/v1/conversations/{conv_id}").json()["messages"]
        if all(m["status"] not in ("pending", "streaming") for m in msgs):
            return msgs
        time.sleep(0.05)
    raise AssertionError("runs did not finish")


def test_ceo_delegates_and_receives_report(api: TestClient, fake: FakeRuntime) -> None:
    org, by = software_org(api)
    ceo, qa = by["프로젝트 매니저"], by["QA 엔지니어"]
    fake.scripts[ceo["id"]] = [
        (
            "call",
            "delegate_task",
            {"assignee": "QA 엔지니어", "title": "회귀 테스트", "brief": "테스트를 돌려 보고해"},
        )
    ]
    fake.scripts[qa["id"]] = [("text", "테스트 12개 통과")]
    conv = api.post("/api/v1/conversations", json={"organization_id": org["id"]}).json()
    res = api.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "릴리스 전 점검해 줘"})
    ceo_msg = wait_message(api, conv["id"], res.json()["assistant_message_ids"][0], timeout=8)
    msgs = wait_all_done(api, conv["id"])
    # CEO 실행에만 위임 도구가 있고, 시스템 프롬프트에 위임 가능 대상이 있다.
    ceo_req = next(r for r in fake.requests if r.agent_id == ceo["id"])
    assert {t.name for t in ceo_req.org_tools} == {"delegate_task", "request_review", "run_plan"}
    assert (
        "위임 가능한 구성원" in ceo_req.system_prompt_append and "QA 엔지니어" in ceo_req.system_prompt_append
    )
    qa_req = next(r for r in fake.requests if r.agent_id == qa["id"])
    assert qa_req.org_tools == ()  # QA는 위임 권한이 없다
    assert "[프로젝트 매니저(Project Manager)의 위임]" in qa_req.prompt
    # QA 응답은 같은 대화에 '위임받은' 메시지로 남고, CEO는 보고를 받아 취합한다.
    qa_msg = next(m for m in msgs if m["agent_id"] == qa["id"])
    assert qa_msg["data"]["delegated_by"] == ceo["id"] and qa_msg["task_id"]
    assert (
        "[QA 엔지니어의 보고 — 작업 상태: done]" in ceo_msg["content"]
        and "테스트 12개 통과" in ceo_msg["content"]
    )
    assert ceo_msg["activity"][0]["activity"] == "delegating"
    tasks = api.get("/api/v1/tasks", params={"organization_id": org["id"]}).json()
    assert (
        tasks[0]["title"] == "회귀 테스트"
        and tasks[0]["status"] == "done"
        and tasks[0]["assignee_id"] == qa["id"]
    )


def test_delegation_respects_org_chart(api: TestClient, fake: FakeRuntime) -> None:
    org, by = software_org(api)
    architect = by["시스템 설계"]
    # 설계자의 하위는 프론트·백엔드뿐. QA는 하위도 협업 대상도 아니다.
    fake.scripts[architect["id"]] = [
        ("call", "delegate_task", {"assignee": "QA 엔지니어", "title": "x", "brief": "y"})
    ]
    conv = api.post(
        "/api/v1/conversations",
        json={"organization_id": org["id"], "target_kind": "agent", "target_id": architect["id"]},
    ).json()
    res = api.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "설계해"})
    msg = wait_message(api, conv["id"], res.json()["assistant_message_ids"][0])
    assert "'QA 엔지니어'에게는 위임할 수 없습니다" in msg["content"]
    assert "백엔드 개발자" in msg["content"] and "프론트엔드 개발자" in msg["content"]
    assert api.get("/api/v1/tasks", params={"organization_id": org["id"]}).json() == []


def test_no_tools_without_delegate_permission(api: TestClient, fake: FakeRuntime) -> None:
    org, by = software_org(api)
    qa = by["QA 엔지니어"]
    fake.scripts[qa["id"]] = [("call", "delegate_task", {"assignee": "x", "brief": "y"})]
    conv = api.post(
        "/api/v1/conversations",
        json={"organization_id": org["id"], "target_kind": "agent", "target_id": qa["id"]},
    ).json()
    res = api.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "해"})
    msg = wait_message(api, conv["id"], res.json()["assistant_message_ids"][0])
    assert fake.requests[-1].org_tools == ()
    assert msg["activity"][0]["status"] == "failed"  # 정책 거부(위임 권한 없음)


def test_collaboration_cycle_rejected(api: TestClient, fake: FakeRuntime) -> None:
    org = api.post("/api/v1/organizations", json={"name": "Cycle"}).json()
    ceo = org["agents"][0]
    perms = {**ceo["permissions"], "can_delegate": True}
    a = api.post(
        f"/api/v1/organizations/{org['id']}/agents",
        json={"name": "A", "reports_to_id": ceo["id"], "permissions": perms},
    ).json()
    b = api.post(
        f"/api/v1/organizations/{org['id']}/agents",
        json={"name": "B", "reports_to_id": ceo["id"], "permissions": perms},
    ).json()
    for src, dst in ((a, b), (b, a)):
        api.post(
            f"/api/v1/organizations/{org['id']}/collaborations",
            json={"source_agent_id": src["id"], "target_agent_id": dst["id"], "kind": "consult"},
        )
    fake.scripts[a["id"]] = [("call", "delegate_task", {"assignee": "B", "title": "t", "brief": "b"})]
    fake.scripts[b["id"]] = [("call", "delegate_task", {"assignee": "A", "title": "t", "brief": "back"})]
    conv = api.post(
        "/api/v1/conversations",
        json={"organization_id": org["id"], "target_kind": "agent", "target_id": a["id"]},
    ).json()
    res = api.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "시작"})
    a_msg = wait_message(api, conv["id"], res.json()["assistant_message_ids"][0], timeout=8)
    msgs = wait_all_done(api, conv["id"])
    b_msg = next(m for m in msgs if m["agent_id"] == b["id"])
    assert "위임 순환" in b_msg["content"]
    assert "[B의 보고" in a_msg["content"]


def test_delegation_requires_approval_when_configured(api: TestClient, fake: FakeRuntime) -> None:
    org, by = software_org(api)
    ceo, qa = by["프로젝트 매니저"], by["QA 엔지니어"]
    perms = {**ceo["permissions"], "require_approval": [*ceo["permissions"]["require_approval"], "delegate"]}
    api.patch(f"/api/v1/organizations/{org['id']}/agents/{ceo['id']}", json={"permissions": perms})
    fake.scripts[ceo["id"]] = [
        ("call", "delegate_task", {"assignee": "QA 엔지니어", "title": "t", "brief": "b"})
    ]
    fake.scripts[qa["id"]] = [("text", "ok")]
    conv = api.post("/api/v1/conversations", json={"organization_id": org["id"]}).json()
    api.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "해"})
    deadline = time.time() + 5
    pending: list[dict[str, Any]] = []
    while not pending and time.time() < deadline:
        pending = api.get("/api/v1/approvals", params={"organization_id": org["id"]}).json()
        time.sleep(0.05)
    assert pending and pending[0]["summary"].startswith("mcp__org__delegate_task: QA 엔지니어")
    api.post(f"/api/v1/approvals/{pending[0]['id']}/decision", json={"allow": True})
    msgs = wait_all_done(api, conv["id"])
    assert any(m["agent_id"] == qa["id"] for m in msgs)
