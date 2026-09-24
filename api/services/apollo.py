"""Step 13 — Apollo ile karar verici araması.

Yalnızca `qualified` / `high priority` şirketlerde çalışır (Step 20).
Apollo araması e-posta döndürmez; e-posta ve LinkedIn için bulunan kişileri
enrich ederiz. Anahtar yoksa veya şirket niteliksizse sessizce 0 döner —
puanlama akışını düşürmez.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api import models
from api.config import get_settings
from api.services.scoring import DEEP_RESEARCH_STATUSES

logger = logging.getLogger(__name__)

APOLLO_BASE = "https://api.apollo.io/api/v1"
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
# Resmi People Search; 403 olursa eski `search`, sonra kayıtlı `contacts/search`.
PEOPLE_SEARCH_PATHS = ("/mixed_people/api_search", "/mixed_people/search")
CONTACTS_SEARCH_PATH = "/contacts/search"
PEOPLE_ENRICH_PATH = "/people/bulk_match"
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


class ApolloSearchError(RuntimeError):
    """Apollo People Search reddedildi — anahtar, kapsam veya plan."""


def _clean_api_key(raw: str) -> str:
    """BOM, tırnak, Bearer ve satır sonlarını temizler — anahtarı loglamaz."""
    cleaned = raw.replace("\ufeff", "").strip()
    cleaned = cleaned.strip('"').strip("'")
    if cleaned.lower().startswith("bearer"):
        cleaned = cleaned[6:].lstrip(" :").strip().strip('"').strip("'")
    return "".join(cleaned.split())


def _read_dotenv_value(path: Path, name: str) -> str:
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() == name:
            return value.strip()
    return ""


def _apollo_api_key() -> str | None:
    """Anahtarı istek anında `.env` dosyasından okur.

    Testlerde `APOLLO_API_KEY` ortam değişkeni önceliklidir; canlıda `.env`
    dosyası süreçte kalan eski değeri ezer (anahtar döndürmeden güncellenir).
    """
    file_value = _read_dotenv_value(_ENV_PATH, "APOLLO_API_KEY")
    process_value = os.getenv("APOLLO_API_KEY") or ""
    if os.getenv("PYTEST_CURRENT_TEST"):
        raw = process_value or file_value
    else:
        load_dotenv(_ENV_PATH)
        raw = file_value or process_value or get_settings().apollo_api_key or ""
    return _clean_api_key(raw) or None


def _response_error_text(response: httpx.Response | None) -> str:
    if response is None:
        return ""
    try:
        payload = response.json()
    except ValueError:
        return (response.text or "")[:300]
    if isinstance(payload, dict):
        return str(
            payload.get("error") or payload.get("error_code") or payload
        )[:300]
    return (response.text or "")[:300]


def _people_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    people = payload.get("people") or payload.get("contacts") or []
    return [row for row in people if isinstance(row, dict)]


def _header_only_auth(api_key: str) -> dict[str, str]:
    """Apollo: anahtar yalnızca header'da. Query string'e asla konmaz."""
    return {
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
        "x-api-key": api_key,
    }


def _json_without_secrets(json_body: dict[str, Any] | None) -> dict[str, Any]:
    body = dict(json_body or {})
    for secret_key in ("api_key", "apiKey", "x-api-key", "X-Api-Key"):
        body.pop(secret_key, None)
    return body


def send_apollo_request(
    method: str,
    path: str,
    *,
    api_key: str,
    json_body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """POST JSON + header auth. `params` verilmez; URL'de `?` olmaz."""
    path = path.split("?", 1)[0]
    url = f"{APOLLO_BASE}{path}"
    if "api_key=" in url.lower() or "?" in url:
        raise RuntimeError("Apollo URL'sine api_key konamaz.")
    headers = _header_only_auth(api_key)
    body = _json_without_secrets(json_body)
    response = httpx.request(
        method,
        url,
        headers=headers,
        json=body,
        timeout=timeout,
    )
    if response.status_code >= 400:
        logger.warning(
            "Apollo %s %s → %s (key_present=%s key_len=%d): %s",
            method,
            path,
            response.status_code,
            bool(api_key),
            len(api_key),
            _response_error_text(response),
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        return {}
    return payload


class ApolloClient:
    """Apollo REST istemcisi: people search + bulk enrich."""

    def __init__(self, api_key: str, *, timeout: float = 30.0) -> None:
        self.api_key = _clean_api_key(api_key)
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return _header_only_auth(self.api_key)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return send_apollo_request(
                method,
                path,
                api_key=self.api_key,
                json_body=json_body,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            logger.warning("Apollo isteği başarısız (%s %s): %s", method, path, exc)
            raise

    def _search_body(self, domain: str, per_page: int) -> dict[str, Any]:
        return {
            "q_organization_domains_list": [domain],
            "person_titles": list(DECISION_MAKER_TITLES),
            "person_seniorities": [
                "owner",
                "founder",
                "c_suite",
                "vp",
                "head",
                "director",
                "manager",
            ],
            "include_similar_titles": True,
            "page": 1,
            "per_page": max(1, min(per_page, 100)),
        }

    def search_people(self, domain: str, per_page: int) -> list[dict[str, Any]]:
        body = self._search_body(domain, per_page)
        last_error: httpx.HTTPStatusError | None = None
        for path in PEOPLE_SEARCH_PATHS:
            try:
                return _people_from_payload(
                    self._request("POST", path, json_body=body)
                )
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status = exc.response.status_code if exc.response is not None else 0
                if status in {401, 403}:
                    continue
                raise

        try:
            saved = _people_from_payload(
                self._request("POST", CONTACTS_SEARCH_PATH, json_body=body)
            )
            if saved:
                logger.info(
                    "Apollo People Search kapalı; contacts/search %d kayıt döndü.",
                    len(saved),
                )
                return saved
        except httpx.HTTPError as exc:
            logger.warning("Apollo contacts/search başarısız: %s", exc)

        if last_error is not None:
            detail = _response_error_text(last_error.response) or str(last_error)
            raise ApolloSearchError(detail) from last_error
        return []

    def enrich_people(self, apollo_ids: list[str]) -> dict[str, dict[str, Any]]:
        """E-posta / LinkedIn için bulk match. Kredisi yoksa boş döner."""
        if not apollo_ids:
            return {}
        try:
            payload = self._request(
                "POST",
                PEOPLE_ENRICH_PATH,
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
        raw_people = self.search_people(domain, get_settings().apollo_max_contacts)
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
        return found[: get_settings().apollo_max_contacts]


def _build_client() -> ApolloClient | None:
    api_key = _apollo_api_key()
    if not api_key:
        return None
    logger.info("Apollo istemcisi hazır (key_len=%d).", len(api_key))
    return ApolloClient(api_key)


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
