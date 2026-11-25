from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_org.config import Settings
from ai_org.main import create_app
from tests.test_chat import FakeRuntime


class DesignerRuntime(FakeRuntime):
    """설계 담당자 응답을 흉내 낸다: structured_output으로 명세를 돌려준다."""

    def __init__(self) -> None:
        super().__init__()
        self.output: dict[str, Any] | None = None

    def start(self, request: Any, on_permission: Any) -> Any:
        self.requests.append(request)
        output = self.output

        class Run:
            async def events(self) -> Any:
                from ai_org.runtime.base import RuntimeEvent

                yield RuntimeEvent(
                    "turn.completed", {"session_id": "design-sess", "structured_output": output}
                )

            async def interrupt(self) -> None:
                return None

        return Run()


@pytest.fixture
def designer() -> DesignerRuntime:
    return DesignerRuntime()


@pytest.fixture
def api(settings: Settings, designer: DesignerRuntime) -> Iterator[TestClient]:
    with TestClient(
        create_app(settings, runtime_for=lambda _id: designer), base_url="http://127.0.0.1:8000"
    ) as c:
        yield c


def wait_idle(api: TestClient, design_id: str) -> dict[str, Any]:
    for _ in range(100):
        d = api.get(f"/api/v1/designs/{design_id}").json()
        if not d["busy"]:
            return d
        time.sleep(0.05)
    raise AssertionError("designer did not finish")


def test_template_design_preview_then_apply(api: TestClient) -> None:
    d = api.post("/api/v1/designs", json={"template_id": "research", "name": "자율운항 연구실"}).json()
    assert d["spec"]["name"] == "자율운항 연구실" and d["origin"] == "template:research@1.0.0"
    assert api.get("/api/v1/organizations").json() == []  # 적용 전에는 조직이 없다
    recs = {(r["kind"], r["name"]): r["status"] for r in d["recommendations"]}
    assert recs[("skill", "research")] == "install_required"  # 테스트 환경엔 설치된 Skill이 없다
    res = api.post(f"/api/v1/designs/{d['id']}/apply", json={}).json()
    org = api.get(f"/api/v1/organizations/{res['organization_id']}").json()
    assert len(org["agents"]) == 7 and len(org["departments"]) == 3
    assert api.post(f"/api/v1/designs/{d['id']}/apply", json={}).status_code == 409


def test_designer_conversation_updates_single_spec(api: TestClient, designer: DesignerRuntime) -> None:
    d = api.post("/api/v1/designs", json={}).json()
    spec = d["spec"]
    spec["departments"] = [{"key": "data", "name": "데이터팀"}]
    spec["agents"].append(
        {
            "key": "lidar",
            "name": "LiDAR 분석",
            "department": "data",
            "reports_to": "ceo",
            "permissions": {"allow_shell": True, "allow_file_delete": True, "require_approval": []},
            "allowed_skills": ["skill:user:hack"],
            "recommended_skills": ["research"],
        }
    )
    designer.output = {
        "reply": "데이터팀을 만들었습니다.",
        "questions": ["몇 명으로 시작할까요?"],
        "spec": spec,
    }
    assert (
        api.post(
            f"/api/v1/designs/{d['id']}/messages", json={"content": "LiDAR 분석 팀을 만들어 줘"}
        ).status_code
        == 202
    )
    d = wait_idle(api, d["id"])
    agent = next(a for a in d["spec"]["agents"] if a["key"] == "lidar")
    # AI는 권한을 넓히거나 실제 허용 목록을 바꿀 수 없다: 제안으로만 남는다.
    assert agent["permissions"]["allow_shell"] is False
    assert agent["permission_suggestion"]["allow_shell"] is True
    assert agent["allowed_skills"] == []
    last = d["messages"][-1]
    assert last["role"] == "designer" and "에이전트 추가: LiDAR 분석" in last["changes"]
    assert last["questions"] == ["몇 명으로 시작할까요?"]
    # 설계 담당자는 도구 없이, 구조화 출력으로만 실행된다.
    req = designer.requests[-1]
    assert req.tools == () and req.output_schema is not None and req.setting_sources == ()
    assert '"lidar"' not in req.prompt  # 이번 턴의 현재 명세에는 아직 없다
    # 사용자가 권한 제안을 명시적으로 수락한다.
    d = api.post(f"/api/v1/designs/{d['id']}/accept-permissions/lidar").json()
    agent = next(a for a in d["spec"]["agents"] if a["key"] == "lidar")
    assert agent["permissions"]["allow_shell"] is True and agent["permission_suggestion"] is None
    # 다음 턴은 같은 설계 세션을 이어 가고, 현재 명세(조직도 편집 포함)를 받는다.
    designer.output = {"reply": "질문만 드립니다.", "spec": None}
    api.post(f"/api/v1/designs/{d['id']}/messages", json={"content": "좋아"})
    wait_idle(api, d["id"])
    assert designer.requests[-1].resume_session_id == "design-sess"
    assert '"lidar"' in designer.requests[-1].prompt


