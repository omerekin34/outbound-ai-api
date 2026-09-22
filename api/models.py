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
    BigInteger,
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
from sqlalchemy.orm import relationship

from api.database import Base

# Şirket kimliklerinin veritabanındaki genişliği.
ID_LENGTH = 255


def utcnow() -> datetime:
    """Zaman dilimi bilgisi taşıyan UTC zamanı."""
    return datetime.now(timezone.utc)


def normalized_status(column: Column) -> object:
    """Kirli `status` verisini karşılaştırılabilir hale getiren SQL ifadesi.

    Veritabanındaki bazı satırlar `'new'` (tırnaklar veri içinde) şeklinde
    yazılmış. Bu ifade tırnak ve boşlukları kırpıp küçük harfe çevirir.
    """
    return func.lower(func.btrim(func.coalesce(column, ""), " '\"\t\n\r"))


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

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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


class CompanyFact(Base):
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
    observed_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

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
    version = Column(String, default="1.0")
    calculated_at = Column(DateTime, default=datetime.utcnow)

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
    detail = Column(JSONB, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now(), index=True
    )
    finished_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - hata ayıklama kolaylığı
        return f"<ActivityLog {self.event_type} status={self.status}>"
