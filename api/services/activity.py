"""Aktivite kaydı: "AI şu anda ne yapıyor?" panelini besleyen olay akışı.

Kayıtlar, iş mantığının kullandığı session'dan **bağımsız** kısa ömürlü bir
session ile yazılır. Böylece iş transaction'ı geri alınsa (rollback) bile
"başarısız oldu" kaydı veritabanında kalır.

Kayıt tutmak asla bir API isteğini düşürmez; tüm hatalar yutulup log'lanır.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from api.database import SessionLocal
from api.models import ActivityLog, utcnow

logger = logging.getLogger(__name__)

# Panelde gösterilecek olay tipleri.
EVENT_COMPANY_DISCOVERY = "company_discovery"
EVENT_WEBSITE_RESEARCH = "website_research"
EVENT_AI_ANALYSIS = "ai_analysis"
EVENT_DECISION_MAKER = "decision_maker_search"

# Panelde tek satırda gösterilebilmesi için mesaj uzunluğu sınırlanır;
# dış servisler bazen sayfalarca hata metni döndürüyor.
MAX_MESSAGE_LENGTH = 240


def _truncate(message: str, limit: int = MAX_MESSAGE_LENGTH) -> str:
    collapsed = " ".join(message.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def _reason(exc: BaseException) -> str:
    """HTTPException'ın okunabilir `detail` alanını, yoksa metnini döndürür."""
    detail = getattr(exc, "detail", None)
    return str(detail) if detail else (str(exc) or type(exc).__name__)


def _json_safe(value: Any) -> Any:
    """`detail` alanının JSONB'ye yazılabilir olmasını garanti eder."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


class ActivityRecorder:
    """Tek bir iş adımının yaşam döngüsünü kaydeder."""

    def __init__(
        self,
        event_type: str,
        message: str,
        *,
        company_id: str | None = None,
        company_name: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.event_type = event_type
        self.message = _truncate(message)
        self.company_id = company_id
        self.company_name = company_name
        self.detail = detail
        self._log_id: int | None = None
        self._started_at: float | None = None
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def start(self) -> None:
        self._started_at = time.monotonic()
        self._log_id = self._insert()

    def succeed(
        self, message: str | None = None, detail: dict[str, Any] | None = None
    ) -> None:
        self._close(ActivityLog.STATUS_SUCCESS, message, detail)

    def skip(
        self, message: str | None = None, detail: dict[str, Any] | None = None
    ) -> None:
        self._close(ActivityLog.STATUS_SKIPPED, message, detail)

    def fail(
        self, message: str | None = None, detail: dict[str, Any] | None = None
    ) -> None:
        self._close(ActivityLog.STATUS_FAILED, message, detail)

    def attach_company(self, company_id: str | None, company_name: str | None) -> None:
        """İş sırasında şirket belli olduğunda kaydı zenginleştirir."""
        self.company_id = company_id or self.company_id
        self.company_name = company_name or self.company_name

    # --- iç kullanım ---

    @property
    def _elapsed_ms(self) -> int | None:
        if self._started_at is None:
            return None
        return int((time.monotonic() - self._started_at) * 1000)

    def _insert(self) -> int | None:
        try:
            with SessionLocal() as db:
                log = ActivityLog(
                    event_type=self.event_type,
                    status=ActivityLog.STATUS_RUNNING,
                    message=self.message,
                    company_id=self.company_id,
                    company_name=self.company_name,
                    detail=_json_safe(self.detail),
                    created_at=utcnow(),
                )
                db.add(log)
                db.commit()
                return log.id
        except SQLAlchemyError as exc:
            logger.warning("Aktivite kaydı oluşturulamadı (%s): %s", self.event_type, exc)
            return None

    def _close(
        self, status: str, message: str | None, detail: dict[str, Any] | None
    ) -> None:
        if self._closed:
            return
        self._closed = True

        updates: dict[str, Any] = {
            "status": status,
            "finished_at": utcnow(),
            "duration_ms": self._elapsed_ms,
        }
        if message:
            updates["message"] = _truncate(message)
        if detail is not None:
            updates["detail"] = _json_safe(detail)
        if self.company_id:
            updates["company_id"] = self.company_id
        if self.company_name:
            updates["company_name"] = self.company_name

        try:
            with SessionLocal() as db:
                if self._log_id is None:
                    # Açılış kaydı yazılamamışsa kapanışı tek seferde yaz.
                    db.add(
                        ActivityLog(
                            event_type=self.event_type,
                            message=_truncate(message) if message else self.message,
                            company_id=self.company_id,
                            company_name=self.company_name,
                            created_at=utcnow(),
                            **{
                                k: v
                                for k, v in updates.items()
                                if k not in {"company_id", "company_name", "message"}
                            },
                        )
                    )
                else:
                    db.query(ActivityLog).filter(ActivityLog.id == self._log_id).update(
                        updates, synchronize_session=False
                    )
                db.commit()
        except SQLAlchemyError as exc:
            logger.warning("Aktivite kaydı kapatılamadı (%s): %s", self.event_type, exc)


@contextmanager
def track_activity(
    event_type: str,
    message: str,
    *,
    company_id: str | None = None,
    company_name: str | None = None,
    detail: dict[str, Any] | None = None,
) -> Iterator[ActivityRecorder]:
    """İş adımını `running` olarak açar, çıkışta sonucuna göre kapatır.

    Kullanım::

        with track_activity(EVENT_WEBSITE_RESEARCH, "Site taranıyor") as activity:
            ...
            activity.succeed("Tarama tamamlandı", {"chars": 1200})
    """
    recorder = ActivityRecorder(
        event_type,
        message,
        company_id=company_id,
        company_name=company_name,
        detail=detail,
    )
    recorder.start()
    try:
        yield recorder
    except Exception as exc:
        recorder.fail(
            f"{message} başarısız: {_reason(exc)}",
            {"error": type(exc).__name__},
        )
        raise
    else:
        if not recorder.closed:
            recorder.succeed()
