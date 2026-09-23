"""Step 13 — Apollo ile karar verici araması.

Yalnızca `qualified` / `high priority` şirketlerde çalışır (Step 20).
Apollo araması e-posta döndürmez; e-posta ve LinkedIn için bulunan kişileri
enrich ederiz. Anahtar yoksa veya şirket niteliksizse sessizce 0 döner —
puanlama akışını düşürmez.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api import models
from api.config import get_settings
from api.services.scoring import DEEP_RESEARCH_STATUSES

logger = logging.getLogger(__name__)
settings = get_settings()

APOLLO_BASE = "https://api.apollo.io/api/v1"
CONTACT_ID_PREFIX = "apollo-"

# Persona puanı (yüksek kazanır). Apollo araması bu unvanlarla sınırlıdır.
PERSONA_RANKS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (100, ("commercial director", "ticari direktör", "ticari direktor", "ticaret direktörü")),
    (90, ("sales director", "satış direktörü", "satis direktoru", "vp sales", "head of sales")),
    (
        85,
        (
            "general manager",
            "genel müdür",
            "genel mudur",
            "ceo",
            "chief executive",
            "owner",
            "kurucu",
            "founder",
        ),
    ),
    (80, ("sales operations manager", "satış operasyon", "sales operations", "satis operasyon")),
    (70, ("it manager", "it müdürü", "it muduru", "bilgi işlem müdürü", "head of it", "it director")),
)

DECISION_MAKER_TITLES = (
    "Commercial Director",
    "Ticari Direktör",
    "Sales Director",
    "Satış Direktörü",
    "General Manager",
    "Genel Müdür",
    "CEO",
    "Owner",
    "Sales Operations Manager",
    "Satış Operasyon Müdürü",
    "IT Manager",
    "IT Müdürü",
)

_TITLE_LIMIT = 100


@dataclass(frozen=True)
class ApolloPerson:
    apollo_id: str
    first_name: str | None
    last_name: str | None
    title: str | None
    email: str | None
    linkedin_url: str | None

    @property
    def contact_id(self) -> str:
        return f"{CONTACT_ID_PREFIX}{self.apollo_id}"


class SupportsApollo(Protocol):
    def search_decision_makers(self, domain: str) -> list[ApolloPerson]: ...


def company_domain(company: models.Company) -> str | None:
    """`companies.domain` veya web sitesi host'undan çıplak alan adı."""
    raw = (company.domain or "").strip().lower()
    if not raw and company.website:
        host = urlparse(company.website).netloc or urlparse(
            f"https://{company.website}"
        ).netloc
        raw = host.lower()
    raw = raw.removeprefix("www.").split("/")[0].strip()
    if not raw or "." not in raw:
        return None
    return raw


def _fold(value: str) -> str:
    return (
        value.casefold()
        .replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )


def persona_rank(title: str | None) -> int:
    """Unvana göre persona puanı; eşleşme yoksa 0."""
    if not title:
        return 0
    folded = _fold(title)
    best = 0
    for score, aliases in PERSONA_RANKS:
        if any(alias in folded or _fold(alias) in folded for alias in aliases):
            best = max(best, score)
    return best


def select_primary_contact(contacts: list[models.Contact]) -> models.Contact | None:
    """En yüksek persona puanlı kişiyi işaretler; yoksa None."""
    if not contacts:
        return None
    for contact in contacts:
        contact.persona_rank = persona_rank(contact.title)
        contact.is_selected = False
    chosen = max(contacts, key=lambda row: (row.persona_rank or 0, bool(row.email)))
    chosen.is_selected = True
    return chosen


def _clean(value: object, limit: int | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split()).strip()
    if not text:
        return None
    if limit is not None:
        return text[:limit]
    return text


def _person_from_payload(raw: dict[str, Any]) -> ApolloPerson | None:
    apollo_id = raw.get("id")
    if not apollo_id:
        return None
    email = _clean(raw.get("email") or raw.get("email_address"))
    if email and "@" not in email:
        email = None
    return ApolloPerson(
        apollo_id=str(apollo_id),
        first_name=_clean(raw.get("first_name"), 100),
        last_name=_clean(raw.get("last_name"), 100),
        title=_clean(raw.get("title"), _TITLE_LIMIT),
        email=email.lower() if email else None,
        linkedin_url=_clean(
            raw.get("linkedin_url") or raw.get("linkedin_uid")
        ),
    )


