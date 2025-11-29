import math
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class GannRequest(BaseModel):
    price: float

@app.post("/analyze_gann")
def analyze(req: GannRequest):
    price = req.price
    # Logica Gann Quadrato del 9 semplificata
    root = math.sqrt(price)
    lower_root = math.floor(root)
    upper_root = math.ceil(root)
    
    support = (lower_root ** 2)
    resistance = (upper_root ** 2)
    
    return {
        "price": price,
        "gann_support": support,
        "gann_resistance": resistance,
        "trend": "BULLISH" if price > (support + resistance)/2 else "BEARISH"
    }

@app.get("/health")
def health():
    return {"status": "ok"}
