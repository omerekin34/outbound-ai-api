"""Analiz sonuçlarının kalıcılaştırılması (profil/fact + backend puanlama).

Akış Step 4–8 + 14–16'ya uyar:
  1. LLM yapılandırılmış ICP/Need profili ve kanıt üretir (puan üretmez).
  2. Kanıtlı fact'ler `company_facts` tablosuna yazılır.
  3. Puanlar Python'da, tablodaki fact'lerden hesaplanır (`scoring.py`).
  4. Yeterlilik kapısı derin araştırmayı açar veya durdurur.

LLM'nin döndürdüğü herhangi bir `scores` alanı burada okunmaz.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from api import models
from api.services.apollo import find_decision_makers
from api.services.deep_research import apply_deep_research
from api.services.outreach import prepare_outreach
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


PAIN_HYPOTHESIS_MAX = 800


def _persist_analyzer_profile(
    company: models.Company, profile: dict[str, Any] | None
) -> None:
    """Analyzer `pain_hypothesis` cümlesini, boşsa şirket kaydına yazar."""
    if not profile or company.pain_hypothesis:
        return
    pain = profile.get("pain_hypothesis")
    if pain is None:
        pain = profile.get("pain_hypotheses")
    if isinstance(pain, list):
        labels = [str(item).strip() for item in pain if str(item).strip()]
        if labels and all(" " not in item for item in labels):
            pain = (
                "Sipariş ve teklif süreçlerinde operasyonel darboğazlar yaşanması muhtemel."
            )
        else:
            pain = next((item for item in labels if " " in item), "")
    if not isinstance(pain, str) or not pain.strip():
        return
    company.pain_hypothesis = pain.strip()[:PAIN_HYPOTHESIS_MAX]


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


def score_company(
    db: Session,
    company_id: str,
    *,
    profile: dict[str, Any] | None = None,
) -> Scores:
    """Tablodaki fact + şirket tabanından puanı hesaplar."""
    company = db.get(models.Company, company_id)
    scores = calculate_scores(
        load_facts(db, company_id),
        company=company,
        profile=profile,
    )
    persist_scores(db, company_id, scores)
    if company is not None:
        company.status = scores.qualification_status
        if not company.country:
            company.country = "Turkey"
        if not company.industry and any(
            token in (company.name or "").casefold()
            for token in ("makina", "makine", "elektronik")
        ):
            company.industry = "Machinery"
    return scores


def persist_analysis(
    db: Session,
    company: models.Company,
    analysis: dict[str, Any],
    *,
    source_type: str,
    source_text: str | None = None,
) -> tuple[int, Scores]:
    """Fact'leri kaydeder, ardından backend puanını hesaplar.

    `analysis["scores"]` kasıtlı olarak yok sayılır — puan yalnızca
    `company_facts` satırlarından gelir.
    """
    written = persist_facts(
        db, company, analysis.get("facts") or [], source_type=source_type
    )
    _persist_analyzer_profile(company, analysis.get("profile"))
    # autoflush kapalı; SELECT'in henüz commit edilmemiş fact'leri görmesi
    # için flush şart. Böylece puan tablodaki (bu koşu + önceki tipler)
    # gerçeği yansıtır, LLM skorunu değil.
    db.flush()
    scores = score_company(db, company.id, profile=analysis.get("profile"))
    # Step 10–17 + 20: derin araştırma → Apollo → doğrulama + taslak.
    if scores.requires_deep_research:
        apply_deep_research(db, company, source_text)
        find_decision_makers(db, company)
        prepare_outreach(db, company)
    return written, scores
