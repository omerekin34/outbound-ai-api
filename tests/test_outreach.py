"""İki adımlı strateji + yalnızca valid e-posta."""

from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from api import models
from api.services.analysis import persist_analysis
from api.services.apollo import find_decision_makers, persona_rank
from api.services.email_verify import STATUS_ACCEPT_ALL, STATUS_UNKNOWN, STATUS_VALID
from api.services.outreach import prepare_outreach, word_count
from api.services.scoring import STATUS_QUALIFIED
from tests.test_apollo import QUALIFIED_FACTS, FakeApollo, _company


def compliant_body(token: str = "SAP") -> str:
    words = ["Merhaba", "Deniz,"] + [token] * 88
    text = " ".join(words)
    assert 80 <= word_count(text) <= 120
    return text


STRATEGY = {
    "main_pain": "Bayi siparişleri stokla kopuk",
    "recommended_product": "Sipariş senkronu",
    "best_sales_angle": "Netsis bayi entegrasyonu",
    "best_persona": "Satış Direktörü",
    "why_now": "Bayi ağı kanıtı var",
}


class FakeCompletions:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(self.payload))
                )
            ]
        )


def test_prepare_outreach_skips_non_valid(db_sessionmaker, monkeypatch) -> None:
    fake = FakeCompletions(
        {"strategy": STRATEGY, "email_body": compliant_body()}
    )
    monkeypatch.setattr(
        "api.services.outreach.openai_client",
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=fake)),
    )
    monkeypatch.setattr(
        "api.services.outreach.verify_email", lambda _addr: STATUS_UNKNOWN
    )
    with db_sessionmaker() as session:
        company = _company(
            status=STATUS_QUALIFIED,
            erp_signal="Netsis",
            pain_hypothesis="Bayi siparişleri kopuk.",
        )
        session.add(company)
        session.add(
            models.Contact(
                id="apollo-1",
                company_id=company.id,
                first_name="Deniz",
                last_name="Korkmaz",
                title="Satış Direktörü",
                email="deniz@ornekmakina.com.tr",
            )
        )
        session.commit()
        drafted = prepare_outreach(session, company)
        session.commit()
        contact = session.get(models.Contact, "apollo-1")

    assert drafted == 0
    assert fake.calls == []
    assert contact.email_status == STATUS_UNKNOWN
    assert contact.generated_email_body is None
    assert contact.is_selected is True


def test_prepare_outreach_skips_accept_all(db_sessionmaker, monkeypatch) -> None:
    fake = FakeCompletions(
        {"strategy": STRATEGY, "email_body": compliant_body()}
    )
    monkeypatch.setattr(
        "api.services.outreach.openai_client",
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=fake)),
    )
    monkeypatch.setattr(
        "api.services.outreach.verify_email", lambda _addr: STATUS_ACCEPT_ALL
    )
    with db_sessionmaker() as session:
        company = _company(status=STATUS_QUALIFIED)
        session.add(company)
        session.add(
            models.Contact(
                id="apollo-1",
                company_id=company.id,
                first_name="Deniz",
                last_name="Korkmaz",
                title="Satış Direktörü",
                email="info@ornekmakina.com.tr",
            )
        )
        session.commit()
        assert prepare_outreach(session, company) == 0
        assert fake.calls == []


