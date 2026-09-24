"""Dış servisler: Firecrawl istemcisi ve AI Company Analyzer.

İstemciler tembel (lazy) oluşturulur: API anahtarı yoksa uygulama yine
ayağa kalkar, yalnızca ilgili endpoint 503 döner.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from fastapi import HTTPException, status

from api.config import get_settings
from api.services.scoring import is_target_industry
from api.services.website_research import ScrapedPage

logger = logging.getLogger(__name__)
settings = get_settings()

# Step 4–8: model ürünümüzü bilerek yapılandırılmış ICP/Need profili çıkarır.
# Puan üretmez. ICP/Need/overall `api.services.scoring` içinde, kanıtlı
# fact'lerden hesaplanır. Modelden gelen `scores` yok sayılır.

PRODUCT_CONTEXT = (
    "AI Commercial Operations Platform: orta ölçekli (50–249 çalışan) "
    "Türkiye'deki B2B fiziksel ürün şirketleri için satış, teklif, sipariş, "
    "stok ve B2B iletişimi otomatikleştirir. Hedef sektörler: makine, "
    "elektronik, endüstriyel ekipman."
)

EXTRACTION_SYSTEM_PROMPT = """Sen bir B2B kanıt analistisin. Ürünümüz: AI Commercial Operations Platform. Orta ölçekli (50–249 çalışan) Türkiye'deki B2B fiziksel ürün şirketlerinde (makine, elektronik, endüstriyel ekipman) satış, teklif, sipariş, stok ve B2B iletişimi otomatikleştirir.

Sana bir şirketin web sitesinden taranmış sayfalar verilecek. Her sayfanın kategorisi ve URL'si belirtilmiştir.

TEK GÖREVİN: sayfada geçen kanıtlardan ve sektör mantığından aşağıdaki JSON profilini çıkarmak.

YAPMA:
- ICP, Need, Timing, Reachability veya overall puanı HESAPLAMA.
- `scores` alanı DÖNDÜRME.
- Kişi, e-posta, ERP adı veya sayı uydurma.
- URL uydurma.

SEKTÖR ÇIKARIMI (zorunlu): Makine / endüstriyel üretici veya elektronik distribütör tespit ettiysen
Türk siteleri "ERP kullanıyoruz" / "teklif usulü çalışıyoruz" yazmasa bile şunları TRUE yap:
- `quote_based_sales`
- `high_sku`
- `multiple_locations`
evidence_text'e "Sektör çıkarımı: …" diye yaz; uydurma alıntı yapma.

HER boolean alan (true VEYA false) için `evidence` içinde gerekçe zorunludur:
- `reasoning`: 1 kısa cümle — neden True veya False dediğini metne dayandır.
  Örnek True: "Hakkımızda sayfasında 'kurumsal müşterilere toptan satış' yazıyor."
  Örnek False: "Çalışan sayısı veya ekip büyüklüğü metinde geçmiyor."
- `value`: kısa, somut olgu (true ise)
- `evidence_text`: sayfadan BİREBİR cümle veya sektör çıkarımı cümlesi
- `source_url`: yalnızca verilen URL'lerden biri
- `confidence`: 0.0–1.0

`employees_50_249` yalnızca çalışan sayısı 50–249 arasındaysa true.
`target_industry` yalnızca makine / elektronik / endüstriyel ekipman kanıtı varsa (machinery | electronics | industrial_equipment | unknown).
`business_model` yalnızca kanıt varsa: distributor | manufacturer | unknown.
`crm_signal` true ise olgun bir CRM adı geçiyor demektir. CRM yok / Excel / manuel takip varsa false.
`pain_hypothesis`: TEK doğal Türkçe cümle. Dizi, etiket veya virgüllü liste YAZMA.
Örnek: "Sipariş ve teklif süreçlerinde operasyonel darboğazlar yaşanması muhtemel."

