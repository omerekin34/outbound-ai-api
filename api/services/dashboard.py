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
    POSITIVE_CLASSIFICATIONS,
    ActivityLog,
    Company,
    Contact,
    Interaction,
    Score,
    normalized_status,
    trim_chars,
)
from api.schemas import (
    ActivityOut,
    AiStatus,
    DailyCount,
    DashboardStats,
    DashboardStatsResponse,
    IndustryCount,
    StatusCount,
)
from api.services.apollo import is_apollo_plan_blocked
from api.services.inbox import count_positive_replies
from api.services.scoring import (
    DEEP_RESEARCH_STATUSES,
    QUALIFICATION_STATUSES,
    STATUS_REVIEW,
)

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


def _day_window(now: datetime, day_count: int) -> list:
    """Bugün dahil, `day_count` takvim günü (1–30)."""
    today = now.date()
    count = max(1, min(int(day_count), 30))
    return [today - timedelta(days=offset) for offset in range(count - 1, -1, -1)]


def empty_company_stats() -> DashboardStats:
    """Boş veritabanı / okuma hatası için sıfırlı sayaçlar."""
    return DashboardStats(
        total_companies=0,
        researched_companies=0,
        pending_companies=0,
        analyzed_companies=0,
        suitable_companies=0,
        companies_added_today=0,
        companies_added_last_7_days=0,
        total_contacts=0,
        average_overall_score=None,
        high_intent_companies=0,
        positive_replies=0,
        unread_replies=0,
        review_companies=0,
    )


def _empty_daily(now: datetime, days: int = 7) -> list[DailyCount]:
    return [
        DailyCount(
            date=day.isoformat(),
            label=f"{day.day} {_MONTHS_TR[day.month]}",
            analyzed=0,
            positive_replies=0,
        )
        for day in _day_window(now, days)
    ]


def empty_dashboard_stats(days: int = 7) -> DashboardStatsResponse:
    now = _utc_now()
    return DashboardStatsResponse(
        generated_at=now,
        stats=empty_company_stats(),
        ai_status=build_ai_status([], now),
        status_breakdown=[],
        top_industries=[],
        daily=_empty_daily(now, days),
    )


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
            .filter(status.in_(tuple(DEEP_RESEARCH_STATUSES)))
            .label("suitable"),
            func.count(Company.id)
            .filter(status == STATUS_REVIEW)
            .label("review"),
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
        suitable_companies=row.suitable or 0,
        review_companies=row.review or 0,
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


_MONTHS_TR = (
    "",
    "Oca",
    "Şub",
    "Mar",
    "Nis",
    "May",
    "Haz",
    "Tem",
    "Ağu",
    "Eyl",
    "Eki",
    "Kas",
    "Ara",
)


def _as_day_key(value: object) -> str:
    text = str(value)
    return text[:10]


def _daily_counts(db: Session, now: datetime, days: int = 7) -> list[DailyCount]:
    """Seçilen pencerede gerçek skor ve olumlu yanıt adedi. Veri yoksa 0."""
    window = _day_window(now, days)
    window_start = datetime.combine(window[0], datetime.min.time())

    analyzed_map: dict[str, int] = {}
    try:
        rows = db.execute(
            select(func.date(Score.calculated_at), func.count(Score.id)).where(
                Score.calculated_at >= window_start
            ).group_by(func.date(Score.calculated_at))
        ).all()
        analyzed_map = {_as_day_key(day): int(count or 0) for day, count in rows}
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("Günlük skor serisi okunamadı: %s", exc)

    reply_map: dict[str, int] = {}
    try:
        rows = db.execute(
            select(func.date(Interaction.received_at), func.count(Interaction.id)).where(
                Interaction.direction == Interaction.DIRECTION_INBOUND,
                Interaction.ai_classification.in_(POSITIVE_CLASSIFICATIONS),
                Interaction.received_at >= window_start,
            ).group_by(func.date(Interaction.received_at))
        ).all()
        reply_map = {_as_day_key(day): int(count or 0) for day, count in rows}
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("Günlük yanıt serisi okunamadı: %s", exc)

    return [
        DailyCount(
            date=day.isoformat(),
            label=f"{day.day} {_MONTHS_TR[day.month]}",
            analyzed=analyzed_map.get(day.isoformat(), 0),
            positive_replies=reply_map.get(day.isoformat(), 0),
        )
        for day in window
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
    presented: list[ActivityOut] = []
    for log in logs:
        item = ActivityOut.model_validate(log)
        if item.status == "failed" and is_apollo_plan_blocked(item.message):
            item = item.model_copy(
                update={
                    "status": "skipped",
                    "message": (
                        "Apollo People Search bu planda yok; kayıtlı kişi bulunamadı."
                    ),
                }
            )
        presented.append(item)
    return presented


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


def build_dashboard_stats(
    db: Session, activity_limit: int, *, days: int = 7
) -> DashboardStatsResponse:
    now = _utc_now()
    activities = fetch_recent_activity(db, activity_limit)

    try:
        stats = _company_counters(db, now)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("Dashboard sayaçları okunamadı; sıfır dönülüyor: %s", exc)
        stats = empty_company_stats()

    try:
        breakdown = _status_breakdown(db)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("Durum dağılımı okunamadı: %s", exc)
        breakdown = []

    try:
        industries = _top_industries(db)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("Sektör dağılımı okunamadı: %s", exc)
        industries = []

    return DashboardStatsResponse(
        generated_at=now,
        stats=stats,
        ai_status=build_ai_status(activities, now),
        status_breakdown=breakdown,
        top_industries=industries,
        daily=_daily_counts(db, now, days),
    )
