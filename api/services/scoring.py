"""Step 4–8 + 17–20 — belirlemimci ICP/Need puanı ve yeterlilik kapıları.

LLM skor üretmez. Puan, `company_facts` satırlarında ilgili sinyalin
**bulunup bulunmadığına** göre tam puan eklenerek hesaplanır (güven ile
ölçeklenmez). Aynı fact seti her çalıştırmada aynı sonucu verir.

ICP (100): B2B 15, fiziksel ürün 15, 50–249 çalışan 15, hedef sektör 15,
Türkiye 10, distribütör/üretici 10, satış ekibi 10, dijital varlık 10.

Need (100): ERP 15, teklif usulü 15, yüksek SKU 10, çoklu depo 10,
bayi ağı 10, satış operasyonu 10, WhatsApp satışı 10, büyük satış ekibi 10,
teknik doküman 5, düşük CRM olgunluğu 5.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Protocol

SCORE_VERSION = "4.0"

# --- yeterlilik durumları (Step 19) ----------------------------------------

STATUS_REJECT = "reject"
STATUS_LOW_PRIORITY = "low priority"
STATUS_REVIEW = "review"
STATUS_QUALIFIED = "qualified"
STATUS_HIGH_PRIORITY = "high priority"

# Step 20: yalnızca bu iki durumda derin araştırma açılır.
DEEP_RESEARCH_STATUSES = frozenset({STATUS_QUALIFIED, STATUS_HIGH_PRIORITY})

ICP_REJECT_BELOW = 60.0
NEED_LOW_PRIORITY_BELOW = 55.0
QUALIFIED_ICP = 75.0
QUALIFIED_NEED = 75.0
HIGH_PRIORITY_OVERALL = 85.0

# Analiz tamamlanmış sayılan durumlar (dashboard sayaçları).
QUALIFICATION_STATUSES = (
    STATUS_REJECT,
    STATUS_LOW_PRIORITY,
    STATUS_REVIEW,
    STATUS_QUALIFIED,
    STATUS_HIGH_PRIORITY,
)


class FactLike(Protocol):
    fact_type: str | None
    value: str | None
    evidence_text: str | None


@dataclass(frozen=True)
class Signal:
    """Tek bir spec kuralı: fact bulunursa `points` eklenir."""

    key: str
    points: float
    fact_types: frozenset[str]
    keywords: frozenset[str] = field(default_factory=frozenset)


# Step 17 — ICP (azami 100).
ICP_SIGNALS: tuple[Signal, ...] = (
    Signal("b2b", 15, frozenset({"b2b"}), frozenset({"b2b", "kurumsal", "toptan"})),
    Signal(
        "physical_product",
        15,
        frozenset({"physical_product", "physical_products", "product_lines"}),
        frozenset(
            {
                "fiziksel urun",
                "physical product",
                "imalat",
                "uretici",
                "hidrolik",
                "makina",
                "makine",
                "donanim",
                "hardware",
            }
        ),
    ),
    Signal(
        "employee_50_249",
        15,
        frozenset({"employee_50_249", "employees_50_249", "company_size_signal"}),
    ),
    Signal(
        "target_industry",
        15,
        frozenset({"target_industry", "industries_served"}),
        frozenset(
            {
                "makina",
                "makine",
                "machinery",
                "elektronik",
                "electronics",
                "endustriyel",
                "endustriyel ekipman",
                "industrial equipment",
                "hidrolik",
                "cnc",
                "otomasyon",
            }
        ),
    ),
    Signal(
        "turkey",
        10,
        frozenset({"turkey", "country", "headquarters", "location"}),
        frozenset({"turkiye", "turkey", "istanbul", "ankara", "izmir", "konya", "bursa"}),
    ),
    Signal(
        "distributor_or_manufacturer",
        10,
        frozenset(
            {
                "distributor_or_manufacturer",
                "manufacturer",
                "distributor",
                "business_model",
            }
        ),
        frozenset({"uretici", "imalatci", "distributor", "manufacturer", "fabrika"}),
    ),
    Signal(
        "sales_team",
        10,
        frozenset({"sales_team"}),
        frozenset({"satis ekibi", "sales team", "saha satisi", "satis kadrosu"}),
    ),
    Signal(
        "digital_presence",
        10,
        frozenset({"digital_presence", "website", "ecommerce_presence"}),
        frozenset({"e-ticaret", "ecommerce", "online magaza", "dijital varlik"}),
    ),
)

# Step 18 — Need (azami 100).
NEED_SIGNALS: tuple[Signal, ...] = (
    Signal(
        "erp_detected",
        15,
        frozenset({"erp_detected", "erp_usage", "erp_signal"}),
        frozenset({"erp", "sap", "netsis", "logo tiger", "mikro", "nebim", "ika"}),
    ),
    Signal(
        "quote_based_sales",
        15,
        frozenset({"quote_based_sales"}),
        frozenset({"teklif usulu", "quote-based", "rfq", "proje bazli", "siparis uzerine"}),
    ),
    Signal(
        "high_sku",
        10,
        frozenset({"high_sku"}),
        frozenset({"yuksek sku", "high sku", "genis katalog", "binlerce urun", "sku"}),
    ),
    Signal(
        "multiple_warehouse",
        10,
        frozenset({"multiple_warehouse", "multiple_locations"}),
        frozenset({"birden fazla depo", "multiple warehouse", "coklu depo", "depolarimiz"}),
    ),
    Signal(
        "dealer_network",
        10,
        frozenset({"dealer_network"}),
        frozenset({"bayi agi", "yetkili bayi", "dealer network", "distribitor agi"}),
    ),
    Signal(
        "sales_operations",
        10,
        frozenset({"sales_operations"}),
        frozenset({"satis operasyon", "sales operations", "satis operasyonu"}),
    ),
    Signal(
        "whatsapp_sales",
        10,
        frozenset({"whatsapp_sales"}),
        frozenset({"whatsapp", "wp ile satis", "whatsapp satisi"}),
    ),
    Signal(
        "large_sales_team",
        10,
        frozenset({"large_sales_team"}),
        frozenset({"buyuk satis ekibi", "large sales team", "genis satis kadrosu"}),
    ),
    Signal(
        "technical_docs",
        5,
        frozenset({"technical_docs", "technical_documents", "catalog_available"}),
        frozenset({"teknik dokuman", "teknik katalog", "datasheet", "cad dosya"}),
    ),
    Signal(
        "low_crm_maturity",
        5,
        frozenset({"low_crm_maturity"}),
        frozenset({"excel", "crm yok", "crm kullanmiyoruz", "manuel takip", "spreadsheet"}),
    ),
)

_HIGH_CRM = frozenset({"salesforce", "hubspot", "dynamics", "pipedrive", "zoho crm"})
_MATURE_CRM_TYPES = frozenset({"crm_signal", "crm_detected"})
_DISTRIBUTOR_TOKENS = frozenset(
    {
        "distributor",
        "manufacturer",
        "uretici",
        "imalatci",
        "fabrika",
        "distribitor",
    }
)
_TARGET_INDUSTRY_TOKENS = frozenset(
    {
        "makina",
        "makine",
        "machinery",
        "elektronik",
        "electronics",
        "endustriyel",
        "endustriyel ekipman",
        "industrial equipment",
        "hidrolik",
        "cnc",
        "otomasyon",
    }
)
_EMPLOYEE_FACT_TYPES = frozenset({"employee_50_249", "employees_50_249"})
_EMPLOYEE_RANGE = (50, 249)
_NUMBER = re.compile(r"\d{1,3}(?:[.\s]\d{3})+|\d+")

_TR_FOLD = str.maketrans(
    {
        "ı": "i",
        "ğ": "g",
        "ü": "u",
        "ş": "s",
        "ö": "o",
        "ç": "c",
        "â": "a",
        "î": "i",
        "û": "u",
    }
)


def _fold(text: str) -> str:
    return (text or "").casefold().translate(_TR_FOLD)


def _as_int(raw: str) -> int | None:
    digits = raw.replace(".", "").replace(" ", "")
    if not digits.isdigit():
        return None
    return int(digits)


def _employee_in_mid_market(text: str) -> bool:
    """Metindeki sayılardan en az biri 50–249 aralığındaysa True."""
    values = [_as_int(match.group(0)) for match in _NUMBER.finditer(text)]
    numbers = [value for value in values if value is not None]
    return any(_EMPLOYEE_RANGE[0] <= number <= _EMPLOYEE_RANGE[1] for number in numbers)


def is_target_industry(text: str) -> bool:
    folded = _fold(text)
    return any(token in folded for token in _TARGET_INDUSTRY_TOKENS)


def is_distributor_or_manufacturer(text: str) -> bool:
    folded = _fold(text)
    return any(token in folded for token in _DISTRIBUTOR_TOKENS)


def _has_mature_crm(facts: list[tuple[str, str]]) -> bool:
    for fact_type, text in facts:
        type_key = _fold(fact_type).replace(" ", "_").replace("-", "_")
        if type_key in _MATURE_CRM_TYPES or fact_type in _MATURE_CRM_TYPES:
            if "false" in text or "yok" in text:
                continue
            return True
        if any(token in text for token in _HIGH_CRM):
            return True
    return False


@dataclass(frozen=True)
class Scores:
    icp_score: float
    need_score: float
    overall_score: float
    qualification_status: str
    requires_deep_research: bool
    timing_score: float = 0.0
    reachability_score: float = 0.0
    version: str = SCORE_VERSION
    matched_signals: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, float | str | bool]:
        return {
            "icp_score": self.icp_score,
            "need_score": self.need_score,
            "timing_score": self.timing_score,
            "reachability_score": self.reachability_score,
            "overall_score": self.overall_score,
            "qualification_status": self.qualification_status,
            "requires_deep_research": self.requires_deep_research,
        }


def _usable_facts(
    facts: Iterable[FactLike | Mapping[str, object]],
) -> list[tuple[str, str]]:
    """Kanıtı ve değeri olan fact'leri (tip, arama metni) çiftine indirger."""
    usable: list[tuple[str, str]] = []
    for fact in facts:
        if isinstance(fact, Mapping):
            fact_type = str(fact.get("fact_type") or "").strip()
            value = str(fact.get("value") or "").strip()
            evidence = str(fact.get("evidence_text") or "").strip()
        else:
            fact_type = str(fact.fact_type or "").strip()
            value = str(fact.value or "").strip()
            evidence = str(fact.evidence_text or "").strip()

        if not fact_type or not value or not evidence:
            continue
        usable.append((fact_type, _fold(f"{fact_type} {value} {evidence}")))
    return usable


