"""SQLAlchemy modelleri.

Bu modeller Neon'daki mevcut tablo yapısıyla birebir eşleşir. Özellikle
dikkat edilmesi gerekenler:

* `companies.id` bir tamsayı değil, VARCHAR(255)'tir (Apollo kaynaklı
  kimlikler tutuluyor, örn. `54a12aa269702da220e32502`). İlişkili tabloların
  `company_id` alanları da bu yüzden String'dir.
* `companies.website` üzerinde tekillik kısıtı vardır (`unique_website`),
  `domain` üzerinde yoktur.
* `status` alanı bazı kayıtlarda tırnak işaretiyle yazılmıştır ("'new'").
  Sorgularda daima `normalized_status()` kullanın.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement

# Postgres'te JSONB, diğer motorlarda (testlerde SQLite) JSON olarak oluşur.
JsonColumn = JSON().with_variant(JSONB(), "postgresql")
from sqlalchemy.orm import relationship

from api.database import Base

# Şirket kimliklerinin veritabanındaki genişliği.
ID_LENGTH = 255


def utcnow() -> datetime:
    """Zaman dilimi bilgisi taşıyan UTC zamanı."""
    return datetime.now(timezone.utc)


def naive_utcnow() -> datetime:
    """Zaman dilimi taşımayan TIMESTAMP kolonları için UTC zamanı.

    `datetime.utcnow()` kullanım dışı bırakıldığı için tercih edilir.
    """
    return utcnow().replace(tzinfo=None)


class _TrimChars(FunctionElement):
    """İki ucundan verilen karakterleri kırpar.

    Postgres'te `btrim(x, chars)`, SQLite'ta `trim(x, chars)` olarak derlenir;
    ikisi de aynı işi yapar. Testler SQLite kullandığı için gerekli.
    """

    name = "trim_chars"
    inherit_cache = True


@compiles(_TrimChars)
def _compile_trim_chars(element, compiler, **kw) -> str:
    return f"btrim({compiler.process(element.clauses, **kw)})"


@compiles(_TrimChars, "sqlite")
def _compile_trim_chars_sqlite(element, compiler, **kw) -> str:
    return f"trim({compiler.process(element.clauses, **kw)})"


#: Kırpılacak varsayılan karakterler: boşluk türleri.
WHITESPACE = " \t\n\r"


def trim_chars(expression: object, chars: str = WHITESPACE) -> object:
    """Motordan bağımsız iki uçlu kırpma."""
    return _TrimChars(expression, chars)


def normalized_status(column: Column) -> object:
    """Kirli `status` verisini karşılaştırılabilir hale getiren SQL ifadesi.

    Veritabanındaki bazı satırlar `'new'` (tırnaklar veri içinde) şeklinde
    yazılmış. Bu ifade tırnak ve boşlukları kırpıp küçük harfe çevirir.
    """
    return func.lower(trim_chars(func.coalesce(column, ""), " '\"\t\n\r"))


class Company(Base):
    __tablename__ = "companies"

    id = Column(String(ID_LENGTH), primary_key=True, index=True)
    name = Column(String, index=True)
    normalized_name = Column(String, index=True)
    domain = Column(String(ID_LENGTH), index=True)
    website = Column(String, unique=True)
    industry = Column(String)
    country = Column(String, default="Turkey")
    city = Column(String)
    postal_code = Column(String(20))
    raw_address = Column(Text)
    status = Column(String, default="new", index=True)

    logo_url = Column(Text)
    linkedin_url = Column(Text)
    founded_year = Column(Integer)
    estimated_num_employees = Column(Integer)
    organization_revenue = Column(BigInteger)

    created_at = Column(DateTime, default=naive_utcnow)
    updated_at = Column(DateTime, default=naive_utcnow, onupdate=naive_utcnow)

    facts = relationship(
        "CompanyFact",
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # `scores.company_id` üzerinde tekillik kısıtı var: şirket başına tek skor.
    score = relationship(
        "Score",
        back_populates="company",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    contacts = relationship("Contact", back_populates="company")
    interactions = relationship(
        "Interaction",
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - hata ayıklama kolaylığı
        return f"<Company id={self.id!r} name={self.name!r}>"


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(String(ID_LENGTH), primary_key=True)
    company_id = Column(String(ID_LENGTH), ForeignKey("companies.id"), index=True)
    first_name = Column(String(100))
    last_name = Column(String(100))
    title = Column(String(100))
    department = Column(Text)
    email = Column(String(ID_LENGTH), unique=True)
    corporate_phone = Column(Text)
    linkedin_url = Column(Text)
    created_at = Column(DateTime, server_default=func.current_timestamp())

    company = relationship("Company", back_populates="contacts")
    interactions = relationship("Interaction", back_populates="contact")

    @property
    def full_name(self) -> str | None:
        """Ekranda gösterilecek ad; iki parça da boşsa None."""
        parts = [part for part in (self.first_name, self.last_name) if part and part.strip()]
        return " ".join(part.strip() for part in parts) or None


class CompanyFact(Base):
    """Step 15 — LLM'nin çıkardığı tek bir kanıtlı olgu.

    Alanlar spec ile birebir: id, company_id, fact_type, value, confidence,
    source_url, source_type, evidence_text, observed_at, expires_at, created_at.
    Puan bu tablodan Python'da hesaplanır; LLM skor yazmaz.
    """

    __tablename__ = "company_facts"
    __table_args__ = (
        UniqueConstraint("company_id", "fact_type", name="unique_company_fact"),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        String(ID_LENGTH), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    fact_type = Column(String, index=True)  # erp, crm, dealer_network vb.
    value = Column(String)
    confidence = Column(Float)
    source_url = Column(String)
    source_type = Column(String)
    evidence_text = Column(Text)
    observed_at = Column(DateTime, default=naive_utcnow)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=naive_utcnow)

    company = relationship("Company", back_populates="facts")


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (
        UniqueConstraint("company_id", name="scores_company_id_unique"),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        String(ID_LENGTH), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    icp_score = Column(Float)
    need_score = Column(Float)
    timing_score = Column(Float)
    reachability_score = Column(Float)
    overall_score = Column(Float, index=True)
    # Step 19–20: yeterlilik sonucu ve derin araştırma bayrağı.
    qualification_status = Column(String(32), index=True)
    requires_deep_research = Column(Boolean, nullable=False, default=False, index=True)
    version = Column(String, default="1.0")
    calculated_at = Column(DateTime, default=naive_utcnow)

    company = relationship("Company", back_populates="score")


class OutreachMessage(Base):
    __tablename__ = "outreach_messages"

    id = Column(Integer, primary_key=True)
    company_id = Column(String(ID_LENGTH), ForeignKey("companies.id"), index=True)
    contact_id = Column(
        String(ID_LENGTH), ForeignKey("contacts.id", ondelete="CASCADE"), index=True
    )
    campaign_id = Column(Integer)
    subject = Column(String(ID_LENGTH))
    body = Column(Text)
    status = Column(String(50), default="draft", index=True)
    provider_message_id = Column(String(ID_LENGTH))
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.current_timestamp())


class Interaction(Base):
    """Bir kişiyle yapılan tek bir yazışma adımı (çoğunlukla gelen e-posta yanıtı).

    "Gelen Kutusu" ve "Fırsatlar" ekranları bu tabloyu besler:
      * `direction == "inbound"` satırlar gelen kutusunu oluşturur.
      * `ai_classification` alanı AI'ın yanıtı nasıl sınıflandırdığını tutar;
        `POSITIVE_CLASSIFICATIONS` içindekiler fırsat sayılır.
      * `body` yanıtın **birebir** metnidir; ekranda kısaltılarak gösterilir.
    """

    __tablename__ = "interactions"
    __table_args__ = (
        Index("ix_interactions_direction_received_at", "direction", "received_at"),
        Index("ix_interactions_classification", "ai_classification", "received_at"),
    )

    DIRECTION_INBOUND = "inbound"
    DIRECTION_OUTBOUND = "outbound"

    CLASS_POSITIVE = "positive"
    CLASS_MEETING_REQUEST = "meeting_request"
    CLASS_QUESTION = "question"
    CLASS_NEUTRAL = "neutral"
    CLASS_NEGATIVE = "negative"
    CLASS_UNSUBSCRIBE = "unsubscribe"
    CLASS_AUTO_REPLY = "auto_reply"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        String(ID_LENGTH), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    contact_id = Column(
        String(ID_LENGTH),
        ForeignKey("contacts.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    # Hangi gönderime cevap geldiği; eşleştirilemezse boş kalır.
    outreach_message_id = Column(
        Integer,
        ForeignKey("outreach_messages.id", ondelete="SET NULL"),
        nullable=True,
    )

    direction = Column(
        String(16), nullable=False, default=DIRECTION_INBOUND, index=True
    )
    channel = Column(String(32), nullable=False, default="email")

    subject = Column(String(500))
    body = Column(Text, nullable=False)

    ai_classification = Column(String(32), index=True, nullable=True)
    ai_confidence = Column(Float, nullable=True)
    ai_summary = Column(Text, nullable=True)
    ai_next_action = Column(Text, nullable=True)

    # Aynı e-postanın iki kez işlenmesini engeller.
    provider_message_id = Column(String(ID_LENGTH), unique=True, nullable=True)

    is_read = Column(Boolean, nullable=False, default=False, index=True)
    received_at = Column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=utcnow,
        server_default=func.now(),
    )

    company = relationship("Company", back_populates="interactions")
    contact = relationship("Contact", back_populates="interactions")

    def __repr__(self) -> str:  # pragma: no cover - hata ayıklama kolaylığı
        return (
            f"<Interaction id={self.id} company_id={self.company_id!r} "
            f"class={self.ai_classification!r}>"
        )


# Fırsat sayılan sınıflandırmalar. Toplantı isteyen bir yanıt da olumludur.
POSITIVE_CLASSIFICATIONS: tuple[str, ...] = (
    Interaction.CLASS_POSITIVE,
    Interaction.CLASS_MEETING_REQUEST,
)


class ActivityLog(Base):
    """"AI şu anda ne yapıyor?" panelini besleyen olay kaydı.

    Her iş adımı `running` durumunda açılır, sonunda `success` / `failed` /
    `skipped` olarak kapatılır. Panel, en son `running` kaydı "şu anda
    yapılan iş" olarak gösterir.
    """

    __tablename__ = "activity_logs"
    __table_args__ = (
        Index("ix_activity_logs_status_created_at", "status", "created_at"),
    )

    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(String(ID_LENGTH), index=True, nullable=True)
    # Panel sorgusunun JOIN yapmasına gerek kalmaması için isim kopyalanır.
    company_name = Column(String, nullable=True)
    event_type = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, default=STATUS_RUNNING, index=True)
    message = Column(Text, nullable=False)
    detail = Column(JsonColumn, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now(), index=True
    )
    finished_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - hata ayıklama kolaylığı
        return f"<ActivityLog {self.event_type} status={self.status}>"
