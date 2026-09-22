"""Dashboard verisini tek bir yerde toplayan servis katmanı.

Router'lar burada üretilen veriyi olduğu gibi döndürür; SQL mantığı
endpoint'lerin içine dağılmaz.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from api.config import get_settings
from api.models import (
    ActivityLog,
    Company,
    Contact,
    Score,
    normalized_status,
    trim_chars,
)
from api.schemas import (
    ActivityOut,
    AiStatus,
    DashboardStats,
    DashboardStatsResponse,
    IndustryCount,
    StatusCount,
)
from api.services.inbox import count_positive_replies
from api.services.scoring import QUALIFICATION_STATUSES

logger = logging.getLogger(__name__)
settings = get_settings()

# Keşfedilmiş ama henüz araştırılmamış kayıtlar.
PENDING_STATUSES = ("", "new", "pending", "queued", "discovered")
# Analiz/puanlama adımını tamamlamış kayıtlar.
ANALYZED_STATUSES = ("analyzed", "scored", *QUALIFICATION_STATUSES)
# Bu puanın üzerindeki şirketler "yüksek niyetli" sayılır.
HIGH_INTENT_SCORE = 70.0

EVENT_LABELS = {
    "company_discovery": "Şirket keşfi",
    "website_research": "Web sitesi taraması",
    "ai_analysis": "AI analizi",
    "decision_maker_search": "Karar verici araması",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _naive_utc(value: datetime) -> datetime:
    """`companies` tablosu zaman dilimi taşımayan TIMESTAMP kullanıyor."""
    return value.replace(tzinfo=None)


def _company_counters(db: Session, now: datetime) -> DashboardStats:
    status = normalized_status(Company.status)
    today_start = _naive_utc(now).replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = _naive_utc(now) - timedelta(days=7)

    row = db.execute(
        select(
            func.count(Company.id).label("total"),
            func.count(Company.id)
            .filter(status.notin_(PENDING_STATUSES))
            .label("researched"),
            func.count(Company.id)
            .filter(status.in_(PENDING_STATUSES))
            .label("pending"),
            func.count(Company.id)
            .filter(status.in_(ANALYZED_STATUSES))
            .label("analyzed"),
            func.count(Company.id)
            .filter(Company.created_at >= today_start)
            .label("today"),
            func.count(Company.id)
            .filter(Company.created_at >= week_start)
            .label("week"),
        )
    ).one()

    contacts_total = db.execute(select(func.count(Contact.id))).scalar() or 0

    score_row = db.execute(
        select(
            func.avg(Score.overall_score),
            func.count(Score.id).filter(Score.overall_score >= HIGH_INTENT_SCORE),
        )
    ).one()
    average_score, high_intent = score_row
    positive_replies, unread_replies = count_positive_replies(db)

    return DashboardStats(
        total_companies=row.total or 0,
        researched_companies=row.researched or 0,
        pending_companies=row.pending or 0,
        analyzed_companies=row.analyzed or 0,
        companies_added_today=row.today or 0,
        companies_added_last_7_days=row.week or 0,
        total_contacts=contacts_total,
        average_overall_score=round(float(average_score), 2) if average_score else None,
        high_intent_companies=high_intent or 0,
        positive_replies=positive_replies,
        unread_replies=unread_replies,
    )


def _status_breakdown(db: Session) -> list[StatusCount]:
    status = normalized_status(Company.status)
    rows = db.execute(
        select(status.label("status"), func.count(Company.id).label("count"))
        .group_by(status)
        .order_by(func.count(Company.id).desc())
    ).all()
    return [
        StatusCount(status=row.status or "bilinmiyor", count=row.count) for row in rows
    ]


def _top_industries(db: Session, limit: int = 5) -> list[IndustryCount]:
    industry = func.nullif(trim_chars(func.coalesce(Company.industry, "")), "")
    rows = db.execute(
        select(industry.label("industry"), func.count(Company.id).label("count"))
        .where(industry.isnot(None))
        .group_by(industry)
        .order_by(func.count(Company.id).desc())
        .limit(limit)
    ).all()
    return [IndustryCount(industry=row.industry, count=row.count) for row in rows]


def fetch_recent_activity(db: Session, limit: int) -> list[ActivityOut]:
    """En son aktivite kayıtlarını getirir; tablo yoksa boş liste döner."""
    try:
        logs = db.execute(
            select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(limit)
        ).scalars().all()
    except SQLAlchemyError as exc:
        # `activity_logs` tablosu henüz oluşturulmamış olabilir; dashboard'un
        # tamamının çökmesine izin vermiyoruz.
        db.rollback()
        logger.warning("Aktivite kayıtları okunamadı: %s", exc)
        return []
    return [ActivityOut.model_validate(log) for log in logs]


def _describe(activity: ActivityOut) -> str:
    label = EVENT_LABELS.get(activity.event_type, activity.event_type)
    target = f" · {activity.company_name}" if activity.company_name else ""
    return f"{label}{target}: {activity.message}"


def build_ai_status(activities: list[ActivityOut], now: datetime) -> AiStatus:
    """Aktivite akışından "AI şu anda ne yapıyor?" bölümünü türetir."""
    if not activities:
        return AiStatus(
            state="idle",
            headline="AI şu anda beklemede — henüz bir işlem kaydı yok.",
            current=None,
            recent=[],
        )

    running = next((item for item in activities if item.status == "running"), None)
    stale_after = timedelta(minutes=settings.activity_stale_after_minutes)

    if running is not None:
        if now - running.created_at > stale_after:
            minutes = int((now - running.created_at).total_seconds() // 60)
            return AiStatus(
                state="stalled",
                headline=f"{_describe(running)} — {minutes} dakikadır yanıt vermiyor.",
                current=running,
                recent=activities,
            )
        return AiStatus(
            state="working",
            headline=_describe(running),
            current=running,
            recent=activities,
        )

    latest = activities[0]
    if latest.status == "failed":
        return AiStatus(
            state="error",
            headline=f"Son işlem hata verdi — {_describe(latest)}",
            current=None,
            recent=activities,
        )

    return AiStatus(
        state="idle",
        headline=f"AI şu anda beklemede. Son iş — {_describe(latest)}",
        current=None,
        recent=activities,
    )


def build_dashboard_stats(db: Session, activity_limit: int) -> DashboardStatsResponse:
    now = _utc_now()
    activities = fetch_recent_activity(db, activity_limit)
    return DashboardStatsResponse(
        generated_at=now,
        stats=_company_counters(db, now),
        ai_status=build_ai_status(activities, now),
        status_breakdown=_status_breakdown(db),
        top_industries=_top_industries(db),
    )
