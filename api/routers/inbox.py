"""Gelen Kutusu ve Fırsatlar endpoint'leri.

İkisi de `interactions` tablosundaki gelen yanıtları okur; Fırsatlar yalnızca
AI'ın olumlu sınıflandırdığı yanıtları döndürür.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import Contact, Interaction
from api.schemas import (
    CompanyContactBrief,
    ContactEmailUpdate,
    ContactListOut,
    InboxResponse,
    OpportunitiesResponse,
    ReplyOut,
)
from api.services.inbox import (
    fetch_contacts,
    fetch_inbox,
    fetch_opportunities,
    fetch_reply,
)

router = APIRouter(tags=["inbox"])

# Filtre olarak kabul edilen sınıflandırmalar.
ALLOWED_CLASSIFICATIONS = (
    Interaction.CLASS_POSITIVE,
    Interaction.CLASS_MEETING_REQUEST,
    Interaction.CLASS_QUESTION,
    Interaction.CLASS_NEUTRAL,
    Interaction.CLASS_NEGATIVE,
    Interaction.CLASS_UNSUBSCRIBE,
    Interaction.CLASS_AUTO_REPLY,
)


@router.get(
    "/contacts",
    response_model=ContactListOut,
    summary="Karar vericiler — Neon contacts tablosu (Apollo)",
)
def list_contacts(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, min_length=1, max_length=200),
    qualified_only: bool = Query(
        default=True,
        description="Yalnızca qualified / high priority şirketlerin kişileri.",
    ),
) -> ContactListOut:
    try:
        return fetch_contacts(
            db,
            limit=limit,
            offset=offset,
            search=search,
            qualified_only=qualified_only,
        )
    except SQLAlchemyError:
        db.rollback()
        return ContactListOut(items=[], total=0, limit=limit, offset=offset)


@router.patch(
    "/contacts/{contact_id}",
    response_model=CompanyContactBrief,
    summary="Soğuk e-posta taslağını kaydet",
)
def update_contact_email(
    contact_id: str,
    payload: ContactEmailUpdate,
    db: Session = Depends(get_db),
) -> CompanyContactBrief:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kişi bulunamadı: {contact_id}",
        )
    contact.generated_email_body = payload.generated_email_body.strip() or None
    db.commit()
    db.refresh(contact)
    parts = [
        part
        for part in (contact.first_name, contact.last_name)
        if part and part.strip()
    ]
    return CompanyContactBrief(
        id=contact.id,
        name=" ".join(parts) or None,
        title=contact.title,
        email=contact.email,
        linkedin_url=contact.linkedin_url,
        email_status=contact.email_status,
        generated_email_body=contact.generated_email_body,
        persona_rank=contact.persona_rank,
        is_selected=bool(contact.is_selected),
    )


@router.get(
    "/inbox",
    response_model=InboxResponse,
    summary="Gelen kutusu — AI tarafından sınıflandırılmış gelen yanıtlar",
)
def list_inbox(
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    classification: str | None = Query(
        default=None, description="Tek bir sınıflandırmaya göre filtrele."
    ),
    unread_only: bool = Query(default=False, description="Sadece okunmamışlar."),
    search: str | None = Query(default=None, min_length=1, max_length=200),
) -> InboxResponse:
    if classification is not None:
        classification = classification.strip().lower()
        if classification not in ALLOWED_CLASSIFICATIONS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "Geçersiz sınıflandırma. Geçerli değerler: "
                    + ", ".join(ALLOWED_CLASSIFICATIONS)
                ),
            )

    try:
        return fetch_inbox(
            db,
            limit=limit,
            offset=offset,
            classification=classification,
            unread_only=unread_only,
            search=search,
        )
    except SQLAlchemyError:
        db.rollback()
        return InboxResponse(
            items=[],
            total=0,
            limit=limit,
            offset=offset,
            inbound_total=0,
            unread_count=0,
            positive_count=0,
            classification_breakdown=[],
        )


@router.get(
    "/opportunities",
    response_model=OpportunitiesResponse,
    summary="Fırsatlar — yalnızca olumlu sınıflandırılmış yanıtlar",
)
def list_opportunities(
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, min_length=1, max_length=200),
) -> OpportunitiesResponse:
    """Şirket puanına göre sıralı olumlu yanıt listesi."""
    try:
        return fetch_opportunities(db, limit=limit, offset=offset, search=search)
    except SQLAlchemyError:
        db.rollback()
        return OpportunitiesResponse(
            items=[],
            total=0,
            limit=limit,
            offset=offset,
            unique_companies=0,
            average_score=None,
        )


@router.patch(
    "/inbox/{interaction_id}/read",
    response_model=ReplyOut,
    summary="Bir yanıtı okundu / okunmadı olarak işaretle",
)
def mark_read(
    interaction_id: int,
    is_read: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> ReplyOut:
    interaction = db.get(Interaction, interaction_id)
    if interaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Yanıt bulunamadı: {interaction_id}",
        )

    interaction.is_read = is_read
    db.commit()

    updated = fetch_reply(db, interaction_id)
    if updated is None:
        # Kayıt var ama gelen yanıt değil (ör. `outbound`): listede yeri yok.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Bu kayıt bir gelen yanıt değil.",
        )
    return updated
