"""Keşif hattı: domain → tara → fact çıkar → puanla → Apollo.

`POST /api/research` bu işi arka planda çalıştırır; n8n ve Keşif ekranı
cevap beklemeden 202 alır. İstek session'ı kapanacağı için arka plan
görevi kendi session'ını açar (`session_scope`).
"""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api import models
from api.config import get_settings
from api.database import session_scope
from api.services.activity import EVENT_WEBSITE_RESEARCH, track_activity
from api.services.analysis import persist_analysis
from api.services.enrichment import analyze_scraped_pages, firecrawl_client
from api.services.website_research import MAX_PAGES, research_website

logger = logging.getLogger(__name__)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


class ResearchJobError(Exception):
    """Tarama/analiz hattı iş kuralı hatası (HTTP'ye bağlı değil)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def clean_domain(value: str) -> str:
    """`https://www.x.com/yol` → `x.com`. Noktasız girdi reddedilir."""
    cleaned = value.strip().lower()
    for prefix in ("https://", "http://"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
    cleaned = cleaned.removeprefix("www.").split("/", 1)[0].split(":", 1)[0].strip()
    if not cleaned or "." not in cleaned or " " in cleaned:
        raise ValueError("Geçerli bir domain girin.")
    return cleaned


def website_for_domain(domain: str) -> str:
    return f"https://{domain}"


def normalize_name(name: str) -> str:
    cleaned = _NON_ALNUM.sub("", name.casefold())
    for suffix in ("as", "ltdsti", "ltd", "sti", "inc", "gmbh", "bv"):
        cleaned = cleaned.removesuffix(suffix)
    return cleaned or name.casefold()


def get_or_create_company(db: Session, domain: str) -> models.Company:
    """Aynı domain/website varsa onu döner; yoksa `new` şirket açar."""
    website = website_for_domain(domain)
    existing = db.execute(
        select(models.Company)
        .where(
            or_(
                models.Company.domain == domain,
                models.Company.website == website,
                models.Company.website == f"https://www.{domain}",
            )
        )
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        if not existing.domain:
            existing.domain = domain
        if not existing.website:
            existing.website = website
        db.flush()
        return existing

    slug = domain.split(".")[0]
    company = models.Company(
        id=uuid.uuid4().hex,
        name=domain,
        normalized_name=normalize_name(slug),
        domain=domain,
        website=website,
        country="Turkey",
        status="new",
    )
    try:
        with db.begin_nested():
            db.add(company)
            db.flush()
    except IntegrityError:
        retry = db.execute(
            select(models.Company)
            .where(
                or_(
                    models.Company.domain == domain,
                    models.Company.website == website,
                )
            )
            .limit(1)
        ).scalar_one_or_none()
        if retry is None:
            raise
        return retry
    return company


def execute_research_pipeline(
    db: Session,
    company: models.Company,
    website: str,
    *,
    max_pages: int = MAX_PAGES,
) -> tuple[object, dict, int, object]:
    """Tara, fact çıkar, puanla; nitelikliyse Apollo kişilerini kaydet.

    `persist_analysis` Step 13/20 kapısını içerir.
    """
    settings = get_settings()
    if company.website != website:
        company.website = website
    if not company.domain:
        try:
            company.domain = clean_domain(website)
        except ValueError:
            pass

    result = research_website(
        firecrawl_client(),
        website,
        max_pages=max_pages,
        map_limit=settings.research_map_limit,
        timeout_seconds=settings.research_scrape_timeout_seconds,
    )
    if not result.scraped_pages:
        raise ResearchJobError(
            f"Hedef sayfaların hiçbiri taranamadı "
            f"({len(result.selected_pages)} sayfa denendi)."
        )

    extraction = analyze_scraped_pages(company.name or "", result.scraped_pages)
    facts_saved, scores = persist_analysis(
        db, company, extraction, source_type="website"
    )
    return result, extraction, facts_saved, scores


def run_research_job(company_id: str, website: str) -> None:
    """HTTP isteğinden bağımsız keşif hattı. Hata API yanıtını etkilemez."""
    try:
        with session_scope() as db:
            company = db.get(models.Company, company_id)
            if company is None:
                logger.warning("Keşif atlandı: şirket yok (%s)", company_id)
                return

            with track_activity(
                EVENT_WEBSITE_RESEARCH,
                f"{company.name} web sitesi araştırılıyor",
                company_id=company.id,
                company_name=company.name,
                detail={"website": website, "source": "async_research"},
            ) as activity:
                try:
                    result, _extraction, facts_saved, scores = execute_research_pipeline(
                        db, company, website
                    )
                except ResearchJobError as exc:
                    activity.fail(exc.message)
                    return
                except Exception as exc:
                    logger.exception("Keşif hattı başarısız: %s (%s)", company.name, website)
                    activity.fail(f"Keşif başarısız: {exc}")
                    raise

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
    except Exception:
        logger.exception("Arka plan keşif görevi düştü (%s, %s)", company_id, website)
