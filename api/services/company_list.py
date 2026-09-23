"""Şirket listesi: Neon şirket + skor + fact + Apollo kişileri."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api import models
from api.schemas import (
    CompanyContactBrief,
    CompanyListOut,
    CompanyOut,
    CompanyRowOut,
    FactOut,
)
from api.services.scoring import DEEP_RESEARCH_STATUSES


def _contact_name(contact: models.Contact) -> str | None:
    parts = [
        part
        for part in (contact.first_name, contact.last_name)
        if part and part.strip()
    ]
    return " ".join(parts) or None


def _row_out(
    company: models.Company,
    score: models.Score | None,
    facts: list[models.CompanyFact],
    contacts: list[models.Contact],
) -> CompanyRowOut:
    base = CompanyRowOut.model_validate(CompanyOut.model_validate(company))
    if score is not None:
        base.icp_score = score.icp_score
        base.need_score = score.need_score
        base.overall_score = score.overall_score
        base.qualification_status = score.qualification_status
        base.requires_deep_research = bool(score.requires_deep_research)
    base.facts = [
        FactOut(
            fact_type=fact.fact_type or "unknown",
            value=fact.value or "",
            confidence=fact.confidence or 0.0,
            evidence_text=fact.evidence_text or "",
            source_url=fact.source_url,
        )
        for fact in facts
        if fact.value and fact.evidence_text
    ]
    base.contacts = [
        CompanyContactBrief(
            id=contact.id,
            name=_contact_name(contact),
            title=contact.title,
            email=contact.email,
            linkedin_url=contact.linkedin_url,
            email_status=contact.email_status,
            generated_email_body=contact.generated_email_body,
            persona_rank=contact.persona_rank,
            is_selected=bool(contact.is_selected),
        )
        for contact in sorted(
            contacts,
            key=lambda row: (not bool(row.is_selected), -(row.persona_rank or 0)),
        )
    ]
    return base


def fetch_companies(
    db: Session,
    *,
    limit: int,
    offset: int,
    status_filter: str | None = None,
    search: str | None = None,
    qualified_only: bool = False,
) -> CompanyListOut:
    filters = []
    if status_filter:
        filters.append(
            models.normalized_status(models.Company.status)
            == status_filter.strip().lower()
        )
    if qualified_only:
        filters.append(
            models.normalized_status(models.Company.status).in_(
                tuple(DEEP_RESEARCH_STATUSES)
            )
        )
    if search and search.strip():
        pattern = f"%{search.strip().lower()}%"
        filters.append(
            func.lower(func.coalesce(models.Company.name, "")).like(pattern)
            | func.lower(func.coalesce(models.Company.domain, "")).like(pattern)
        )

    total = db.execute(
        select(func.count(models.Company.id)).where(*filters)
    ).scalar() or 0

    companies = list(
        db.execute(
            select(models.Company)
            .where(*filters)
            .order_by(
                models.Company.created_at.desc().nullslast(), models.Company.id
            )
            .limit(limit)
            .offset(offset)
        ).scalars()
    )
    ids = [company.id for company in companies]
    scores_by_id: dict[str, models.Score] = {}
    facts_by_id: dict[str, list[models.CompanyFact]] = defaultdict(list)
    contacts_by_id: dict[str, list[models.Contact]] = defaultdict(list)
    if ids:
        for score in db.execute(
            select(models.Score).where(models.Score.company_id.in_(ids))
        ).scalars():
            scores_by_id[score.company_id] = score
        for fact in db.execute(
            select(models.CompanyFact)
            .where(models.CompanyFact.company_id.in_(ids))
            .order_by(models.CompanyFact.id)
        ).scalars():
            facts_by_id[fact.company_id].append(fact)
        for contact in db.execute(
            select(models.Contact)
            .where(models.Contact.company_id.in_(ids))
            .order_by(models.Contact.last_name.asc().nullslast())
        ).scalars():
            contacts_by_id[contact.company_id].append(contact)

    items = [
        _row_out(
            company,
            scores_by_id.get(company.id),
            facts_by_id.get(company.id, []),
            contacts_by_id.get(company.id, []),
        )
        for company in companies
    ]
    return CompanyListOut(items=items, total=total, limit=limit, offset=offset)
