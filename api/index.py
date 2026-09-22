"""FastAPI uygulama giriş noktası.

Yapı:
    api/config.py            -> ortam değişkenleri
    api/database.py          -> engine + session
    api/models.py            -> SQLAlchemy tabloları
    api/schemas.py           -> Pydantic giriş/çıkış sözleşmesi
    api/services/            -> iş mantığı (dashboard, aktivite, zenginleştirme)
    api/routers/             -> HTTP katmanı
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from api import models  # noqa: F401  (metadata'nın yüklenmesi için gerekli)
from api.config import get_settings
from api.database import Base, engine
from api.routers import companies, dashboard, health

settings = get_settings()

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(
        "API başlatılıyor (ortam=%s, veritabanı=%s)",
        settings.environment,
        settings.database_host,
    )
    if settings.auto_create_tables:
        # Sadece eksik tabloları oluşturur; mevcut tabloları değiştirmez.
        # Şema değişiklikleri için scripts/migrate.py kullanılmalıdır.
        try:
            Base.metadata.create_all(bind=engine)
        except SQLAlchemyError:
            logger.exception("Tablolar oluşturulamadı; API yine de başlatılıyor")
    yield
    engine.dispose()
    logger.info("API kapatıldı")


app = FastAPI(
    title="AI Commercial Operations API",
    description="B2B outbound otomasyonu için şirket keşfi, araştırma ve dashboard API'si.",
    version=health.SERVICE_VERSION,
    lifespan=lifespan,
)

# --- CORS -------------------------------------------------------------------
# İzinli origin'ler .env içindeki CORS_ORIGINS ile yönetilir (virgülle ayrılmış).
# Wildcard ("*") kullanıldığında tarayıcı kuralları gereği credential kapatılır.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=settings.allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
    max_age=600,
)

app.include_router(health.router)
app.include_router(dashboard.router, prefix="/api")
app.include_router(companies.router, prefix="/api")
# Eski frontend çağrılarını kırmamak için prefix'siz yollar da açık tutulur
# (`/companies/discover`). Dokümantasyonda gösterilmez; yeni kodda `/api` kullanın.
app.include_router(companies.router, include_in_schema=False)


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Veritabanı hatalarını 503 olarak döndürür, içeriği dışarı sızdırmaz."""
    logger.exception("İşlenmeyen veritabanı hatası", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Veritabanı şu anda kullanılamıyor, lütfen tekrar deneyin."},
    )
