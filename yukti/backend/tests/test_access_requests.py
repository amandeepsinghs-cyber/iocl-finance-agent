"""15-Nov: IOCL Finance access requests (Grades A-D -> Director (Finance) / CMD approval)."""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("YUKTI_PERSONA_SIGNING_KEY", "test-signing-key-for-access-requests-0123456789")

from app.access_requests import reset_store_for_tests  # noqa: E402
from app.main import app  # noqa: E402


def _client(persona: str) -> TestClient:
    c = TestClient(app, base_url="https://testserver")  # the session cookie is Secure
    r = c.post("/api/auth/session", json={"persona_id": persona})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture(autouse=True)
def _clean():
    reset_store_for_tests()
    yield
    reset_store_for_tests()


def _create(c: TestClient, turn_id: str = "turn-1"):
    return c.post("/api/access-requests", json={
        "turn_id": turn_id,
        "question": "Show counterparty credit sub-ledger and confidential Q4 Board pack",
        "code": "R-FUNC",
        "rule_ref": "D-43",
        "reason": "confidential finance sub-ledger restricted for Grades A-D",
    })


def test_requires_sign_in():
    assert TestClient(app).get("/api/access-requests").status_code == 401


def test_grade_a_finance_request_routes_to_director_finance_and_dedupes():
    e1 = _client("A_FIN")  # alias normalizes to E1_FIN
    r = _create(e1)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending" and body["function"] == "FIN"
    assert body["approver_label"] == "Director (Finance) / Chairman"
    assert _create(e1).json()["id"] == body["id"]  # same card, one open request
    mine = e1.get("/api/access-requests").json()
    assert mine["role"] == "requester" and mine["pending"] == 1


def test_directors_and_cmd_cannot_request():
    for p in ("CMD", "CHAIRMAN", "DIR_FIN", "DIR_REF", "DIR_MKT"):
        assert _create(_client(p)).status_code == 400


def test_only_director_finance_or_cmd_can_decide_fin_request():
    rid = _create(_client("E2_FIN")).json()["id"]
    dir_ref = _client("DIR_REF")
    assert dir_ref.get("/api/access-requests").json()["requests"] == []
    assert dir_ref.post(f"/api/access-requests/{rid}/decision", json={"decision": "approved"}).status_code == 403
    assert _client("E3_FIN").post(f"/api/access-requests/{rid}/decision", json={"decision": "approved"}).status_code == 403
    dir_fin = _client("DIR_FIN")
    inbox = dir_fin.get("/api/access-requests").json()
    assert inbox["role"] == "approver" and inbox["pending"] == 1
    out = dir_fin.post(f"/api/access-requests/{rid}/decision", json={"decision": "approved", "note": "ok"}).json()
    assert out["status"] == "approved" and out["decided_by"]["persona"] == "DIR_FIN"
    assert "official Finance channel" in out["outcome"]


def test_grade_c_finance_officer_routes_to_director_finance_and_cmd_can_reject():
    rid = _create(_client("E3_FIN")).json()["id"]
    assert _client("DIR_FIN").get("/api/access-requests").json()["pending"] == 1
    out = _client("CMD").post(f"/api/access-requests/{rid}/decision", json={"decision": "rejected", "note": "Use published aggregates"}).json()
    assert out["status"] == "rejected" and "Use published aggregates" in out["outcome"]


def test_bad_decision_value():
    rid = _create(_client("E1_FIN")).json()["id"]
    assert _client("DIR_FIN").post(f"/api/access-requests/{rid}/decision", json={"decision": "maybe"}).status_code == 400
