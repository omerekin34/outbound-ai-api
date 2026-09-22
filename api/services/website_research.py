"""Workflow 3 — Web Sitesi Araştırması.

Spec:
  1. Girdi olarak `company_id` ve `website` zorunludur.
  2. Site kör biçimde taranmaz; Firecrawl `map` ile URL'ler keşfedilir ve
     yalnızca hedef sayfalar (anasayfa, hakkında, ürünler, iletişim, bayiler,
     katalog, markalar, çözümler) seçilerek taranır.
  3. Taranan sayfa sayısı hiçbir koşulda `MAX_PAGES` (20) değerini geçemez.
  4. Toplanan içerik AI Company Analyzer'a verilerek yapılandırılmış fact ve
     kanıt (evidence) üretilir — bu adım `services/enrichment.py` içindedir.

Buradaki seçim mantığı (`select_target_pages`) bilinçli olarak saf bir
fonksiyondur: ağ erişimi olmadan test edilebilir.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Protocol
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlparse, urlunparse

logger = logging.getLogger(__name__)

# Spec kuralı: Workflow 3 tek çalıştırmada en fazla 20 sayfa tarar.
MAX_PAGES = 20

HOMEPAGE = "homepage"

# Hedef kategoriler, spec'teki sırayla. Kapsama garantisi ve kalan kontenjanın
# doldurulması bu sıraya göre yapılır.
CATEGORY_ORDER: tuple[str, ...] = (
    HOMEPAGE,
    "about",
    "products",
    "contact",
    "dealers",
    "catalog",
    "brands",
    "solutions",
)

# URL segmentlerinde aranan anahtarlar. Türkçe siteler hedef olduğu için
# Türkçe slug'lar İngilizce karşılıklarıyla birlikte tutulur.
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "about": (
        "hakkimizda",
        "hakkinda",
        "kurumsal",
        "bizkimiz",
        "biz-kimiz",
        "sirketimiz",
        "about",
        "aboutus",
        "company",
        "who-we-are",
    ),
    "products": (
        "urun",
        "urunler",
        "urungruplari",
        "product",
        "products",
        "portfolio",
    ),
    "contact": (
        "iletisim",
        "bizeulasin",
        "bize-ulasin",
        "contact",
        "contactus",
        "reachus",
    ),
    "dealers": (
        "bayi",
        "bayiler",
        "bayilik",
        "satisnoktalari",
        "satis-noktalari",
        "yetkilisatici",
        "yetkiliservis",
        "dealer",
        "dealers",
        "distributor",
        "distributors",
        "reseller",
        "partner",
        "partners",
    ),
    "catalog": (
        "katalog",
        "kataloglar",
        "ekatalog",
        "brosur",
        "catalog",
        "catalogue",
        "brochure",
        "downloads",
    ),
    "brands": ("marka", "markalar", "brand", "brands"),
    "solutions": (
        "cozum",
        "cozumler",
        "uygulama",
        "uygulamalar",
        "sektor",
        "sektorler",
        "hizmet",
        "hizmetler",
        "solution",
        "solutions",
        "services",
        "industries",
    ),
}

# `map` hiçbir sonuç döndürmezse denenecek kanonik yollar (kategori başına bir
# tahmin). Hâlâ hedefli bir istek listesidir; kör tarama yapılmaz.
FALLBACK_PATHS: dict[str, tuple[str, ...]] = {
    "about": ("/hakkimizda", "/about"),
    "products": ("/urunler", "/products"),
    "contact": ("/iletisim", "/contact"),
    "dealers": ("/bayiler", "/dealers"),
    "catalog": ("/katalog", "/catalog"),
    "brands": ("/markalar", "/brands"),
    "solutions": ("/cozumler", "/solutions"),
}

# Metin içermeyen dosyalar taranmaz (kredi ve token israfı).
ASSET_SUFFIXES: tuple[str, ...] = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".bmp",
    ".css",
    ".js",
    ".json",
    ".xml",
    ".rss",
    ".zip",
    ".rar",
    ".7z",
    ".gz",
    ".mp3",
    ".mp4",
    ".avi",
    ".mov",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".exe",
    ".dmg",
)

# Aynı sayfayı farklı URL'lerle tekrar taramamak için atılan parametreler.
TRACKING_PARAMS = frozenset(
    {
        "gclid",
        "fbclid",
        "yclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "ref",
        "referrer",
    }
)

# Türkçe karakterleri ASCII'ye indirger; `hakkımızda` ile `hakkimizda` eşleşsin.
_TURKISH_FOLD = str.maketrans(
    {
        "ı": "i",
        "İ": "i",
        "I": "i",
        "ş": "s",
        "Ş": "s",
        "ğ": "g",
        "Ğ": "g",
        "ü": "u",
        "Ü": "u",
        "ö": "o",
        "Ö": "o",
        "ç": "c",
        "Ç": "c",
        "â": "a",
        "î": "i",
        "û": "u",
    }
)


@dataclass(frozen=True)
class TargetPage:
    """Taranmak üzere seçilmiş sayfa."""

    url: str
    category: str


@dataclass(frozen=True)
class ScrapedPage:
    """Başarıyla taranmış ve içerik döndüren sayfa."""

    url: str
    category: str
    markdown: str

    @property
    def characters(self) -> int:
        return len(self.markdown)


@dataclass
class ResearchResult:
    website: str
    max_pages: int
    discovered_urls: int
    selected_pages: list[TargetPage]
    scraped_pages: list[ScrapedPage]
    credits_used: int | None
    used_fallback: bool

    @property
    def total_characters(self) -> int:
        return sum(page.characters for page in self.scraped_pages)


class SupportsFirecrawl(Protocol):
    """Kullandığımız Firecrawl yüzeyi — testlerde taklit edilebilir."""

    def map(self, url: str, **kwargs: Any) -> Any: ...

    def batch_scrape(self, urls: list[str], **kwargs: Any) -> Any: ...


def fold(value: str) -> str:
    """Karşılaştırma için metni ASCII'ye indirip küçük harfe çevirir."""
    return value.translate(_TURKISH_FOLD).lower()


