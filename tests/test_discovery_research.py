"""`POST /api/research` — 202 + arka plan keşif hattı."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from api import models
from api.routers import research as research_router
from api.services import research_job as research_job_service
from api.services.research_job import clean_domain
from tests.test_research_endpoint import (
    BASE,
    FAKE_ANALYSIS,
    FakeFirecrawl,
    FakeOpenAI,
)


def test_clean_domain_strips_scheme_www_and_path() -> None:
    assert clean_domain("https://www.OrnekMakina.com.tr/hakkimizda") == "ornekmakina.com.tr"


def test_research_rejects_invalid_domain(client: TestClient) -> None:
    response = client.post("/api/research", json={"domain": "not a domain"})
    assert response.status_code == 422


def test_research_requires_domain(client: TestClient) -> None:
    assert client.post("/api/research", json={}).status_code == 422


def test_research_returns_202_immediately(
    client: TestClient, monkeypatch
) -> None:
    queued: list[tuple[str, str]] = []

    def fake_job(company_id: str, website: str) -> None:
        queued.append((company_id, website))

    monkeypatch.setattr(research_router, "enqueue_research_job", fake_job)

    response = client.post(
        "/api/research", json={"domain": "https://www.ornekmakina.com.tr/iletisim"}
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "accepted"
    assert body["message"] == "Research started in the background"
    assert body["domain"] == "ornekmakina.com.tr"
    assert body["website"] == "https://ornekmakina.com.tr"
    assert body["company_id"]
    assert queued == [(body["company_id"], "https://ornekmakina.com.tr")]


def test_research_reuses_existing_company(
    client: TestClient, db_sessionmaker, monkeypatch
) -> None:
    monkeypatch.setattr(research_router, "enqueue_research_job", lambda *_: None)
    first = client.post("/api/research", json={"domain": "ornekmakina.com.tr"}).json()
    second = client.post("/api/research", json={"domain": "ornekmakina.com.tr"}).json()
    assert first["company_id"] == second["company_id"]

    with db_sessionmaker() as session:
        count = len(
            session.execute(
                select(models.Company).where(models.Company.domain == "ornekmakina.com.tr")
            ).scalars().all()
        )
    assert count == 1


def test_background_job_runs_full_pipeline(
    client: TestClient,
    db_sessionmaker,
    monkeypatch,
) -> None:
    fake = FakeFirecrawl()
    monkeypatch.setattr(
        research_router, "enqueue_research_job", research_job_service.run_research_job
    )
    monkeypatch.setattr(research_job_service, "firecrawl_client", lambda: fake)
    monkeypatch.setattr(
        "api.services.enrichment.openai_client", lambda: FakeOpenAI(FAKE_ANALYSIS)
    )

    response = client.post("/api/research", json={"domain": "ornekmakina.com.tr"})
    assert response.status_code == 202
    company_id = response.json()["company_id"]

    with db_sessionmaker() as session:
        company = session.get(models.Company, company_id)
        facts = session.execute(
            select(models.CompanyFact).where(models.CompanyFact.company_id == company_id)
        ).scalars().all()
        score = session.execute(
            select(models.Score).where(models.Score.company_id == company_id)
        ).scalar_one()

    assert company is not None
    assert company.domain == "ornekmakina.com.tr"
    assert company.website == BASE
    assert len(facts) == 3
    assert score.overall_score is not None
    assert fake.scraped_urls


def test_scrape_timeout_marks_company_timeout(db_sessionmaker, monkeypatch) -> None:
    from api.services.research_job import ResearchJobError, execute_research_pipeline
    from api.services.scoring import STATUS_TIMEOUT
    from api.services.website_research import ScrapeTimeoutError

    monkeypatch.setattr(
        research_job_service,
        "research_website",
        lambda *_a, **_k: (_ for _ in ()).throw(ScrapeTimeoutError(60)),
    )
    monkeypatch.setattr(research_job_service, "firecrawl_client", lambda: object())

    with db_sessionmaker() as session:
        company = models.Company(
            id="c-timeout",
            name="Yavaş Site",
            domain="yavas.example",
            website="https://yavas.example",
            status="new",
        )
        session.add(company)
        session.commit()

        with pytest.raises(ResearchJobError, match="zaman aşımı"):
            execute_research_pipeline(session, company, "https://yavas.example")
        session.commit()
        stored = session.get(models.Company, "c-timeout")

    assert stored is not None
    assert stored.status == STATUS_TIMEOUT
