"""Dashboard Keşif / Uygun sayaçları Step 19 yeterlilik durumuna uyar."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api import models
from api.services.scoring import (
    STATUS_HIGH_PRIORITY,
    STATUS_LOW_PRIORITY,
    STATUS_QUALIFIED,
    STATUS_REJECT,
)


def test_suitable_count_excludes_low_priority_and_reject(
    client: TestClient, db_sessionmaker
) -> None:
    with db_sessionmaker() as session:
        session.add_all(
            [
                models.Company(id="c-aselsan", name="Aselsan", status=STATUS_LOW_PRIORITY),
                models.Company(id="c-ok", name="Uygun A.Ş.", status=STATUS_QUALIFIED),
                models.Company(id="c-hot", name="Öncelikli", status=STATUS_HIGH_PRIORITY),
                models.Company(id="c-no", name="Red", status=STATUS_REJECT),
                models.Company(id="c-new", name="Yeni", status="new"),
            ]
        )
        session.commit()

    stats = client.get("/api/dashboard-stats").json()["stats"]
    breakdown = {
        row["status"]: row["count"]
        for row in client.get("/api/dashboard-stats").json()["status_breakdown"]
    }

    assert stats["analyzed_companies"] == 4
    assert stats["suitable_companies"] == 2
    assert stats["pending_companies"] == 1
    assert stats["review_companies"] == 0
    assert len(client.get("/api/dashboard-stats").json()["daily"]) == 7
    assert breakdown.get(STATUS_LOW_PRIORITY) == 1
    assert breakdown.get(STATUS_QUALIFIED) == 1
    assert breakdown.get(STATUS_HIGH_PRIORITY) == 1
    assert breakdown.get(STATUS_REJECT) == 1


def test_empty_database_returns_zero_stats(client: TestClient) -> None:
    body = client.get("/api/dashboard-stats").json()
    stats = body["stats"]

    assert stats["total_companies"] == 0
    assert stats["suitable_companies"] == 0
    assert stats["total_contacts"] == 0
    assert stats["high_intent_companies"] == 0
    assert stats["positive_replies"] == 0
    assert body["status_breakdown"] == []
    assert body["top_industries"] == []
    assert len(body["daily"]) == 7
    assert all(day["analyzed"] == 0 and day["positive_replies"] == 0 for day in body["daily"])
    assert body["ai_status"]["state"] == "idle"
    assert client.get("/api/companies").json() == {
        "items": [],
        "total": 0,
        "limit": 25,
        "offset": 0,
    }


def test_cors_allows_next_on_port_3001(client: TestClient) -> None:
    origin = "http://localhost:3001"
    preflight = client.options(
        "/api/dashboard-stats",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.headers.get("access-control-allow-origin") == origin

    response = client.get("/api/dashboard-stats", headers={"Origin": origin})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin


def test_dashboard_daily_window_follows_days_query(client: TestClient) -> None:
    default = client.get("/api/dashboard-stats").json()["daily"]
    fortnight = client.get("/api/dashboard-stats?days=14").json()["daily"]
    today = client.get("/api/dashboard-stats?days=1").json()["daily"]

    assert len(default) == 7
    assert len(fortnight) == 14
    assert len(today) == 1
    assert client.get("/api/dashboard-stats?days=99").status_code == 422
