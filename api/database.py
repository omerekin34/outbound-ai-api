import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# .env dosyasındaki verileri yükle
load_dotenv()

# Neon veritabanı URL'sini al
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# Engine ve Session oluştur
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency (API isteklerinde veritabanı bağlantısı açıp kapatmak için)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()