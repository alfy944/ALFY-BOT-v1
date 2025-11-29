from fastapi import FastAPI
from pydantic import BaseModel
import random

app = FastAPI()

class TechRequest(BaseModel):
    symbol: str

@app.post("/analyze_multi_tf")
def analyze(req: TechRequest):
    # Simulazione dati tecnici per sbloccare il sistema
    # In produzione qui ci andrebbe ccxt o yfinance
    price = 90500.0 if "BTC" in req.symbol else (3000.0 if "ETH" in req.symbol else 136.0)
    return {
        "symbol": req.symbol,
        "price": price,
        "trend": "BULLISH" if random.random() > 0.5 else "BEARISH",
        "rsi": 50 + random.randint(-10, 10),
        "macd": "POSITIVE",
        "support": price * 0.95,
        "resistance": price * 1.05
    }

@app.get("/health")
def health(): return {"status": "ok"}