def test_invalid_ai_spec_is_rejected(api: TestClient, designer: DesignerRuntime) -> None:
    d = api.post("/api/v1/designs", json={}).json()
    bad = {**d["spec"], "agents": [{**d["spec"]["agents"][0], "is_lead": False}]}
    designer.output = {"reply": "x", "spec": bad}
    api.post(f"/api/v1/designs/{d['id']}/messages", json={"content": "x"})
    d2 = wait_idle(api, d["id"])
    assert d2["spec"] == d["spec"] and "올바르지 않아" in d2["messages"][-1]["error"]


def test_direct_edit_validation_and_history_restore(api: TestClient) -> None:
    org = api.post("/api/v1/organizations/from-template", json={"template_key": "personal"}).json()
    d = api.post("/api/v1/designs", json={"organization_id": org["id"]}).json()
    spec = d["spec"]
    cycle = {
        **spec,
        "agents": [
            {**a, "reports_to": spec["agents"][1]["key"]} if a["is_lead"] else a for a in spec["agents"]
        ],
    }
    assert api.put(f"/api/v1/designs/{d['id']}/spec", json={"spec": cycle}).status_code == 422
    removed = spec["agents"][-1]
    spec["agents"] = spec["agents"][:-1]
    spec["departments"].append({"key": "new", "name": "마케팅팀"})
    d = api.put(f"/api/v1/designs/{d['id']}/spec", json={"spec": spec}).json()
    assert d["messages"][-1]["role"] == "edit"
    res = api.post(f"/api/v1/designs/{d['id']}/apply", json={}).json()
    assert f"에이전트 삭제: {removed['name']}" in res["changes"] and "부서 추가: 마케팅팀" in res["changes"]
    after = api.get(f"/api/v1/organizations/{org['id']}").json()
    assert len(after["agents"]) == len(org["agents"]) - 1
    revisions = api.get(f"/api/v1/organizations/{org['id']}/revisions").json()
    assert len(revisions) == 2
    restore = api.post(f"/api/v1/organizations/{org['id']}/revisions/{revisions[1]['id']}/restore").json()
    assert restore["status"] == "draft" and len(restore["spec"]["agents"]) == len(org["agents"])
    api.post(f"/api/v1/designs/{restore['id']}/apply", json={})
    assert len(api.get(f"/api/v1/organizations/{org['id']}").json()["agents"]) == len(org["agents"])


def test_designer_permission_allows_only_structured_output() -> None:
    import asyncio

    from ai_org.api.designs import _designer_permission

    assert asyncio.run(_designer_permission("StructuredOutput", {})).allow
    assert not asyncio.run(_designer_permission("Bash", {"command": "ls"})).allow
    assert not asyncio.run(_designer_permission("Read", {"file_path": "/etc/passwd"})).allow
