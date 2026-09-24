"""Keşif endpoint'i: n8n ve Keşif ekranı için 202 + arka plan hattı."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from api.database import get_db
from api.schemas import DomainResearchRequest, PipelineStatusOut, ResearchAcceptedOut
from api.services import research_job
from api.services.research_queue import (
    enqueue_research_job,
    pause_pipeline,
    pipeline_snapshot,
    resume_pipeline,
)

router = APIRouter(tags=["research"])


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


@router.get(
    "/pipeline",
    response_model=PipelineStatusOut,
    summary="Keşif kuyruğunun duraklatma durumu",
)
def get_pipeline_status() -> PipelineStatusOut:
    return PipelineStatusOut.model_validate(pipeline_snapshot())


@router.post(
    "/pipeline/pause",
    response_model=PipelineStatusOut,
    summary="Keşif kuyruğunu duraklat",
)
def pause_research_pipeline() -> PipelineStatusOut:
    return PipelineStatusOut.model_validate(pause_pipeline())


@router.post(
    "/pipeline/resume",
    response_model=PipelineStatusOut,
    summary="Keşif kuyruğunu devam ettir",
)
def resume_research_pipeline() -> PipelineStatusOut:
    return PipelineStatusOut.model_validate(resume_pipeline())