Çıktıyı TAM olarak bu JSON şemasıyla ver:
{
  "b2b": true,
  "physical_products": true,
  "business_model": "distributor",
  "high_sku": true,
  "quote_based_sales": true,
  "dealer_network": true,
  "multiple_locations": true,
  "whatsapp_sales": true,
  "technical_documents": true,
  "erp_signal": false,
  "crm_signal": false,
  "pain_hypothesis": "Sipariş ve teklif süreçlerinde operasyonel darboğazlar yaşanması muhtemel.",
  "employees_50_249": true,
  "target_industry": "machinery",
  "turkey": true,
  "sales_team": true,
  "digital_presence": true,
  "sales_operations": false,
  "large_sales_team": false,
  "evidence": {
    "b2b": {
      "value": "B2B toptan satış",
      "confidence": 0.9,
      "reasoning": "Hakkımızda sayfası kurumsal / toptan müşteri dilini kullanıyor.",
      "evidence_text": "Kurumsal müşterilere toptan satış yapıyoruz.",
      "source_url": "https://ornek.com/hakkimizda"
    },
    "sales_operations": {
      "value": "Satış operasyonu yok",
      "confidence": 0.6,
      "reasoning": "Metinde satış operasyonu, sipariş süreci veya CRM ekibi geçmiyor.",
      "evidence_text": "Satış operasyonu kanıtı yok.",
      "source_url": "https://ornek.com/hakkimizda"
    }
  }
}

