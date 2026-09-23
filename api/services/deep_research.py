"""Step 10–12 — nitelikli şirketlerde yapılandırılmış ERP kanıtı.

Derin araştırma ikinci bir LLM çağrısıdır. ERP çıktısı düz metin değil,
şu şemaya uyan JSON'dur:

    {"erp": {"value": "Netsis" | "SAP" | "unknown", "confidence": 0.90, "evidence_count": 2}}

Kanıt yoksa value=`unknown`, confidence=null. Puan ve kişi uydurulmaz.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from api import models
from api.config import get_settings
from api.services.activity import EVENT_DEEP_RESEARCH, track_activity
from api.services.enrichment import (
    build_pages_prompt,
    openai_client,
)
from api.services.scoring import DEEP_RESEARCH_STATUSES
from api.services.website_research import ScrapedPage

logger = logging.getLogger(__name__)

ERP_SIGNAL_MAX = 64
PAIN_HYPOTHESIS_MAX = 800
ERP_UNKNOWN = "unknown"

# Kullanıcının şemasındaki kanonik değerler + sitede geçen diğer ERP adları.
_ERP_ALIASES = (
    (re.compile(r"\bs/?4\s*hana\b|\bsap\b|\bbusiness\s+one\b", re.I), "SAP"),
    (re.compile(r"\bnetsis\b", re.I), "Netsis"),
    (re.compile(r"\bnebim\b", re.I), "Nebim"),
    (re.compile(r"\blogo(?:\s+tiger)?\b", re.I), "Logo"),
    (re.compile(r"\bmikro\b", re.I), "Mikro"),
    (re.compile(r"\bika\b", re.I), "IKA"),
    (re.compile(r"\bcanias\b", re.I), "Canias"),
    (re.compile(r"\boracle\b", re.I), "Oracle"),
    (re.compile(r"\bdynamics\s*365\b|\bmicrosoft\s+dynamics\b", re.I), "Dynamics"),
)

DEEP_RESEARCH_SYSTEM_PROMPT = """Sen bir B2B kanıt analistisin. Nitelikli bir firmanın taranmış web metni ve kayıtlı fact'leri verilecek.

TEK GÖREVİN: ERP kanıtını yapılandırılmış JSON olarak çıkarmak. Uydurma.

`erp.value` yalnızca sitede veya fact'te geçen yazılım olabilir.
Kanıt yoksa value="unknown" ve confidence=null yaz.
Kanıt varsa value'yu şu kanonik adlardan birine indir: SAP, Netsis.
(Nebim, Logo, Mikro gibi başka bir ERP açıkça geçiyorsa o adı yaz.)
`confidence` 0.0–1.0. `evidence_count` birbirinden ayrı kanıt sayısı (alıntı / fact).

`pain_hypothesis` isteğe bağlı: yalnızca kanıta dayalı 1 cümle. Kanıt yoksa null.

YAPMA:
- Sitede geçmeyen ERP uydurma.
- Puan hesaplama.
- Kişi / e-posta uydurma.

