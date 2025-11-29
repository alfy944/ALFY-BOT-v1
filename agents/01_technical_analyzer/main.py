from fastapi import FastAPI
from pydantic import BaseModel
from indicators import CryptoTechnicalAnalysisBybit

app = FastAPI()
analyzer = CryptoTechnicalAnalysisBybit()

class TechRequest(BaseModel):
    symbol: str

@app.post("/analyze_multi_tf")
def analyze_endpoint(req: TechRequest):
    data = analyzer.get_complete_analysis(req.symbol)
    if not data:
        return {"symbol": req.symbol, "error": "Analysis Failed", "price": 0, "rsi": 50}
    return data

@app.get("/health")
def health(): return {"status": "active"}
