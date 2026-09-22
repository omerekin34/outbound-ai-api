"""Sağlık kontrolü: deploy sonrası ve uptime izleme için."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from api.config import get_settings
from api.database import engine
from api.schemas import HealthResponse

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(tags=["system"])

SERVICE_NAME = "Outbound Automation API"
SERVICE_VERSION = "1.1.0"


def _database_is_up() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError as exc:
        logger.warning("Veritabanı sağlık kontrolü başarısız: %s", exc)
        return False


@router.get("/", response_model=HealthResponse, summary="Servis durumu")
@router.get("/api/health", response_model=HealthResponse, summary="Servis durumu")
def health() -> HealthResponse:
    database_up = _database_is_up()
    return HealthResponse(
        status="ok" if database_up else "degraded",
        service=SERVICE_NAME,
        environment=settings.environment,
        database="up" if database_up else "down",
        # Yalnızca sunucu adı; kullanıcı adı/şifre dışarı verilmez.
        database_host=settings.database_host,
        version=SERVICE_VERSION,
    )
