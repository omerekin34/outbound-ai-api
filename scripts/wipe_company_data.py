"""Tüm iş verisini siler; tabloları DROP etmez.

Neon/Postgres: TRUNCATE ... RESTART IDENTITY CASCADE
  — FK sırasını otomatik çözer, identity/serial dizilerini 1'e alır.

Kullanım:
    python -m scripts.wipe_company_data
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from api.database import SessionLocal, engine

# Kullanıcının istediği çekirdek tablolar + bilinen bağlı kayıtlar.
REQUESTED_TABLES = (
    "companies",
    "company_facts",
    "scores",
    "contacts",
    "contact_emails",
    "outreach_messages",
    "opportunities",
    "research_runs",
    "interactions",
    "activity_logs",
)

# Şema sürümü durmalı; iş verisi değil.
_KEEP_TABLES = frozenset({"alembic_version", "schema_migrations"})


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _public_tables(inspector) -> list[str]:
    return [
        name
        for name in inspector.get_table_names()
        if name not in _KEEP_TABLES
    ]


def _row_counts(db, tables: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in tables:
        counts[name] = db.execute(text(f"SELECT COUNT(*) FROM {_quote(name)}")).scalar() or 0
    return counts


def _reset_sequences(db, tables: list[str]) -> None:
    """TRUNCATE RESTART IDENTITY kaçırırsa identity/serial dizilerini sıfırlar."""
    rows = db.execute(
        text(
            """
            SELECT
                n.nspname,
                c.relname AS table_name,
                a.attname AS column_name,
                pg_get_serial_sequence(n.nspname || '.' || c.relname, a.attname) AS seq
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              AND c.relname = ANY(:tables)
            """
        ),
        {"tables": tables},
    ).mappings()
    for row in rows:
        seq = row["seq"]
        if not seq:
            continue
        db.execute(text(f"ALTER SEQUENCE {seq} RESTART WITH 1"))
        print(f"  dizi sıfırlandı: {seq}")


def main() -> None:
    inspector = inspect(engine)
    existing = _public_tables(inspector)
    missing = [name for name in REQUESTED_TABLES if name not in existing]
    extras = [name for name in existing if name not in REQUESTED_TABLES]

    print("tablolar:", ", ".join(existing) or "(yok)")
    if missing:
        print("yok (atlanacak):", ", ".join(missing))
    if extras:
        print("ekstra (yine silinecek):", ", ".join(extras))

    if not existing:
        print("silinecek tablo yok; şema duruyor.")
        return

    with SessionLocal() as db:
        before = _row_counts(db, existing)
        print("önce:", before)

        listed = ", ".join(_quote(name) for name in existing)
        db.execute(text(f"TRUNCATE TABLE {listed} RESTART IDENTITY CASCADE"))
        _reset_sequences(db, existing)
        db.commit()

        after = _row_counts(db, existing)
        leftover = {name: count for name, count in after.items() if count}
        print("sonra:", after)
        if leftover:
            raise SystemExit(f"temizlik tamamlanmadı: {leftover}")
        print("veritabanı sıfırlandı; tablolar duruyor, diziler 1'den başlar.")


if __name__ == "__main__":
    main()
