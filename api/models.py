from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from api.database import Base

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    normalized_name = Column(String, index=True)
    domain = Column(String, unique=True, index=True)
    website = Column(String)
    industry = Column(String)
    employee_count = Column(Integer)
    country = Column(String, default="Turkey")
    city = Column(String)
    status = Column(String, default="new")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    facts = relationship("CompanyFact", back_populates="company")
    scores = relationship("Score", back_populates="company")

class CompanyFact(Base):
    __tablename__ = "company_facts"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    fact_type = Column(String, index=True) # erp, crm, dealer_network vb.
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

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    icp_score = Column(Float)
    need_score = Column(Float)
    timing_score = Column(Float)
    reachability_score = Column(Float)
    overall_score = Column(Float)
    version = Column(String, default="1.0")
    calculated_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="scores")