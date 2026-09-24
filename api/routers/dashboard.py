"""Dashboard endpoint'leri: frontend'in tek çağrıda ihtiyaç duyduğu veri."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from api.config import get_settings
from api.database import get_db
from api.schemas import ActivityOut, DashboardStatsResponse
from api.services.dashboard import (
    build_dashboard_stats,
    empty_dashboard_stats,
    fetch_recent_activity,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# Prefix `index.py` içinde verilir -> `/api/dashboard-stats`, `/api/activity`.
router = APIRouter(tags=["dashboard"])


@router.get(
    "/dashboard-stats",
    response_model=DashboardStatsResponse,
    summary="Dashboard sayaçları ve AI durum akışı",
)
def get_dashboard_stats(
    db: Session = Depends(get_db),
    activity_limit: int = Query(
        default=None,
        ge=1,
        le=50,
        description="Dönecek aktivite kaydı sayısı.",
    ),
) -> DashboardStatsResponse:
    """Tek istekte dashboard'un tamamını besleyen özet veriyi döndürür."""
    limit = activity_limit or settings.dashboard_activity_limit
    try:
        return build_dashboard_stats(db, limit)
    except SQLAlchemyError as exc:
        logger.exception("Dashboard istatistikleri hesaplanamadı; boş özet dönülüyor")
        db.rollback()
        return empty_dashboard_stats()


@router.get(
    "/activity",
    response_model=list[ActivityOut],
    summary="AI aktivite akışı (sayfalanabilir)",
)
def get_activity_feed(
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ActivityOut]:
    """Panelin "AI şu anda ne yapıyor?" bölümünü canlı tutmak için kullanılır."""
    return fetch_recent_activity(db, limit)
