"""Gelen Kutusu / Fırsatlar ekranları için **demo** verisi ekler.

`contacts` ve `interactions` tabloları boş olduğu sürece bu ekranlar boş
görünür. Bu script, arayüzü gerçek veriyle görebilmek için örnek karar
vericiler ve AI tarafından sınıflandırılmış e-posta yanıtları üretir.

Bu veri GERÇEK DEĞİLDİR. Tüm kayıtlar `demo-` önekiyle işaretlenir ve
tek komutla geri alınabilir:

    python -m scripts.seed_inbox_demo            # ekle (idempotent)
    python -m scripts.seed_inbox_demo --remove   # sadece demo kayıtları sil
    python -m scripts.seed_inbox_demo --dry-run  # ne yapacağını yaz
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta

from sqlalchemy import select

from api.config import get_settings
from api.database import SessionLocal
from api.models import Company, Contact, Interaction, Score, utcnow

# Demo kayıtlarını ayırt etmek için kullanılan önek.
DEMO_PREFIX = "demo-"

# (kişi adı, soyadı, ünvan, sınıflandırma, güven, saat önce, konu, gövde,
#  özet, sonraki adım, okundu mu)
REPLIES = [
    (
        "Ayşe",
        "Yılmaz",
        "Satın Alma Müdürü",
        Interaction.CLASS_POSITIVE,
        0.94,
        2,
        "Re: Tedarik süreçlerinizde %30 tasarruf",
        "Merhaba,\n\nAnlattığınız çözüm ilgimizi çekti. Şu anda tedarik "
        "tarafında Excel ile ilerliyoruz ve bu bizi ciddi şekilde "
        "yavaşlatıyor. Önümüzdeki hafta 30 dakikalık bir demo ayarlayabilir "
        "miyiz? Perşembe veya Cuma öğleden sonra müsaitim.\n\nAyrıca "
        "fiyatlandırma modelinizi de paylaşabilirseniz sevinirim.\n\n"
        "İyi çalışmalar,\nAyşe Yılmaz",
        "Demo talep ediyor, Perşembe/Cuma öğleden sonra müsait. Fiyat bilgisi istiyor.",
        "Perşembe 14:00 için takvim daveti ve fiyat listesi gönder.",
        False,
    ),
    (
        "Mehmet",
        "Demir",
        "Genel Müdür",
        Interaction.CLASS_MEETING_REQUEST,
        0.91,
        5,
        "Re: Kısa bir görüşme talebi",
        "Merhaba,\n\nBu konuyu ekiple değerlendirdik. Detayları konuşmak "
        "için bu hafta içinde bir görüşme yapalım. Salı 10:00 uygun mu?\n\n"
        "Saygılarımla,\nMehmet Demir",
        "Salı 10:00 için görüşme öneriyor.",
        "Salı 10:00'ı onayla, toplantı linkini gönder.",
        False,
    ),
    (
        "Zeynep",
        "Kaya",
        "Bilgi Teknolojileri Direktörü",
        Interaction.CLASS_POSITIVE,
        0.87,
        9,
        "Re: Entegrasyon soruları",
        "Merhaba,\n\nMevcut ERP'mizle entegrasyon mümkünse ilerlemek "
        "isteriz. API dokümantasyonunuzu paylaşır mısınız? Teknik ekibimiz "
        "inceledikten sonra bir pilot başlatabiliriz.\n\nZeynep Kaya",
        "Entegrasyona açık, API dokümanı istiyor, pilot ihtimali var.",
        "API dokümanını ve pilot sürecini özetleyen e-posta gönder.",
        True,
    ),
    (
        "Can",
        "Öztürk",
        "Operasyon Müdürü",
        Interaction.CLASS_QUESTION,
        0.78,
        14,
        "Re: Tanışma",
        "Merhaba,\n\nÇözümünüz kaç kullanıcıya kadar ölçekleniyor? Ayrıca "
        "verilerimiz Türkiye'de mi barındırılıyor? Bu iki konu netleşmeden "
        "ilerleyemeyiz.\n\nCan Öztürk",
        "Ölçeklenebilirlik ve veri lokasyonu soruyor.",
        "Kullanıcı limitleri ve Türkiye veri merkezi bilgisini yanıtla.",
        False,
    ),
    (
        "Elif",
        "Şahin",
        "Finans Müdürü",
        Interaction.CLASS_NEGATIVE,
        0.83,
        26,
        "Re: Tanışma talebi",
        "Merhaba,\n\nTeşekkür ederiz ancak bu yıl için bütçemiz kapandı. "
        "2027 planlamasında tekrar değerlendirebiliriz.\n\nElif Şahin",
        "Bütçe yok, 2027'de tekrar değerlendirilebilir.",
        "Takibi 2026 Kasım'a ertele.",
        True,
    ),
    (
        "Burak",
        "Aydın",
        "Satış Direktörü",
        Interaction.CLASS_UNSUBSCRIBE,
        0.96,
        38,
        "Re: Tanışma",
        "Lütfen beni listenizden çıkarın.",
        "Listeden çıkarılmak istiyor.",
        "E-posta adresini kara listeye ekle, bir daha yazma.",
        False,
    ),
    (
        "Deniz",
        "Arslan",
        "Ürün Müdürü",
        Interaction.CLASS_AUTO_REPLY,
        0.99,
        52,
        "Otomatik yanıt: Yıllık izin",
        "25 Eylül'e kadar ofis dışındayım. Acil konular için "
        "destek@example.com adresine yazabilirsiniz.",
        "Otomatik izin yanıtı.",
        "25 Eylül sonrası tekrar dene.",
        True,
    ),
    (
        "Selin",
        "Koç",
        "CTO",
        Interaction.CLASS_POSITIVE,
        0.89,
        70,
        "Re: Pilot teklifi",
        "Merhaba,\n\nPilot fikrini beğendik. Küçük bir ekiple başlayıp "
        "sonuçları ölçmek isteriz. Sözleşme ve KVKK dokümanlarını "
        "gönderebilir misiniz?\n\nSelin Koç",
        "Pilot başlatmaya hazır, sözleşme ve KVKK dokümanı istiyor.",
        "Pilot sözleşmesi ve KVKK metnini gönder.",
        True,
    ),
]


def _demo_contact_id(index: int) -> str:
    return f"{DEMO_PREFIX}contact-{index}"


def _demo_message_id(index: int) -> str:
    return f"{DEMO_PREFIX}msg-{index}"


def remove_demo_rows(session, dry_run: bool) -> int:
    """Yalnızca `demo-` önekli kayıtları siler."""
    interactions = session.execute(
        select(Interaction).where(
            Interaction.provider_message_id.like(f"{DEMO_PREFIX}%")
        )
    ).scalars().all()
    contacts = session.execute(
        select(Contact).where(Contact.id.like(f"{DEMO_PREFIX}%"))
    ).scalars().all()

    print(f"Silinecek: {len(interactions)} yanıt, {len(contacts)} kişi.")
    if dry_run:
        return 0

    for row in interactions:
        session.delete(row)
    # Yanıtlar silinmeden kişiler silinemez (FK).
    session.flush()
    for row in contacts:
        session.delete(row)
    session.commit()
    return len(interactions) + len(contacts)


def seed(session, dry_run: bool) -> int:
    # Puanı olan şirketler başa alınır: Fırsatlar ekranındaki "Puan" kolonu ve
    # puana göre sıralama demo veriyle de görülebilsin.
    companies = session.execute(
        select(Company)
        .outerjoin(Score, Score.company_id == Company.id)
        .order_by(
            Score.overall_score.desc().nullslast(),
            Company.created_at.desc().nullslast(),
            Company.id,
        )
    ).scalars().all()

    if not companies:
        print("HATA: `companies` tablosu boş. Önce şirket keşfi yapın.")
        return 0

    print(f"{len(companies)} şirket bulundu, {len(REPLIES)} demo yanıt üretilecek.")
    now = utcnow()
    written = 0

    for index, reply in enumerate(REPLIES):
        (
            first_name,
            last_name,
            title,
            classification,
            confidence,
            hours_ago,
            subject,
            body,
            summary,
            next_action,
            is_read,
        ) = reply

        # Yanıtlar mevcut şirketlere sırayla dağıtılır.
        company = companies[index % len(companies)]
        contact_id = _demo_contact_id(index)
        message_id = _demo_message_id(index)

        existing = session.execute(
            select(Interaction).where(Interaction.provider_message_id == message_id)
        ).scalar_one_or_none()
        if existing is not None:
            print(f"  [atlandı] {message_id} zaten var.")
            continue

        if dry_run:
            print(
                f"  [dry-run] {company.name} <- {first_name} {last_name} "
                f"({classification})"
            )
            written += 1
            continue

        if session.get(Contact, contact_id) is None:
            domain = company.domain or "example.com"
            session.add(
                Contact(
                    id=contact_id,
                    company_id=company.id,
                    first_name=first_name,
                    last_name=last_name,
                    title=title,
                    email=f"{first_name.lower()}.{last_name.lower()}@{domain}",
                )
            )
            session.flush()

        session.add(
            Interaction(
                company_id=company.id,
                contact_id=contact_id,
                direction=Interaction.DIRECTION_INBOUND,
                channel="email",
                subject=subject,
                body=body,
                ai_classification=classification,
                ai_confidence=confidence,
                ai_summary=summary,
                ai_next_action=next_action,
                provider_message_id=message_id,
                is_read=is_read,
                received_at=now - timedelta(hours=hours_ago),
            )
        )
        written += 1
        print(f"  [+] {company.name} <- {first_name} {last_name} ({classification})")

    if not dry_run:
        session.commit()
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--remove", action="store_true", help="Demo kayıtları sil ve çık."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Değişiklik yapmadan planı göster."
    )
    args = parser.parse_args()

    settings = get_settings()
    print(f"Veritabanı: {settings.database_host}")
    print("DİKKAT: Bu script GERÇEK OLMAYAN demo verisi ekler.\n")

    with SessionLocal() as session:
        if args.remove:
            count = remove_demo_rows(session, args.dry_run)
            print(f"\n{count} demo kayıt silindi.")
            return 0

        count = seed(session, args.dry_run)
        print(f"\n{count} demo yanıt eklendi.")
        print("Geri almak için: python -m scripts.seed_inbox_demo --remove")
    return 0


if __name__ == "__main__":
    sys.exit(main())