def _keyword_forms(keywords: Iterable[str]) -> tuple[str, ...]:
    """Anahtarları URL token'larıyla aynı biçime indirger.

    Böylece anahtar listeleri `satis-noktalari` gibi okunaklı yazılabilir ama
    karşılaştırma `satisnoktalari` üzerinden yapılır.
    """
    forms = {"".join(char for char in fold(word) if char.isalnum()) for word in keywords}
    return tuple(sorted(form for form in forms if form))


_KEYWORD_FORMS: dict[str, tuple[str, ...]] = {
    category: _keyword_forms(keywords)
    for category, keywords in CATEGORY_KEYWORDS.items()
}

# Alan adı: harf/rakam/nokta/tire ve isteğe bağlı port.
_VALID_HOST = re.compile(r"^[a-z0-9.\-]+(?::\d+)?$")

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def normalize_url(raw: str) -> str | None:
    """URL'i tekilleştirilebilir kanonik biçime getirir.

    Fragment atılır, izleme parametreleri temizlenir, host küçük harfe
    çevrilir, sondaki `/` kaldırılır. http(s) dışındaki şemalar reddedilir.
    """
    if not raw or not raw.strip():
        return None

    candidate = raw.strip()
    parsed = urlparse(candidate)

    if not parsed.scheme:
        parsed = urlparse(f"https://{candidate}")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    host = parsed.netloc.lower()
    if not host.isascii():
        # IDN alan adları (`örnekmakina.com.tr`) punycode'a çevrilir.
        try:
            host = host.encode("idna").decode("ascii")
        except (UnicodeError, UnicodeDecodeError):
            return None
    if not _VALID_HOST.match(host):
        return None
    hostname = host.split(":", 1)[0]
    if "." not in hostname and hostname != "localhost":
        return None

    path = parsed.path or "/"
    while "//" in path:
        path = path.replace("//", "/")
    if len(path) > 1:
        path = path.rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS and not key.lower().startswith("utm_")
    ]

    return urlunparse((parsed.scheme, host, path, "", urlencode(query_pairs), ""))


def _is_asset(url: str) -> bool:
    return urlparse(url).path.lower().endswith(ASSET_SUFFIXES)


