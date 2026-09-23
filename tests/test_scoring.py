"""Step 14–20: kanıt çıkarma, ICP/Need puanı, yeterlilik ve derin araştırma.

Puanlama FastAPI'de, LLM'de değil. Fact bulunduysa spec'teki tam puan eklenir.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from api import models
from api.services.analysis import persist_analysis
from api.services.enrichment import (
    EXTRACTION_SYSTEM_PROMPT,
    PRODUCT_CONTEXT,
    _normalize_facts,
    assemble_analysis,
)
from api.services.scoring import (
    SCORE_VERSION,
    STATUS_HIGH_PRIORITY,
    STATUS_QUALIFIED,
    STATUS_REJECT,
    calculate_scores,
    qualify,
)

from tests.test_research_endpoint import BASE, COMPANY_ID, FAKE_ANALYSIS


def _fact(fact_type: str, value: str, evidence: str | None = None) -> dict[str, object]:
    return {
        "fact_type": fact_type,
        "value": value,
        "confidence": 1.0,
        "evidence_text": evidence or value,
    }


# --- prompt sözleşmesi -----------------------------------------------------


def test_extraction_prompt_does_not_ask_for_scores() -> None:
    prompt = EXTRACTION_SYSTEM_PROMPT.casefold()
    for forbidden in (
        "icp_score",
        "need_score",
        "timing_score",
        "reachability_score",
        "overall_score",
        '"scores"',
    ):
        assert forbidden not in prompt

    assert "evidence_text" in EXTRACTION_SYSTEM_PROMPT
    assert "employee_50_249" in EXTRACTION_SYSTEM_PROMPT
    assert "requires_deep_research" not in prompt
    assert "ai commercial operations platform" in prompt
    assert '"physical_products"' in EXTRACTION_SYSTEM_PROMPT
    assert '"pain_hypothesis"' in EXTRACTION_SYSTEM_PROMPT
    assert "sektör çıkarımı" in prompt
    assert "50–249" in PRODUCT_CONTEXT


# --- fact normalizasyonu ---------------------------------------------------


def test_facts_without_evidence_or_value_are_dropped() -> None:
    payload = {
        "facts": [
            _fact("dealer_network", "42 bayi", "42 yetkili bayi"),
            {
                "fact_type": "erp_detected",
                "value": "SAP",
                "confidence": 0.8,
                "evidence_text": "",
                "source_url": f"{BASE}/",
            },
            {
                "fact_type": "low_crm_maturity",
                "value": "",
                "confidence": 0.7,
                "evidence_text": "CRM kullanmıyoruz",
                "source_url": f"{BASE}/",
            },
        ]
    }
    facts = _normalize_facts(payload, {f"{BASE}/"}, f"{BASE}/")
    assert [fact["fact_type"] for fact in facts] == ["dealer_network"]


def test_llm_scores_in_payload_are_not_returned() -> None:
    payload = {
        "scores": {"overall_score": 99, "icp_score": 100},
        "facts": [_fact("physical_product", "Hidrolik pres", "Hidrolik pres.")],
    }
    facts = _normalize_facts(payload, set(), None)
    assert len(facts) == 1


# --- Step 4–8: yapılandırılmış analyzer profili ----------------------------


def _evidence(value: str, url: str = f"{BASE}/") -> dict[str, object]:
    return {
        "value": value,
        "confidence": 0.9,
        "evidence_text": f"{value}.",
        "source_url": url,
    }


FULL_PROFILE = {
    "b2b": True,
    "physical_products": True,
    "business_model": "distributor",
    "high_sku": True,
    "quote_based_sales": True,
    "dealer_network": True,
    "multiple_locations": True,
    "whatsapp_sales": True,
    "technical_documents": True,
    "erp_signal": True,
    "crm_signal": False,
    "pain_hypothesis": "Sipariş ve teklif süreçlerinde operasyonel darboğazlar yaşanması muhtemel.",
    "employees_50_249": True,
    "target_industry": "machinery",
    "turkey": True,
    "sales_team": True,
    "digital_presence": True,
    "sales_operations": True,
    "large_sales_team": True,
    "evidence": {
        "b2b": _evidence("B2B toptan"),
        "physical_products": _evidence("Hidrolik pres"),
        "business_model": _evidence("distributor"),
        "high_sku": _evidence("Yüksek SKU"),
        "quote_based_sales": _evidence("Teklif usulü"),
        "dealer_network": _evidence("42 yetkili bayi"),
        "multiple_locations": _evidence("Üç depo"),
        "whatsapp_sales": _evidence("WhatsApp sipariş"),
        "technical_documents": _evidence("Datasheet"),
        "erp_signal": _evidence("SAP"),
        "crm_signal": _evidence("Excel ile takip"),
        "pain_hypothesis": _evidence("Teklifler Excel'de"),
        "employees_50_249": _evidence("120 çalışan"),
        "target_industry": _evidence("machinery"),
        "turkey": _evidence("Türkiye"),
        "sales_team": _evidence("Satış ekibi"),
        "digital_presence": _evidence("e-ticaret"),
        "sales_operations": _evidence("Satış operasyon"),
        "large_sales_team": _evidence("Geniş satış kadrosu"),
    },
}


def test_profile_without_evidence_does_not_create_facts() -> None:
    assembled = assemble_analysis(
        {
            "b2b": True,
            "physical_products": True,
            "erp_signal": False,
            "crm_signal": False,
            "pain_hypothesis": "Sipariş ve teklif süreçlerinde operasyonel darboğazlar yaşanması muhtemel.",
        },
        {f"{BASE}/"},
        f"{BASE}/",
    )
    types = {fact["fact_type"] for fact in assembled["facts"]}
    assert "b2b" in types
    assert "physical_product" in types
    assert assembled["profile"]["b2b"] is True


def test_structured_profile_scores_icp_and_need_to_100() -> None:
    assembled = assemble_analysis(FULL_PROFILE, {f"{BASE}/"}, f"{BASE}/")
    scores = calculate_scores(assembled["facts"])
    assert scores.icp_score == 100
    assert scores.need_score == 100
    assert assembled["profile"]["business_model"] == "distributor"
    assert "darboğaz" in assembled["profile"]["pain_hypothesis"]


def test_crm_signal_true_blocks_low_crm_points() -> None:
    payload = {
        **FULL_PROFILE,
        "crm_signal": True,
        "evidence": {
            **FULL_PROFILE["evidence"],
            "crm_signal": _evidence("Salesforce"),
        },
        "facts": [_fact("low_crm_maturity", "Excel ile takip")],
    }
    assembled = assemble_analysis(payload, {f"{BASE}/"}, f"{BASE}/")
    types = {fact["fact_type"] for fact in assembled["facts"]}
    assert "low_crm_maturity" not in types
    scores = calculate_scores(assembled["facts"])
    assert scores.need_score == 95  # 100 - 5


def test_food_industry_does_not_score_target_industry() -> None:
    scores = calculate_scores(
        [_fact("target_industry", "Gıda üretimi", "Gıda üretimi yapıyoruz.")]
    )
    assert scores.icp_score == 0
    assert "target_industry" not in scores.matched_signals


def test_apollo_company_base_adds_icp_points() -> None:
    company = models.Company(
        id="c-base",
        name="Ünsal Makina",
        domain="unsalmakina.com",
        website="https://unsalmakina.com",
        country="Turkey",
        industry="Machinery",
        estimated_num_employees=120,
    )
    scores = calculate_scores(
        [
            _fact("b2b", "B2B"),
            _fact("physical_product", "Pres hattı"),
            _fact("quote_based_sales", "true"),
            _fact("high_sku", "true"),
            _fact("multiple_warehouse", "true"),
        ],
        company=company,
    )
    assert scores.icp_score >= 75
    assert scores.need_score >= 35
    assert "turkey" in scores.matched_signals
    assert "employee_50_249" in scores.matched_signals
    assert "target_industry" in scores.matched_signals
    assert scores.requires_deep_research is True


def test_industrial_industry_infers_need_signals() -> None:
    scores = calculate_scores(
        [
            _fact("b2b", "B2B"),
            _fact("physical_product", "Pres hattı"),
            _fact("target_industry", "Makina"),
            _fact("turkey", "Türkiye"),
            _fact("distributor_or_manufacturer", "Üretici"),
        ]
    )
    assert scores.icp_score == 65  # 15+15+15+10+10
    assert scores.need_score == 35  # quote 15 + sku 10 + locations 10
    assert scores.qualification_status == STATUS_QUALIFIED
    assert scores.requires_deep_research is True
    assert {"quote_based_sales", "high_sku", "multiple_warehouse"} <= set(
        scores.matched_signals
    )


def test_pain_labels_become_turkish_sentence() -> None:
    assembled = assemble_analysis(
        {"pain_hypotheses": ["quotation", "order_entry"], "target_industry": "unknown"},
        {f"{BASE}/"},
        f"{BASE}/",
    )
    assert assembled["profile"]["pain_hypothesis"].startswith("Sipariş ve teklif")


def test_business_model_does_not_count_as_b2b() -> None:
    scores = calculate_scores(
        [_fact("business_model", "distributor", "Yetkili distributor ağı.")]
    )
    assert scores.icp_score == 10
    assert scores.matched_signals == ("distributor_or_manufacturer",)


# --- Step 17 / 18: fact bulunduysa tam puan --------------------------------


def test_empty_facts_score_zero_and_reject() -> None:
    scores = calculate_scores([])
    assert scores.icp_score == 0
    assert scores.need_score == 0
    assert scores.overall_score == 0
    assert scores.qualification_status == STATUS_REJECT
    assert scores.requires_deep_research is False


def test_fact_without_value_and_evidence_does_not_affect_score() -> None:
    scored = calculate_scores([_fact("dealer_network", "42 bayi", "42 yetkili bayi")])
    ignored = calculate_scores(
        [{"fact_type": "dealer_network", "value": "", "evidence_text": ""}]
    )
    assert scored.need_score == 10
    assert ignored.need_score == 0


def test_boolean_flag_without_quote_still_scores() -> None:
    scores = calculate_scores(
        [{"fact_type": "quote_based_sales", "value": "true", "evidence_text": ""}]
    )
    assert scores.need_score == 15


def test_icp_points_are_added_when_each_signal_is_found() -> None:
    facts = [
        _fact("b2b", "B2B üretici"),
        _fact("physical_product", "Fiziksel ürün satıyoruz"),
        _fact("employee_50_249", "120 çalışan"),
        _fact("target_industry", "Makina imalat"),
        _fact("turkey", "Türkiye"),
        _fact("distributor_or_manufacturer", "Üretici"),
        _fact("sales_team", "Satış ekibi var"),
        _fact("digital_presence", "e-ticaret sitemiz"),
    ]
    scores = calculate_scores(facts)
    assert scores.icp_score == 100  # 15+15+15+15+10+10+10+10
    assert set(scores.matched_signals) >= {
        "b2b",
        "physical_product",
        "employee_50_249",
        "target_industry",
        "turkey",
        "distributor_or_manufacturer",
        "sales_team",
        "digital_presence",
    }


def test_need_points_are_added_when_each_signal_is_found() -> None:
    facts = [
        _fact("erp_detected", "SAP kullanıyoruz"),
        _fact("quote_based_sales", "Teklif usulü çalışıyoruz"),
        _fact("high_sku", "Yüksek SKU"),
        _fact("multiple_warehouse", "Birden fazla depo"),
        _fact("dealer_network", "42 yetkili bayi"),
        _fact("sales_operations", "Satış operasyon ekibi"),
        _fact("whatsapp_sales", "WhatsApp ile sipariş"),
        _fact("large_sales_team", "Büyük satış ekibi"),
        _fact("technical_docs", "Teknik döküman indirin"),
        _fact("low_crm_maturity", "Excel ile takip"),
    ]
    scores = calculate_scores(facts)
    assert scores.need_score == 100  # 15+15+10+10+10+10+10+10+5+5


def test_legacy_aliases_still_fire_signals() -> None:
    """Eski fact_type adları (erp_usage, product_lines) yeni kurallara bağlanır."""
    scores = calculate_scores(
        [
            _fact("erp_usage", "Netsis ERP", "Netsis ERP kullanıyoruz."),
            _fact("product_lines", "Hidrolik pres", "Hidrolik pres, CNC torna."),
            _fact("dealer_network", "42 bayi", "Anadolu genelinde 42 yetkili bayi."),
        ]
    )
    assert "erp_detected" in scores.matched_signals
    assert "physical_product" in scores.matched_signals
    assert "dealer_network" in scores.matched_signals
    assert scores.icp_score == 15
    assert scores.need_score == 25  # erp 15 + dealer 10


def test_employee_range_only_scores_50_to_249() -> None:
    in_range = calculate_scores(
        [_fact("company_size_signal", "120 çalışan", "Şirketimizde 120 kişi çalışıyor.")]
    )
    too_small = calculate_scores(
        [_fact("company_size_signal", "12 kişilik ekip", "12 kişilik ekibimiz var.")]
    )
    too_big = calculate_scores(
        [_fact("company_size_signal", "800 çalışan", "800 çalışanımız var.")]
    )
    assert in_range.icp_score == 15
    assert too_small.icp_score == 0
    assert too_big.icp_score == 0


def test_duplicate_signal_is_counted_once() -> None:
    scores = calculate_scores(
        [
            _fact("dealer_network", "42 bayi"),
            _fact("dealer_network", "Anadolu bayileri"),
        ]
    )
    assert scores.need_score == 10


def test_confidence_does_not_scale_points() -> None:
    """Spec: fact bulunduysa tam puan — güven çarpanı yok."""
    low = calculate_scores(
        [
            {
                "fact_type": "b2b",
                "value": "B2B",
                "confidence": 0.2,
                "evidence_text": "B2B müşterilere satıyoruz",
            }
        ]
    )
    assert low.icp_score == 15


def test_unknown_fact_type_without_keywords_is_ignored() -> None:
    scores = calculate_scores([_fact("favorite_color", "mavi", "Ofis rengimiz mavi")])
    assert scores.overall_score == 0
    assert scores.matched_signals == ()


def test_overall_is_average_of_icp_and_need() -> None:
    scores = calculate_scores(
        [
            _fact("b2b", "B2B"),
            _fact("dealer_network", "bayi ağı"),
        ]
    )
    assert scores.icp_score == 15
    assert scores.need_score == 10
    assert scores.overall_score == 12.5


def test_same_facts_always_produce_the_same_scores() -> None:
    assert calculate_scores(FAKE_ANALYSIS["facts"]) == calculate_scores(
        FAKE_ANALYSIS["facts"]
    )


# --- Step 19 yeterlilik ----------------------------------------------------


@pytest.mark.parametrize(
    ("icp", "need", "expected"),
    [
        (50, 90, STATUS_REJECT),
        (60, 0, STATUS_QUALIFIED),
        (60, 40, STATUS_QUALIFIED),
        (70, 70, STATUS_QUALIFIED),
        (75, 75, STATUS_QUALIFIED),
        (80, 90, STATUS_HIGH_PRIORITY),  # avg 85
        (90, 80, STATUS_HIGH_PRIORITY),
        (100, 50, STATUS_QUALIFIED),
        (74, 80, STATUS_QUALIFIED),
    ],
)
def test_qualification_matrix(icp: float, need: float, expected: str) -> None:
    assert qualify(icp, need) == expected


def test_high_priority_wins_over_qualified() -> None:
    assert qualify(90, 90) == STATUS_HIGH_PRIORITY


# --- Step 20 derin araştırma ----------------------------------------------


def test_deep_research_only_for_qualified_and_high_priority() -> None:
    reject = calculate_scores([_fact("b2b", "B2B")])
    assert reject.requires_deep_research is False
    assert reject.qualification_status == STATUS_REJECT

    # ICP 100 + Need 80 = overall 90 → high priority
    high = calculate_scores(
        [
            _fact("b2b", "B2B"),
            _fact("physical_product", "Fiziksel ürün"),
            _fact("employee_50_249", "80 kişi"),
            _fact("target_industry", "Makina"),
            _fact("turkey", "Türkiye"),
            _fact("distributor_or_manufacturer", "Üretici"),
            _fact("sales_team", "Satış ekibi"),
            _fact("digital_presence", "Web sitemiz"),
            _fact("erp_detected", "SAP"),
            _fact("quote_based_sales", "Teklif usulü"),
            _fact("dealer_network", "bayi ağı"),
            _fact("sales_operations", "Satış operasyon"),
            _fact("whatsapp_sales", "WhatsApp satış"),
            _fact("high_sku", "Yüksek SKU"),
        ]
    )
    assert high.icp_score == 100
    assert high.need_score == 80  # mevcut 70 + çıkarım multiple_warehouse 10
    assert high.overall_score == 90
    assert high.qualification_status == STATUS_HIGH_PRIORITY
    assert high.requires_deep_research is True

    qualified = calculate_scores(
        [
            _fact("b2b", "B2B"),
            _fact("physical_product", "Fiziksel ürün"),
            _fact("employee_50_249", "80 kişi"),
            _fact("target_industry", "Makina"),
            _fact("turkey", "Türkiye"),
            _fact("erp_detected", "SAP"),
            _fact("quote_based_sales", "Teklif usulü"),
            _fact("dealer_network", "bayi ağı"),
            _fact("sales_operations", "Satış operasyon"),
            _fact("whatsapp_sales", "WhatsApp satış"),
            _fact("high_sku", "Yüksek SKU"),
            _fact("multiple_warehouse", "Birden fazla depo"),
        ]
    )
    # Geçici kapı: ICP 70 >= 60 → qualified + derin araştırma.
    assert qualified.icp_score == 70
    assert qualified.need_score == 80
    assert qualified.qualification_status == STATUS_QUALIFIED
    assert qualified.requires_deep_research is True


def test_qualified_band_sets_deep_research() -> None:
    # ICP 80, Need 80, overall 80 — 75/75 eşiğini geçer, 85 ortalamayı geçmez.
    scores = calculate_scores(
        [
            _fact("b2b", "B2B"),
            _fact("physical_product", "Fiziksel ürün"),
            _fact("employee_50_249", "90 kişi"),
            _fact("target_industry", "Makina"),
            _fact("turkey", "Türkiye"),
            _fact("sales_team", "Satış ekibi"),
            _fact("erp_detected", "SAP"),
            _fact("quote_based_sales", "Teklif usulü"),
            _fact("dealer_network", "bayi ağı"),
            _fact("high_sku", "Yüksek SKU"),
            _fact("multiple_warehouse", "Birden fazla depo"),
            _fact("sales_operations", "Satış operasyon"),
            _fact("whatsapp_sales", "WhatsApp"),
        ]
    )
    assert scores.icp_score == 80
    assert scores.need_score == 80
    assert scores.overall_score == 80
    assert scores.qualification_status == STATUS_QUALIFIED
    assert scores.requires_deep_research is True


# --- kalıcılık -------------------------------------------------------------


def test_persist_analysis_writes_scores_status_and_flag(db_sessionmaker) -> None:
    with db_sessionmaker() as session:
        session.add(
            models.Company(
                id=COMPANY_ID,
                name="Örnek Makina",
                domain="ornekmakina.com.tr",
                status="new",
            )
        )
        session.commit()
        company = session.get(models.Company, COMPANY_ID)

        written, scores = persist_analysis(
            session,
            company,
            {
                "scores": {"overall_score": 99, "icp_score": 100},
                "facts": FAKE_ANALYSIS["facts"],
            },
            source_type="website",
        )
        session.commit()

        expected = calculate_scores(FAKE_ANALYSIS["facts"], company=company)
        assert written == 3
        assert scores.overall_score == pytest.approx(expected.overall_score)
        assert scores.overall_score != pytest.approx(99)
        assert scores.qualification_status == expected.qualification_status
        assert scores.requires_deep_research is expected.requires_deep_research
        assert scores.version == SCORE_VERSION

        stored = session.execute(
            select(models.Score).where(models.Score.company_id == COMPANY_ID)
        ).scalar_one()
        assert stored.overall_score == pytest.approx(expected.overall_score)
        assert stored.qualification_status == expected.qualification_status
        assert stored.requires_deep_research is expected.requires_deep_research
        assert stored.version == SCORE_VERSION

        company = session.get(models.Company, COMPANY_ID)
        assert company.status == expected.qualification_status

        fact = session.execute(
            select(models.CompanyFact).where(
                models.CompanyFact.company_id == COMPANY_ID,
                models.CompanyFact.fact_type == "dealer_network",
            )
        ).scalar_one()
        assert fact.evidence_text.startswith("Türkiye genelinde 42")


def test_persist_analysis_seeds_pain_from_profile(db_sessionmaker) -> None:
    with db_sessionmaker() as session:
        session.add(
            models.Company(
                id=COMPANY_ID,
                name="Örnek Makina",
                domain="ornekmakina.com.tr",
                status="new",
            )
        )
        session.commit()
        company = session.get(models.Company, COMPANY_ID)
        persist_analysis(
            session,
            company,
            {
                "facts": [_fact("b2b", "B2B")],
                "profile": {
                    "pain_hypothesis": (
                        "Sipariş ve teklif süreçlerinde operasyonel "
                        "darboğazlar yaşanması muhtemel."
                    )
                },
            },
            source_type="website",
        )
        session.commit()
        stored = session.get(models.Company, COMPANY_ID)
        assert "darboğaz" in (stored.pain_hypothesis or "")