JSON (bu şema zorunlu):
{
  "erp": {
    "value": "Netsis",
    "confidence": 0.90,
    "evidence_count": 2
  },
  "pain_hypothesis": "Bayi siparişleri Netsis stokuyla senkron değil."
}"""


@dataclass(frozen=True)
class ErpEvidence:
    value: str
    confidence: float | None
    evidence_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
        }


@dataclass(frozen=True)
class DeepResearchResult:
    erp: ErpEvidence
    pain_hypothesis: str | None

    @property
    def erp_signal(self) -> str | None:
        return None if self.erp.value == ERP_UNKNOWN else self.erp.value

    def as_dict(self) -> dict[str, Any]:
        return {"erp": self.erp.as_dict(), "pain_hypothesis": self.pain_hypothesis}


def unknown_erp() -> ErpEvidence:
    return ErpEvidence(value=ERP_UNKNOWN, confidence=None, evidence_count=0)


def pages_to_source_text(pages: list[ScrapedPage] | None) -> str:
    if not pages:
        return ""
    settings = get_settings()
    return build_pages_prompt(
        pages,
        chars_per_page=settings.research_chars_per_page,
        total_chars=settings.research_total_chars,
    )


def canonicalize_erp(raw: Any) -> str:
    if not isinstance(raw, str):
        return ERP_UNKNOWN
    cleaned = " ".join(raw.split()).strip()
    if not cleaned or cleaned.lower() in {"null", "none", "yok", "bilinmiyor", ERP_UNKNOWN}:
        return ERP_UNKNOWN
    for pattern, label in _ERP_ALIASES:
        if pattern.search(cleaned):
            return label
    return cleaned[:ERP_SIGNAL_MAX]


def _clean_text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split()).strip()
    if not cleaned or cleaned.lower() in {"null", "none", "yok", "bilinmiyor"}:
        return None
    return cleaned[:limit]


def _as_confidence(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, number))


def _as_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _facts_summary(facts: Iterable[models.CompanyFact]) -> str:
    lines: list[str] = []
    for fact in facts:
        if not fact.fact_type or not fact.value:
            continue
        lines.append(f"- {fact.fact_type}: {fact.value}")
    return "\n".join(lines) if lines else "- (fact yok)"


def erp_from_facts(facts: Iterable[models.CompanyFact]) -> ErpEvidence | None:
    """LLM kaçırırsa `erp_detected` / `erp_usage` fact değerini kullan."""
    preferred = {"erp_detected", "erp_usage", "erp"}
    matches = [fact for fact in facts if (fact.fact_type or "").strip() in preferred]
    if not matches:
        return None
    value = canonicalize_erp(matches[0].value)
    if value == ERP_UNKNOWN:
        return None
    confidence = _as_confidence(matches[0].confidence)
    return ErpEvidence(
        value=value,
        confidence=confidence if confidence is not None else 0.7,
        evidence_count=len(matches),
    )


def parse_erp_block(payload: dict[str, Any]) -> ErpEvidence:
    block = payload.get("erp")
    if not isinstance(block, dict):
        # Eski düz alan geriye dönük: {"erp_signal": "SAP"}
        value = canonicalize_erp(payload.get("erp_signal") or payload.get("value"))
        if value == ERP_UNKNOWN:
            return unknown_erp()
        return ErpEvidence(value=value, confidence=_as_confidence(payload.get("confidence")), evidence_count=1)

    value = canonicalize_erp(block.get("value"))
    if value == ERP_UNKNOWN:
        return unknown_erp()
    count = _as_count(block.get("evidence_count"))
    return ErpEvidence(
        value=value,
        confidence=_as_confidence(block.get("confidence")),
        evidence_count=count if count else 1,
    )


def parse_deep_research_payload(payload: dict[str, Any]) -> DeepResearchResult:
    return DeepResearchResult(
        erp=parse_erp_block(payload),
        pain_hypothesis=_clean_text(payload.get("pain_hypothesis"), PAIN_HYPOTHESIS_MAX),
    )


def extract_erp_and_pain(
    company: models.Company,
    source_text: str,
    facts: Iterable[models.CompanyFact],
) -> DeepResearchResult:
    """OpenAI'den yapılandırılmış ERP + isteğe bağlı ağrı ister."""
    client = openai_client()
    settings = get_settings()
    fact_block = _facts_summary(facts)
    user_content = (
        f"Şirket: {company.name or company.domain or company.id}\n"
        f"Sektör: {company.industry or 'bilinmiyor'}\n"
        f"Şehir: {company.city or 'bilinmiyor'}\n"
        f"Ülke: {company.country or 'Turkey'}\n\n"
        f"Kayıtlı fact'ler:\n{fact_block}\n\n"
        f"Taranan metin:\n{source_text[: settings.research_total_chars]}"
    )
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": DEEP_RESEARCH_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Derin araştırma JSON değil: %s", company.name)
        return DeepResearchResult(erp=unknown_erp(), pain_hypothesis=None)
    if not isinstance(parsed, dict):
        return DeepResearchResult(erp=unknown_erp(), pain_hypothesis=None)
    return parse_deep_research_payload(parsed)


def _apply_erp(company: models.Company, erp: ErpEvidence) -> None:
    company.erp_signal = None if erp.value == ERP_UNKNOWN else erp.value
    company.erp_confidence = erp.confidence
    company.erp_evidence_count = erp.evidence_count
    company.erp_evidence = {"erp": erp.as_dict()}


def apply_deep_research(
    db: Session,
    company: models.Company,
    source_text: str | None,
) -> DeepResearchResult | None:
    """Nitelikli şirketlere ERP kanıtı yazar. Başarısızlık hattı düşürmez."""
    status = (company.status or "").strip().lower()
    if status not in DEEP_RESEARCH_STATUSES:
        return None

    facts = list(
        db.execute(
            select(models.CompanyFact).where(
                models.CompanyFact.company_id == company.id
            )
        ).scalars()
    )
    text = (source_text or "").strip()
    result = DeepResearchResult(erp=unknown_erp(), pain_hypothesis=None)

    with track_activity(
        EVENT_DEEP_RESEARCH,
        f"{company.name} derin araştırma",
        company_id=company.id,
        company_name=company.name,
    ) as activity:
        if text:
            try:
                result = extract_erp_and_pain(company, text, facts)
            except Exception as exc:
                logger.exception("Derin araştırma LLM başarısız: %s", company.name)
                activity.fail(f"Derin araştırma tamamlanamadı: {exc}")
                fallback = erp_from_facts(facts)
                if fallback and not company.erp_signal:
                    _apply_erp(company, fallback)
                return None

        erp = result.erp
        if erp.value == ERP_UNKNOWN:
            erp = erp_from_facts(facts) or unknown_erp()
        pain = result.pain_hypothesis or company.pain_hypothesis
        _apply_erp(company, erp)
        if result.pain_hypothesis:
            company.pain_hypothesis = result.pain_hypothesis

        activity.succeed(
            f"{company.name}: ERP={erp.value}; kanıt={erp.evidence_count}.",
            {
                "erp": erp.as_dict(),
                "pain_hypothesis": pain,
                "used_llm": bool(text),
            },
        )
    return DeepResearchResult(erp=erp, pain_hypothesis=pain)
