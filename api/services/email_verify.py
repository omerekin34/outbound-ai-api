"""Step 15 — e-posta doğrulama.

Giden hat yalnızca `valid` kabul eder. Diğer durumlar kullanılamaz:
  * `invalid`    — boş veya geçersiz sözdizimi
  * `unknown`    — sözdizimi tamam, MX yok / sorgu başarısız
  * `accept_all` — MX var ama yerel kısım genel (info@, satis@)
  * `risky`      — tek kullanımlık / şüpheli alan adı
  * `valid`      — kişisel adres + MX
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

STATUS_VALID = "valid"
STATUS_INVALID = "invalid"
STATUS_UNKNOWN = "unknown"
STATUS_ACCEPT_ALL = "accept_all"
STATUS_RISKY = "risky"

UNUSABLE_STATUSES = frozenset(
    {STATUS_INVALID, STATUS_UNKNOWN, STATUS_ACCEPT_ALL, STATUS_RISKY}
)
VALID_FOR_COPY = frozenset({STATUS_VALID})

_EMAIL_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9._%+-]{0,62}[a-z0-9])?@"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$",
    re.IGNORECASE,
)

GENERIC_LOCAL_PARTS = frozenset(
    {
        "info",
        "bilgi",
        "contact",
        "hello",
        "office",
        "admin",
        "destek",
        "support",
        "sales",
        "satis",
        "satislar",
        "noreply",
        "no-reply",
        "mailbox",
        "mail",
    }
)

DISPOSABLE_DOMAINS = frozenset(
    {
        "mailinator.com",
        "guerrillamail.com",
        "10minutemail.com",
        "tempmail.com",
        "yopmail.com",
        "trashmail.com",
        "sharklasers.com",
    }
)


def normalize_email(address: str | None) -> str | None:
    cleaned = (address or "").strip().lower()
    return cleaned or None


def is_email_usable(status: str | None) -> bool:
    return (status or "").strip().lower() == STATUS_VALID


def resolve_mx(domain: str) -> bool:
    """Alan adında MX kaydı var mı? Ağ hatası False döner."""
    try:
        import dns.resolver
    except ImportError:  # pragma: no cover
        logger.warning("dnspython yok; MX kontrolü atlandı.")
        return False

    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=4.0)
        return any(getattr(record, "exchange", None) for record in answers)
    except Exception as exc:
        logger.info("MX sorgusu başarısız (%s): %s", domain, exc)
        return False


def verify_email(address: str | None, *, mx_lookup=None) -> str:
    """Sözdizimi + MX. Testlerde `mx_lookup` enjekte edilir."""
    lookup = mx_lookup or resolve_mx
    normalized = normalize_email(address)
    if normalized is None or not _EMAIL_RE.match(normalized):
        return STATUS_INVALID

    local, domain = normalized.split("@", 1)
    if domain in DISPOSABLE_DOMAINS:
        return STATUS_RISKY
    if not lookup(domain):
        return STATUS_UNKNOWN
    if local in GENERIC_LOCAL_PARTS:
        return STATUS_ACCEPT_ALL
    return STATUS_VALID