İsteğe bağlı `facts` dizisi eski kanıt satırları içindir; puan yine yalnızca kanıtlı alanlardan hesaplanır.
`employee_50_249` yalnızca 50–249 çalışan kanıtı varsa yaz.
`low_crm_maturity` yalnızca CRM yoksa / Excel / manuel takip varsa yaz."""


def _missing_key(service: str, env_var: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"{service} yapılandırılmamış. .env dosyasına {env_var} ekleyin.",
    )


@lru_cache(maxsize=1)
def _build_firecrawl() -> Any:
    from firecrawl import Firecrawl

    return Firecrawl(api_key=settings.firecrawl_api_key)


@lru_cache(maxsize=1)
def _build_openai() -> Any:
    from openai import OpenAI

    return OpenAI(api_key=settings.openai_api_key)


def firecrawl_client() -> Any:
    """Firecrawl istemcisi; anahtar yoksa 503 yükseltir."""
    if not settings.firecrawl_api_key:
        raise _missing_key("Firecrawl", "FIRECRAWL_API_KEY")
    return _build_firecrawl()


def openai_client() -> Any:
    """OpenAI istemcisi; anahtar yoksa 503 yükseltir."""
    if not settings.openai_api_key:
        raise _missing_key("OpenAI", "OPENAI_API_KEY")
    return _build_openai()


def build_pages_prompt(
    pages: list[ScrapedPage],
    *,
    chars_per_page: int,
    total_chars: int,
) -> str:
    """Taranan sayfaları, karakter bütçesini aşmadan tek bir prompt'a çevirir.

    Sayfalar seçim sırasında geldiği için (anasayfa önce, sonra kategori
    önceliği) bütçe dolduğunda kesilen sayfalar en az öncelikli olanlardır.
    """
    sections: list[str] = []
    remaining = total_chars

    for index, page in enumerate(pages, start=1):
        if remaining <= 0:
            break
        budget = min(chars_per_page, remaining)
        content = page.markdown[:budget]
        remaining -= len(content)

        truncated = " (kısaltıldı)" if len(page.markdown) > len(content) else ""
        sections.append(
            f"### SAYFA {index}\n"
            f"Kategori: {page.category}\n"
            f"URL: {page.url}\n"
            f"İçerik{truncated}:\n{content}"
        )

    return "\n\n".join(sections)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


PROFILE_BOOL_TO_FACT: dict[str, tuple[str, str]] = {
    "b2b": ("b2b", "B2B"),
    "physical_products": ("physical_product", "Fiziksel ürün"),
    "high_sku": ("high_sku", "Yüksek SKU"),
    "quote_based_sales": ("quote_based_sales", "Teklif usulü satış"),
    "dealer_network": ("dealer_network", "Bayi ağı"),
    "multiple_locations": ("multiple_warehouse", "Birden fazla lokasyon / depo"),
    "whatsapp_sales": ("whatsapp_sales", "WhatsApp satışı"),
    "technical_documents": ("technical_docs", "Teknik doküman"),
    "erp_signal": ("erp_detected", "ERP"),
    "employees_50_249": ("employee_50_249", "50–249 çalışan"),
    "turkey": ("turkey", "Türkiye"),
    "sales_team": ("sales_team", "Satış ekibi"),
    "digital_presence": ("digital_presence", "Dijital varlık"),
    "sales_operations": ("sales_operations", "Satış operasyonu"),
    "large_sales_team": ("large_sales_team", "Büyük satış ekibi"),
}

_DISTRIBUTOR_MODELS = frozenset(
    {"distributor", "manufacturer", "uretici", "üretici", "imalatci", "imalatçı"}
)
_TARGET_INDUSTRY_VALUES = frozenset(
    {
        "machinery",
        "electronics",
        "industrial_equipment",
        "industrial",
        "makina",
        "makine",
        "elektronik",
        "endustriyel",
    }
)
_PAIN_LABELS = frozenset(
    {"quotation", "order_entry", "inventory", "dealer_coordination"}
)
DEFAULT_PAIN_HYPOTHESIS = (
    "Sipariş ve teklif süreçlerinde operasyonel darboğazlar yaşanması muhtemel."
)
INFERRED_NEED_FACTS: tuple[tuple[str, str, str], ...] = (
    ("quote_based_sales", "quote_based_sales", "Teklif usulü satış (sektör çıkarımı)"),
    ("high_sku", "high_sku", "Yüksek SKU (sektör çıkarımı)"),
    ("multiple_locations", "multiple_warehouse", "Çoklu lokasyon (sektör çıkarımı)"),
)
INFERRED_NEED_EVIDENCE = (
    "Sektör çıkarımı: makine / elektronik / endüstriyel operasyonlarda "
    "teklif usulü satış, geniş katalog ve birden fazla lokasyon varsayılır."
)


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        folded = value.strip().casefold()
        if folded in {"true", "yes", "1", "evet"}:
            return True
        if folded in {"false", "no", "0", "hayir", "hayır"}:
            return False
    return None


def _evidence_for(payload: dict[str, Any], field: str) -> dict[str, Any] | None:
    raw = payload.get("evidence")
    if isinstance(raw, dict):
        item = raw.get(field)
        if isinstance(item, dict):
            return item
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and str(item.get("field") or "") == field:
                return item
    nested = payload.get(f"{field}_evidence")
    if isinstance(nested, dict):
        return nested
    return None


def _fact_from_evidence(
    fact_type: str,
    default_value: str,
    evidence: dict[str, Any],
    allowed_urls: set[str],
    default_url: str | None,
) -> dict[str, Any] | None:
    value = str(evidence.get("value") or default_value).strip()
    evidence_text = str(evidence.get("evidence_text") or "").strip()
    reasoning = str(evidence.get("reasoning") or "").strip()
    if reasoning and evidence_text and reasoning not in evidence_text:
        evidence_text = f"{reasoning} {evidence_text}"
    elif reasoning and not evidence_text:
        evidence_text = reasoning
    if not value or not evidence_text:
        return None
    source_url = evidence.get("source_url")
    if not isinstance(source_url, str) or source_url not in allowed_urls:
        source_url = default_url
    return {
        "fact_type": fact_type,
        "value": value,
        "confidence": _clamp(_as_float(evidence.get("confidence"), 1.0), 0.0, 1.0),
        "evidence_text": evidence_text,
        "source_url": source_url,
    }


def normalize_profile(payload: dict[str, Any]) -> dict[str, Any]:
    """Analyzer JSON'unu kanonik profile indirger; skor içermez."""
    model = str(payload.get("business_model") or "unknown").strip().casefold()
    if model not in _DISTRIBUTOR_MODELS and model != "unknown":
        model = "unknown"
    industry = str(payload.get("target_industry") or "unknown").strip().casefold()
    if industry not in _TARGET_INDUSTRY_VALUES:
        industry = "unknown"
    return {
        "b2b": _coerce_bool(payload.get("b2b")) is True,
        "physical_products": _coerce_bool(payload.get("physical_products")) is True,
        "business_model": model,
        "high_sku": _coerce_bool(payload.get("high_sku")) is True,
        "quote_based_sales": _coerce_bool(payload.get("quote_based_sales")) is True,
        "dealer_network": _coerce_bool(payload.get("dealer_network")) is True,
        "multiple_locations": _coerce_bool(payload.get("multiple_locations")) is True,
        "whatsapp_sales": _coerce_bool(payload.get("whatsapp_sales")) is True,
        "technical_documents": _coerce_bool(payload.get("technical_documents")) is True,
        "erp_signal": _coerce_bool(payload.get("erp_signal")) is True,
        "crm_signal": _coerce_bool(payload.get("crm_signal")),
        "pain_hypothesis": _normalize_pain_hypothesis(payload),
        "employees_50_249": _coerce_bool(payload.get("employees_50_249")) is True,
        "target_industry": industry,
        "turkey": _coerce_bool(payload.get("turkey")) is True,
        "sales_team": _coerce_bool(payload.get("sales_team")) is True,
        "digital_presence": _coerce_bool(payload.get("digital_presence")) is True,
        "sales_operations": _coerce_bool(payload.get("sales_operations")) is True,
        "large_sales_team": _coerce_bool(payload.get("large_sales_team")) is True,
    }