def url_tokens(url: str) -> list[str]:
    """URL yolunu/sorgusunu eşleştirilebilir token'lara böler.

    Her `/` parçası için hem tek tek kelimeler hem de birleşik hâli üretilir:
    `/yetkili-satici` -> `yetkili`, `satici`, `yetkilisatici`. Böylece çok
    kelimeli anahtarlar (`satisnoktalari`) da yakalanır.
    """
    parsed = urlparse(url)
    # Sitemap'ler Türkçe yolları yüzdelik kodlayabiliyor
    # (`/%C3%BCr%C3%BCnler`); çözmeden eşleştirme yapılamaz.
    raw = unquote(parsed.path)
    if parsed.query:
        raw = f"{raw}/{unquote(parsed.query)}"

    tokens: list[str] = []
    for part in fold(raw).split("/"):
        words = [word for word in _TOKEN_SPLIT.split(part) if word]
        if not words:
            continue
        tokens.extend(words)
        if len(words) > 1:
            tokens.append("".join(words))
    return tokens


def classify_url(url: str, base_url: str) -> str | None:
    """URL'i hedef kategorilerden birine eşler, eşleşmezse None döner.

    Eşleşme token *başlangıcına* göre yapılır. Serbest substring araması
    yanlış pozitif üretiyordu: `/duruna` içinde `urun` geçtiği için ürün
    sayfası sayılıyordu; `urunler` ise `urun` ile başladığı için yakalanır.
    """
    if url == base_url:
        return HOMEPAGE

    tokens = url_tokens(url)
    if not tokens:
        return HOMEPAGE

    for category in CATEGORY_ORDER:
        if category == HOMEPAGE:
            continue
        keywords = _KEYWORD_FORMS[category]
        if any(token.startswith(keywords) for token in tokens):
            return category
    return None


def _canonical_rank(url: str) -> tuple[int, int]:
    """Daha kısa/sığ URL'ler daha kanoniktir: `/urunler` > `/urunler/a/b`."""
    parsed = urlparse(url)
    depth = len([part for part in parsed.path.split("/") if part])
    return (depth, len(url))


def select_target_pages(
    base_url: str,
    candidate_urls: Iterable[str],
    max_pages: int = MAX_PAGES,
) -> list[TargetPage]:
    """Keşfedilen URL'lerden taranacak hedef sayfaları seçer.

    Kurallar:
      * Anasayfa daima ilk sırada yer alır.
      * Önce her kategoriden en kanonik bir sayfa alınır (kapsama garantisi).
      * Kalan kontenjan kategori sırasına göre doldurulur.
      * Hiçbir kategoriye girmeyen URL'ler **hiç** taranmaz (kör tarama yok).
      * Sonuç asla `max_pages` değerini geçmez.
    """
    limit = max(1, min(max_pages, MAX_PAGES))

    base = normalize_url(base_url)
    if base is None:
        return []

    base_host = urlparse(base).netloc

    # Kategoriye göre gruplanmış, tekilleştirilmiş adaylar.
    grouped: dict[str, list[str]] = defaultdict(list)
    seen: set[str] = set()

    for raw in candidate_urls:
        url = normalize_url(raw)
        if url is None or url in seen:
            continue
        if urlparse(url).netloc != base_host:
            continue
        if _is_asset(url):
            continue
        seen.add(url)

        category = classify_url(url, base)
        if category is None or category == HOMEPAGE:
            continue
        grouped[category].append(url)

    for urls in grouped.values():
        urls.sort(key=_canonical_rank)

    selected: list[TargetPage] = [TargetPage(base, HOMEPAGE)]
    used: set[str] = {base}

    # 1. tur — kapsama garantisi: her kategoriden birer sayfa.
    for category in CATEGORY_ORDER:
        if category == HOMEPAGE or len(selected) >= limit:
            continue
        for url in grouped.get(category, []):
            if url not in used:
                selected.append(TargetPage(url, category))
                used.add(url)
                break

    # 2. tur — kalan kontenjanı kategori sırasına göre doldur.
    for category in CATEGORY_ORDER:
        if category == HOMEPAGE:
            continue
        for url in grouped.get(category, []):
            if len(selected) >= limit:
                return selected
            if url in used:
                continue
            selected.append(TargetPage(url, category))
            used.add(url)

    return selected[:limit]


