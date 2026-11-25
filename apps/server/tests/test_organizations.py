from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_org_starts_with_single_ceo(client: TestClient) -> None:
    res = client.post("/api/v1/organizations", json={"name": "Acme"})
    assert res.status_code == 201
    org = res.json()
    assert [a["name"] for a in org["agents"]] == ["CEO"]
    assert org["agents"][0]["is_lead"] is True
    assert org["agents"][0]["status"] == "idle"


def test_templates_create_full_org(client: TestClient) -> None:
    keys = [t["template_id"] for t in client.get("/api/v1/templates").json()]
    assert keys == ["business", "marketing", "personal", "research", "software", "university"]
    org = client.post("/api/v1/organizations/from-template", json={"template_key": "software"}).json()
    assert len(org["departments"]) == 4
    leads = [a for a in org["agents"] if a["is_lead"]]
    assert len(leads) == 1
    by_id = {a["id"]: a for a in org["agents"]}
    # 모든 에이전트는 CEO까지 상위 체인이 이어진다.
    for agent in org["agents"]:
        cursor = agent
        hops = 0
        while cursor["reports_to_id"]:
            cursor = by_id[cursor["reports_to_id"]]
            hops += 1
            assert hops < 10
        assert cursor["is_lead"]
    assert len(org["collaborations"]) == 5
    assert client.get(f"/api/v1/organizations/{org['id']}/revisions").json()[0]["agent_count"] == 8


def test_reporting_cycle_rejected(client: TestClient) -> None:
    org = client.post("/api/v1/organizations", json={"name": "Acme"}).json()
    ceo = org["agents"][0]
    a = client.post(
        f"/api/v1/organizations/{org['id']}/agents", json={"name": "A", "reports_to_id": ceo["id"]}
    ).json()
    b = client.post(
        f"/api/v1/organizations/{org['id']}/agents", json={"name": "B", "reports_to_id": a["id"]}
    ).json()
    res = client.patch(f"/api/v1/organizations/{org['id']}/agents/{a['id']}", json={"reports_to_id": b["id"]})
    assert res.status_code == 422
    res = client.patch(f"/api/v1/organizations/{org['id']}/agents/{a['id']}", json={"reports_to_id": a["id"]})
    assert res.status_code == 422


def test_delete_agent_reattaches_reports(client: TestClient) -> None:
    org = client.post("/api/v1/organizations", json={"name": "Acme"}).json()
    ceo = org["agents"][0]
    mid = client.post(
        f"/api/v1/organizations/{org['id']}/agents", json={"name": "Mid", "reports_to_id": ceo["id"]}
    ).json()
    leaf = client.post(
        f"/api/v1/organizations/{org['id']}/agents", json={"name": "Leaf", "reports_to_id": mid["id"]}
    ).json()
    assert client.delete(f"/api/v1/organizations/{org['id']}/agents/{mid['id']}").status_code == 204
    assert client.get(f"/api/v1/agents/{leaf['id']}").json()["reports_to_id"] == ceo["id"]


def test_single_lead_enforced(client: TestClient) -> None:
    org = client.post("/api/v1/organizations", json={"name": "Acme"}).json()
    new = client.post(
        f"/api/v1/organizations/{org['id']}/agents", json={"name": "COO", "is_lead": True}
    ).json()
    full = client.get(f"/api/v1/organizations/{org['id']}").json()
    assert [a["id"] for a in full["agents"] if a["is_lead"]] == [new["id"]]


def test_cross_org_references_rejected(client: TestClient) -> None:
    one = client.post("/api/v1/organizations", json={"name": "One"}).json()
    two = client.post("/api/v1/organizations", json={"name": "Two"}).json()
    foreign = two["agents"][0]["id"]
    res = client.post(
        f"/api/v1/organizations/{one['id']}/agents", json={"name": "X", "reports_to_id": foreign}
    )
    assert res.status_code == 404
    res = client.post(
        f"/api/v1/organizations/{one['id']}/collaborations",
        json={"source_agent_id": one["agents"][0]["id"], "target_agent_id": foreign},
    )
    assert res.status_code == 404


def test_collaboration_and_layout(client: TestClient) -> None:
    org = client.post("/api/v1/organizations", json={"name": "Acme"}).json()
    ceo = org["agents"][0]
    a = client.post(f"/api/v1/organizations/{org['id']}/agents", json={"name": "A"}).json()
    body = {"source_agent_id": a["id"], "target_agent_id": ceo["id"], "kind": "review", "label": "검토"}
    assert client.post(f"/api/v1/organizations/{org['id']}/collaborations", json=body).status_code == 201
    assert client.post(f"/api/v1/organizations/{org['id']}/collaborations", json=body).status_code == 409
    res = client.put(
        f"/api/v1/organizations/{org['id']}/layout", json={"positions": [{"id": a["id"], "x": 10, "y": 20}]}
    )
    assert res.status_code == 204
    assert client.get(f"/api/v1/agents/{a['id']}").json()["pos_x"] == 10


def test_permissions_reject_bypass_mode(client: TestClient) -> None:
    org = client.post("/api/v1/organizations", json={"name": "Acme"}).json()
    res = client.post(
        f"/api/v1/organizations/{org['id']}/agents",
        json={"name": "X", "permissions": {"permission_mode": "bypassPermissions"}},
    )
    assert res.status_code == 422


def test_workspace_overview_and_activity(client: TestClient) -> None:
    client.post("/api/v1/organizations", json={"name": "Acme"})
    overview = client.get("/api/v1/workspace").json()
    assert overview["organizations"][0]["agent_count"] == 1
    assert overview["running_agents"] == []
    assert overview["pending_approvals"] == []
    assert overview["activity"][0]["kind"] == "org.created"
