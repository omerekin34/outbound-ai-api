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
