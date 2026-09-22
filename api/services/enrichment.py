"""Dış servisler (Firecrawl + OpenAI) ile zenginleştirme mantığı.

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

logger = logging.getLogger(__name__)
settings = get_settings()

# Tek istekte modele gönderilecek azami karakter sayısı (maliyet kontrolü).
MAX_CONTENT_CHARS = 5_000

ANALYSIS_SYSTEM_PROMPT = """Sen uzman bir B2B satış analiz asistanısın. Görevin, verilen şirket web sitesi metnini inceleyerek şirketin profilini çıkarmak ve puanlamaktır.
Aşağıdaki JSON formatında, anahtarları eksiksiz olarak çıktı ver:
{
    "scores": {
        "icp_score": 85.5,
        "need_score": 70.0,
        "timing_score": 60.0,
        "reachability_score": 90.0,
        "overall_score": 76.3
    },
    "facts": [
        {
            "fact_type": "target_audience",
            "value": "Oyuncular ve e-sporcular",
            "confidence": 0.9,
            "evidence_text": "Web sitesindeki 'oyuncu ekipmanları' vurgusu."
        }
    ]
}"""


def _missing_key(service: str, env_var: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"{service} yapılandırılmamış. .env dosyasına {env_var} ekleyin.",
    )


@lru_cache(maxsize=1)
def _firecrawl_client() -> Any:
    from firecrawl import FirecrawlApp

    return FirecrawlApp(api_key=settings.firecrawl_api_key)


@lru_cache(maxsize=1)
def _openai_client() -> Any:
    from openai import OpenAI

    return OpenAI(api_key=settings.openai_api_key)


def scrape_website(url: str) -> str:
    """Web sitesini Firecrawl ile tarayıp markdown içeriğini döndürür."""
    if not settings.firecrawl_api_key:
        raise _missing_key("Firecrawl", "FIRECRAWL_API_KEY")

    try:
        result = _firecrawl_client().scrape_url(url, formats=["markdown"])
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Firecrawl taraması başarısız: %s", url)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Web sitesi taranamadı: {exc}",
        ) from exc

    if isinstance(result, dict):
        markdown = result.get("markdown") or ""
    else:
        markdown = getattr(result, "markdown", "") or ""

    if not markdown.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Tarama boş içerik döndürdü.",
        )
    return markdown


def analyze_company_content(company_name: str, website_content: str) -> dict[str, Any]:
    """Site içeriğini modele verip skor + fact JSON'u döndürür."""
    if not settings.openai_api_key:
        raise _missing_key("OpenAI", "OPENAI_API_KEY")

    try:
        response = _openai_client().chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Şirket Adı: {company_name}\n\n"
                        f"Web Sitesi İçeriği:\n{website_content[:MAX_CONTENT_CHARS]}"
                    ),
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
