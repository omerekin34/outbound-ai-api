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

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol

SCORE_VERSION = "4.2"

logger = logging.getLogger(__name__)

# --- yeterlilik durumları (Step 19) ----------------------------------------

STATUS_REJECT = "reject"
STATUS_LOW_PRIORITY = "low priority"
STATUS_REVIEW = "review"
STATUS_QUALIFIED = "qualified"
STATUS_HIGH_PRIORITY = "high priority"
STATUS_TIMEOUT = "timeout"
STATUS_FAILED = "failed"

# Step 20: yalnızca bu iki durumda derin araştırma açılır.
DEEP_RESEARCH_STATUSES = frozenset({STATUS_QUALIFIED, STATUS_HIGH_PRIORITY})

ICP_REJECT_BELOW = 60.0
NEED_LOW_PRIORITY_BELOW = 55.0
QUALIFIED_ICP = 75.0
QUALIFIED_NEED = 75.0
HIGH_PRIORITY_OVERALL = 85.0
# Geçici E2E kapısı: ICP >= 60 → qualified + derin araştırma.
TEMP_QUALIFY_ICP_AT = 60.0

# Makine / elektronik / endüstriyel tespitinde Need'e eklenen çıkarımlar.
INFERRED_NEED_KEYS = frozenset(
    {"quote_based_sales", "high_sku", "multiple_warehouse"}
)

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


class CompanyLike(Protocol):
    name: str | None
    domain: str | None
    website: str | None
    country: str | None
    industry: str | None
    estimated_num_employees: int | None


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

        if not fact_type:
            continue
        if not value and not evidence:
            continue
        if not value:
            value = fact_type
        if not evidence:
            evidence = value
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

    Geçici E2E kuralı: ICP >= 60 ise qualified (Need beklenmez).
    Overall >= 85 hâlâ high priority'dir.
    """
    overall = (icp + need) / 2.0
    if overall >= HIGH_PRIORITY_OVERALL:
        return STATUS_HIGH_PRIORITY
    if icp >= TEMP_QUALIFY_ICP_AT:
        return STATUS_QUALIFIED
    return STATUS_REJECT


def should_infer_industrial_need(matched_icp: Iterable[str]) -> bool:
    """Hedef sektör (makine / elektronik / endüstriyel) varsa Need çıkarımı."""
    return "target_industry" in set(matched_icp)


def _apply_inferred_need(
    need: float, need_hits: list[str], icp_hits: list[str]
) -> tuple[float, list[str]]:
    if not should_infer_industrial_need(icp_hits):
        return need, need_hits
    hits = list(need_hits)
    total = need
    for signal in NEED_SIGNALS:
        if signal.key in INFERRED_NEED_KEYS and signal.key not in hits:
            total += signal.points
            hits.append(signal.key)
    return min(100.0, total), hits


_TRUE_VALUES = frozenset({"true", "1", "yes", "evet"})

_PROFILE_FLAG_FACTS: tuple[tuple[str, str, str], ...] = (
    ("b2b", "b2b", "B2B"),
    ("physical_products", "physical_product", "Fiziksel ürün"),
    ("high_sku", "high_sku", "Yüksek SKU"),
    ("quote_based_sales", "quote_based_sales", "Teklif usulü satış"),
    ("dealer_network", "dealer_network", "Bayi ağı"),
    ("multiple_locations", "multiple_warehouse", "Çoklu lokasyon"),
    ("whatsapp_sales", "whatsapp_sales", "WhatsApp satışı"),
    ("technical_documents", "technical_docs", "Teknik doküman"),
    ("erp_signal", "erp_detected", "ERP"),
    ("employees_50_249", "employee_50_249", "50–249 çalışan"),
    ("turkey", "turkey", "Türkiye"),
    ("sales_team", "sales_team", "Satış ekibi"),
    ("digital_presence", "digital_presence", "Dijital varlık"),
    ("sales_operations", "sales_operations", "Satış operasyonu"),
    ("large_sales_team", "large_sales_team", "Büyük satış ekibi"),
)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str):
        return value.strip().casefold() in _TRUE_VALUES
    return False


def _synthetic_fact(fact_type: str, value: str, evidence: str) -> dict[str, str]:
    return {
        "fact_type": fact_type,
        "value": value,
        "evidence_text": evidence,
    }


def company_base_facts(company: CompanyLike | None) -> list[dict[str, str]]:
    """Apollo / şirket kaydından ICP taban puanları (TR, 50–249, makine)."""
    if company is None:
        return []
    facts: list[dict[str, str]] = []
    name = f"{company.name or ''} {company.domain or ''} {company.industry or ''}"
    country = (company.country or "Turkey").strip()
    if _fold(country) in {"turkey", "turkiye", "tr"}:
        facts.append(_synthetic_fact("turkey", country, f"Ülke: {country}"))

    employees = company.estimated_num_employees
    if employees is not None and _EMPLOYEE_RANGE[0] <= employees <= _EMPLOYEE_RANGE[1]:
        facts.append(
            _synthetic_fact(
                "employee_50_249",
                str(employees),
                f"{employees} çalışan (Apollo)",
            )
        )
    elif employees is None and is_target_industry(name):
        facts.append(
            _synthetic_fact(
                "employee_50_249",
                "50–249",
                "Orta ölçekli B2B üretici / distribütör (ICP tabanı).",
            )
        )

    industry = (company.industry or "").strip() or name
    if is_target_industry(industry):
        facts.append(
            _synthetic_fact(
                "target_industry",
                company.industry or "Machinery",
                f"Sektör: {industry}",
            )
        )
        facts.append(
            _synthetic_fact(
                "distributor_or_manufacturer",
                "manufacturer",
                f"Makine / endüstriyel üretici veya elektronik distribütör: {name}",
            )
        )

    if company.website:
        facts.append(
            _synthetic_fact(
                "digital_presence",
                company.website,
                f"Web sitesi: {company.website}",
            )
        )
    return facts


def profile_flag_facts(profile: Mapping[str, Any] | None) -> list[dict[str, str]]:
    """Analyzer boolean bayraklarını puanlanabilir fact'e çevirir."""
    if not profile:
        return []
    facts: list[dict[str, str]] = []
    for field, fact_type, label in _PROFILE_FLAG_FACTS:
        if _truthy(profile.get(field)):
            facts.append(_synthetic_fact(fact_type, label, f"{label} (analiz bayrağı)"))
    model = str(profile.get("business_model") or "").strip().casefold()
    if is_distributor_or_manufacturer(model):
        facts.append(_synthetic_fact("business_model", model, f"İş modeli: {model}"))
    industry = str(profile.get("target_industry") or "").strip()
    if industry and is_target_industry(industry):
        facts.append(
            _synthetic_fact("target_industry", industry, f"Sektör: {industry}")
        )
    if profile.get("crm_signal") is False:
        facts.append(
            _synthetic_fact(
                "low_crm_maturity",
                "Düşük CRM olgunluğu",
                "CRM sinyali yok (analiz bayrağı).",
            )
        )
    return facts