def profile_to_facts(
    payload: dict[str, Any], allowed_urls: set[str], default_url: str | None
) -> list[dict[str, Any]]:
    """Yapılandırılmış profili, yalnızca kanıtı olan fact satırlarına çevirir."""
    facts: list[dict[str, Any]] = []
    for field, (fact_type, default_value) in PROFILE_BOOL_TO_FACT.items():
        if _coerce_bool(payload.get(field)) is not True:
            continue
        evidence = _evidence_for(payload, field) or {
            "value": default_value,
            "evidence_text": f"{default_value} (analiz bayrağı).",
            "confidence": 0.7,
            "source_url": default_url,
        }
        fact = _fact_from_evidence(
            fact_type, default_value, evidence, allowed_urls, default_url
        )
        if fact:
            facts.append(fact)

    model = str(payload.get("business_model") or "").strip().casefold()
    if model in _DISTRIBUTOR_MODELS:
        evidence = _evidence_for(payload, "business_model")
        if evidence is not None:
            fact = _fact_from_evidence(
                "business_model",
                model,
                evidence,
                allowed_urls,
                default_url,
            )
            if fact:
                facts.append(fact)

    industry = str(payload.get("target_industry") or "").strip()
    if industry.casefold() in _TARGET_INDUSTRY_VALUES:
        evidence = _evidence_for(payload, "target_industry")
        if evidence is not None:
            fact = _fact_from_evidence(
                "target_industry",
                industry,
                evidence,
                allowed_urls,
                default_url,
            )
            if fact:
                facts.append(fact)

    crm = _coerce_bool(payload.get("crm_signal"))
    if crm is False:
        evidence = _evidence_for(payload, "crm_signal")
        if evidence is not None:
            fact = _fact_from_evidence(
                "low_crm_maturity",
                "Düşük CRM olgunluğu",
                evidence,
                allowed_urls,
                default_url,
            )
            if fact:
                facts.append(fact)
    elif crm is True:
        evidence = _evidence_for(payload, "crm_signal")
        if evidence is not None:
            fact = _fact_from_evidence(
                "crm_signal",
                "CRM tespit edildi",
                evidence,
                allowed_urls,
                default_url,
            )
            if fact:
                facts.append(fact)

    pain = _normalize_pain_hypothesis(payload)
    if pain:
        evidence = _evidence_for(payload, "pain_hypothesis") or _evidence_for(
            payload, "pain_hypotheses"
        )
        if evidence is not None:
            fact = _fact_from_evidence(
                "pain_hypothesis",
                pain,
                evidence,
                allowed_urls,
                default_url,
            )
            if fact:
                facts.append(fact)

    return _apply_industry_need_inference(facts, payload, default_url)


def _normalize_pain_hypothesis(payload: dict[str, Any]) -> str:
    raw = payload.get("pain_hypothesis")
    if raw is None:
        raw = payload.get("pain_hypotheses")
    if isinstance(raw, str) and raw.strip():
        text = raw.strip()
        if "," in text and all(
            part.strip().casefold() in _PAIN_LABELS for part in text.split(",") if part.strip()
        ):
            return DEFAULT_PAIN_HYPOTHESIS
        return text
    if isinstance(raw, list):
        labels = [str(item).strip() for item in raw if str(item).strip()]
        if labels and all(item.casefold() in _PAIN_LABELS for item in labels):
            return DEFAULT_PAIN_HYPOTHESIS
        sentences = [item for item in labels if " " in item]
        if sentences:
            return sentences[0]
    return ""


def _apply_industry_need_inference(
    facts: list[dict[str, Any]],
    payload: dict[str, Any],
    default_url: str | None,
) -> list[dict[str, Any]]:
    """Makine / elektronik / endüstriyel profilde Need sinyallerini tamamlar."""
    industry = str(payload.get("target_industry") or "").strip().casefold()
    typed = any(
        str(fact.get("fact_type") or "") in {"target_industry", "industries_served"}
        and is_target_industry(f"{fact.get('value') or ''} {fact.get('evidence_text') or ''}")
        for fact in facts
    )
    if industry not in _TARGET_INDUSTRY_VALUES and not typed:
        return facts
    have = {str(fact.get("fact_type") or "") for fact in facts}
    extra: list[dict[str, Any]] = []
    for _field, fact_type, value in INFERRED_NEED_FACTS:
        if fact_type in have:
            continue
        extra.append(
            {
                "fact_type": fact_type,
                "value": value,
                "confidence": 0.7,
                "evidence_text": INFERRED_NEED_EVIDENCE,
                "source_url": default_url,
            }
        )
    return facts + extra


