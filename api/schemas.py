"""Pydantic şemaları: API'nin giriş/çıkış sözleşmesi.

Frontend yalnızca buradaki alanlara güvenmelidir; veritabanı kolon adları
değişse bile bu sözleşme korunur.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.services.website_research import MAX_PAGES

AiState = Literal["working", "idle", "stalled", "error"]
ActivityStatus = Literal["running", "success", "failed", "skipped"]


def as_utc(value: datetime | None) -> datetime | None:
    """Naive zaman damgalarını UTC kabul eder (mevcut tablolar naive tutuyor)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class UtcModel(BaseModel):
    """ORM nesnelerinden okunan zaman alanlarını UTC'ye sabitler.

    Mevcut tablolar zaman dilimi taşımayan TIMESTAMP kullanıyor. Burada
    doğrulama anında UTC etiketi eklenir; böylece hem JSON çıktısı `Z` ekli
    olur hem de servis katmanındaki tarih karşılaştırmaları tutarlı çalışır.
    """

    model_config = ConfigDict(from_attributes=True)

    @field_validator("*", mode="after")
    @classmethod
    def _ensure_utc(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            return as_utc(value)
        return value


# --- İstekler ---------------------------------------------------------------


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    domain: str = Field(min_length=3, max_length=255)
    website: str | None = None
    industry: str | None = None
    employee_count: int | None = Field(default=None, ge=0)
    country: str | None = "Turkey"
    city: str | None = None
    linkedin_url: str | None = None
    founded_year: int | None = Field(default=None, ge=1800, le=2100)

    @field_validator("domain")
    @classmethod
    def _clean_domain(cls, value: str) -> str:
        """`https://www.x.com/abc` gibi girdileri `x.com` haline getirir."""
        cleaned = value.strip().lower()
        for prefix in ("https://", "http://"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :]
        cleaned = cleaned.removeprefix("www.").split("/", 1)[0].strip()
        if not cleaned:
            raise ValueError("Geçerli bir domain girin.")
        return cleaned


class CompanyResearchRequest(BaseModel):
    """Workflow 3 girdisi. Spec: `company_id` ve `website` zorunludur."""

    company_id: str = Field(min_length=1, max_length=255)
    website: str = Field(min_length=4, max_length=2048)
    # Spec: 20 kesin üst sınırdır; daha küçük bir değer verilebilir ama
    # `le=MAX_PAGES` sayesinde aşılamaz.
    max_pages: int = Field(default=MAX_PAGES, ge=1, le=MAX_PAGES)

    @field_validator("website")
    @classmethod
    def _normalize_website(cls, value: str) -> str:
        """Şemasız girdileri `https://` ile tamamlar ve adresi doğrular."""
        candidate = value.strip()
        if not candidate:
            raise ValueError("Web sitesi adresi boş olamaz.")
        if "://" not in candidate:
            candidate = f"https://{candidate}"

        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Web sitesi adresi http veya https olmalıdır.")
        if not parsed.netloc or "." not in parsed.netloc:
            raise ValueError("Geçerli bir web sitesi alan adı girin.")
        return candidate


class CompanyAnalyzeRequest(BaseModel):
    company_id: str = Field(min_length=1, max_length=255)
    website_content: str = Field(min_length=1)
    source_url: str | None = None


# --- Yanıtlar ---------------------------------------------------------------


class CompanyOut(UtcModel):
    id: str
    name: str | None
    domain: str | None
    website: str | None
    industry: str | None
    country: str | None
    city: str | None
    status: str | None

    @field_validator("status", mode="after")
    @classmethod
    def _clean_status(cls, value: str | None) -> str | None:
        """Bazı satırlarda status tırnakla kaydedilmiş ("'new'"); temizleyip döner."""
        if value is None:
            return None
        return value.strip(" '\"\t\n\r").lower() or None
    estimated_num_employees: int | None
    founded_year: int | None
    linkedin_url: str | None
    logo_url: str | None
    created_at: datetime | None
    updated_at: datetime | None


class CompanyListOut(BaseModel):
    items: list[CompanyOut]
    total: int
    limit: int
    offset: int


class ScoresOut(BaseModel):
    icp_score: float
    need_score: float
    timing_score: float = 0.0
    reachability_score: float = 0.0
    #: Step 19: (ICP + Need) / 2.
    overall_score: float
    qualification_status: str
    requires_deep_research: bool


class FactOut(BaseModel):
    fact_type: str
    value: str
    confidence: float
    evidence_text: str
    #: Kanıtın alındığı sayfa; analyzer'ın uydurduğu adresler filtrelenir.
    source_url: str | None


class CompanyAnalysisOut(BaseModel):
    scores: ScoresOut
    facts: list[FactOut]


class ResearchedPageOut(BaseModel):
    url: str
    category: str
    characters: int


class WebsiteResearchResponse(BaseModel):
    """Workflow 3 çıktısı."""

    status: Literal["success"]
    company_id: str
    company: str | None
    website: str
    max_pages: int
    discovered_urls: int
    selected_pages: int
    scraped_pages: int
    total_characters: int
    credits_used: int | None
    used_fallback: bool
    pages: list[ResearchedPageOut]
    analysis: CompanyAnalysisOut
    facts_saved: int
    message: str


class ReplyOut(UtcModel):
    """Gelen kutusu / fırsatlar listesindeki tek bir yanıt satırı."""

    id: int

    # Şirket
    company_id: str | None
    company_name: str | None
    company_domain: str | None
    company_industry: str | None
    company_city: str | None

    # Karar verici
    contact_id: str | None
    contact_name: str | None
    contact_title: str | None
    contact_email: str | None

    # Yanıtın kendisi
    subject: str | None
    #: Yanıtın birebir metni.
    body: str
    #: Tabloda gösterilen tek satırlık önizleme.
    snippet: str

    # AI sınıflandırması
    classification: str | None
    confidence: float | None
    ai_summary: str | None
    ai_next_action: str | None

    channel: str
    is_read: bool
    received_at: datetime
    #: Şirketin genel puanı (varsa); fırsat sıralamasında kullanılır.
    overall_score: float | None


class ClassificationCount(BaseModel):
    classification: str
    count: int


class InboxResponse(BaseModel):
    items: list[ReplyOut]
    #: Seçili filtrelere uyan yanıt sayısı (sayfalama için).
    total: int
    limit: int
    offset: int
    #: Sınıflandırma/okunma filtresi uygulanmadan toplam gelen yanıt sayısı.
    #: Üst sayaçlar ve "Tümü" çipi bunu kullanır.
    inbound_total: int
    unread_count: int
    positive_count: int
    classification_breakdown: list[ClassificationCount]


class OpportunitiesResponse(BaseModel):
    items: list[ReplyOut]
    total: int
    limit: int
    offset: int
    unique_companies: int
    #: Fırsat listesindeki şirketlerin ortalama genel puanı.
    average_score: float | None


class ActivityOut(UtcModel):
    id: int
    event_type: str
    status: ActivityStatus
    message: str
    company_id: str | None
    company_name: str | None
    detail: dict[str, Any] | None
    duration_ms: int | None
    created_at: datetime
    finished_at: datetime | None


class DashboardStats(BaseModel):
    """Dashboard'un üst bölümündeki sayaçlar."""

    total_companies: int
    researched_companies: int
    pending_companies: int
    analyzed_companies: int
    companies_added_today: int
    companies_added_last_7_days: int
    total_contacts: int
    average_overall_score: float | None
    high_intent_companies: int
    #: AI'ın olumlu sınıflandırdığı gelen yanıt sayısı ("Olumlu yanıt" kartı).
    positive_replies: int
    #: Henüz okunmamış gelen yanıt sayısı (gelen kutusu rozeti).
    unread_replies: int


class AiStatus(BaseModel):
    """"AI şu anda ne yapıyor?" bölümünün içeriği."""

    state: AiState
    headline: str
    current: ActivityOut | None
    recent: list[ActivityOut]


class StatusCount(BaseModel):
    status: str
    count: int


class IndustryCount(BaseModel):
    industry: str
    count: int


class DashboardStatsResponse(BaseModel):
    generated_at: datetime
    stats: DashboardStats
    ai_status: AiStatus
    status_breakdown: list[StatusCount]
    top_industries: list[IndustryCount]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    environment: str
    database: Literal["up", "down"]
    database_host: str
    version: str
