"""Şirket ve bağlı kayıtları siler; tabloları DROP etmez.

Kullanım:
    python -m scripts.wipe_company_data
"""

from __future__ import annotations

from sqlalchemy import delete, func, inspect, select, text

from api.database import SessionLocal, engine
from api.models import (
    ActivityLog,
    Company,
    CompanyFact,
    Contact,
    Interaction,
    OutreachMessage,
    Score,
)

# FK sırası: çocuklar önce. activity_logs'ta FK yok ama şirket izi taşır.
_DELETE_ORDER = (
    Interaction,
    OutreachMessage,
    Contact,
    CompanyFact,
    Score,
    ActivityLog,
    Company,
)


def _count(db, model) -> int:
    return db.execute(select(func.count()).select_from(model)).scalar() or 0


def main() -> None:
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print("tablolar:", ", ".join(tables) or "(yok)")

    with SessionLocal() as db:
        before = {model.__tablename__: _count(db, model) for model in _DELETE_ORDER}
        print("önce:", before)

        for model in _DELETE_ORDER:
            if model.__tablename__ not in tables:
                continue
            result = db.execute(delete(model))
            print(f"  silindi {model.__tablename__}: {result.rowcount}")

        # Modelde olmayan ama company_id taşıyan ekstra tablolar.
        extra = []
        for name in tables:
            if name in before:
                continue
            columns = {col["name"] for col in inspector.get_columns(name)}
            if "company_id" in columns:
                extra.append(name)
        for name in extra:
            result = db.execute(text(f'DELETE FROM "{name}"'))
            print(f"  silindi {name} (ekstra): {result.rowcount}")

        db.commit()

        after = {model.__tablename__: _count(db, model) for model in _DELETE_ORDER}
        leftover = {name: count for name, count in after.items() if count}
        print("sonra:", after)
        if leftover:
            raise SystemExit(f"temizlik tamamlanmadı: {leftover}")
        print("veritabanı sıfırlandı; tablolar duruyor.")


if __name__ == "__main__":
    main()
