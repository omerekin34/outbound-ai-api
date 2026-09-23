"""GET /api/companies canlı puan, kanıt ve Apollo kişisi döner."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api import models
from api.services.scoring import STATUS_LOW_PRIORITY, STATUS_QUALIFIED


def test_company_list_includes_scores_facts_and_contacts(
    client: TestClient, db_sessionmaker
) -> None:
    with db_sessionmaker() as session:
        session.add(
            models.Company(
                id="c-ok",
                name="Örnek Makina",
                domain="ornekmakina.com.tr",
                status=STATUS_QUALIFIED,
                erp_signal="Nebim V3",
                pain_hypothesis="Bayi siparişleri Excel ile Nebim arasında kopuk.",
            )
        )
        session.add(
            models.Score(
                company_id="c-ok",
                icp_score=80,
                need_score=70,
                overall_score=75,
                qualification_status=STATUS_QUALIFIED,
                requires_deep_research=True,
            )
        )
        session.add(
            models.CompanyFact(
                company_id="c-ok",
                fact_type="dealer_network",
                value="42 bayi",
                confidence=0.9,
                evidence_text="Türkiye genelinde 42 yetkili bayi.",
                source_type="website",
            )
        )
        session.add(
            models.Contact(
                id="apollo-1",
                company_id="c-ok",
                first_name="Deniz",
                last_name="Korkmaz",
                title="Satış Direktörü",
                email="deniz@ornekmakina.com.tr",
                email_status="valid",
                generated_email_body="Merhaba Deniz, Nebim taslağı.",
                persona_rank=90,
                is_selected=True,
            )
        )
        session.commit()

    body = client.get("/api/companies").json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["icp_score"] == 80
    assert item["need_score"] == 70
    assert item["facts"][0]["evidence_text"].startswith("Türkiye")
    assert item["contacts"][0]["name"] == "Deniz Korkmaz"
    assert "Ayşe" not in item["contacts"][0]["name"]
    assert item["erp_signal"] == "Nebim V3"
    assert "Excel" in item["pain_hypothesis"]
    assert item["contacts"][0]["email_status"] == "valid"
    assert item["contacts"][0]["is_selected"] is True
    assert item["contacts"][0]["persona_rank"] == 90
    assert "Nebim" in item["contacts"][0]["generated_email_body"]


def test_qualified_only_hides_low_priority(
    client: TestClient, db_sessionmaker
) -> None:
    with db_sessionmaker() as session:
        session.add(
            models.Company(id="c-low", name="Aselsan", status=STATUS_LOW_PRIORITY)
        )
        session.add(
            models.Company(id="c-ok", name="Uygun", status=STATUS_QUALIFIED)
        )
        session.commit()

    assert client.get("/api/companies").json()["total"] == 2
    only = client.get("/api/companies?qualified_only=true").json()
    assert only["total"] == 1
    assert only["items"][0]["name"] == "Uygun"