def test_prepare_outreach_writes_strategy_for_top_valid_persona(
    db_sessionmaker, monkeypatch
) -> None:
    fake = FakeCompletions(
        {"strategy": STRATEGY, "email_body": compliant_body("Netsis")}
    )
    monkeypatch.setattr(
        "api.services.outreach.openai_client",
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=fake)),
    )
    with db_sessionmaker() as session:
        company = _company(
            status=STATUS_QUALIFIED,
            erp_signal="Netsis",
            erp_evidence={"erp": {"value": "Netsis", "confidence": 0.9, "evidence_count": 2}},
            pain_hypothesis="Bayi siparişleri Excel ile Netsis arasında kopuk.",
        )
        session.add(company)
        session.add_all(
            [
                models.Contact(
                    id="apollo-it",
                    company_id=company.id,
                    first_name="Ali",
                    last_name="Yılmaz",
                    title="IT Manager",
                    email="ali.yilmaz@ornekmakina.com.tr",
                ),
                models.Contact(
                    id="apollo-sales",
                    company_id=company.id,
                    first_name="Deniz",
                    last_name="Korkmaz",
                    title="Commercial Director",
                    email="deniz.korkmaz@ornekmakina.com.tr",
                ),
            ]
        )
        session.commit()
        drafted = prepare_outreach(session, company)
        session.commit()
        session.refresh(company)
        sales = session.get(models.Contact, "apollo-sales")
        it = session.get(models.Contact, "apollo-it")

    assert drafted == 1
    assert fake.calls
    user_prompt = fake.calls[0]["messages"][1]["content"]
    assert "Netsis" in user_prompt
    assert "Deniz" in user_prompt
    assert sales.email_status == STATUS_VALID
    assert sales.is_selected is True
    assert sales.persona_rank == 100
    assert it.is_selected is False
    assert it.persona_rank == 70
    assert it.generated_email_body is None
    assert "Netsis" in (sales.generated_email_body or "")
    assert company.outreach_strategy["best_sales_angle"] == STRATEGY["best_sales_angle"]


def test_prepare_outreach_does_not_overwrite_edit(
    db_sessionmaker, monkeypatch
) -> None:
    fake = FakeCompletions(
        {"strategy": STRATEGY, "email_body": compliant_body("Yeni")}
    )
    monkeypatch.setattr(
        "api.services.outreach.openai_client",
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=fake)),
    )
    with db_sessionmaker() as session:
        company = _company(status=STATUS_QUALIFIED)
        session.add(company)
        session.add(
            models.Contact(
                id="apollo-1",
                company_id=company.id,
                first_name="Deniz",
                last_name="Korkmaz",
                title="Sales Director",
                email="deniz@ornekmakina.com.tr",
                email_status=STATUS_VALID,
                generated_email_body="Kullanıcı düzenlemesi.",
            )
        )
        session.commit()
        prepare_outreach(session, company)
        session.commit()
        contact = session.get(models.Contact, "apollo-1")

    assert fake.calls == []
    assert contact.generated_email_body == "Kullanıcı düzenlemesi."


def test_persist_analysis_prepares_outreach_after_apollo(
    db_sessionmaker, monkeypatch
) -> None:
    fake_llm = FakeCompletions(
        {"strategy": STRATEGY, "email_body": compliant_body("SAP")}
    )
    monkeypatch.setattr(
        "api.services.outreach.openai_client",
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=fake_llm)),
    )
    fake_apollo = FakeApollo()
    monkeypatch.setattr(
        "api.services.analysis.find_decision_makers",
        lambda db, company, **kwargs: find_decision_makers(
            db, company, client=fake_apollo, **kwargs
        ),
    )
    with db_sessionmaker() as session:
        company = _company(status="new", erp_signal="SAP", pain_hypothesis="Teklif Excel.")
        session.add(company)
        session.commit()
        persist_analysis(
            session, company, {"facts": QUALIFIED_FACTS}, source_type="website"
        )
        session.commit()
        contact = session.execute(select(models.Contact)).scalar_one()

    assert contact.email_status == STATUS_VALID
    assert contact.is_selected is True
    assert persona_rank(contact.title) == 90
    assert "SAP" in (contact.generated_email_body or "")


def test_patch_contact_saves_edited_body(
    client: TestClient, db_sessionmaker
) -> None:
    with db_sessionmaker() as session:
        session.add(_company(status=STATUS_QUALIFIED))
        session.add(
            models.Contact(
                id="apollo-1",
                company_id="c-ornek",
                first_name="Deniz",
                last_name="Korkmaz",
                email="deniz@ornekmakina.com.tr",
                email_status=STATUS_VALID,
                generated_email_body="Eski taslak.",
                is_selected=True,
                persona_rank=90,
            )
        )
        session.commit()

    response = client.patch(
        "/api/contacts/apollo-1",
        json={"generated_email_body": "Düzenlenmiş taslak."},
    )
    assert response.status_code == 200
    assert response.json()["generated_email_body"] == "Düzenlenmiş taslak."
    assert response.json()["email_status"] == STATUS_VALID
    assert response.json()["is_selected"] is True