def _signal_found(signal: Signal, facts: list[tuple[str, str]]) -> bool:
    """Spec: ilgili fact bulunduysa puan ver. Güven ile çarpılmaz."""
    if signal.key == "low_crm_maturity" and _has_mature_crm(facts):
        return False
    for fact_type, text in facts:
        type_key = _fold(fact_type).replace(" ", "_").replace("-", "_")
        if type_key in signal.fact_types or fact_type in signal.fact_types:
            if signal.key == "employee_50_249":
                # Canonical extractor tipi bu aralığı zaten seçmiştir.
                if type_key in _EMPLOYEE_FACT_TYPES or fact_type in _EMPLOYEE_FACT_TYPES:
                    return True
                return _employee_in_mid_market(text)
            if signal.key == "target_industry":
                if is_target_industry(text):
                    return True
                continue
            if signal.key == "distributor_or_manufacturer":
                if type_key == "business_model" or fact_type == "business_model":
                    if is_distributor_or_manufacturer(text):
                        return True
                    continue
            if signal.key == "low_crm_maturity":
                if fact_type == "low_crm_maturity" or type_key == "low_crm_maturity":
                    return True
                if any(token in text for token in _HIGH_CRM):
                    return False
            return True
        if signal.key == "employee_50_249" and _employee_in_mid_market(text):
            return True
        if signal.key == "target_industry":
            continue
        if signal.keywords and any(keyword in text for keyword in signal.keywords):
            if signal.key == "low_crm_maturity" and any(token in text for token in _HIGH_CRM):
                continue
            return True
    return False


