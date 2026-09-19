import os
import json
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from firecrawl import FirecrawlApp
from openai import OpenAI

from api.database import engine, get_db
from api import models

# Tabloları veritabanında oluştur (Eğer yoksa)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Commercial Operations API", version="1.0")

# Firecrawl uygulamasını başlat (Key .env dosyasından otomatik alınır)
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
firecrawl_app = FirecrawlApp(api_key=FIRECRAWL_API_KEY) if FIRECRAWL_API_KEY else None

# OpenAI uygulamasını başlat
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# --- PYDANTIC MODELLERİ (Gelen İsteklerin Formatı) ---

class CompanyCreate(BaseModel):
    name: str
    domain: str
    website: str | None = None
    industry: str | None = None
    employee_count: int | None = None
    country: str = "Turkey"
    city: str | None = None

class CompanyResearchRequest(BaseModel):
    company_id: int

class CompanyAnalyzeRequest(BaseModel):
    company_id: int
    website_content: str


# --- UÇ NOKTALAR (ENDPOINTS) ---

@app.get("/")
def read_root():
    return {"status": "ok", "service": "Outbound Automation API is running"}


# Ana Workflow 1: Şirket Keşfi ve Veritabanına Kayıt
@app.post("/companies/discover")
def discover_company(company: CompanyCreate, db: Session = Depends(get_db)):
    
    # Kural 9: Duplicate Mantığı (Domain üzerinden kontrol)
    existing_company = db.query(models.Company).filter(models.Company.domain == company.domain).first()
    
    if existing_company:
        return {
            "status": "skipped", 
            "message": "Bu şirket zaten veritabanında mevcut.", 
            "company_id": existing_company.id
        }

    # Yeni şirketi oluştur
    new_company = models.Company(
        name=company.name,
        normalized_name=company.name.lower().replace(" ", ""), # Basit normalize işlemi
        domain=company.domain,
        website=company.website,
        industry=company.industry,
        employee_count=company.employee_count,
        country=company.country,
        city=company.city,
        status="new"
    )
    
    # Veritabanına kaydet
    db.add(new_company)
    db.commit()
    db.refresh(new_company)
    
    return {
        "status": "success", 
        "message": "Şirket başarıyla kaydedildi.", 
        "company_id": new_company.id
    }


# Ana Workflow 3: Web Sitesi Taraması (Website Research)
@app.post("/companies/research-website")
def research_website(req: CompanyResearchRequest, db: Session = Depends(get_db)):
    if not firecrawl_app:
        raise HTTPException(status_code=500, detail="Firecrawl API Key eksik.")

    # 1. Şirketi veritabanından bul
    company = db.query(models.Company).filter(models.Company.id == req.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Şirket bulunamadı.")
    
    if not company.website:
        raise HTTPException(status_code=400, detail="Bu şirketin kayıtlı bir web sitesi yok.")

    try:
        # 2. Firecrawl ile siteyi tara ve Markdown'a çevir
        scrape_result = firecrawl_app.scrape_url(
            company.website, 
            formats=['markdown']
        )
        
        if isinstance(scrape_result, dict):
            markdown_content = scrape_result.get('markdown', '')
        else:
            markdown_content = getattr(scrape_result, 'markdown', '')

        # 3. Şirketin durumunu güncelle
        company.status = "website_scraped"
        db.commit()

        # 4. Sonucu döndür
        return {
            "status": "success",
            "company": company.name,
            "scraped_length": len(markdown_content),
            "preview": markdown_content[:300] + "... (devamı var)",
            "message": "Web sitesi başarıyla tarandı ve markdown formatına çevrildi."
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tarama sırasında hata oluştu: {str(e)}")


# Ana Workflow 4: Yapay Zeka ile Analiz ve Puanlama
@app.post("/companies/analyze")
def analyze_company(req: CompanyAnalyzeRequest, db: Session = Depends(get_db)):
    if not openai_client:
        raise HTTPException(status_code=500, detail="OpenAI API Key eksik.")

    company = db.query(models.Company).filter(models.Company.id == req.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Şirket bulunamadı.")

    # 1. Yapay Zekaya verilecek Prompt'u hazırla
    system_prompt = """Sen uzman bir B2B satış analiz asistanısın. Görevin, verilen şirket web sitesi metnini inceleyerek şirketin profilini çıkarmak ve puanlamaktır.
    Aşağıdaki JSON formatında, anahtarları eksiksiz olarak çıktı ver:
    {
        "scores": {
            "icp_score": 85.5,
            "need_score": 70.0,
            "timing_score": 60.0,
            "reachability_score": 90.0,
            "overall_score": 76.3
        },
        "facts": [
            {
                "fact_type": "target_audience",
                "value": "Oyuncular ve e-sporcular",
                "confidence": 0.9,
                "evidence_text": "Web sitesindeki 'oyuncu ekipmanları' vurgusu."
            }
        ]
    }"""

    try:
        # 2. OpenAI API'sine İsteği Gönder (Hızlı ve ucuz olan gpt-4o-mini modelini kullanıyoruz)
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Şirket Adı: {company.name}\n\nWeb Sitesi İçeriği:\n{req.website_content[:5000]}"} 
            ],
            response_format={ "type": "json_object" } # Sadece JSON dönmesini zorunlu kılıyoruz
        )

        # 3. Gelen JSON yanıtını Python sözlüğüne çevir
        result_text = response.choices[0].message.content
        analysis_data = json.loads(result_text)

        # 4. Skorları Veritabanına (scores tablosuna) Yaz
        scores_data = analysis_data.get("scores", {})
        new_score = models.Score(
            company_id=company.id,
            icp_score=scores_data.get("icp_score", 0),
            need_score=scores_data.get("need_score", 0),
            timing_score=scores_data.get("timing_score", 0),
            reachability_score=scores_data.get("reachability_score", 0),
            overall_score=scores_data.get("overall_score", 0)
        )
        db.add(new_score)

        # 5. Bulunan Gerçekleri (facts tablosuna) Yaz
        facts_data = analysis_data.get("facts", [])
        for fact in facts_data:
            new_fact = models.CompanyFact(
                company_id=company.id,
                fact_type=fact.get("fact_type", "unknown"),
                value=str(fact.get("value", "")),
                confidence=fact.get("confidence", 0.0),
                evidence_text=fact.get("evidence_text", ""),
                source_type="website",
                source_url=company.website
            )
            db.add(new_fact)

        # 6. Şirketin durumunu "analiz edildi" olarak güncelle
        company.status = "analyzed"
        db.commit()

        return {
            "status": "success",
            "message": "Şirket yapay zeka ile başarıyla analiz edildi ve veritabanına kaydedildi.",
            "data": analysis_data
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Analiz hatası: {str(e)}")