def _merge_facts(
    profile_facts: list[dict[str, Any]],
    legacy_facts: list[dict[str, Any]],
    *,
    crm_signal: bool | None,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for fact in profile_facts + legacy_facts:
        fact_type = str(fact.get("fact_type") or "")
        if not fact_type:
            continue
        merged.setdefault(fact_type, fact)
    if crm_signal is True:
        merged.pop("low_crm_maturity", None)
    return list(merged.values())


def _normalize_facts(
    payload: dict[str, Any], allowed_urls: set[str], default_url: str | None
) -> list[dict[str, Any]]:
    """Model çıktısından yalnızca kanıtlı fact'leri alır; skorları yok sayar.

    Step 14: `value`, `confidence`, `evidence_text`, `source_url` zorunlu.
    Kanıtsız veya değersiz satırlar atılır. Uydurma URL'ler taranan sayfalara
    düşürülür. `payload["scores"]` varsa bile okunmaz (Step 16).
    """
    facts: list[dict[str, Any]] = []
    for raw in payload.get("facts") or []:
        if not isinstance(raw, dict):
            continue

        fact_type = str(raw.get("fact_type") or "unknown").strip()[:64] or "unknown"
        value = str(raw.get("value") or "").strip()
        evidence_text = str(raw.get("evidence_text") or "").strip()
        # Kanıt yoksa bu bir fact değil, model tahmini — kaydetme.
        if not value or not evidence_text:
            continue

        source_url = raw.get("source_url")
        if not isinstance(source_url, str) or source_url not in allowed_urls:
            source_url = default_url

        facts.append(
            {
                "fact_type": fact_type,
                "value": value,
                "confidence": _clamp(_as_float(raw.get("confidence")), 0.0, 1.0),
                "evidence_text": evidence_text,
                "source_url": source_url,
            }
        )

    return facts


def _request_analysis(company_name: str, user_content: str) -> dict[str, Any]:
    client = openai_client()
    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Şirket Adı: {company_name}\n\n{user_content}",
                },
            ],
            response_format={"type": "json_object"},
        )
        payload = response.choices[0].message.content or "{}"
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("OpenAI analizi başarısız: %s", company_name)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI analizi tamamlanamadı: {exc}",
        ) from exc

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI geçerli JSON döndürmedi.",
        ) from exc

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI beklenmeyen bir formatta yanıt verdi.",
        )
    parsed.pop("scores", None)
    return parsed


def analyze_scraped_pages(
    company_name: str, pages: list[ScrapedPage]
) -> dict[str, Any]:
    """Workflow 3'ün 4. adımı: taranan sayfalardan yalnızca fact + kanıt çıkarır.

    Puan üretmez; skor `persist_analysis` içinde Python tarafından hesaplanır.
    """
    if not pages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Analiz edilecek içerik yok: hiçbir hedef sayfa taranamadı.",
        )

    prompt = build_pages_prompt(
        pages,
        chars_per_page=settings.research_chars_per_page,
        total_chars=settings.research_total_chars,
    )
    payload = _request_analysis(company_name, f"Taranan sayfalar:\n\n{prompt}")
    allowed = {page.url for page in pages}
    return assemble_analysis(payload, allowed, pages[0].url)


def analyze_company_content(
    company_name: str, website_content: str, source_url: str | None = None
) -> dict[str, Any]:
    """Tek parça metni analiz eder (`POST /api/companies/analyze` için)."""
    content = website_content[: settings.research_total_chars]
    payload = _request_analysis(company_name, f"Web Sitesi İçeriği:\n{content}")

    allowed = {source_url} if source_url else set()
    return assemble_analysis(payload, allowed, source_url)


def assemble_analysis(
    payload: dict[str, Any],
    allowed_urls: set[str],
    default_url: str | None,
) -> dict[str, Any]:
    """Profil + kanıtlı fact'leri birleştirir; LLM skorunu yok sayar."""
    payload = dict(payload)
    payload.pop("scores", None)
    facts = _merge_facts(
        profile_to_facts(payload, allowed_urls, default_url),
        _normalize_facts(payload, allowed_urls, default_url),
        crm_signal=_coerce_bool(payload.get("crm_signal")),
    )
    facts = _apply_industry_need_inference(facts, payload, default_url)
    return {"facts": facts, "profile": normalize_profile(payload)}
