"""Step 16–17 — iki adımlı mesaj: strateji, sonra kanıta bağlı gövde.

Yalnızca `valid` e-posta ve en yüksek puanlı persona için LLM çağrılır.
Model e-postayı doğrudan yazmaz; önce strateji JSON'u üretir, gövde
yalnızca doğrulanmış kanıta dayanır. Kullanıcı taslağının üzerine yazılmaz.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from api import models
from api.config import get_settings
from api.services.activity import EVENT_OUTREACH_PREP, track_activity
from api.services.apollo import persona_rank, select_primary_contact
from api.services.email_verify import STATUS_VALID, is_email_usable, verify_email
from api.services.enrichment import openai_client

logger = logging.getLogger(__name__)

EMAIL_BODY_MAX = 4_000
WORD_MIN = 80
WORD_MAX = 120

COPYWRITER_SYSTEM_PROMPT = """Sen bir B2B satış stratejisti ve copywriter'sın. Kanıt paketi verilecek.

ASLA doğrudan e-posta uydurma. Önce Part A, sonra Part B. İkisini tek JSON'da döndür.

PART A — strategy (yalnızca verilen kanıttan):
- main_pain
- recommended_product
- best_sales_angle
- best_persona
- why_now
Kanıtta yoksa alanı null yaz. Ürün, ERP, sayı veya unvan uydurma.

PART B — email_body:
- Dil: Türkçe
- Uzunluk: kesin 80–120 kelime
- Ton: doğal, satış jargonu yok, abartılı övgü yok
- Yalnızca doğrulanmış kanıtı operasyonel ağrıya bağla
- Tek, net CTA
- HTML / markdown / konu satırı yok

YAPMA:
- Kanıtta geçmeyen fact, isim, ERP, rakam uydurma.
- "Dijital dönüşüm yolculuğu" gibi klişe.

JSON:
{
  "strategy": {
    "main_pain": "...",
    "recommended_product": "...",
    "best_sales_angle": "...",
    "best_persona": "...",
    "why_now": "..."
  },
  "email_body": "Merhaba Deniz, ..."
}"""


@dataclass(frozen=True)
class OutreachDraft:
    strategy: dict[str, Any]
    email_body: str


def word_count(text: str) -> int:
    return len(text.split())


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split()).strip()
    return cleaned or None


def _clean_body(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.replace("\r\n", "\n").strip()
    if not cleaned:
        return None
    cleaned = cleaned[:EMAIL_BODY_MAX]
    words = word_count(cleaned)
    if words < WORD_MIN or words > WORD_MAX:
        logger.warning("E-posta kelime sayısı %s (80–120 dışı)", words)
        return None
    return cleaned


def _strategy_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("strategy")
    if not isinstance(raw, dict):
        raw = {}
    keys = (
        "main_pain",
        "recommended_product",
        "best_sales_angle",
        "best_persona",
        "why_now",
    )
    return {key: _clean_text(raw.get(key)) for key in keys}


def _evidence_pack(
    company: models.Company,
    contact: models.Contact,
    facts: list[models.CompanyFact] | None = None,
) -> str:
    lines = []
    for fact in facts if facts is not None else list(company.facts or []):
        if fact.value and fact.evidence_text:
            lines.append(f"- {fact.fact_type}: {fact.value} | {fact.evidence_text}")
    evidence = company.erp_evidence if isinstance(company.erp_evidence, dict) else None
    erp_block = evidence.get("erp") if evidence else None
    return (
        f"Şirket: {company.name or company.domain or company.id}\n"
        f"Sektör: {company.industry or 'verilmedi'}\n"
        f"ERP kanıtı: {json.dumps(erp_block or {'value': company.erp_signal or 'unknown'}, ensure_ascii=False)}\n"
        f"Ağrı hipotezi: {company.pain_hypothesis or 'verilmedi'}\n"
        f"Seçilen persona: {contact.full_name or contact.first_name or 'verilmedi'}\n"
        f"Ünvan: {contact.title or 'verilmedi'}\n"
        f"Persona puanı: {contact.persona_rank or 0}\n\n"
        f"Doğrulanmış fact'ler:\n"
        + ("\n".join(lines) if lines else "- (fact yok)")
    )


def generate_outreach_draft(
    company: models.Company,
    contact: models.Contact,
    facts: list[models.CompanyFact] | None = None,
) -> OutreachDraft | None:
    """İki adımlı JSON: strateji + 80–120 kelimelik gövde."""
    settings = get_settings()
    try:
        client = openai_client()
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": COPYWRITER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _evidence_pack(company, contact, facts),
                },
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)
    except Exception:
        logger.exception("Soğuk e-posta üretilemedi: %s", contact.email)
        return None

    if not isinstance(parsed, dict):
        return None
    body = _clean_body(parsed.get("email_body"))
    if not body:
        return None
    return OutreachDraft(strategy=_strategy_from_payload(parsed), email_body=body)


def _outreach_target(contacts: list[models.Contact]) -> models.Contact | None:
    """En yüksek puanlı ve `valid` e-postalı kişi."""
    usable = [row for row in contacts if is_email_usable(row.email_status)]
    if not usable:
        return None
    return max(usable, key=lambda row: (row.persona_rank or 0, bool(row.is_selected)))


def prepare_outreach(db: Session, company: models.Company) -> int:
    """Doğrular, persona seçer; yalnızca valid hedefe taslak yazar."""
    contacts = list(
        db.execute(
            select(models.Contact).where(models.Contact.company_id == company.id)
        ).scalars()
    )
    if not contacts:
        return 0

    for contact in contacts:
        contact.email_status = verify_email(contact.email)
        contact.persona_rank = persona_rank(contact.title)

    select_primary_contact(contacts)
    target = _outreach_target(contacts)
    if target is not None:
        for contact in contacts:
            contact.is_selected = contact.id == target.id

    drafted = 0
    with track_activity(
        EVENT_OUTREACH_PREP,
        f"{company.name} için e-posta doğrulama ve taslak",
        company_id=company.id,
        company_name=company.name,
    ) as activity:
        if target is None:
            activity.skip("valid e-posta yok; taslak yazılmadı.")
            return 0
        if not (target.generated_email_body and target.generated_email_body.strip()):
            facts = list(
                db.execute(
                    select(models.CompanyFact).where(
                        models.CompanyFact.company_id == company.id
                    )
                ).scalars()
            )
            draft = generate_outreach_draft(company, target, facts)
            if draft:
                target.generated_email_body = draft.email_body
                company.outreach_strategy = draft.strategy
                drafted = 1

        valid_count = sum(1 for row in contacts if row.email_status == STATUS_VALID)
        activity.succeed(
            f"{company.name}: {valid_count} valid e-posta, {drafted} taslak "
            f"({target.full_name or target.email}).",
            {
                "valid": valid_count,
                "drafted": drafted,
                "selected_contact_id": target.id,
                "persona_rank": target.persona_rank,
            },
        )
    return drafted
