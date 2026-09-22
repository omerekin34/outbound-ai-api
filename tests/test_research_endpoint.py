"""`POST /api/companies/research-website` uçtan uca testleri.

Firecrawl ve OpenAI taklit edilir, veritabanı olarak geçici SQLite kullanılır;
test için ne API anahtarı ne de Neon bağlantısı gerekir.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from api import models
from api.services import enrichment
from api.services import research_job as research_job_service
from api.services.scoring import SCORE_VERSION, calculate_scores

BASE = "https://ornekmakina.com.tr"
HOME = f"{BASE}/"
COMPANY_ID = "test-company-1"

SITE_URLS = [
    HOME,
    f"{BASE}/hakkimizda",
    f"{BASE}/urunler",
    f"{BASE}/bayiler",
    f"{BASE}/iletisim",
]

PAGE_CONTENT = {
    HOME: "Örnek Makina - endüstriyel hidrolik pres üreticisi",
    f"{BASE}/hakkimizda": "1998'den beri Konya'da üretim yapıyoruz.",
    f"{BASE}/urunler": "Hidrolik pres, CNC torna tezgâhları.",
    f"{BASE}/bayiler": "Türkiye genelinde 42 yetkili bayi.",
    f"{BASE}/iletisim": "Telefon: 0332 000 00 00",
}

# Analyzer'ın döndürdüğünü varsaydığımız yapılandırılmış çıktı.
FAKE_ANALYSIS = {
    "scores": {
        "icp_score": 82,
        "need_score": 61,
        "timing_score": 44,
        "reachability_score": 90,
        "overall_score": 74.5,
    },
    "facts": [
        {
            "fact_type": "dealer_network",
            "value": "Türkiye genelinde 42 yetkili bayi",
            "confidence": 0.9,
            "evidence_text": "Türkiye genelinde 42 yetkili bayi.",
            "source_url": f"{BASE}/bayiler",
        },
        {
            "fact_type": "product_lines",
            "value": "Hidrolik pres ve CNC torna",
            "confidence": 0.8,
            "evidence_text": "Hidrolik pres, CNC torna tezgâhları.",
            "source_url": f"{BASE}/urunler",
        },
        {
            # Analyzer taranmayan bir adres uydurursa kanıt anasayfaya bağlanır.
            "fact_type": "certifications",
            "value": "ISO 9001",
            "confidence": 0.4,
            "evidence_text": "ISO 9001 belgeli üretim.",
            "source_url": "https://uydurma-adres.com/kalite",
        },
    ],
}


class FakeMeta:
    def __init__(self, url: str) -> None:
        self.source_url = url
        self.url = url


class FakeDocument:
    def __init__(self, url: str) -> None:
        self.markdown = PAGE_CONTENT.get(url, "")
        self.metadata = FakeMeta(url)


class FakeJob:
    def __init__(self, urls: list[str]) -> None:
        self.data = [FakeDocument(url) for url in urls]
        self.credits_used = len(urls)


class FakeFirecrawl:
    def __init__(self) -> None:
        self.scraped_urls: list[str] = []

    def map(self, url: str, **kwargs: Any) -> Any:
        links = [FakeMeta(link) for link in SITE_URLS]
        return type("MapData", (), {"links": links})()

    def batch_scrape(self, urls: list[str], **kwargs: Any) -> FakeJob:
        self.scraped_urls = list(urls)
        return FakeJob(urls)


class FakeOpenAI:
    """`client.chat.completions.create(...)` çağrısını taklit eder."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.prompts: list[str] = []

        message = type("Message", (), {"content": json.dumps(payload)})()
        choice = type("Choice", (), {"message": message})()
        response = type("Response", (), {"choices": [choice]})()

        outer = self

        class Completions:
            def create(self, **kwargs: Any) -> Any:
                outer.prompts.append(kwargs["messages"][-1]["content"])
                return response

        self.chat = type("Chat", (), {"completions": Completions()})()


@pytest.fixture(autouse=True)
def seed_company(db_sessionmaker) -> None:
    """Testlerin araştırdığı şirket. Ortak `client` fixture'ı conftest'te."""
    with db_sessionmaker() as session:
        session.add(
            models.Company(
                id=COMPANY_ID,
                name="Örnek Makina",
                normalized_name="ornekmakina",
                domain="ornekmakina.com.tr",
                status="new",
            )
        )
        session.commit()


