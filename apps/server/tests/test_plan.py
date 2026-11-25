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
from tests.test_delegation import software_org, wait_all_done


@pytest.fixture
def fake() -> FakeRuntime:
    return FakeRuntime()


@pytest.fixture
def api(settings: Settings, fake: FakeRuntime) -> Iterator[TestClient]:
    with TestClient(
        create_app(replace(settings, max_concurrent_runs=2), runtime_for=lambda _id: fake),
        base_url="http://127.0.0.1:8000",
    ) as c:
        yield c


def start(
    api: TestClient, org: dict[str, Any], fake: FakeRuntime, ceo: dict[str, Any], tasks: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    fake.scripts[ceo["id"]] = [("call", "run_plan", {"tasks": tasks})]
    conv = api.post("/api/v1/conversations", json={"organization_id": org["id"]}).json()
    res = api.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "계획대로 진행해"})
    msg = wait_message(api, conv["id"], res.json()["assistant_message_ids"][0], timeout=15)
    return conv, msg


def test_plan_runs_in_dependency_order_and_passes_results(api: TestClient, fake: FakeRuntime) -> None:
    org, by = software_org(api)
    ceo, planner, backend, qa = by["프로젝트 매니저"], by["제품 기획"], by["백엔드 개발자"], by["QA 엔지니어"]
    fake.scripts[planner["id"]] = [("sleep", 0.2), ("text", "요구사항: 로그인 API")]
    fake.scripts[backend["id"]] = [("text", "구현 완료")]
    fake.scripts[qa["id"]] = [("text", "테스트 통과")]
    conv, msg = start(
        api,
        org,
        fake,
        ceo,
        [
            {"key": "spec", "assignee": "제품 기획", "title": "요구사항", "brief": "정리해"},
            {
                "key": "impl",
                "assignee": "백엔드 개발자",
                "title": "구현",
                "brief": "만들어",
                "depends_on": ["spec"],
            },
            {
                "key": "test",
                "assignee": "QA 엔지니어",
                "title": "검증",
                "brief": "테스트해",
                "depends_on": ["impl"],
            },
        ],
    )
    assert "[작업 계획 결과 — 3건]" in msg["content"]
    assert msg["content"].count("— 완료") == 3
    # 선행 결과가 뒤 작업 지시에 붙는다.
    impl_req = next(r for r in fake.requests if r.agent_id == backend["id"])
    assert "[선행 작업 결과]" in impl_req.prompt and "요구사항: 로그인 API" in impl_req.prompt
    # 순서: 기획 → 구현 → 검증
    order = [r.agent_id for r in fake.requests if r.agent_id != ceo["id"]]
    assert order == [planner["id"], backend["id"], qa["id"]]
    tasks = {t["title"]: t for t in api.get("/api/v1/tasks", params={"organization_id": org["id"]}).json()}
    assert {tasks[k]["status"] for k in ("요구사항", "구현", "검증")} == {"done"}
    wait_all_done(api, conv["id"])


def test_review_rejection_triggers_rework_then_approval(api: TestClient, fake: FakeRuntime) -> None:
    org, by = software_org(api)
    ceo, backend, reviewer = by["프로젝트 매니저"], by["백엔드 개발자"], by["코드 리뷰어"]
    fake.queues[backend["id"]] = [[("text", "1차 구현")], [("text", "2차 구현(테스트 추가)")]]
    fake.queues[reviewer["id"]] = [[("text", "[수정 요청] 테스트가 없습니다")], [("text", "[승인] 좋습니다")]]
    _, msg = start(
        api,
        org,
        fake,
        ceo,
        [
            {
                "key": "impl",
                "assignee": "백엔드 개발자",
                "title": "API",
                "brief": "만들어",
                "review_by": "코드 리뷰어",
            },
        ],
    )
    assert "2차 구현(테스트 추가)" in msg["content"] and "(검토 승인: 코드 리뷰어)" in msg["content"]
    review_req = next(r for r in fake.requests if r.agent_id == reviewer["id"])
    assert "[작업 지시(선행 작업 결과 포함)]" in review_req.prompt and "1차 구현" in review_req.prompt
    rework = [r for r in fake.requests if r.agent_id == backend["id"]][1]
    assert "재작업 요청(1회차)" in rework.prompt and "테스트가 없습니다" in rework.prompt


