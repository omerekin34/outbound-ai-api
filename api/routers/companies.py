"""Şirket keşfi, web sitesi taraması ve AI analizi endpoint'leri."""

from __future__ import annotations

import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api import models
from api.config import get_settings
from api.database import get_db
from api.schemas import (
    CompanyAnalysisOut,
    CompanyAnalyzeRequest,
    CompanyCreate,
    CompanyListOut,
    CompanyOut,
    CompanyResearchRequest,
    ResearchedPageOut,
    WebsiteResearchResponse,
)
from api.services.activity import (
    EVENT_AI_ANALYSIS,
    EVENT_COMPANY_DISCOVERY,
    EVENT_WEBSITE_RESEARCH,
    track_activity,
)
from api.services.analysis import persist_analysis
from api.services.enrichment import (
    analyze_company_content,
    analyze_scraped_pages,
    firecrawl_client,
)
from api.services.website_research import research_website

logger = logging.getLogger(__name__)
settings = get_settings()

# Prefix `index.py` içinde verilir: `/api/companies` (ve geriye dönük
# uyumluluk için prefix'siz `/companies`).
router = APIRouter(prefix="/companies", tags=["companies"])

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalize_name(name: str) -> str:
    """Tekilleştirme için şirket adını sadeleştirir ("Delta A.Ş." -> "delta")."""
    cleaned = _NON_ALNUM.sub("", name.casefold())
    for suffix in ("as", "ltdsti", "ltd", "sti", "inc", "gmbh", "bv"):
        cleaned = cleaned.removesuffix(suffix)
    return cleaned or name.casefold()


def _get_company_or_404(db: Session, company_id: str) -> models.Company:
    company = db.get(models.Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Şirket bulunamadı: {company_id}",
        )
    return company


def _find_duplicate(
    db: Session, *, domain: str, website: str | None, normalized_name: str
) -> models.Company | None:
    """Kural 9: domain, website veya sadeleştirilmiş isim üzerinden tekillik."""
    conditions = [models.Company.domain == domain]
    if website:
        conditions.append(models.Company.website == website)
    if normalized_name:
        conditions.append(models.Company.normalized_name == normalized_name)

    return db.execute(
        select(models.Company).where(or_(*conditions)).limit(1)
    ).scalar_one_or_none()