@pytest.fixture
def fake_firecrawl(monkeypatch) -> FakeFirecrawl:
    fake = FakeFirecrawl()
    # Hattı `research_job` yürütür; istemci orada çözülür.
    monkeypatch.setattr(research_job_service, "firecrawl_client", lambda: fake)
    monkeypatch.setattr(enrichment, "firecrawl_client", lambda: fake)
    return fake


@pytest.fixture
def fake_openai(monkeypatch) -> FakeOpenAI:
    fake = FakeOpenAI(FAKE_ANALYSIS)
    # `openai_client` yalnızca `enrichment` içinden çağrılıyor.
    monkeypatch.setattr(enrichment, "openai_client", lambda: fake)
    return fake


# --- girdi doğrulama (spec 1 ve 3) ----------------------------------------


def test_website_is_required(client: TestClient) -> None:
    response = client.post(
        "/api/companies/research-website", json={"company_id": COMPANY_ID}
    )
    assert response.status_code == 422
    assert any(
        error["loc"] == ["body", "website"] for error in response.json()["detail"]
    )


def test_company_id_is_required(client: TestClient) -> None:
    response = client.post(
        "/api/companies/research-website", json={"website": BASE}
    )
    assert response.status_code == 422


def test_max_pages_above_twenty_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/companies/research-website",
        json={"company_id": COMPANY_ID, "website": BASE, "max_pages": 21},
    )
    assert response.status_code == 422


def test_unknown_company_returns_404(
    client: TestClient, fake_firecrawl: FakeFirecrawl, fake_openai: FakeOpenAI
) -> None:
    response = client.post(
        "/api/companies/research-website",
        json={"company_id": "yok-boyle-bir-sirket", "website": BASE},
    )
    assert response.status_code == 404


def test_malformed_website_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/companies/research-website",
        json={"company_id": COMPANY_ID, "website": "bu bir adres degil"},
    )
    assert response.status_code == 422


# --- mutlu yol --------------------------------------------------------------


