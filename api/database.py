"""Veritabanı bağlantısı (Neon PostgreSQL) ve session yönetimi."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from api.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

if not settings.database_url:
    raise RuntimeError(
        "DATABASE_URL tanımlı değil. Neon bağlantı adresini .env dosyasına ekleyin."
    )

# Neon bağlantıları boşta kalınca kapatılır; `pool_pre_ping` ölü bağlantıları
# istek anında tespit edip yenisini açar.
_engine_kwargs: dict[str, object] = {
    "pool_pre_ping": True,
    "future": True,
    "connect_args": {
        "connect_timeout": settings.db_connect_timeout_seconds,
        "application_name": "otomasyon-ai-api",
        # Kaçak bir sorgunun tüm havuzu kilitlemesini engeller.
        "options": f"-c statement_timeout={settings.db_statement_timeout_ms}",
    },
}

if settings.db_use_null_pool:
    _engine_kwargs["poolclass"] = NullPool
else:
    _engine_kwargs.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle_seconds,
    )

engine = create_engine(settings.database_url, **_engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

Base = declarative_base()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: istek başına bir session açar ve garantili kapatır."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        # Yarım kalmış transaction'ın bir sonraki isteğe sızmasını engeller.
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """HTTP isteği dışındaki işler (arka plan görevleri, script'ler) için session."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
