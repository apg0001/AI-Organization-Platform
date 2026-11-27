"""에이전트 model 값 검증(#87): 형태 검증, null로 되돌리기, 저장된 잘못된 값의 관용 처리, 실행 전달."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai_org.config import Settings
from ai_org.main import create_app
from ai_org.models import Agent
from ai_org.schemas import AgentPatch, clean_model, stored_model
from ai_org.spec import SpecAgent
from tests.test_chat import FakeRuntime, setup_org, wait_message

VALID = ["opus", "sonnet", "haiku", "claude-sonnet-5-5", "opus[1m]", "claude-opus-5-5:latest", "a", "x" * 100]
INVALID = [
    "--dangerously-skip-permissions",
    "-m",
    "-",
    "opus --permission-mode bypassPermissions",
    "claude sonnet",
    "opus\nsonnet",
    "opus\tx",
    "opus\x00",
    "opus\x1b[0m",
    '"opus"',
    "'opus'",
    "opus;ls",
    "opus$(id)",
    "opus`id`",
    "opus/../x",
    "opus=x",
    "모델",
    "x" * 101,
    123,
    ["opus"],
]


@pytest.fixture
def fake() -> FakeRuntime:
    return FakeRuntime()


@pytest.fixture
def chat(settings: Settings, fake: FakeRuntime) -> Iterator[TestClient]:
    with TestClient(
        create_app(settings, runtime_for=lambda _id: fake), base_url="http://127.0.0.1:8000"
    ) as c:
        yield c


def agent_url(org: dict[str, Any], agent: dict[str, Any]) -> str:
    return f"/api/v1/organizations/{org['id']}/agents/{agent['id']}"


@pytest.mark.parametrize("value", VALID)
def test_valid_model_names(value: str) -> None:
    assert clean_model(value) == value
    assert AgentPatch(model=f"  {value} ").model == value
    assert SpecAgent(key="a", name="A", model=value).model == value


def test_blank_model_means_default() -> None:
    for value in (None, "", "   "):
        assert clean_model(value) is None
        assert AgentPatch(model=value).model is None


@pytest.mark.parametrize("value", INVALID)
def test_invalid_model_names(value: Any) -> None:
    with pytest.raises(ValueError):
        clean_model(value)
    with pytest.raises(ValidationError):
        AgentPatch(model=value)
    with pytest.raises(ValidationError):
        SpecAgent(key="a", name="A", model=value)
    assert stored_model(value) is None  # 저장돼 있던 값이면 기본 모델로 본다


def test_patch_model_set_reset_and_omit(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    ceo = next(a for a in org["agents"] if a["is_lead"])
    res = chat.patch(agent_url(org, ceo), json={"model": " claude-sonnet-5-5 "})
    assert res.status_code == 200 and res.json()["model"] == "claude-sonnet-5-5"
    # 다른 필드만 보내면 model은 그대로다(생략 ≠ null).
    res = chat.patch(agent_url(org, ceo), json={"title": "대표"})
    assert res.json()["model"] == "claude-sonnet-5-5"
    # 실행 요청에 그대로 전달된다.
    reply = chat.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "안녕"}).json()
    wait_message(chat, conv["id"], reply["assistant_message_ids"][0])
    assert fake.requests[-1].model == "claude-sonnet-5-5"
    # null을 명시하면 기본값으로 되돌아간다.
    res = chat.patch(agent_url(org, ceo), json={"model": None})
    assert res.status_code == 200 and res.json()["model"] is None
    assert chat.get(f"/api/v1/agents/{ceo['id']}").json()["model"] is None
    reply = chat.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "다시"}).json()
    wait_message(chat, conv["id"], reply["assistant_message_ids"][0])
    assert fake.requests[-1].model is None
    # 빈 문자열도 기본값이다.
    chat.patch(agent_url(org, ceo), json={"model": "opus"})
    assert chat.patch(agent_url(org, ceo), json={"model": ""}).json()["model"] is None


@pytest.mark.parametrize("value", [v for v in INVALID if isinstance(v, str)])
def test_api_rejects_invalid_model_with_422(chat: TestClient, value: str) -> None:
    org, _ = setup_org(chat)
    ceo = next(a for a in org["agents"] if a["is_lead"])
    chat.patch(agent_url(org, ceo), json={"model": "opus"})
    res = chat.patch(agent_url(org, ceo), json={"model": value})
    assert res.status_code == 422
    detail = res.json()["detail"][0]
    assert detail["loc"][-1] == "model" and "모델 이름" in detail["msg"]
    assert chat.get(f"/api/v1/agents/{ceo['id']}").json()["model"] == "opus"
    created = chat.post(
        f"/api/v1/organizations/{org['id']}/agents", json={"name": "새 구성원", "model": value}
    )
    assert created.status_code == 422


def test_stored_invalid_model_does_not_break_read_or_run(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    ceo = next(a for a in org["agents"] if a["is_lead"])
    with chat.app.state.runs.factory() as db:  # type: ignore[attr-defined]
        agent = db.get(Agent, ceo["id"])
        agent.model = "--dangerously-skip-permissions"
        db.commit()
    assert chat.get(f"/api/v1/agents/{ceo['id']}").json()["model"] is None
    res = chat.get(f"/api/v1/organizations/{org['id']}")
    assert res.status_code == 200
    assert next(a for a in res.json()["agents"] if a["id"] == ceo["id"])["model"] is None
    reply = chat.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "안녕"}).json()
    msg = wait_message(chat, conv["id"], reply["assistant_message_ids"][0])
    assert msg["status"] == "done" and fake.requests[-1].model is None  # 옵션으로 넘어가지 않는다
    # 기존 조직에서 설계 초안을 만드는 경로도 깨지지 않는다.
    design = chat.post("/api/v1/designs", json={"organization_id": org["id"]})
    assert design.status_code in (200, 201)
    spec_agent = next(a for a in design.json()["spec"]["agents"] if a["key"] == ceo["id"])
    assert spec_agent["model"] is None


def test_design_spec_edit_validates_model(chat: TestClient) -> None:
    d = chat.post("/api/v1/designs", json={}).json()
    spec = d["spec"]
    spec["agents"][0]["model"] = "--print"
    assert chat.put(f"/api/v1/designs/{d['id']}/spec", json={"spec": spec}).status_code == 422
    spec["agents"][0]["model"] = "opus[1m]"
    res = chat.put(f"/api/v1/designs/{d['id']}/spec", json={"spec": spec})
    assert res.status_code == 200 and res.json()["spec"]["agents"][0]["model"] == "opus[1m]"
