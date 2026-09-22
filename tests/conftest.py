"""Ortak test altyapısı.

Testler geçici bir SQLite dosyası kullanır ve dış servislere hiç çıkmaz:
ne Neon bağlantısı ne de API anahtarı gerekir.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api import database as database_module
from api.database import Base, get_db
from api.index import app
from api.services import activity as activity_service
from api.services import apollo as apollo_service
from api.services import enrichment


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch) -> None:
    """Gerçek Firecrawl/OpenAI istemcilerinin kurulmasını engeller."""

    def explode(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Test gerçek bir dış servis istemcisi oluşturdu")

    monkeypatch.setattr(enrichment, "_build_firecrawl", explode)
    monkeypatch.setattr(enrichment, "_build_openai", explode)
    monkeypatch.setattr(apollo_service.ApolloClient, "_request", explode)
    # .env'de anahtar olsa bile testler gerçek Apollo istemcisi kurmaz.
    monkeypatch.setattr(apollo_service, "_build_client", lambda: None)


@pytest.fixture
def db_sessionmaker(tmp_path, monkeypatch) -> Iterator[Any]:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(activity_service, "SessionLocal", maker)
    monkeypatch.setattr(database_module, "SessionLocal", maker)
    yield maker
    engine.dispose()


@pytest.fixture
def client(db_sessionmaker, monkeypatch) -> Iterator[TestClient]:
    """`get_db`'yi SQLite'a yönlendirmiş TestClient."""

    def override_get_db() -> Iterator[Any]:
        session = db_sessionmaker()
        try:
            yield session
        finally:
            session.close()

    # Aktivite ve arka plan keşif görevi kendi session'ını açar; SQLite'a çek.
    monkeypatch.setattr(activity_service, "SessionLocal", db_sessionmaker)
    monkeypatch.setattr(database_module, "SessionLocal", db_sessionmaker)
    app.dependency_overrides[get_db] = override_get_db

    # Bilinçli olarak context manager kullanmıyoruz: `lifespan` gerçek Neon
    # motoruna `create_all` çalıştırıyor, testin buna ihtiyacı yok.
    yield TestClient(app)

    app.dependency_overrides.clear()
