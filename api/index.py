from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="AI Commercial Operations API", version="1.0")

class CompanyRequest(BaseModel):
    company_id: str
    website: str | None = None

@app.get("/")
def read_root():
    return {"status": "ok", "service": "Outbound Automation API is running"}

@app.post("/companies/analyze")
def analyze_company(req: CompanyRequest):
    # n8n'den gelecek ilk analiz istekleri buraya düşecek
    return {
        "status": "success",
        "company_id": req.company_id,
        "message": "AI analiz endpoint'i ayağa kalktı."
    }