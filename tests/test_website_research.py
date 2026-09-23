"""Workflow 3 — hedef sayfa seçimi ve tarama akışı testleri.

Firecrawl taklit edilir; testler ağ erişimi veya API anahtarı gerektirmez.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from api.services.website_research import (
    CATEGORY_ORDER,
    MAX_PAGES,
    ScrapedPage,
    classify_url,
    normalize_url,
    research_website,
    select_target_pages,
)

BASE = "https://ornekmakina.com.tr"
# Kök adres kanonik biçimde sondaki `/` ile temsil edilir.
HOME = f"{BASE}/"

# Tipik bir Türk sanayi sitesinin sitemap çıktısı.
SITE_URLS = [
    f"{BASE}/",
    f"{BASE}/hakkimizda",
    f"{BASE}/kurumsal/vizyon-misyon",
    f"{BASE}/urunler",
    f"{BASE}/urunler/hidrolik-pres",
    f"{BASE}/urunler/cnc-torna",
    f"{BASE}/iletisim",
    f"{BASE}/bayiler",
    f"{BASE}/bayilik-basvurusu",
    f"{BASE}/katalog",
    f"{BASE}/markalar",
    f"{BASE}/cozumler",
    f"{BASE}/sektorler/otomotiv",
    # Hedef dışı sayfalar — taranmamalı.
    f"{BASE}/blog/2024-fuar-takvimi",
    f"{BASE}/kvkk-aydinlatma-metni",
    f"{BASE}/sepet",
    f"{BASE}/kullanici/giris",
]


class FakeDocument:
    def __init__(self, url: str, markdown: str) -> None:
        self.markdown = markdown
        self.metadata = type("Meta", (), {"source_url": url, "url": url})()


@dataclass
class FakeJob:
    data: list[FakeDocument]
    credits_used: int = 0


@dataclass
class FakeFirecrawl:
    """`map` + `batch_scrape` yüzeyini taklit eder."""

    links: list[str] = field(default_factory=list)
    empty_for: set[str] = field(default_factory=set)
    map_raises: bool = False
    map_calls: list[dict[str, Any]] = field(default_factory=list)
    scraped_urls: list[str] = field(default_factory=list)

    def map(self, url: str, **kwargs: Any) -> Any:
        self.map_calls.append({"url": url, **kwargs})
        if self.map_raises:
            raise RuntimeError("map patladi")
        links = [type("Link", (), {"url": link})() for link in self.links]
        return type("MapData", (), {"links": links})()

    def batch_scrape(self, urls: list[str], **kwargs: Any) -> FakeJob:
        self.scraped_urls = list(urls)
        return FakeJob(
            data=[
                FakeDocument(url, "" if url in self.empty_for else f"# {url}\nicerik")
                for url in urls
            ],
            credits_used=len(urls),
        )


# --- normalize_url ---------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (f"{BASE}/urunler/", f"{BASE}/urunler"),
        (f"{BASE}/urunler#detay", f"{BASE}/urunler"),
        (f"{BASE}//urunler///a", f"{BASE}/urunler/a"),
        ("ornekmakina.com.tr/urunler", f"{BASE}/urunler"),
        (f"{BASE}/urunler?utm_source=google&id=5", f"{BASE}/urunler?id=5"),
        (f"https://ORNEKMAKINA.com.tr/Urunler", "https://ornekmakina.com.tr/Urunler"),
        ("mailto:info@ornekmakina.com.tr", None),
        ("javascript:void(0)", None),
        ("   ", None),
    ],
)
def test_normalize_url(raw: str, expected: str | None) -> None:
    assert normalize_url(raw) == expected


def test_homepage_variants_collapse_to_one_url() -> None:
    assert normalize_url(f"{BASE}/") == normalize_url(BASE) == HOME


@pytest.mark.parametrize(
    "raw",
    ["https://not a url/x", "https://bosluk lu.com", "https://localdomain/x"],
)
def test_invalid_hosts_are_rejected(raw: str) -> None:
    assert normalize_url(raw) is None


def test_idn_domains_become_punycode() -> None:
    assert normalize_url("https://örnekmakina.com.tr/ürünler") == (
        "https://xn--rnekmakina-dcb.com.tr/ürünler"
    )


def test_percent_encoded_turkish_slugs_are_classified() -> None:
    """Sitemap'ler yolları yüzdelik kodlayabilir."""
    url = f"{BASE}/%C3%BCr%C3%BCnler"
    assert classify_url(url, BASE) == "products"
    assert classify_url(f"{BASE}/hakk%C4%B1m%C4%B1zda", BASE) == "about"