def test_review_never_approved_marks_for_human(api: TestClient, fake: FakeRuntime) -> None:
    org, by = software_org(api)
    ceo, backend, reviewer = by["프로젝트 매니저"], by["백엔드 개발자"], by["코드 리뷰어"]
    fake.scripts[backend["id"]] = [("text", "구현")]
    fake.scripts[reviewer["id"]] = [("text", "[수정 요청] 아직 부족")]
    _, msg = start(
        api,
        org,
        fake,
        ceo,
        [
            {
                "key": "impl",
                "assignee": "백엔드 개발자",
                "title": "API",
                "brief": "만들어",
                "review_by": "코드 리뷰어",
            },
        ],
    )
    assert "— 검토 미승인" in msg["content"]
    assert len([r for r in fake.requests if r.agent_id == backend["id"]]) == 3  # 최초 + 재작업 2회
    task = next(
        t
        for t in api.get("/api/v1/tasks", params={"organization_id": org["id"]}).json()
        if t["title"] == "API"
    )
    assert task["status"] == "review"


def test_independent_tasks_run_in_parallel(api: TestClient, fake: FakeRuntime) -> None:
    org, by = software_org(api)
    ceo, backend, frontend, qa = (
        by["프로젝트 매니저"],
        by["백엔드 개발자"],
        by["프론트엔드 개발자"],
        by["QA 엔지니어"],
    )
    fake.scripts[backend["id"]] = [("sleep", 0.3), ("text", "API 완료")]
    fake.scripts[frontend["id"]] = [("sleep", 0.3), ("text", "화면 완료")]
    fake.scripts[qa["id"]] = [("text", "검증")]
    _, msg = start(
        api,
        org,
        fake,
        ceo,
        [
            {"key": "a", "assignee": "백엔드 개발자", "title": "백엔드", "brief": "b"},
            {"key": "b", "assignee": "프론트엔드 개발자", "title": "프론트", "brief": "f"},
            {
                "key": "c",
                "assignee": "QA 엔지니어",
                "title": "통합 검증",
                "brief": "q",
                "depends_on": ["a", "b"],
            },
        ],
    )
    starts = {r.agent_id: i for i, r in enumerate(fake.requests)}
    assert abs(starts[backend["id"]] - starts[frontend["id"]]) == 1  # 독립 작업은 함께 시작
    assert starts[qa["id"]] > max(starts[backend["id"]], starts[frontend["id"]])
    assert msg["content"].count("— 완료") == 3


def test_failed_dependency_cancels_dependents(api: TestClient, fake: FakeRuntime) -> None:
    org, by = software_org(api)
    ceo, backend, qa = by["프로젝트 매니저"], by["백엔드 개발자"], by["QA 엔지니어"]
    fake.scripts[backend["id"]] = [("fail", "빌드 실패")]
    fake.scripts[qa["id"]] = [("text", "검증")]
    _, msg = start(
        api,
        org,
        fake,
        ceo,
        [
            {"key": "a", "assignee": "백엔드 개발자", "title": "구현", "brief": "b"},
            {"key": "c", "assignee": "QA 엔지니어", "title": "검증", "brief": "q", "depends_on": ["a"]},
        ],
    )
    assert "구현 (백엔드 개발자) — 실패" in msg["content"] and "검증 (QA 엔지니어) — 취소" in msg["content"]
    assert all(r.agent_id != qa["id"] for r in fake.requests)
    tasks = {
        t["title"]: t["status"]
        for t in api.get("/api/v1/tasks", params={"organization_id": org["id"]}).json()
    }
    assert tasks == {"구현": "failed", "검증": "cancelled"}


@pytest.mark.parametrize(
    ("tasks", "error"),
    [
        (
            [
                {"key": "a", "assignee": "백엔드 개발자", "title": "t", "brief": "b", "depends_on": ["b"]},
                {"key": "b", "assignee": "QA 엔지니어", "title": "t", "brief": "b", "depends_on": ["a"]},
            ],
            "순환",
        ),
        ([{"key": "a", "assignee": "없는 사람", "title": "t", "brief": "b"}], "위임할 수 없습니다"),
        (
            [{"key": "a", "assignee": "QA 엔지니어", "title": "t", "brief": "b", "depends_on": ["zzz"]}],
            "없는 선행 작업",
        ),
        (
            [{"key": "a", "assignee": "QA 엔지니어", "title": "t", "brief": "b", "review_by": "QA 엔지니어"}],
            "달라야",
        ),
    ],
)
def test_invalid_plans_rejected(
    api: TestClient, fake: FakeRuntime, tasks: list[dict[str, Any]], error: str
) -> None:
    org, by = software_org(api)
    _, msg = start(api, org, fake, by["프로젝트 매니저"], tasks)
    assert error in msg["content"]
    assert api.get("/api/v1/tasks", params={"organization_id": org["id"]}).json() == []
    time.sleep(0)
