"""Step 13: Apollo karar verici araması yalnızca nitelikli şirketlerde çalışır."""

from __future__ import annotations

from sqlalchemy import select

from api import models
from api.services.analysis import persist_analysis
from api.services.apollo import (
    ApolloPerson,
    company_domain,
    find_decision_makers,
    persist_apollo_contacts,
)
from api.services.scoring import STATUS_HIGH_PRIORITY, STATUS_QUALIFIED, STATUS_REJECT

QUALIFIED_FACTS = [
    {"fact_type": key, "value": value, "evidence_text": f"{value} kanıtı", "confidence": 0.9}
    for key, value in (
        ("b2b", "B2B"),
        ("physical_product", "Fiziksel ürün"),
        ("employee_50_249", "90 kişi"),
        ("target_industry", "Makina"),
        ("turkey", "Türkiye"),
        ("sales_team", "Satış ekibi"),
        ("erp_detected", "SAP"),
        ("quote_based_sales", "Teklif usulü"),
        ("dealer_network", "bayi ağı"),
        ("high_sku", "Yüksek SKU"),
        ("multiple_warehouse", "Birden fazla depo"),
        ("sales_operations", "Satış operasyon"),
        ("whatsapp_sales", "WhatsApp"),
    )
]


class FakeApollo:
    def __init__(self, people: list[ApolloPerson] | None = None) -> None:
        self.calls: list[str] = []
        self.people = people or [
            ApolloPerson(
                apollo_id="p1",
                first_name="Deniz",
                last_name="Korkmaz",
                title="Satış Direktörü",
                email="deniz.korkmaz@ornekmakina.com.tr",
                linkedin_url="https://linkedin.com/in/denizkorkmaz",
            )
        ]

    def search_decision_makers(self, domain: str) -> list[ApolloPerson]:
        self.calls.append(domain)
        return list(self.people)


def _company(**kwargs) -> models.Company:
    values = {
        "id": "c-ornek",
        "name": "Örnek Makina",
        "domain": "ornekmakina.com.tr",
        "website": "https://ornekmakina.com.tr",
        "status": STATUS_QUALIFIED,
    }
    values.update(kwargs)
    return models.Company(**values)


def test_company_domain_strips_www_and_path() -> None:
    company = models.Company(
        id="x",
        website="https://www.OrnekMakina.com.tr/hakkimizda",
        domain=None,
    )
    assert company_domain(company) == "ornekmakina.com.tr"


def test_apollo_is_skipped_when_company_is_not_qualified(db_sessionmaker) -> None:
    fake = FakeApollo()
    with db_sessionmaker() as session:
        company = _company(status=STATUS_REJECT)
        session.add(company)
        session.commit()

        saved = find_decision_makers(session, company, client=fake)

    assert saved == 0
    assert fake.calls == []


def test_apollo_runs_for_qualified_and_high_priority(db_sessionmaker) -> None:
    for status in (STATUS_QUALIFIED, STATUS_HIGH_PRIORITY):
        slug = status.replace(" ", "-")
        domain = f"{slug}.ornekmakina.com.tr"
        fake = FakeApollo(
            [
                ApolloPerson(
                    apollo_id=f"p-{slug}",
                    first_name="Deniz",
                    last_name="Korkmaz",
                    title="Satış Direktörü",
                    email=f"deniz.{slug}@{domain}",
                    linkedin_url="https://linkedin.com/in/denizkorkmaz",
                )
            ]
        )
        with db_sessionmaker() as session:
            company = _company(
                id=f"c-{slug}",
                domain=domain,
                website=f"https://{domain}",
                status=status,
            )
            session.add(company)
            session.commit()

            saved = find_decision_makers(session, company, client=fake)
            session.commit()

            contacts = session.execute(
                select(models.Contact).where(models.Contact.company_id == company.id)
            ).scalars().all()

        assert fake.calls == [domain]
        assert saved == 1
        assert contacts[0].first_name == "Deniz"
        assert contacts[0].title == "Satış Direktörü"
        assert contacts[0].email == f"deniz.{slug}@{domain}"
        assert contacts[0].linkedin_url.endswith("denizkorkmaz")


def test_apollo_is_not_called_again_if_contacts_exist(db_sessionmaker) -> None:
    fake = FakeApollo()
    with db_sessionmaker() as session:
        company = _company()
        session.add(company)
        session.commit()
        find_decision_makers(session, company, client=fake)
        session.commit()

        fake.calls.clear()
        saved = find_decision_makers(session, company, client=fake)

    assert saved == 0
    assert fake.calls == []


