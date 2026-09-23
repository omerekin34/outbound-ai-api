"""Uygulama ayarları: tüm ortam değişkenleri tek yerden okunur.

Ortam değişkenleri `.env` dosyasından yüklenir. Hiçbir sır (secret) log'a
veya API yanıtına yazılmaz; bağlantı adresleri `masked_database_url` ile
maskelenmiş şekilde raporlanır.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv

load_dotenv()

# Frontend geliştirme sunucularının varsayılan adresleri (Next.js / Vite).
DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
)

# Vercel preview deployment'larını otomatik kabul et.
DEFAULT_CORS_ORIGIN_REGEX = r"https://.*\.vercel\.app"


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value.strip() if value else default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = _env(name)
    if not raw:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _normalize_database_url(raw: str) -> str:
    """Neon connection string'ini SQLAlchemy + psycopg2 için hazırlar.

    - `postgres://` şemasını `postgresql+psycopg2://` yapar.
    - Neon TLS zorunlu olduğu için `sslmode=require` ekler.
    """
    if not raw:
        return ""

    parts = urlsplit(raw)
    scheme = parts.scheme
    if scheme in {"postgres", "postgresql"}:
        scheme = "postgresql+psycopg2"

    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("sslmode", "require")

    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _mask_database_url(url: str) -> str:
    """Şifreyi gizleyerek log'lanabilir bir bağlantı adresi üretir."""
    if not url:
        return ""
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return f"{parts.scheme}://{parts.netloc}{parts.path}"
    credentials, host = parts.netloc.rsplit("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{parts.scheme}://{user}:***@{host}{parts.path}"


@dataclass(frozen=True)
class Settings:
    database_url: str
    environment: str
    debug: bool

    # Veritabanı havuzu
    db_pool_size: int
    db_max_overflow: int
    db_pool_recycle_seconds: int
    db_connect_timeout_seconds: int
    db_statement_timeout_ms: int
    db_use_null_pool: bool

    # CORS
    cors_origins: tuple[str, ...]
    cors_origin_regex: str

    # Davranış
    auto_create_tables: bool
    activity_stale_after_minutes: int
    dashboard_activity_limit: int

    # Üçüncü parti servisler
    firecrawl_api_key: str
    openai_api_key: str
    openai_model: str
    apollo_api_key: str
    apollo_max_contacts: int

    # Workflow 3 — web sitesi araştırması
    # Not: taranacak azami sayfa sayısı (20) spec gereği sabittir ve ortam
    # değişkeniyle yükseltilemez; bkz. services/website_research.MAX_PAGES.
    research_map_limit: int
    research_chars_per_page: int
    research_total_chars: int
    research_scrape_timeout_seconds: int
    #: n8n toplu gönderiminde şirketler arası bekleme; 0 kapatır.
    research_job_gap_seconds: float

    @property
    def masked_database_url(self) -> str:
        """Şifresi gizlenmiş bağlantı adresi — yalnızca sunucu log'ları için."""
        return _mask_database_url(self.database_url)

    @property
    def database_host(self) -> str:
        """Sadece sunucu adı. Herkese açık health endpoint'inde kullanılır."""
        if not self.database_url:
            return ""
        return urlsplit(self.database_url).hostname or ""

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def allow_credentials(self) -> bool:
        # Tarayıcılar `Access-Control-Allow-Origin: *` ile credential göndermeyi
        # reddeder; wildcard kullanılıyorsa credential'ı kapatıyoruz.
        return "*" not in self.cors_origins


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Vercel gibi serverless ortamlarda her istek yeni bir süreçte çalışabilir,
    # bu yüzden kalıcı bağlantı havuzu tutmak yerine NullPool kullanılır.
    on_serverless = bool(_env("VERCEL") or _env("AWS_LAMBDA_FUNCTION_NAME"))

    return Settings(
        database_url=_normalize_database_url(_env("DATABASE_URL")),
        environment=_env("ENVIRONMENT", "development"),
        debug=_env_bool("DEBUG", default=False),
        db_pool_size=_env_int("DB_POOL_SIZE", 5),
        db_max_overflow=_env_int("DB_MAX_OVERFLOW", 5),
        db_pool_recycle_seconds=_env_int("DB_POOL_RECYCLE", 300),
        db_connect_timeout_seconds=_env_int("DB_CONNECT_TIMEOUT", 10),
        db_statement_timeout_ms=_env_int("DB_STATEMENT_TIMEOUT_MS", 15_000),
        db_use_null_pool=_env_bool("DB_USE_NULL_POOL", default=on_serverless),
        cors_origins=_env_list("CORS_ORIGINS", DEFAULT_CORS_ORIGINS),
        cors_origin_regex=_env("CORS_ORIGIN_REGEX", DEFAULT_CORS_ORIGIN_REGEX),
        auto_create_tables=_env_bool("AUTO_CREATE_TABLES", default=True),
        activity_stale_after_minutes=_env_int("ACTIVITY_STALE_AFTER_MINUTES", 10),
        dashboard_activity_limit=_env_int("DASHBOARD_ACTIVITY_LIMIT", 10),
        firecrawl_api_key=_env("FIRECRAWL_API_KEY"),
        openai_api_key=_env("OPENAI_API_KEY"),
        openai_model=_env("OPENAI_MODEL", "gpt-4o-mini"),
        apollo_api_key=_env("APOLLO_API_KEY"),
        apollo_max_contacts=_env_int("APOLLO_MAX_CONTACTS", 8),
        research_map_limit=_env_int("RESEARCH_MAP_LIMIT", 300),
        research_chars_per_page=_env_int("RESEARCH_CHARS_PER_PAGE", 2_500),
        research_total_chars=_env_int("RESEARCH_TOTAL_CHARS", 30_000),
        research_scrape_timeout_seconds=_env_int("RESEARCH_SCRAPE_TIMEOUT", 180),
        research_job_gap_seconds=_env_float("RESEARCH_JOB_GAP_SECONDS", 5.0),
    )
