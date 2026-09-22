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
from api.services.website_research import ScrapedPage

logger = logging.getLogger(__name__)
settings = get_settings()

# Step 14 + 16: model yalnızca kanıt çıkarır. ICP/Need/overall puanı
# `api.services.scoring` içinde, kaydedilmiş fact'lerden hesaplanır.
# Bu yüzden prompt'ta skor alanı YOKTUR; modelden gelen `scores` yok sayılır.

EXTRACTION_SYSTEM_PROMPT = """Sen bir B2B kanıt çıkarıcısısın. Sana bir şirketin web sitesinden taranmış sayfalar verilecek. Her sayfanın kategorisi ve URL'si belirtilmiştir.

TEK GÖREVİN: sayfalarda gerçekten geçen yapılandırılmış fact'leri çıkarmak.

YAPMA:
- ICP, Need, Timing, Reachability veya overall puanı HESAPLAMA.
- `scores` alanı DÖNDÜRME.
- Sayfada yazmayan bilgi uydurma.
- URL uydurma.

Her fact için şu dört alan ZORUNLUDUR:
- `value`: çıkarılan olgu (kısa, somut).
- `confidence`: 0.0 ile 1.0 arası güven. Emin değilsen düşür veya fact'i ekleme.
- `evidence_text`: sayfadan BİREBİR alıntı. Kendi cümleni yazma; sitede geçen cümleyi kopyala.
- `source_url`: bu alıntının alındığı sayfanın URL'si. SADECE sana verilen URL'lerden birini kullan.

Kanıtsız (`evidence_text` boş) fact ekleme. Yalnızca metinde gerçekten yer alan bilgileri raporla.

Çıktıyı tam olarak bu JSON şemasıyla ver:
{
  "facts": [
    {
      "fact_type": "dealer_network",
      "value": "Türkiye genelinde 42 yetkili bayi",
      "confidence": 0.9,
      "evidence_text": "Türkiye genelinde 42 yetkili bayi.",
      "source_url": "https://ornek.com/bayiler"
    }
  ]
}

Önerilen `fact_type` değerleri — puanlama bu tipleri arar, uygun olanları kullan:

ICP sinyalleri:
b2b, physical_product, employee_50_249, target_industry, turkey,
distributor_or_manufacturer, sales_team, digital_presence

Need sinyalleri:
erp_detected, quote_based_sales, high_sku, multiple_warehouse, dealer_network,
sales_operations, whatsapp_sales, large_sales_team, technical_docs, low_crm_maturity

`employee_50_249` yalnızca çalışan sayısı 50–249 arasındaysa yaz.
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
    return {"facts": _normalize_facts(payload, allowed, pages[0].url)}


def analyze_company_content(
    company_name: str, website_content: str, source_url: str | None = None
) -> dict[str, Any]:
    """Tek parça metni analiz eder (`POST /api/companies/analyze` için)."""
    content = website_content[: settings.research_total_chars]
    payload = _request_analysis(company_name, f"Web Sitesi İçeriği:\n{content}")

    allowed = {source_url} if source_url else set()
    return {"facts": _normalize_facts(payload, allowed, source_url)}