def test_force_refreshes_existing_contacts(db_sessionmaker) -> None:
    first = FakeApollo()
    second = FakeApollo(
        [
            ApolloPerson(
                apollo_id="p1",
                first_name="Deniz",
                last_name="Korkmaz",
                title="Genel Müdür",
                email="deniz.korkmaz@ornekmakina.com.tr",
                linkedin_url="https://linkedin.com/in/denizkorkmaz",
            )
        ]
    )
    with db_sessionmaker() as session:
        company = _company()
        session.add(company)
        session.commit()
        find_decision_makers(session, company, client=first)
        session.commit()

        saved = find_decision_makers(session, company, client=second, force=True)
        session.commit()
        contact = session.get(models.Contact, "apollo-p1")

    assert saved == 1
    assert contact.title == "Genel Müdür"


def test_persist_writes_required_contact_fields(db_sessionmaker) -> None:
    people = [
        ApolloPerson("ok", "Ada", "Yılmaz", "CTO", "ada@ornek.com", None)
    ]
    with db_sessionmaker() as session:
        company = _company()
        session.add(company)
        session.commit()
        written = persist_apollo_contacts(session, company, people)
        session.commit()
        assert written == 1
        assert session.get(models.Contact, "apollo-ok").email == "ada@ornek.com"


def test_contacts_endpoint_returns_real_rows(
    client, db_sessionmaker
) -> None:
    with db_sessionmaker() as session:
        session.add(_company())
        session.add(
            models.Contact(
                id="apollo-p1",
                company_id="c-ornek",
                first_name="Deniz",
                last_name="Korkmaz",
                title="Satış Direktörü",
                email="deniz@ornekmakina.com.tr",
                linkedin_url="https://linkedin.com/in/denizkorkmaz",
            )
        )
        session.commit()

    body = client.get("/api/contacts").json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Deniz Korkmaz"
    assert body["items"][0]["title"] == "Satış Direktörü"
    assert "Ayşe" not in body["items"][0]["name"]


def test_contacts_endpoint_hides_unqualified_companies(client, db_sessionmaker) -> None:
    with db_sessionmaker() as session:
        session.add(_company(status=STATUS_REJECT))
        session.add(
            models.Contact(
                id="apollo-hidden",
                company_id="c-ornek",
                first_name="Gizli",
                last_name="Kişi",
                title="CEO",
                email="gizli@ornek.com",
            )
        )
        session.commit()

    assert client.get("/api/contacts").json()["total"] == 0
    assert client.get("/api/contacts?qualified_only=false").json()["total"] == 1


def test_persist_analysis_triggers_apollo_after_qualification(
    db_sessionmaker, monkeypatch
) -> None:
    fake = FakeApollo()
    monkeypatch.setattr(
        "api.services.analysis.find_decision_makers",
        lambda db, company, **kwargs: find_decision_makers(
            db, company, client=fake, **kwargs
        ),
    )
    with db_sessionmaker() as session:
        company = _company(status="new")
        session.add(company)
        session.commit()

        _, scores = persist_analysis(
            session, company, {"facts": QUALIFIED_FACTS}, source_type="website"
        )
        session.commit()
        contacts = session.execute(select(models.Contact)).scalars().all()

    assert scores.qualification_status == STATUS_QUALIFIED
    assert scores.requires_deep_research is True
    assert fake.calls == ["ornekmakina.com.tr"]
    assert len(contacts) == 1
    assert contacts[0].company_id == "c-ornek"
    assert contacts[0].first_name == "Deniz"
    assert contacts[0].email == "deniz.korkmaz@ornekmakina.com.tr"


def test_persist_analysis_skips_apollo_when_not_qualified(
    db_sessionmaker, monkeypatch
) -> None:
    fake = FakeApollo()
    monkeypatch.setattr(
        "api.services.analysis.find_decision_makers",
        lambda db, company, **kwargs: find_decision_makers(
            db, company, client=fake, **kwargs
        ),
    )
    with db_sessionmaker() as session:
        company = _company(status="new")
        session.add(company)
        session.commit()
        persist_analysis(session, company, {"facts": []}, source_type="website")
        session.commit()

    assert fake.calls == []