def _dimension_score(
    facts: list[tuple[str, str]], signals: tuple[Signal, ...]
) -> tuple[float, list[str]]:
    matched: list[str] = []
    total = 0.0
    for signal in signals:
        if _signal_found(signal, facts):
            total += signal.points
            matched.append(signal.key)
    return min(100.0, total), matched


def qualify(icp: float, need: float) -> str:
    """Step 19 — ICP/Need'den yeterlilik durumu.

    Çakışmada daha güçlü etiket kazanır: high priority > qualified.
    Dört kuralın kapsamadığı bant (`ICP >= 60`, `Need >= 55`, overall < 85,
    henüz 75/75 değil) `review` olur; belirsiz bırakılmaz.
    """
    overall = (icp + need) / 2.0
    if overall >= HIGH_PRIORITY_OVERALL:
        return STATUS_HIGH_PRIORITY
    if icp >= QUALIFIED_ICP and need >= QUALIFIED_NEED:
        return STATUS_QUALIFIED
    if icp >= ICP_REJECT_BELOW and need < NEED_LOW_PRIORITY_BELOW:
        return STATUS_LOW_PRIORITY
    if icp < ICP_REJECT_BELOW:
        return STATUS_REJECT
    return STATUS_REVIEW


def calculate_scores(facts: Iterable[FactLike | Mapping[str, object]]) -> Scores:
    """`company_facts` satırlarından ICP, Need, yeterlilik ve derin-araştırma bayrağı."""
    usable = _usable_facts(facts)
    icp, icp_hits = _dimension_score(usable, ICP_SIGNALS)
    need, need_hits = _dimension_score(usable, NEED_SIGNALS)
    overall = round((icp + need) / 2.0, 1)
    status = qualify(icp, need)

    return Scores(
        icp_score=icp,
        need_score=need,
        overall_score=overall,
        qualification_status=status,
        requires_deep_research=status in DEEP_RESEARCH_STATUSES,
        matched_signals=tuple(icp_hits + need_hits),
    )