def fallback_candidates(base_url: str) -> list[str]:
    """`map` boş dönerse denenecek kanonik hedef adresleri üretir."""
    base = normalize_url(base_url)
    if base is None:
        return []
    return [
        urljoin(f"{base}/", path.lstrip("/"))
        for paths in FALLBACK_PATHS.values()
        for path in paths
    ]


def discover_candidate_urls(
    client: SupportsFirecrawl, website: str, map_limit: int
) -> list[str]:
    """Firecrawl `map` ile sitedeki URL'leri listeler (tarama yapmaz)."""
    try:
        result = client.map(
            website,
            limit=map_limit,
            include_subdomains=False,
            ignore_query_parameters=True,
        )
    except Exception as exc:  # SDK kendi hata tiplerini sarmalıyor
        logger.warning("Firecrawl map başarısız (%s): %s", website, exc)
        return []

    links = getattr(result, "links", None) or []
    urls: list[str] = []
    for link in links:
        url = link if isinstance(link, str) else getattr(link, "url", None)
        if url:
            urls.append(url)
    return urls


def _document_source_url(document: Any) -> str | None:
    metadata = getattr(document, "metadata", None)
    if metadata is None:
        return None
    return getattr(metadata, "source_url", None) or getattr(metadata, "url", None)


def scrape_target_pages(
    client: SupportsFirecrawl,
    pages: list[TargetPage],
    timeout_seconds: int,
) -> tuple[list[ScrapedPage], int | None]:
    """Seçilen sayfaları tek bir batch isteğiyle tarar."""
    if not pages:
        return [], None

    # Sınırın tek ve gerçek uygulama noktası burası: Firecrawl'a hiçbir koşulda
    # MAX_PAGES'ten fazla adres gönderilmez (`assert` -O ile silinebilirdi).
    if len(pages) > MAX_PAGES:
        logger.warning(
            "Seçilen sayfa sayısı (%d) sınırı aştı, %d sayfaya kırpıldı.",
            len(pages),
            MAX_PAGES,
        )
        pages = pages[:MAX_PAGES]

    category_by_url = {page.url: page.category for page in pages}

    job = client.batch_scrape(
        [page.url for page in pages],
        formats=["markdown"],
        only_main_content=True,
        ignore_invalid_urls=True,
        wait_timeout=timeout_seconds,
    )

    documents = getattr(job, "data", None) or []
    credits_used = getattr(job, "credits_used", None)

    scraped: list[ScrapedPage] = []
    for index, document in enumerate(documents):
        markdown = (getattr(document, "markdown", None) or "").strip()
        if not markdown:
            continue

        source_url = _document_source_url(document)
        normalized = normalize_url(source_url) if source_url else None

        # Batch sonuçları istek sırasını koruyor; `source_url` eşleşmezse
        # sıraya göre geri düşüyoruz.
        if normalized in category_by_url:
            url, category = normalized, category_by_url[normalized]
        elif index < len(pages):
            url, category = pages[index].url, pages[index].category
        else:
            continue

        scraped.append(ScrapedPage(url=url, category=category, markdown=markdown))

    return scraped, credits_used


def research_website(
    client: SupportsFirecrawl,
    website: str,
    *,
    max_pages: int = MAX_PAGES,
    map_limit: int = 300,
    timeout_seconds: int = 180,
) -> ResearchResult:
    """Workflow 3'ün tarama aşamasını uçtan uca yürütür."""
    base = normalize_url(website)
    if base is None:
        raise ValueError(f"Geçersiz web sitesi adresi: {website!r}")

    limit = max(1, min(max_pages, MAX_PAGES))

    candidates = discover_candidate_urls(client, base, map_limit)
    selected = select_target_pages(base, candidates, limit)
    used_fallback = False

    # `map` yalnızca anasayfayı verdiyse kanonik yolları deneyelim.
    if len(selected) <= 1:
        used_fallback = True
        selected = select_target_pages(
            base, candidates + fallback_candidates(base), limit
        )

    # Spec 3: sınır `scrape_target_pages` içinde de bir kez daha uygulanır.
    scraped, credits_used = scrape_target_pages(client, selected, timeout_seconds)

    return ResearchResult(
        website=base,
        max_pages=limit,
        discovered_urls=len(candidates),
        selected_pages=selected,
        scraped_pages=scraped,
        credits_used=credits_used,
        used_fallback=used_fallback,
    )
