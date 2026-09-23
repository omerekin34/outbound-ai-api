"""Neon şemasını `api/models.py` ile hizalayan tek seferlik migration.

Yaptıkları:
  1. Eksik tabloları oluşturur (`activity_logs`, `interactions`).
  2. `companies.normalized_name` kolonunu ekler (tekilleştirme için gerekli).
  3. `scores`, `company_facts`, `outreach_messages` tablolarındaki `company_id`
     kolonunu INTEGER -> VARCHAR(255) yapar. `companies.id` VARCHAR olduğu için
     bu kolonlar mevcut hallerinde şirketlerle eşleşemiyor.
  4. Dashboard sorgularının kullandığı indeksleri ekler.
  5. `--fix-status` verilirse `status` alanındaki tırnak kirliliğini temizler
     ("'new'" -> "new").

Çalıştırma:
    python -m scripts.migrate            # kontrol + şema düzeltmeleri
    python -m scripts.migrate --fix-status
    python -m scripts.migrate --dry-run  # sadece ne yapacağını yazar

Kolon tipi değişiklikleri yalnızca ilgili tablo **boşsa** uygulanır; veri
varsa script uyarı verip o adımı atlar.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import inspect, text

from api.config import get_settings
from api.database import Base, engine
from api.models import (  # noqa: F401  (metadata'ya kaydolması için)
    ActivityLog,
    Interaction,
)

ID_TYPE = "VARCHAR(255)"

# (tablo, kolon) -> companies.id ile aynı tipe çekilecek alanlar.
COMPANY_ID_COLUMNS = (
    ("scores", "company_id"),
    ("company_facts", "company_id"),
    ("outreach_messages", "company_id"),
)

# Boş tablolarda `companies.id`'ye foreign key kurulur.
FOREIGN_KEYS = (
    ("scores", "company_id", "scores_company_id_fkey"),
    ("company_facts", "company_id", "company_facts_company_id_fkey"),
)

INDEXES = (
    ("ix_companies_status", "companies", "(status)"),
    ("ix_companies_created_at", "companies", "(created_at DESC)"),
    ("ix_companies_domain", "companies", "(domain)"),
    ("ix_companies_normalized_name", "companies", "(normalized_name)"),
    ("ix_contacts_company_id", "contacts", "(company_id)"),
    # Gelen kutusu / fırsatlar sorguları.
    ("ix_interactions_company_id", "interactions", "(company_id)"),
    ("ix_interactions_received_at", "interactions", "(received_at DESC)"),
    ("ix_scores_qualification_status", "scores", "(qualification_status)"),
    ("ix_scores_requires_deep_research", "scores", "(requires_deep_research)"),
    ("ix_contacts_email_status", "contacts", "(email_status)"),
)


class Migrator:
    def __init__(self, dry_run: bool) -> None:
        self.dry_run = dry_run
        self.applied: list[str] = []
        self.skipped: list[str] = []

    def log_applied(self, message: str) -> None:
        prefix = "[DRY-RUN]" if self.dry_run else "[OK]"
        print(f"{prefix} {message}")
        self.applied.append(message)

    def log_skipped(self, message: str) -> None:
        print(f"[ATLANDI] {message}")
        self.skipped.append(message)

    def execute(self, connection, sql: str, description: str) -> None:
        if self.dry_run:
            self.log_applied(f"{description}\n           {sql}")
            return
        connection.execute(text(sql))
        self.log_applied(description)


def row_count(connection, table: str) -> int:
    return connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar() or 0


def column_type(connection, table: str, column: str) -> str | None:
    return connection.execute(
        text(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = :table AND column_name = :column
            """
        ),
        {"table": table, "column": column},
    ).scalar()


def create_missing_tables(migrator: Migrator) -> None:
    existing = set(inspect(engine).get_table_names())
    missing = [name for name in Base.metadata.tables if name not in existing]

    if not missing:
        migrator.log_skipped("Tüm tablolar mevcut, oluşturulacak tablo yok.")
        return

    if migrator.dry_run:
        migrator.log_applied(f"Oluşturulacak tablolar: {', '.join(sorted(missing))}")
        return

    # `create_all` var olan tablolara dokunmaz, sadece eksikleri kurar.
    Base.metadata.create_all(bind=engine)
    migrator.log_applied(f"Tablolar oluşturuldu: {', '.join(sorted(missing))}")


