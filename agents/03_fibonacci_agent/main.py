from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class FibRequest(BaseModel):
    symbol: str
    price: float

@app.post("/analyze_fib")
def analyze(req: FibRequest):
    # Calcolo livelli base simulati
    p = req.price
    return {
        "symbol": req.symbol,
        "price": p,
        "fib_levels": {
            "0.382": p * 0.98,
            "0.5": p * 0.95,
            "0.618": p * 0.92
        },
        "status": "ok"
    }

@app.get("/health")
def health(): return {"status": "ok"}
