from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class ForecastRequest(BaseModel):
    symbol: str

@app.post("/forecast")
def forecast(req: ForecastRequest):
    return {
        "symbol": req.symbol,
        "forecast_bias": "NEUTRAL",
        "expected_move_pct": 0.05
    }

@app.get("/health")
def health(): return {"status": "ok"}