def add_normalized_name(connection, migrator: Migrator) -> None:
    if column_type(connection, "companies", "normalized_name"):
        migrator.log_skipped("companies.normalized_name zaten var.")
        return

    migrator.execute(
        connection,
        "ALTER TABLE companies ADD COLUMN normalized_name VARCHAR",
        "companies.normalized_name kolonu eklendi.",
    )
    # Mevcut satırlar için değeri isimden üret: küçük harf, alfanümerik dışı kaldırılır.
    migrator.execute(
        connection,
        """
        UPDATE companies
        SET normalized_name = regexp_replace(lower(coalesce(name, '')), '[^a-z0-9]+', '', 'g')
        WHERE normalized_name IS NULL
        """,
        "Mevcut şirketler için normalized_name dolduruldu.",
    )


def align_company_id_columns(connection, migrator: Migrator) -> None:
    for table, column in COMPANY_ID_COLUMNS:
        current = column_type(connection, table, column)
        if current is None:
            migrator.log_skipped(f"{table}.{column} bulunamadı.")
            continue
        if current.lower() in {"character varying", "text"}:
            migrator.log_skipped(f"{table}.{column} zaten metin tipinde.")
            continue

        rows = row_count(connection, table)
        if rows:
            migrator.log_skipped(
                f"{table} tablosunda {rows} satır var; {column} tipi elle taşınmalı "
                f"(mevcut tip: {current})."
            )
            continue

        migrator.execute(
            connection,
            f'ALTER TABLE "{table}" ALTER COLUMN {column} TYPE {ID_TYPE} '
            f"USING {column}::{ID_TYPE}",
            f"{table}.{column} tipi {ID_TYPE} yapıldı.",
        )


def add_foreign_keys(connection, migrator: Migrator) -> None:
    for table, column, constraint in FOREIGN_KEYS:
        exists = connection.execute(
            text(
                """
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_name = :table AND constraint_name = :constraint
                """
            ),
            {"table": table, "constraint": constraint},
        ).scalar()
        if exists:
            migrator.log_skipped(f"{constraint} zaten var.")
            continue

        current = column_type(connection, table, column)
        if current is None or current.lower() not in {"character varying", "text"}:
            migrator.log_skipped(
                f"{table}.{column} henüz metin tipinde değil, foreign key atlandı."
            )
            continue

        # Eşleşmeyen satır varsa kısıt eklenemez; önce kontrol edelim.
        orphans = connection.execute(
            text(
                f"""
                SELECT count(*) FROM "{table}" t
                WHERE t.{column} IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM companies c WHERE c.id = t.{column})
                """
            )
        ).scalar()
        if orphans:
            migrator.log_skipped(
                f"{table} tablosunda {orphans} eşleşmeyen {column} var, foreign key atlandı."
            )
            continue

        migrator.execute(
            connection,
            f'ALTER TABLE "{table}" ADD CONSTRAINT {constraint} '
            f"FOREIGN KEY ({column}) REFERENCES companies(id) ON DELETE CASCADE",
            f"{constraint} eklendi.",
        )


def add_enterprise_research_columns(connection, migrator: Migrator) -> None:
    """ERP kanıt JSON'u, persona sırası ve iki adımlı mesaj stratejisi."""
    extras = (
        ("companies", "erp_confidence", "DOUBLE PRECISION"),
        ("companies", "erp_evidence_count", "INTEGER"),
        ("companies", "erp_evidence", "JSONB"),
        ("companies", "outreach_strategy", "JSONB"),
        ("contacts", "persona_rank", "INTEGER"),
        ("contacts", "is_selected", "BOOLEAN NOT NULL DEFAULT FALSE"),
    )
    for table, column, sql_type in extras:
        if column_type(connection, table, column) is None:
            migrator.execute(
                connection,
                f'ALTER TABLE "{table}" ADD COLUMN {column} {sql_type}',
                f"{table}.{column} kolonu eklendi.",
            )
        else:
            migrator.log_skipped(f"{table}.{column} zaten var.")


def add_contact_outreach_columns(connection, migrator: Migrator) -> None:
    """Step 15–17: e-posta doğrulama durumu ve soğuk e-posta taslağı."""
    if column_type(connection, "contacts", "email_status") is None:
        migrator.execute(
            connection,
            "ALTER TABLE contacts ADD COLUMN email_status VARCHAR(32)",
            "contacts.email_status kolonu eklendi.",
        )
    else:
        migrator.log_skipped("contacts.email_status zaten var.")

    if column_type(connection, "contacts", "generated_email_body") is None:
        migrator.execute(
            connection,
            "ALTER TABLE contacts ADD COLUMN generated_email_body TEXT",
            "contacts.generated_email_body kolonu eklendi.",
        )
    else:
        migrator.log_skipped("contacts.generated_email_body zaten var.")