# --- classify_url ----------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/", "homepage"),
        ("/hakkimizda", "about"),
        ("/hakkımızda", "about"),  # Türkçe karakterli slug
        ("/kurumsal/vizyon-misyon", "about"),
        ("/urunler", "products"),
        ("/ürünler/hidrolik-pres", "products"),
        ("/iletisim", "contact"),
        ("/bayiler", "dealers"),
        ("/yetkili-satici", "dealers"),
        ("/katalog", "catalog"),
        ("/markalar", "brands"),
        ("/cozumler", "solutions"),
        ("/sektorler/otomotiv", "solutions"),
        ("/index.php?p=hakkimizda", "about"),  # sorgu tabanlı yönlendirme
        ("/blog/2024-fuar-takvimi", None),
        ("/kvkk-aydinlatma-metni", None),
        ("/sepet", None),
    ],
)
def test_classify_url(path: str, expected: str | None) -> None:
    url = normalize_url(f"{BASE}{path}")
    assert url is not None
    assert classify_url(url, BASE) == expected


def test_classification_avoids_substring_false_positives() -> None:
    """Segment içinde arama yapılır; `/duruna` ürün sayfası sayılmamalı."""
    assert classify_url(f"{BASE}/duruna", BASE) is None


# --- select_target_pages ---------------------------------------------------


def test_homepage_is_always_first() -> None:
    pages = select_target_pages(BASE, SITE_URLS)
    assert pages[0].url == HOME
    assert pages[0].category == "homepage"


def test_every_target_category_is_covered_once() -> None:
    pages = select_target_pages(BASE, SITE_URLS)
    assert {page.category for page in pages} == set(CATEGORY_ORDER)


def test_canonical_page_wins_within_category() -> None:
    """`/urunler`, `/urunler/cnc-torna` yerine önce seçilmeli."""
    pages = select_target_pages(BASE, SITE_URLS)
    products = [page.url for page in pages if page.category == "products"]
    assert products[0] == f"{BASE}/urunler"


def test_off_target_pages_are_never_selected() -> None:
    """Spec: kör tarama yok — kategoriye girmeyen URL hiç taranmaz."""
    pages = select_target_pages(BASE, SITE_URLS)
    selected = {page.url for page in pages}
    for off_target in ("/blog/2024-fuar-takvimi", "/kvkk-aydinlatma-metni", "/sepet"):
        assert f"{BASE}{off_target}" not in selected


def test_max_pages_is_enforced_with_many_candidates() -> None:
    flood = [f"{BASE}/urunler/urun-{index}" for index in range(500)]
    pages = select_target_pages(BASE, SITE_URLS + flood)
    assert len(pages) == MAX_PAGES


def test_lower_max_pages_is_respected_and_cannot_exceed_limit() -> None:
    flood = [f"{BASE}/urunler/urun-{index}" for index in range(100)]
    assert len(select_target_pages(BASE, flood, max_pages=5)) == MAX_PAGES
    # Sınırın üstünü istemek MAX_PAGES'e kırpılır.
    assert len(select_target_pages(BASE, flood, max_pages=999)) == MAX_PAGES


def test_coverage_beats_volume_when_quota_is_tight() -> None:
    """Kontenjan darsa tek kategori değil, farklı kategoriler seçilir."""
    candidates = [f"{BASE}/urunler/urun-{i}" for i in range(50)] + [
        f"{BASE}/hakkimizda",
        f"{BASE}/iletisim",
    ]
    pages = select_target_pages(BASE, candidates, max_pages=3)
    assert [page.category for page in pages] == ["homepage", "about", "products"]


def test_external_domains_and_assets_are_filtered() -> None:
    noisy = [
        "https://baska-site.com/urunler",
        "https://facebook.com/ornekmakina",
        f"{BASE}/katalog/katalog-2024.pdf",
        f"{BASE}/img/urun.jpg",
        f"{BASE}/assets/app.js",
        f"{BASE}/urunler",
    ]
    pages = select_target_pages(BASE, noisy)
    assert [page.url for page in pages] == [HOME, f"{BASE}/urunler"]


def test_duplicate_urls_are_collapsed() -> None:
    duplicates = [
        f"{BASE}/urunler",
        f"{BASE}/urunler/",
        f"{BASE}/urunler#top",
        f"{BASE}/urunler?utm_source=ads",
    ]
    pages = select_target_pages(BASE, duplicates)
    assert len(pages) == 2  # anasayfa + tek ürün sayfası


