"""Gelen Kutusu ve Fırsatlar ekranlarını besleyen sorgular.

Her iki ekran da aynı JOIN'i kullanır:

    interactions  ->  companies   (INNER, şirket adı zorunlu)
                  ->  contacts    (LEFT,  kişi eşleşmemiş olabilir)
                  ->  scores      (LEFT,  şirket henüz puanlanmamış olabilir)

Fark filtredeyken: Fırsatlar yalnızca AI'ın olumlu sınıflandırdığı yanıtları
(`POSITIVE_CLASSIFICATIONS`) gösterir, Gelen Kutusu tüm gelen yanıtları.
"""

from __future__ import annotations

import logging

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from api.models import (
    POSITIVE_CLASSIFICATIONS,
    Company,
    Contact,
    Interaction,
    Score,
)
from api.schemas import (
    ClassificationCount,
    InboxResponse,
    OpportunitiesResponse,
    ReplyOut,
)

logger = logging.getLogger(__name__)

# Listede gösterilen kısa önizleme uzunluğu. Tam metin `body` alanında döner.
SNIPPET_LENGTH = 220


def _snippet(body: str, limit: int = SNIPPET_LENGTH) -> str:
    """Yanıt metnini tek satırlık önizlemeye indirger."""
    collapsed = " ".join((body or "").split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def _contact_name(first: str | None, last: str | None) -> str | None:
    parts = [part.strip() for part in (first, last) if part and part.strip()]
    return " ".join(parts) or None


def _base_query() -> Select:
    """Gelen yanıtlar için ortak JOIN ve seçilen kolonlar."""
    return (
        select(
            Interaction.id,
            Interaction.company_id,
            Interaction.contact_id,
            Interaction.subject,
            Interaction.body,
            Interaction.ai_classification,
            Interaction.ai_confidence,
            Interaction.ai_summary,
            Interaction.ai_next_action,
            Interaction.channel,
            Interaction.is_read,
            Interaction.received_at,
            Company.name.label("company_name"),
            Company.domain.label("company_domain"),
            Company.industry.label("company_industry"),
            Company.city.label("company_city"),
            Contact.first_name.label("contact_first_name"),
            Contact.last_name.label("contact_last_name"),
            Contact.title.label("contact_title"),
            Contact.email.label("contact_email"),
            Score.overall_score.label("overall_score"),
        )
        .join(Company, Company.id == Interaction.company_id)
        .outerjoin(Contact, Contact.id == Interaction.contact_id)
        .outerjoin(Score, Score.company_id == Interaction.company_id)
        # Gelen kutusu yalnızca gelen yazışmaları gösterir; gönderdiğimiz
        # e-postalar (`outbound`) buraya karışmaz.
        .where(Interaction.direction == Interaction.DIRECTION_INBOUND)
    )


def _apply_search(query: Select, search: str | None) -> Select:
    """Şirket adı, kişi adı/e-postası, konu ve gövdede arama yapar."""
    if not search or not search.strip():
        return query

    pattern = f"%{search.strip().lower()}%"
    return query.where(
        or_(
            func.lower(func.coalesce(Company.name, "")).like(pattern),
            func.lower(func.coalesce(Contact.first_name, "")).like(pattern),
            func.lower(func.coalesce(Contact.last_name, "")).like(pattern),
            func.lower(func.coalesce(Contact.email, "")).like(pattern),
            func.lower(func.coalesce(Interaction.subject, "")).like(pattern),
            func.lower(func.coalesce(Interaction.body, "")).like(pattern),
        )
    )


def _count_for(query: Select, db: Session) -> int:
    """Sayfalamadan bağımsız toplam kayıt sayısı."""
    subquery = query.order_by(None).subquery()
    return db.execute(select(func.count()).select_from(subquery)).scalar() or 0


def _to_item(row) -> ReplyOut:
    return ReplyOut(
        id=row.id,
        company_id=row.company_id,
        company_name=row.company_name,
        company_domain=row.company_domain,
        company_industry=row.company_industry,
        company_city=row.company_city,
        contact_id=row.contact_id,
        contact_name=_contact_name(row.contact_first_name, row.contact_last_name),
        contact_title=row.contact_title,
        contact_email=row.contact_email,
        subject=row.subject,
        body=row.body,
        snippet=_snippet(row.body),
        classification=row.ai_classification,
        confidence=row.ai_confidence,
        ai_summary=row.ai_summary,
        ai_next_action=row.ai_next_action,
        channel=row.channel,
        is_read=bool(row.is_read),
        received_at=row.received_at,
        overall_score=row.overall_score,
    )


def fetch_reply(db: Session, interaction_id: int) -> ReplyOut | None:
    """Tek bir yanıtı listelerle aynı biçimde döndürür."""
    row = db.execute(
        _base_query().where(Interaction.id == interaction_id)
    ).one_or_none()
    return _to_item(row) if row is not None else None


def _classification_counts(db: Session, search: str | None) -> list[ClassificationCount]:
    """Filtre çipleri için sınıflandırma başına toplam."""
    query = _apply_search(
        select(
            Interaction.ai_classification.label("classification"),
            func.count(Interaction.id).label("count"),
        )
        .join(Company, Company.id == Interaction.company_id)
        .outerjoin(Contact, Contact.id == Interaction.contact_id)
        .where(Interaction.direction == Interaction.DIRECTION_INBOUND),
        search,
    ).group_by(Interaction.ai_classification)

    rows = db.execute(query.order_by(func.count(Interaction.id).desc())).all()
    return [
        ClassificationCount(
            classification=row.classification or "unclassified", count=row.count
        )
        for row in rows
    ]


def fetch_inbox(
    db: Session,
    *,
    limit: int,
    offset: int,
    classification: str | None = None,
    unread_only: bool = False,
    search: str | None = None,
) -> InboxResponse:
    """Gelen kutusu: tüm gelen yanıtlar, en yenisi en üstte."""
    query = _apply_search(_base_query(), search)

    if classification:
        query = query.where(Interaction.ai_classification == classification)
    if unread_only:
        query = query.where(Interaction.is_read.is_(False))

    total = _count_for(query, db)
    rows = db.execute(
        query.order_by(Interaction.received_at.desc(), Interaction.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    # Üst sayaçlar ve filtre çipleri sınıflandırma/okunma filtresinden
    # etkilenmez; yalnızca aramaya göre daralır. Aksi halde bir filtre
    # seçildiğinde "Tümü" çipi de o filtreye düşerdi.
    search_scoped = _apply_search(_base_query(), search)

    return InboxResponse(
        items=[_to_item(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        inbound_total=_count_for(search_scoped, db),
        unread_count=_count_for(
            search_scoped.where(Interaction.is_read.is_(False)), db
        ),
        positive_count=_count_for(
            search_scoped.where(
                Interaction.ai_classification.in_(POSITIVE_CLASSIFICATIONS)
            ),
            db,
        ),
        classification_breakdown=_classification_counts(db, search),
    )


def fetch_opportunities(
    db: Session,
    *,
    limit: int,
    offset: int,
    search: str | None = None,
) -> OpportunitiesResponse:
    """Fırsatlar: yalnızca AI'ın olumlu işaretlediği yanıtlar.

    Sıralama şirket puanına göre yapılır; puanı olmayan kayıtlar sona düşer.
    """
    query = _apply_search(_base_query(), search).where(
        Interaction.ai_classification.in_(POSITIVE_CLASSIFICATIONS)
    )

    rows = db.execute(
        query.order_by(
            Score.overall_score.desc().nullslast(),
            Interaction.received_at.desc(),
            Interaction.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    ).all()

    total, unique_companies, average_score = _opportunity_summary(db, query)

    return OpportunitiesResponse(
        items=[_to_item(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        unique_companies=unique_companies,
        average_score=average_score,
    )


def _opportunity_summary(db: Session, query: Select) -> tuple[int, int, float | None]:
    """Fırsat listesinin üst özeti: toplam, tekil şirket, ortalama puan.

    Ortalama puan **şirket başına** hesaplanır; aynı şirketten iki olumlu yanıt
    gelmesi ortalamayı bozmasın.
    """
    matches = query.order_by(None).subquery()

    total = db.execute(select(func.count()).select_from(matches)).scalar() or 0

    companies = (
        select(matches.c.company_id, matches.c.overall_score).distinct().subquery()
    )
    row = db.execute(
        select(
            func.count(companies.c.company_id),
            func.avg(companies.c.overall_score),
        )
    ).one()

    average = round(float(row[1]), 1) if row[1] is not None else None
    return total, row[0] or 0, average


def count_positive_replies(db: Session) -> tuple[int, int]:
    """Dashboard kartı için (olumlu yanıt, okunmamış yanıt) sayıları.

    `interactions` tablosu henüz oluşturulmamışsa panel çökmesin diye (0, 0)
    döner — `fetch_recent_activity` ile aynı savunma yaklaşımı.
    """
    try:
        row = db.execute(
            select(
                func.count(Interaction.id).filter(
                    Interaction.ai_classification.in_(POSITIVE_CLASSIFICATIONS)
                ),
                func.count(Interaction.id).filter(Interaction.is_read.is_(False)),
            ).where(Interaction.direction == Interaction.DIRECTION_INBOUND)
        ).one()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("interactions tablosu okunamadı: %s", exc)
        return 0, 0
    return row[0] or 0, row[1] or 0