def add_company_deep_research_columns(connection, migrator: Migrator) -> None:
    """Step 10–12: ERP sinyali ve ağrı hipotezi."""
    if column_type(connection, "companies", "erp_signal") is None:
        migrator.execute(
            connection,
            "ALTER TABLE companies ADD COLUMN erp_signal TEXT",
            "companies.erp_signal kolonu eklendi.",
        )
    else:
        migrator.log_skipped("companies.erp_signal zaten var.")

    if column_type(connection, "companies", "pain_hypothesis") is None:
        migrator.execute(
            connection,
            "ALTER TABLE companies ADD COLUMN pain_hypothesis TEXT",
            "companies.pain_hypothesis kolonu eklendi.",
        )
    else:
        migrator.log_skipped("companies.pain_hypothesis zaten var.")


def add_score_qualification_columns(connection, migrator: Migrator) -> None:
    """Step 19–20: yeterlilik durumu ve derin araştırma bayrağı."""
    if column_type(connection, "scores", "qualification_status") is None:
        migrator.execute(
            connection,
            "ALTER TABLE scores ADD COLUMN qualification_status VARCHAR(32)",
            "scores.qualification_status kolonu eklendi.",
        )
    else:
        migrator.log_skipped("scores.qualification_status zaten var.")

    if column_type(connection, "scores", "requires_deep_research") is None:
        migrator.execute(
            connection,
            "ALTER TABLE scores ADD COLUMN requires_deep_research BOOLEAN "
            "NOT NULL DEFAULT FALSE",
            "scores.requires_deep_research kolonu eklendi.",
        )
    else:
        migrator.log_skipped("scores.requires_deep_research zaten var.")


def create_indexes(connection, migrator: Migrator) -> None:
    for name, table, definition in INDEXES:
        if not column_type(connection, table, definition.strip("()").split()[0]):
            migrator.log_skipped(f"{name} için kolon bulunamadı, atlandı.")
            continue
        migrator.execute(
            connection,
            f'CREATE INDEX IF NOT EXISTS {name} ON "{table}" {definition}',
            f"{name} indeksi hazır.",
        )


def fix_status_values(connection, migrator: Migrator) -> None:
    """`status` alanına yanlışlıkla yazılmış tırnakları temizler."""
    dirty = connection.execute(
        text(
            """
            SELECT count(*) FROM companies
            WHERE status IS NOT NULL AND status <> btrim(status, ' ''"')
            """
        )
    ).scalar()

    if not dirty:
        migrator.log_skipped("status alanında temizlenecek kayıt yok.")
        return

    migrator.execute(
        connection,
        """
        UPDATE companies
        SET status = lower(btrim(status, ' ''"'))
        WHERE status IS NOT NULL AND status <> btrim(status, ' ''"')
        """,
        f"{dirty} şirketin status değeri normalize edildi.",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Değişiklik yapmadan planı göster."
    )
    parser.add_argument(
        "--fix-status",
        action="store_true",
        help="companies.status alanındaki tırnak kirliliğini temizle (veri günceller).",
    )
    args = parser.parse_args()

    settings = get_settings()
    print(f"Veritabanı: {settings.database_host}")
    print(f"Mod: {'DRY-RUN' if args.dry_run else 'UYGULA'}\n")

    migrator = Migrator(args.dry_run)

    create_missing_tables(migrator)

    with engine.begin() as connection:
        add_normalized_name(connection, migrator)
        align_company_id_columns(connection, migrator)
        add_foreign_keys(connection, migrator)
        add_score_qualification_columns(connection, migrator)
        add_company_deep_research_columns(connection, migrator)
        add_contact_outreach_columns(connection, migrator)
        add_enterprise_research_columns(connection, migrator)
        create_indexes(connection, migrator)
        if args.fix_status:
            fix_status_values(connection, migrator)
        if args.dry_run:
            connection.rollback()

    print(
        f"\nÖzet: {len(migrator.applied)} işlem, {len(migrator.skipped)} atlandı."
    )
    if not args.fix_status:
        print(
            "Not: status alanındaki tırnak kirliliği için `--fix-status` ile tekrar çalıştırın."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