class ApolloClient:
    """Apollo REST istemcisi: people search + bulk enrich."""

    def __init__(self, api_key: str, *, timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "Accept": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: list[tuple[str, str]] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{APOLLO_BASE}{path}"
        try:
            response = httpx.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json_body,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Apollo isteği başarısız (%s %s): %s", method, path, exc)
            raise
        payload = response.json()
        if not isinstance(payload, dict):
            return {}
        return payload

    def search_people(self, domain: str, per_page: int) -> list[dict[str, Any]]:
        params: list[tuple[str, str]] = [
            ("q_organization_domains_list[]", domain),
            ("include_similar_titles", "true"),
            ("per_page", str(per_page)),
            ("page", "1"),
        ]
        for title in DECISION_MAKER_TITLES:
            params.append(("person_titles[]", title))
        for seniority in ("c_suite", "founder", "vp", "head", "director", "manager"):
            params.append(("person_seniorities[]", seniority))

        payload = self._request("POST", "/mixed_people/api_search", params=params)
        people = payload.get("people") or payload.get("contacts") or []
        return [row for row in people if isinstance(row, dict)]

    def enrich_people(self, apollo_ids: list[str]) -> dict[str, dict[str, Any]]:
        """E-posta / LinkedIn için bulk match. Kredisi yoksa boş döner."""
        if not apollo_ids:
            return {}
        try:
            payload = self._request(
                "POST",
                "/people/bulk_match",
                json_body={"details": [{"id": person_id} for person_id in apollo_ids]},
            )
        except httpx.HTTPError:
            return {}

        matches = payload.get("matches") or payload.get("people") or []
        by_id: dict[str, dict[str, Any]] = {}
        for row in matches:
            if isinstance(row, dict) and row.get("id"):
                by_id[str(row["id"])] = row
        return by_id

    def search_decision_makers(self, domain: str) -> list[ApolloPerson]:
        raw_people = self.search_people(domain, settings.apollo_max_contacts)
        enrichments = self.enrich_people(
            [str(row["id"]) for row in raw_people if row.get("id")]
        )

        found: list[ApolloPerson] = []
        seen: set[str] = set()
        for row in raw_people:
            merged = {**row, **enrichments.get(str(row.get("id") or ""), {})}
            person = _person_from_payload(merged)
            if person is None or person.apollo_id in seen:
                continue
            if not person.first_name and not person.last_name and not person.email:
                continue
            seen.add(person.apollo_id)
            found.append(person)
        found.sort(key=lambda person: persona_rank(person.title), reverse=True)
        return found[: settings.apollo_max_contacts]


def _build_client() -> ApolloClient | None:
    if not settings.apollo_api_key:
        return None
    return ApolloClient(settings.apollo_api_key)


def persist_apollo_contacts(
    db: Session, company: models.Company, people: list[ApolloPerson]
) -> int:
    """Apollo kişilerini `contacts` tablosuna yazar; e-posta tekilliğine uyar."""
    written = 0
    for person in people:
        values = {
            "company_id": company.id,
            "first_name": person.first_name,
            "last_name": person.last_name,
            "title": person.title,
            "email": person.email,
            "linkedin_url": person.linkedin_url,
        }
        record = db.get(models.Contact, person.contact_id)
        if record is None and person.email:
            record = db.execute(
                select(models.Contact).where(models.Contact.email == person.email)
            ).scalar_one_or_none()

        try:
            with db.begin_nested():
                if record is None:
                    db.add(models.Contact(id=person.contact_id, **values))
                else:
                    for key, value in values.items():
                        if value:
                            setattr(record, key, value)
                db.flush()
            written += 1
        except IntegrityError:
            logger.warning(
                "Apollo kişisi atlandı (tekillik): %s / %s",
                person.contact_id,
                person.email,
            )
    stored = list(
        db.execute(
            select(models.Contact).where(models.Contact.company_id == company.id)
        ).scalars()
    )
    select_primary_contact(stored)
    return written


def find_decision_makers(
    db: Session,
    company: models.Company,
    *,
    client: SupportsApollo | None = None,
    force: bool = False,
) -> int:
    """Nitelikli şirket için Apollo araması yapıp kişileri kaydeder.

    Niteliksiz şirket, alan adı yok veya API anahtarı yoksa 0 döner.
    """
    status = (company.status or "").strip().lower().strip("'\"")
    if status not in DEEP_RESEARCH_STATUSES:
        return 0

    domain = company_domain(company)
    if domain is None:
        logger.info("Apollo atlandı: %s için alan adı yok", company.id)
        return 0

    if not force:
        existing = db.execute(
            select(models.Contact.id).where(
                models.Contact.company_id == company.id,
                models.Contact.id.like(f"{CONTACT_ID_PREFIX}%"),
            )
        ).first()
        if existing is not None:
            return 0

    resolved = client
    if resolved is None:
        resolved = _build_client()
    if resolved is None:
        logger.info("Apollo atlandı: APOLLO_API_KEY tanımlı değil")
        return 0

    from api.services.activity import EVENT_DECISION_MAKER, track_activity

    with track_activity(
        EVENT_DECISION_MAKER,
        f"{company.name} için karar verici aranıyor",
        company_id=company.id,
        company_name=company.name,
        detail={"domain": domain},
    ) as activity:
        try:
            people = resolved.search_decision_makers(domain)
        except Exception as exc:
            logger.exception("Apollo araması başarısız: %s (%s)", company.name, domain)
            activity.fail(f"Apollo araması başarısız: {exc}")
            return 0

        written = persist_apollo_contacts(db, company, people)
        if written:
            activity.succeed(
                f"{company.name}: {written} karar verici kaydedildi.",
                {"domain": domain, "saved": written},
            )
        else:
            activity.skip(f"{company.name}: Apollo eşleşen karar verici döndürmedi.")
        return written
