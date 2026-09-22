"""Analiz sonuçlarının kalıcılaştırılması (fact/kanıt + backend puanlama).

Akış Step 14–16'ya uyar:
  1. LLM yalnızca fact üretir.
  2. Fact'ler `company_facts` tablosuna yazılır.
  3. Puanlar Python'da, tablodaki fact'lerden hesaplanır (`scoring.py`).
  4. Hesaplanan puan `scores` tablosuna yazılır.

LLM'nin döndürdüğü herhangi bir `scores` alanı burada okunmaz.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from api import models
from api.services.scoring import SCORE_VERSION, Scores, calculate_scores


def persist_scores(db: Session, company_id: str, scores: dict[str, Any] | Scores) -> None:
    """`scores.company_id` tekil olduğu için var olan kayıt güncellenir."""
    record = db.execute(
        select(models.Score).where(models.Score.company_id == company_id)
    ).scalar_one_or_none()

    payload = scores.as_dict() if isinstance(scores, Scores) else dict(scores)
    values: dict[str, Any] = {
        field: payload.get(field, 0.0)
        for field in (
            "icp_score",
            "need_score",
            "timing_score",
            "reachability_score",
            "overall_score",
        )
    }
    values["qualification_status"] = payload.get("qualification_status")
    values["requires_deep_research"] = bool(payload.get("requires_deep_research"))
    values["calculated_at"] = models.naive_utcnow()
    values["version"] = (
        scores.version if isinstance(scores, Scores) else payload.get("version", SCORE_VERSION)
    )

    if record is None:
        db.add(models.Score(company_id=company_id, **values))
        return
    for key, value in values.items():
        setattr(record, key, value)


def persist_facts(
    db: Session,
    company: models.Company,
    facts: list[dict[str, Any]],
    *,
    source_type: str,
) -> int:
    """`(company_id, fact_type)` tekil olduğu için tip başına tek kayıt tutulur."""
    existing = {
        fact.fact_type: fact
        for fact in db.execute(
            select(models.CompanyFact).where(
                models.CompanyFact.company_id == company.id
            )
        ).scalars()
    }

    written = 0
    for fact in facts:
        value = (fact.get("value") or "").strip()
        evidence = (fact.get("evidence_text") or "").strip()
        # Step 14: kanıtsız satır skor ve tabloya girmez.
        if not value or not evidence:
            continue

        fact_type = fact.get("fact_type") or "unknown"
        values = {
            "value": value,
            "confidence": fact.get("confidence") or 0.0,
            "evidence_text": evidence,
            "source_type": source_type,
            # Kanıtın alındığı asıl sayfa; yoksa şirketin web sitesi.
            "source_url": fact.get("source_url") or company.website,
            "observed_at": models.naive_utcnow(),
        }

        record = existing.get(fact_type)
        if record is None:
            # Yeni kaydı sözlüğe de koyuyoruz: aynı yanıtta tekrar eden bir
            # fact_type ikinci kez INSERT edilirse tekillik kısıtı patlar.
            record = models.CompanyFact(
                company_id=company.id, fact_type=fact_type, **values
            )
            db.add(record)
            existing[fact_type] = record
        else:
            for key, value in values.items():
                setattr(record, key, value)
        written += 1

    return written


def load_facts(db: Session, company_id: str) -> list[models.CompanyFact]:
    """Şirketin `company_facts` satırlarını okur (puanlama girdisi)."""
    return list(
        db.execute(
            select(models.CompanyFact).where(models.CompanyFact.company_id == company_id)
        ).scalars()
    )


def score_company(db: Session, company_id: str) -> Scores:
    """Tablodaki fact'lerden puanı hesaplar; skor ve şirket durumunu yazar."""
    scores = calculate_scores(load_facts(db, company_id))
    persist_scores(db, company_id, scores)

    company = db.get(models.Company, company_id)
    if company is not None:
        company.status = scores.qualification_status
    return scores


def persist_analysis(
    db: Session,
    company: models.Company,
    analysis: dict[str, Any],
    *,
    source_type: str,
) -> tuple[int, Scores]:
    """Fact'leri kaydeder, ardından backend puanını hesaplar.

    `analysis["scores"]` kasıtlı olarak yok sayılır — puan yalnızca
    `company_facts` satırlarından gelir.
    """
    written = persist_facts(
        db, company, analysis.get("facts") or [], source_type=source_type
    )
    # autoflush kapalı; SELECT'in henüz commit edilmemiş fact'leri görmesi
    # için flush şart. Böylece puan tablodaki (bu koşu + önceki tipler)
    # gerçeği yansıtır, LLM skorunu değil.
    db.flush()
    scores = score_company(db, company.id)
    return written, scores