def _log_breakdown(
    label: str,
    icp: float,
    icp_hits: list[str],
    need: float,
    need_hits: list[str],
    overall: float,
    status: str,
) -> None:
    icp_parts = []
    for signal in ICP_SIGNALS:
        mark = "HIT" if signal.key in icp_hits else "—"
        icp_parts.append(f"{signal.key}={signal.points:.0f}[{mark}]")
    need_parts = []
    for signal in NEED_SIGNALS:
        mark = "HIT" if signal.key in need_hits else "—"
        need_parts.append(f"{signal.key}={signal.points:.0f}[{mark}]")
    message = (
        f"[score] {label} | ICP={icp:.0f} ({', '.join(icp_parts)}) | "
        f"Need={need:.0f} ({', '.join(need_parts)}) | "
        f"overall={overall} | status={status}"
    )
    print(message, flush=True)
    logger.info(message)


def calculate_scores(
    facts: Iterable[FactLike | Mapping[str, object]],
    *,
    company: CompanyLike | None = None,
    profile: Mapping[str, Any] | None = None,
) -> Scores:
    """Fact + Apollo/şirket tabanı + analyzer bayraklarından ICP/Need."""
    merged: list[FactLike | Mapping[str, object]] = [
        *list(facts),
        *company_base_facts(company),
        *profile_flag_facts(profile),
    ]
    usable = _usable_facts(merged)
    icp, icp_hits = _dimension_score(usable, ICP_SIGNALS)
    need, need_hits = _dimension_score(usable, NEED_SIGNALS)
    need, need_hits = _apply_inferred_need(need, need_hits, icp_hits)
    overall = round((icp + need) / 2.0, 1)
    status = qualify(icp, need)
    label = getattr(company, "name", None) or getattr(company, "domain", None) or "company"
    _log_breakdown(str(label), icp, icp_hits, need, need_hits, overall, status)

    return Scores(
        icp_score=icp,
        need_score=need,
        overall_score=overall,
        qualification_status=status,
        requires_deep_research=status in DEEP_RESEARCH_STATUSES,
        matched_signals=tuple(icp_hits + need_hits),
    )
