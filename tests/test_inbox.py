"""`GET /api/inbox` ve `GET /api/opportunities` testleri.

Odak noktası JOIN'in doğruluğu: şirket + karar verici + yanıt metni + AI
sınıflandırması aynı satırda buluşmalı, gönderilen e-postalar listeye
karışmamalı, Fırsatlar yalnızca olumlu yanıtları göstermeli.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api import models

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)

POSITIVE_BODY = (
    "Merhaba, teklifiniz ilgimizi çekti. Önümüzdeki hafta bir demo "
    "ayarlayabilir miyiz? Perşembe günü müsaitiz."
)
NEGATIVE_BODY = "Teşekkürler ancak şu dönem için bütçemiz yok."


def _company(cid: str, name: str, **kwargs) -> models.Company:
    return models.Company(
        id=cid,
        name=name,
        normalized_name=name.lower().replace(" ", ""),
        domain=f"{cid}.com.tr",
        status="analyzed",
        **kwargs,
    )


def _contact(cid: str, company_id: str, first: str, last: str, title: str):
    return models.Contact(
        id=cid,
        company_id=company_id,
        first_name=first,
        last_name=last,
        title=title,
        email=f"{first.lower()}@{company_id}.com.tr",
    )


def _interaction(**kwargs) -> models.Interaction:
    defaults = {
        "direction": models.Interaction.DIRECTION_INBOUND,
        "channel": "email",
        "subject": "Re: Tanışma",
        "received_at": NOW,
    }
    return models.Interaction(**{**defaults, **kwargs})


@pytest.fixture(autouse=True)
def seed(db_sessionmaker) -> None:
    """İki şirket, iki karar verici ve çeşitli sınıflandırmalarda yanıtlar."""
    with db_sessionmaker() as s:
        s.add_all(
            [
                _company("c-nebim", "Nebim Yazılım", industry="Yazılım", city="İstanbul"),
                _company("c-delta", "Delta Yazılım", industry="Yazılım", city="Ankara"),
                _company("c-kale", "Kale Yazılım", industry="Yazılım", city="Bursa"),
                _contact("p-ayse", "c-nebim", "Ayşe", "Yılmaz", "Satın Alma Müdürü"),
                _contact("p-mehmet", "c-delta", "Mehmet", "Demir", "Genel Müdür"),
                models.Score(company_id="c-nebim", overall_score=82.0),
                models.Score(company_id="c-delta", overall_score=91.5),
                # c-kale puansız: LEFT JOIN'in çalıştığını göstermek için.
            ]
        )
        s.commit()

        s.add_all(
            [
                # Olumlu yanıt, karar verici eşleşmiş.
                _interaction(
                    id=1,
                    company_id="c-nebim",
                    contact_id="p-ayse",
                    body=POSITIVE_BODY,
                    ai_classification=models.Interaction.CLASS_POSITIVE,
                    ai_confidence=0.93,
                    ai_summary="Demo talep ediyor.",
                    ai_next_action="Perşembe için takvim daveti gönder.",
                    is_read=False,
                    received_at=NOW,
                ),
                # Toplantı isteği de fırsat sayılır.
                _interaction(
                    id=2,
                    company_id="c-delta",
                    contact_id="p-mehmet",
                    body="Bu hafta görüşebilir miyiz?",
                    ai_classification=models.Interaction.CLASS_MEETING_REQUEST,
                    ai_confidence=0.88,
                    is_read=True,
                    received_at=NOW - timedelta(hours=2),
                ),
                # Olumsuz: gelen kutusunda var, fırsatlarda yok.
                _interaction(
                    id=3,
                    company_id="c-nebim",
                    contact_id="p-ayse",
                    body=NEGATIVE_BODY,
                    ai_classification=models.Interaction.CLASS_NEGATIVE,
                    ai_confidence=0.7,
                    is_read=False,
                    received_at=NOW - timedelta(hours=5),
                ),
                # Kişi eşleşmemiş olumlu yanıt (contact_id NULL).
                _interaction(
                    id=4,
                    company_id="c-kale",
                    contact_id=None,
                    body="İlgileniyoruz, detay gönderir misiniz?",
                    ai_classification=models.Interaction.CLASS_POSITIVE,
                    ai_confidence=0.6,
                    is_read=False,
                    received_at=NOW - timedelta(days=1),
                ),
                # Bizim gönderdiğimiz e-posta: hiçbir listede görünmemeli.
                _interaction(
                    id=5,
                    company_id="c-nebim",
                    contact_id="p-ayse",
                    direction=models.Interaction.DIRECTION_OUTBOUND,
                    body="Merhaba, ürünümüzü tanıtmak isteriz.",
                    ai_classification=None,
                    received_at=NOW - timedelta(days=2),
                ),
                # Sınıflandırılmamış gelen yanıt.
                _interaction(
                    id=6,
                    company_id="c-delta",
                    contact_id="p-mehmet",
                    body="Otomatik yanıt: yıllık izindeyim.",
                    ai_classification=None,
                    is_read=False,
                    received_at=NOW - timedelta(days=3),
                ),
            ]
        )
        s.commit()


# --- gelen kutusu ----------------------------------------------------------


def test_inbox_returns_only_inbound_replies(client: TestClient) -> None:
    body = client.get("/api/inbox").json()

    assert body["total"] == 5  # 6 kayıt var, biri outbound
    assert 5 not in [item["id"] for item in body["items"]]


def test_inbox_is_sorted_newest_first(client: TestClient) -> None:
    items = client.get("/api/inbox").json()["items"]
    assert [item["id"] for item in items] == [1, 2, 3, 4, 6]


def test_join_exposes_company_and_decision_maker(client: TestClient) -> None:
    """Şirket adı + karar verici adı/ünvanı aynı satırda gelmeli."""
    item = next(i for i in client.get("/api/inbox").json()["items"] if i["id"] == 1)

    assert item["company_name"] == "Nebim Yazılım"
    assert item["company_domain"] == "c-nebim.com.tr"
    assert item["company_industry"] == "Yazılım"
    assert item["contact_name"] == "Ayşe Yılmaz"
    assert item["contact_title"] == "Satın Alma Müdürü"
    assert item["contact_email"] == "ayşe@c-nebim.com.tr"
    assert item["overall_score"] == 82.0


def test_exact_reply_text_is_returned_with_snippet(client: TestClient) -> None:
    item = next(i for i in client.get("/api/inbox").json()["items"] if i["id"] == 1)

    # `body` birebir metin, `snippet` tek satırlık önizleme.
    assert item["body"] == POSITIVE_BODY
    assert item["snippet"].startswith("Merhaba, teklifiniz ilgimizi çekti.")
    assert "\n" not in item["snippet"]


def test_ai_classification_fields_are_returned(client: TestClient) -> None:
    item = next(i for i in client.get("/api/inbox").json()["items"] if i["id"] == 1)

    assert item["classification"] == "positive"
    assert item["confidence"] == pytest.approx(0.93)
    assert item["ai_summary"] == "Demo talep ediyor."
    assert item["ai_next_action"] == "Perşembe için takvim daveti gönder."


def test_missing_contact_does_not_drop_the_row(client: TestClient) -> None:
    """LEFT JOIN: kişi eşleşmemiş yanıt da listelenir."""
    item = next(i for i in client.get("/api/inbox").json()["items"] if i["id"] == 4)

    assert item["company_name"] == "Kale Yazılım"
    assert item["contact_name"] is None
    assert item["contact_title"] is None
    # Şirketin puanı yok; LEFT JOIN None döner.
    assert item["overall_score"] is None


def test_unclassified_reply_is_listed(client: TestClient) -> None:
    item = next(i for i in client.get("/api/inbox").json()["items"] if i["id"] == 6)
    assert item["classification"] is None


def test_inbox_counts(client: TestClient) -> None:
    body = client.get("/api/inbox").json()

    assert body["unread_count"] == 4  # 1, 3, 4, 6
    assert body["positive_count"] == 3  # 1, 2, 4
    breakdown = {r["classification"]: r["count"] for r in body["classification_breakdown"]}
    assert breakdown == {
        "positive": 2,
        "meeting_request": 1,
        "negative": 1,
        "unclassified": 1,
    }


def test_classification_filter(client: TestClient) -> None:
    body = client.get("/api/inbox?classification=positive").json()
    assert [item["id"] for item in body["items"]] == [1, 4]
    assert body["total"] == 2


def test_summary_counts_ignore_the_active_filter(client: TestClient) -> None:
    """Bir filtre seçilince üst sayaçlar ve "Tümü" çipi daralmamalı."""
    body = client.get("/api/inbox?classification=meeting_request").json()

    assert body["total"] == 1  # sayfalama filtreye uyar
    assert body["inbound_total"] == 5  # üst sayaç uymaz
    assert body["unread_count"] == 4
    assert body["positive_count"] == 3
    # Çip sayıları da sabit kalır, aksi halde diğer filtreler kaybolurdu.
    assert len(body["classification_breakdown"]) == 4


def test_summary_counts_do_follow_search(client: TestClient) -> None:
    """Arama ise gerçekten daraltır: sayaçlar arama sonucuna göre hesaplanır."""
    body = client.get("/api/inbox?search=nebim").json()

    assert body["inbound_total"] == 2  # 1 ve 3
    assert body["positive_count"] == 1
    assert body["unread_count"] == 2


def test_invalid_classification_is_rejected(client: TestClient) -> None:
    response = client.get("/api/inbox?classification=cok-olumlu")
    assert response.status_code == 422
    assert "Geçersiz sınıflandırma" in response.json()["detail"]


def test_unread_only_filter(client: TestClient) -> None:
    body = client.get("/api/inbox?unread_only=true").json()
    assert [item["id"] for item in body["items"]] == [1, 3, 4, 6]


@pytest.mark.parametrize(
    ("query", "expected_ids"),
    [
        ("nebim", [1, 3]),          # şirket adı
        ("mehmet", [2, 6]),         # kişi adı
        ("demo", [1]),              # yanıt gövdesi
        ("bütçemiz", [3]),          # gövdede Türkçe karakter
        ("bulunmayan-kelime", []),
    ],
)
def test_search_matches_company_contact_and_body(
    client: TestClient, query: str, expected_ids: list[int]
) -> None:
    body = client.get(f"/api/inbox?search={query}").json()
    assert [item["id"] for item in body["items"]] == expected_ids


def test_pagination(client: TestClient) -> None:
    first = client.get("/api/inbox?limit=2&offset=0").json()
    second = client.get("/api/inbox?limit=2&offset=2").json()

    assert [i["id"] for i in first["items"]] == [1, 2]
    assert [i["id"] for i in second["items"]] == [3, 4]
    # Toplam sayfalamadan etkilenmez.
    assert first["total"] == second["total"] == 5


# --- fırsatlar -------------------------------------------------------------


def test_opportunities_only_include_positive_classifications(
    client: TestClient,
) -> None:
    body = client.get("/api/opportunities").json()

    classifications = {item["classification"] for item in body["items"]}
    assert classifications == {"positive", "meeting_request"}
    assert body["total"] == 3
    # Olumsuz ve sınıflandırılmamış yanıtlar burada yok.
    assert {item["id"] for item in body["items"]} == {1, 2, 4}


def test_opportunities_are_sorted_by_company_score(client: TestClient) -> None:
    items = client.get("/api/opportunities").json()["items"]

    # Delta 91.5, Nebim 82.0, Kale puansız (sonda).
    assert [item["id"] for item in items] == [2, 1, 4]
    assert [item["overall_score"] for item in items] == [91.5, 82.0, None]


def test_opportunities_summary(client: TestClient) -> None:
    body = client.get("/api/opportunities").json()

    assert body["unique_companies"] == 3
    # Şirket başına ortalama: (91.5 + 82.0) / 2 — puansız şirket dışta.
    assert body["average_score"] == pytest.approx(86.8, abs=0.1)


def test_opportunity_rows_carry_the_reply_and_decision_maker(
    client: TestClient,
) -> None:
    item = next(i for i in client.get("/api/opportunities").json()["items"] if i["id"] == 1)

    assert item["company_name"] == "Nebim Yazılım"
    assert item["contact_name"] == "Ayşe Yılmaz"
    assert item["contact_title"] == "Satın Alma Müdürü"
    assert item["body"] == POSITIVE_BODY
    assert item["classification"] == "positive"


def test_opportunities_search(client: TestClient) -> None:
    body = client.get("/api/opportunities?search=kale").json()
    assert [item["id"] for item in body["items"]] == [4]
    assert body["unique_companies"] == 1


def test_average_score_not_double_counted_for_repeat_replies(
    client: TestClient, db_sessionmaker
) -> None:
    """Aynı şirketten ikinci olumlu yanıt ortalamayı kaydırmamalı."""
    before = client.get("/api/opportunities").json()["average_score"]

    with db_sessionmaker() as s:
        s.add(
            _interaction(
                id=99,
                company_id="c-delta",
                contact_id="p-mehmet",
                body="Bir de fiyat listesi alabilir miyiz?",
                ai_classification=models.Interaction.CLASS_POSITIVE,
                received_at=NOW,
            )
        )
        s.commit()

    after = client.get("/api/opportunities").json()
    assert after["total"] == 4          # satır sayısı arttı
    assert after["unique_companies"] == 3  # şirket sayısı aynı
    assert after["average_score"] == pytest.approx(before)


# --- okundu işaretleme ------------------------------------------------------


def test_mark_read_updates_the_row(client: TestClient) -> None:
    response = client.patch("/api/inbox/1/read")
    assert response.status_code == 200
    # Güncellenen satırın kendisi dönmeli, listenin ilk satırı değil.
    assert response.json()["id"] == 1
    assert response.json()["is_read"] is True

    assert client.get("/api/inbox").json()["unread_count"] == 3


def test_mark_unread(client: TestClient) -> None:
    client.patch("/api/inbox/1/read")
    body = client.patch("/api/inbox/1/read?is_read=false").json()
    assert body["is_read"] is False


def test_mark_read_unknown_id_returns_404(client: TestClient) -> None:
    assert client.patch("/api/inbox/9999/read").status_code == 404


def test_mark_read_on_outbound_is_rejected(client: TestClient) -> None:
    response = client.patch("/api/inbox/5/read")
    assert response.status_code == 422


# --- dashboard kartı --------------------------------------------------------


def test_dashboard_reports_positive_reply_count(client: TestClient) -> None:
    stats = client.get("/api/dashboard-stats").json()["stats"]

    assert stats["positive_replies"] == 3
    assert stats["unread_replies"] == 4


def test_empty_database_returns_empty_lists(client: TestClient, db_sessionmaker) -> None:
    with db_sessionmaker() as s:
        s.query(models.Interaction).delete()
        s.commit()

    inbox = client.get("/api/inbox").json()
    opportunities = client.get("/api/opportunities").json()

    assert inbox["items"] == [] and inbox["total"] == 0
    assert inbox["inbound_total"] == 0 and inbox["unread_count"] == 0
    assert inbox["classification_breakdown"] == []
    assert opportunities["items"] == [] and opportunities["total"] == 0
    assert opportunities["average_score"] is None
    assert opportunities["unique_companies"] == 0
