"""Yapılandırılmış ERP kanıtı yalnızca nitelikli şirketlerde yazılır."""

from __future__ import annotations

import json
from types import SimpleNamespace

from sqlalchemy import select

from api import models
from api.services.analysis import persist_analysis
from api.services.deep_research import (
    apply_deep_research,
    erp_from_facts,
    parse_deep_research_payload,
)
from api.services.scoring import STATUS_QUALIFIED, STATUS_REJECT

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


def _company(**kwargs) -> models.Company:
    values = {
        "id": "c-deep",
        "name": "Örnek Makina",
        "domain": "ornekmakina.com.tr",
        "website": "https://ornekmakina.com.tr",
        "industry": "Makina",
        "status": STATUS_QUALIFIED,
    }
    values.update(kwargs)
    return models.Company(**values)


def test_parse_unknown_erp_nulls_confidence() -> None:
    parsed = parse_deep_research_payload(
        {
            "erp": {"value": "unknown", "confidence": 0.9, "evidence_count": 0},
            "pain_hypothesis": "  yok  ",
        }
    )
    assert parsed.erp.value == "unknown"
    assert parsed.erp.confidence is None
    assert parsed.erp.evidence_count == 0
    assert parsed.pain_hypothesis is None


def test_parse_structured_erp_block() -> None:
    parsed = parse_deep_research_payload(
        {
            "erp": {"value": "Netsis", "confidence": 0.9, "evidence_count": 2},
            "pain_hypothesis": "Bayi siparişleri gecikiyor.",
        }
    )
    assert parsed.erp.as_dict() == {
        "value": "Netsis",
        "confidence": 0.9,
        "evidence_count": 2,
    }
    assert parsed.erp_signal == "Netsis"


def test_erp_from_facts_prefers_detected() -> None:
    facts = [
        models.CompanyFact(fact_type="dealer_network", value="42 bayi"),
        models.CompanyFact(fact_type="erp_detected", value="Nebim V3", confidence=0.8),
    ]
    evidence = erp_from_facts(facts)
    assert evidence is not None
    assert evidence.value == "Nebim"
    assert evidence.evidence_count == 1


def test_apply_deep_research_skips_reject(db_sessionmaker) -> None:
    with db_sessionmaker() as session:
        company = _company(status=STATUS_REJECT)
        session.add(company)
        session.commit()
        assert apply_deep_research(session, company, "Nebim ERP kullanıyoruz") is None
        session.refresh(company)
        assert company.erp_signal is None
        assert company.pain_hypothesis is None


def test_apply_deep_research_uses_fact_fallback_without_text(db_sessionmaker) -> None:
    with db_sessionmaker() as session:
        company = _company()
        session.add(company)
        session.add(
            models.CompanyFact(
                company_id="c-deep",
                fact_type="erp_detected",
                value="Logo Tiger",
                evidence_text="Logo Tiger kullanıyoruz.",
            )
        )
        session.commit()

        result = apply_deep_research(session, company, None)
        session.commit()
        session.refresh(company)

    assert result is not None
    assert result.erp.value == "Logo"
    assert company.erp_signal == "Logo"
    assert company.erp_evidence["erp"]["value"] == "Logo"
    assert company.pain_hypothesis is None


def test_apply_deep_research_writes_llm_fields(db_sessionmaker, monkeypatch) -> None:
    fake = FakeCompletions(
        {
            "erp": {"value": "Netsis", "confidence": 0.91, "evidence_count": 2},
            "pain_hypothesis": "Bayi siparişleri Excel ile Netsis arasında kopuk.",
        }
    )
    monkeypatch.setattr(
        "api.services.deep_research.openai_client",
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=fake)),
    )
    with db_sessionmaker() as session:
        company = _company()
        session.add(company)
        session.commit()
        result = apply_deep_research(
            session, company, "Türkiye genelinde 42 bayi. Netsis ERP."
        )
        session.commit()
        session.refresh(company)

    assert fake.calls
    assert result is not None
    assert company.erp_signal == "Netsis"
    assert company.erp_confidence == 0.91
    assert company.erp_evidence_count == 2
    assert "Excel" in (company.pain_hypothesis or "")


def test_persist_analysis_writes_deep_research_when_qualified(
    db_sessionmaker, monkeypatch
) -> None:
    fake = FakeCompletions(
        {
            "erp": {"value": "SAP", "confidence": 0.88, "evidence_count": 1},
            "pain_hypothesis": "Teklifler SAP dışı Excel’de hazırlanıyor.",
        }
    )
    monkeypatch.setattr(
        "api.services.deep_research.openai_client",
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=fake)),
    )
    monkeypatch.setattr("api.services.analysis.find_decision_makers", lambda *a, **k: 0)

    with db_sessionmaker() as session:
        company = _company(status="new")
        session.add(company)
        session.commit()
        _, scores = persist_analysis(
            session,
            company,
            {"facts": QUALIFIED_FACTS},
            source_type="website",
            source_text="SAP S/4HANA ve bayi ağı.",
        )
        session.commit()
        session.refresh(company)

    assert scores.qualification_status == STATUS_QUALIFIED
    assert scores.requires_deep_research is True
    assert fake.calls
    assert company.erp_signal == "SAP"
    assert company.erp_evidence["erp"]["value"] == "SAP"
    assert "Excel" in (company.pain_hypothesis or "")


def test_persist_analysis_skips_deep_research_when_rejected(
    db_sessionmaker, monkeypatch
) -> None:
    called = {"llm": 0}
    monkeypatch.setattr(
        "api.services.deep_research.openai_client",
        lambda: called.__setitem__("llm", called["llm"] + 1),
    )
    with db_sessionmaker() as session:
        company = _company(status="new")
        session.add(company)
        session.commit()
        persist_analysis(
            session,
            company,
            {"facts": []},
            source_type="website",
            source_text="SAP geçiyor ama şirket uygun değil.",
        )
        session.commit()
        stored = session.execute(
            select(models.Company).where(models.Company.id == "c-deep")
        ).scalar_one()

    assert called["llm"] == 0
    assert stored.status == STATUS_REJECT
    assert stored.erp_signal is None
    assert stored.pain_hypothesis is None