def test_invalid_base_url_yields_nothing() -> None:
    assert select_target_pages("not a url", SITE_URLS) == []


# --- research_website (uçtan uca, taklit istemciyle) -----------------------


def test_research_website_scrapes_only_selected_pages() -> None:
    client = FakeFirecrawl(links=SITE_URLS)
    result = research_website(client, BASE, map_limit=300)

    assert result.discovered_urls == len(SITE_URLS)
    assert len(result.selected_pages) == len(client.scraped_urls)
    assert len(result.scraped_pages) <= MAX_PAGES
    assert client.map_calls[0]["limit"] == 300
    # Hedef dışı sayfalar Firecrawl'a hiç gönderilmedi.
    assert f"{BASE}/sepet" not in client.scraped_urls


def test_research_website_never_exceeds_max_pages() -> None:
    client = FakeFirecrawl(links=[f"{BASE}/urunler/u-{i}" for i in range(400)])
    result = research_website(client, BASE)
    assert len(client.scraped_urls) == MAX_PAGES
    assert len(result.scraped_pages) == MAX_PAGES


def test_scrape_enforces_limit_even_if_selection_is_bypassed() -> None:
    """Sınır, Firecrawl'ın çağrıldığı yerde de uygulanır."""
    from api.services.website_research import TargetPage, scrape_target_pages

    client = FakeFirecrawl()
    oversized = [
        TargetPage(url=f"{BASE}/urunler/u-{i}", category="products") for i in range(50)
    ]
    scrape_target_pages(client, oversized, timeout_seconds=30)

    assert len(client.scraped_urls) == MAX_PAGES


def test_falls_back_to_canonical_paths_when_map_is_empty() -> None:
    client = FakeFirecrawl(links=[])
    result = research_website(client, BASE)

    assert result.used_fallback is True
    assert result.discovered_urls == 0
    assert f"{BASE}/hakkimizda" in client.scraped_urls
    assert len(client.scraped_urls) <= MAX_PAGES


def test_falls_back_when_map_raises() -> None:
    client = FakeFirecrawl(links=[], map_raises=True)
    result = research_website(client, BASE)
    assert result.used_fallback is True
    assert result.scraped_pages  # yine de içerik toplandı


def test_pages_without_content_are_dropped() -> None:
    client = FakeFirecrawl(
        links=SITE_URLS, empty_for={f"{BASE}/iletisim", f"{BASE}/katalog"}
    )
    result = research_website(client, BASE)

    scraped = {page.url for page in result.scraped_pages}
    assert f"{BASE}/iletisim" not in scraped
    assert len(result.selected_pages) <= MAX_PAGES
    assert "homepage" in {page.category for page in result.selected_pages}


def test_categories_survive_the_round_trip() -> None:
    client = FakeFirecrawl(links=SITE_URLS)
    result = research_website(client, BASE)
    by_url = {page.url: page.category for page in result.scraped_pages}

    assert by_url[HOME] == "homepage"
    assert by_url[f"{BASE}/hakkimizda"] == "about"
    assert by_url[f"{BASE}/urunler"] == "products"
    assert f"{BASE}/bayiler" not in by_url


def test_invalid_website_raises() -> None:
    with pytest.raises(ValueError):
        research_website(FakeFirecrawl(), "mailto:info@ornek.com")


# --- analyzer prompt bütçesi ----------------------------------------------


def test_prompt_respects_per_page_and_total_budget() -> None:
    from api.services.enrichment import build_pages_prompt

    pages = [
        ScrapedPage(url=f"{BASE}/p{i}", category="products", markdown="x" * 5_000)
        for i in range(10)
    ]
    prompt = build_pages_prompt(pages, chars_per_page=1_000, total_chars=4_000)

    assert prompt.count("### SAYFA") == 4  # 4_000 / 1_000
    assert prompt.count("x") == 4_000
    assert f"{BASE}/p0" in prompt  # en öncelikli sayfa korunur


def test_prompt_labels_every_page_with_url_and_category() -> None:
    from api.services.enrichment import build_pages_prompt

    pages = [
        ScrapedPage(url=BASE, category="homepage", markdown="anasayfa"),
        ScrapedPage(url=f"{BASE}/bayiler", category="dealers", markdown="bayi listesi"),
    ]
    prompt = build_pages_prompt(pages, chars_per_page=500, total_chars=5_000)

    assert "Kategori: homepage" in prompt
    assert f"URL: {BASE}/bayiler" in prompt
    assert "Kategori: dealers" in prompt
