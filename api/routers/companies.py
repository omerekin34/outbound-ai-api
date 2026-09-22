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
from api.database import get_db
from api.schemas import (
    CompanyAnalyzeRequest,
    CompanyCreate,
    CompanyListOut,
    CompanyOut,
    CompanyResearchRequest,
)
from api.services.activity import (
    EVENT_AI_ANALYSIS,
    EVENT_COMPANY_DISCOVERY,
    EVENT_WEBSITE_RESEARCH,
    track_activity,
)
from api.services.enrichment import analyze_company_content, scrape_website

logger = logging.getLogger(__name__)

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


@router.post("/research-website", summary="Web sitesi taraması (Firecrawl)")
def research_website(
    payload: CompanyResearchRequest, db: Session = Depends(get_db)
) -> dict:
    company = _get_company_or_404(db, payload.company_id)

    if not company.website:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu şirketin kayıtlı bir web sitesi yok.",
        )

    with track_activity(
        EVENT_WEBSITE_RESEARCH,
        f"{company.name} web sitesi taranıyor",
        company_id=company.id,
        company_name=company.name,
        detail={"website": company.website},
    ) as activity:
        markdown = scrape_website(company.website)

        company.status = "website_scraped"
        db.commit()

        activity.succeed(
            f"{company.name} web sitesi tarandı ({len(markdown):,} karakter).",
            {"characters": len(markdown)},
        )

        return {
            "status": "success",
            "company_id": company.id,
            "company": company.name,
            "scraped_length": len(markdown),
            "preview": markdown[:300],
            "content": markdown,
            "message": "Web sitesi tarandı ve markdown formatına çevrildi.",
        }


@router.post("/analyze", summary="AI ile analiz ve puanlama")
def analyze_company(
    payload: CompanyAnalyzeRequest, db: Session = Depends(get_db)
) -> dict:
    company = _get_company_or_404(db, payload.company_id)

    with track_activity(
        EVENT_AI_ANALYSIS,
        f"{company.name} AI ile analiz ediliyor",
        company_id=company.id,
        company_name=company.name,
    ) as activity:
        analysis = analyze_company_content(company.name or "", payload.website_content)

        scores = analysis.get("scores") or {}
        _upsert_score(db, company.id, scores)

        facts = analysis.get("facts") or []
        fact_count = _upsert_facts(db, company, facts)

        company.status = "analyzed"
        db.commit()

        overall = scores.get("overall_score")
        activity.succeed(
            f"{company.name} analiz edildi (genel puan: {overall}).",
            {"overall_score": overall, "fact_count": fact_count},
        )

        return {
            "status": "success",
            "company_id": company.id,
            "message": "Şirket analiz edildi ve sonuçlar kaydedildi.",
            "data": analysis,
        }


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _upsert_score(db: Session, company_id: str, scores: dict) -> None:
    """`scores.company_id` tekil olduğu için var olan kayıt güncellenir."""
    record = db.execute(
        select(models.Score).where(models.Score.company_id == company_id)
    ).scalar_one_or_none()

    values = {
        "icp_score": _as_float(scores.get("icp_score")),
        "need_score": _as_float(scores.get("need_score")),
        "timing_score": _as_float(scores.get("timing_score")),
        "reachability_score": _as_float(scores.get("reachability_score")),
        "overall_score": _as_float(scores.get("overall_score")),
        "calculated_at": models.utcnow().replace(tzinfo=None),
    }

    if record is None:
        db.add(models.Score(company_id=company_id, **values))
        return
    for key, value in values.items():
        setattr(record, key, value)


def _upsert_facts(db: Session, company: models.Company, facts: list) -> int:
    """`(company_id, fact_type)` tekil olduğu için tip başına tek kayıt tutulur."""
    existing = {
        fact.fact_type: fact
        for fact in db.execute(
            select(models.CompanyFact).where(
                models.CompanyFact.company_id == company.id
            )
        ).scalars()
    }

    written = 0
    for raw in facts:
        if not isinstance(raw, dict):
            continue
        fact_type = str(raw.get("fact_type") or "unknown")
        values = {
            "value": str(raw.get("value") or ""),
            "confidence": _as_float(raw.get("confidence")),
            "evidence_text": str(raw.get("evidence_text") or ""),
            "source_type": "website",
            "source_url": company.website,
            "observed_at": models.utcnow().replace(tzinfo=None),
        }

        record = existing.get(fact_type)
        if record is None:
            db.add(
                models.CompanyFact(
                    company_id=company.id, fact_type=fact_type, **values
                )
            )
        else:
            for key, value in values.items():
                setattr(record, key, value)
        written += 1

    return written
