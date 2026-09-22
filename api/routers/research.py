"""Keşif endpoint'i: n8n ve Keşif ekranı için 202 + arka plan hattı."""

from __future__ import annotations

import threading

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from api.database import get_db
from api.schemas import DomainResearchRequest, ResearchAcceptedOut
from api.services import research_job

router = APIRouter(tags=["research"])


def enqueue_research_job(company_id: str, website: str) -> None:
    """BackgroundTask yalnızca thread açar; tarama yanıtı tutmaz."""
    thread = threading.Thread(
        target=research_job.run_research_job,
        args=(company_id, website),
        daemon=True,
        name=f"research-{company_id[:12]}",
    )
    thread.start()


@router.post(
    "/research",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ResearchAcceptedOut,
    summary="Keşif hattını arka planda başlat (domain)",
)
def start_research(
    payload: DomainResearchRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ResearchAcceptedOut:
    """Domain alır, şirketi kaydeder, scrape → fact → skor → Apollo'yu kuyruğa alır.

    Cevap tarama bitmeden döner; n8n zaman aşımına düşmez.
    """
    company = research_job.get_or_create_company(db, payload.domain)
    db.commit()

    website = company.website or research_job.website_for_domain(payload.domain)
    background_tasks.add_task(enqueue_research_job, company.id, website)

    return ResearchAcceptedOut(
        status="accepted",
        message="Research started in the background",
        domain=payload.domain,
        website=website,
        company_id=company.id,
    )