def test_research_returns_targeted_pages_and_analysis(
    client: TestClient, fake_firecrawl: FakeFirecrawl, fake_openai: FakeOpenAI
) -> None:
    response = client.post(
        "/api/companies/research-website",
        json={"company_id": COMPANY_ID, "website": BASE},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "success"
    assert body["website"] == HOME
    assert body["max_pages"] == 20
    assert body["discovered_urls"] == len(SITE_URLS)
    assert body["scraped_pages"] == len(SITE_URLS)
    assert body["used_fallback"] is False

    categories = {page["category"] for page in body["pages"]}
    assert categories == {"homepage", "about", "products", "dealers", "contact"}
    expected = calculate_scores(FAKE_ANALYSIS["facts"])
    assert body["analysis"]["scores"]["overall_score"] == pytest.approx(
        expected.overall_score
    )
    # LLM 74.5 dönse bile yanıt backend puanıdır.
    assert body["analysis"]["scores"]["overall_score"] != pytest.approx(74.5)
    assert body["facts_saved"] == 3


def test_analyzer_prompt_includes_every_page_url(
    client: TestClient, fake_firecrawl: FakeFirecrawl, fake_openai: FakeOpenAI
) -> None:
    client.post(
        "/api/companies/research-website",
        json={"company_id": COMPANY_ID, "website": BASE},
    )
    prompt = fake_openai.prompts[-1]

    for url in SITE_URLS:
        assert f"URL: {url}" in prompt
    assert "Örnek Makina" in prompt


def test_facts_are_persisted_with_page_level_evidence(
    client: TestClient,
    fake_firecrawl: FakeFirecrawl,
    fake_openai: FakeOpenAI,
    db_sessionmaker,
) -> None:
    client.post(
        "/api/companies/research-website",
        json={"company_id": COMPANY_ID, "website": BASE},
    )

    with db_sessionmaker() as session:
        facts = {
            fact.fact_type: fact
            for fact in session.execute(
                select(models.CompanyFact).where(
                    models.CompanyFact.company_id == COMPANY_ID
                )
            ).scalars()
        }

    # Kanıt, bulgunun alındığı asıl sayfaya bağlanır.
    assert facts["dealer_network"].source_url == f"{BASE}/bayiler"
    assert facts["dealer_network"].evidence_text.startswith("Türkiye genelinde 42")
    assert facts["product_lines"].source_url == f"{BASE}/urunler"
    # Uydurma URL anasayfaya düşürüldü.
    assert facts["certifications"].source_url == HOME


def test_scores_are_persisted_and_status_advances(
    client: TestClient,
    fake_firecrawl: FakeFirecrawl,
    fake_openai: FakeOpenAI,
    db_sessionmaker,
) -> None:
    client.post(
        "/api/companies/research-website",
        json={"company_id": COMPANY_ID, "website": BASE},
    )

    with db_sessionmaker() as session:
        score = session.execute(
            select(models.Score).where(models.Score.company_id == COMPANY_ID)
        ).scalar_one()
        company = session.get(models.Company, COMPANY_ID)

        expected = calculate_scores(FAKE_ANALYSIS["facts"])
        assert score.overall_score == pytest.approx(expected.overall_score)
        assert score.icp_score == pytest.approx(expected.icp_score)
        assert score.version == SCORE_VERSION
        assert company.status == expected.qualification_status
        assert score.qualification_status == expected.qualification_status
        assert score.requires_deep_research is expected.requires_deep_research
        # Spec: adres girdiden gelir ve kayda işlenir.
        assert company.website == BASE


def test_rerunning_updates_instead_of_duplicating(
    client: TestClient,
    fake_firecrawl: FakeFirecrawl,
    fake_openai: FakeOpenAI,
    db_sessionmaker,
) -> None:
    payload = {"company_id": COMPANY_ID, "website": BASE}
    assert client.post("/api/companies/research-website", json=payload).status_code == 200
    assert client.post("/api/companies/research-website", json=payload).status_code == 200

    with db_sessionmaker() as session:
        facts = session.execute(
            select(models.CompanyFact).where(
                models.CompanyFact.company_id == COMPANY_ID
            )
        ).scalars().all()
        scores = session.execute(
            select(models.Score).where(models.Score.company_id == COMPANY_ID)
        ).scalars().all()

    assert len(facts) == len(FAKE_ANALYSIS["facts"])
    assert len(scores) == 1


def test_analyze_uses_backend_scores_not_llm_scores(
    client: TestClient, fake_openai: FakeOpenAI
) -> None:
    response = client.post(
        "/api/companies/analyze",
        json={
            "company_id": COMPANY_ID,
            "website_content": "Türkiye genelinde 42 yetkili bayi.",
            "source_url": HOME,
        },
    )
    assert response.status_code == 200, response.text
    expected = calculate_scores(FAKE_ANALYSIS["facts"])
    scores = response.json()["data"]["scores"]
    assert scores["overall_score"] == pytest.approx(expected.overall_score)
    assert scores["overall_score"] != pytest.approx(74.5)


def test_activity_log_records_the_run(
    client: TestClient,
    fake_firecrawl: FakeFirecrawl,
    fake_openai: FakeOpenAI,
    db_sessionmaker,
) -> None:
    client.post(
        "/api/companies/research-website",
        json={"company_id": COMPANY_ID, "website": BASE},
    )

    with db_sessionmaker() as session:
        log = session.execute(
            select(models.ActivityLog).where(
                models.ActivityLog.event_type == "website_research"
            )
        ).scalars().all()[-1]

    assert log.status == "success"
    assert log.detail["scraped_pages"] == len(SITE_URLS)


def test_only_target_pages_are_sent_to_firecrawl(
    client: TestClient, fake_firecrawl: FakeFirecrawl, fake_openai: FakeOpenAI
) -> None:
    client.post(
        "/api/companies/research-website",
        json={"company_id": COMPANY_ID, "website": BASE},
    )
    assert set(fake_firecrawl.scraped_urls) == set(SITE_URLS)


def test_max_pages_is_passed_through(
    client: TestClient, fake_firecrawl: FakeFirecrawl, fake_openai: FakeOpenAI
) -> None:
    response = client.post(
        "/api/companies/research-website",
        json={"company_id": COMPANY_ID, "website": BASE, "max_pages": 3},
    )
    assert response.status_code == 200
    assert len(fake_firecrawl.scraped_urls) == 3
    assert response.json()["max_pages"] == 3