@router.get("", response_model=CompanyListOut, summary="Şirket listesi")
def list_companies(
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, min_length=1, max_length=200),
) -> CompanyListOut:
    """Dashboard tablosunu besleyen sayfalanmış şirket listesi."""
    filters = []
    if status_filter:
        filters.append(
            models.normalized_status(models.Company.status) == status_filter.strip().lower()
        )
    if search:
        pattern = f"%{search.strip().lower()}%"
        filters.append(
            func.lower(func.coalesce(models.Company.name, ""))
            .like(pattern)
            | func.lower(func.coalesce(models.Company.domain, "")).like(pattern)
        )

    total = db.execute(
        select(func.count(models.Company.id)).where(*filters)
    ).scalar() or 0

    companies = db.execute(
        select(models.Company)
        .where(*filters)
        .order_by(models.Company.created_at.desc().nullslast(), models.Company.id)
        .limit(limit)
        .offset(offset)
    ).scalars().all()

    return CompanyListOut(
        items=[CompanyOut.model_validate(item) for item in companies],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{company_id}", response_model=CompanyOut, summary="Tek şirket detayı")
def get_company(company_id: str, db: Session = Depends(get_db)) -> CompanyOut:
    return CompanyOut.model_validate(_get_company_or_404(db, company_id))


@router.post(
    "/discover",
    status_code=status.HTTP_201_CREATED,
    summary="Şirket keşfi ve veritabanına kayıt",
)
def discover_company(payload: CompanyCreate, db: Session = Depends(get_db)) -> dict:
    normalized_name = _normalize_name(payload.name)

    with track_activity(
        EVENT_COMPANY_DISCOVERY,
        f"{payload.name} keşfediliyor",
        company_name=payload.name,
        detail={"domain": payload.domain},
    ) as activity:
        existing = _find_duplicate(
            db,
            domain=payload.domain,
            website=payload.website,
            normalized_name=normalized_name,
        )
        if existing is not None:
            activity.attach_company(existing.id, existing.name)
            activity.skip(f"{payload.name} zaten kayıtlı, atlandı.")
            return {
                "status": "skipped",
                "message": "Bu şirket zaten veritabanında mevcut.",
                "company_id": existing.id,
            }

        company = models.Company(
            id=uuid.uuid4().hex,
            name=payload.name,
            normalized_name=normalized_name,
            domain=payload.domain,
            website=payload.website,
            industry=payload.industry,
            estimated_num_employees=payload.employee_count,
            country=payload.country,
            city=payload.city,
            linkedin_url=payload.linkedin_url,
            founded_year=payload.founded_year,
            status="new",
        )
        db.add(company)

        try:
            db.commit()
        except IntegrityError:
            # `unique_website` gibi kısıtlar yarış durumunda burada yakalanır.
            db.rollback()
            activity.skip(f"{payload.name} eşzamanlı olarak eklenmiş, atlandı.")
            return {
                "status": "skipped",
                "message": "Bu şirket eşzamanlı bir istek tarafından eklenmiş.",
                "company_id": None,
            }

        db.refresh(company)
        activity.attach_company(company.id, company.name)
        activity.succeed(f"{company.name} veritabanına eklendi.")

        return {
            "status": "success",
            "message": "Şirket başarıyla kaydedildi.",
            "company_id": company.id,
        }


@router.post(
    "/research-website",
    response_model=WebsiteResearchResponse,
    summary="Workflow 3 — hedefli web sitesi araştırması ve AI analizi",
)
def research_website_endpoint(
    payload: CompanyResearchRequest, db: Session = Depends(get_db)
) -> WebsiteResearchResponse:
    """Workflow 3'ü uçtan uca yürütür.

    1. `company_id` + `website` girdisi doğrulanır.
    2. Firecrawl `map` ile URL'ler keşfedilir, yalnızca hedef kategorilerdeki
       sayfalar seçilir (kör tarama yok).
    3. En fazla `max_pages` (üst sınır 20) sayfa taranır.
    4. Toplanan içerik AI Company Analyzer'a verilir; fact ve kanıtlar kaydedilir.
    """
    company = _get_company_or_404(db, payload.company_id)

    with track_activity(
        EVENT_WEBSITE_RESEARCH,
        f"{company.name} web sitesi araştırılıyor",
        company_id=company.id,
        company_name=company.name,
        detail={"website": payload.website, "max_pages": payload.max_pages},
    ) as activity:
        # Spec: adres girdiden gelir. Kayıtlı adres farklıysa güncelliyoruz ki
        # sonraki adımlar aynı kaynağı kullansın.
        if company.website != payload.website:
            company.website = payload.website

        result = research_website(
            firecrawl_client(),
            payload.website,
            max_pages=payload.max_pages,
            map_limit=settings.research_map_limit,
            timeout_seconds=settings.research_scrape_timeout_seconds,
        )

        if not result.scraped_pages:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    f"Hedef sayfaların hiçbiri taranamadı "
                    f"({len(result.selected_pages)} sayfa denendi)."
                ),
            )

        extraction = analyze_scraped_pages(company.name or "", result.scraped_pages)
        facts_saved, scores = persist_analysis(
            db, company, extraction, source_type="website"
        )
        db.commit()

        analysis = {"facts": extraction["facts"], "scores": scores.as_dict()}
        activity.succeed(
            f"{company.name}: {len(result.scraped_pages)} sayfa tarandı, "
            f"{facts_saved} bulgu çıkarıldı "
            f"({scores.qualification_status}, genel puan: {scores.overall_score}).",
            {
                "scraped_pages": len(result.scraped_pages),
                "discovered_urls": result.discovered_urls,
                "facts": facts_saved,
                "overall_score": scores.overall_score,
                "qualification_status": scores.qualification_status,
                "requires_deep_research": scores.requires_deep_research,
                "credits_used": result.credits_used,
                "score_version": scores.version,
            },
        )

        return WebsiteResearchResponse(
            status="success",
            company_id=company.id,
            company=company.name,
            website=result.website,
            max_pages=result.max_pages,
            discovered_urls=result.discovered_urls,
            selected_pages=len(result.selected_pages),
            scraped_pages=len(result.scraped_pages),
            total_characters=result.total_characters,
            credits_used=result.credits_used,
            used_fallback=result.used_fallback,
            pages=[
                ResearchedPageOut(
                    url=page.url,
                    category=page.category,
                    characters=page.characters,
                )
                for page in result.scraped_pages
            ],
            analysis=CompanyAnalysisOut.model_validate(analysis),
            facts_saved=facts_saved,
            message=(
                f"{len(result.scraped_pages)} hedef sayfa tarandı ve analiz edildi."
            ),
        )


@router.post("/analyze", summary="Hazır metinden AI analizi ve puanlama")
def analyze_company(
    payload: CompanyAnalyzeRequest, db: Session = Depends(get_db)
) -> dict:
    """Elde hazır içerik varken analiz eder; taramayı Workflow 3 yapar."""
    company = _get_company_or_404(db, payload.company_id)

    with track_activity(
        EVENT_AI_ANALYSIS,
        f"{company.name} AI ile analiz ediliyor",
        company_id=company.id,
        company_name=company.name,
    ) as activity:
        extraction = analyze_company_content(
            company.name or "",
            payload.website_content,
            payload.source_url or company.website,
        )
        fact_count, scores = persist_analysis(
            db, company, extraction, source_type="website"
        )
        db.commit()

        analysis = {"facts": extraction["facts"], "scores": scores.as_dict()}
        activity.succeed(
            f"{company.name} analiz edildi "
            f"({scores.qualification_status}, genel puan: {scores.overall_score}).",
            {
                "overall_score": scores.overall_score,
                "qualification_status": scores.qualification_status,
                "requires_deep_research": scores.requires_deep_research,
                "fact_count": fact_count,
                "score_version": scores.version,
            },
        )

        return {
            "status": "success",
            "company_id": company.id,
            "message": "Şirket analiz edildi ve sonuçlar kaydedildi.",
            "data": analysis,
        }
