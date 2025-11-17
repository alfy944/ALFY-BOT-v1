from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

# Importiamo le nostre nuove funzioni
from main import get_wallet_balance, place_order

class OrderInput(BaseModel):
    symbol: str
    side: str # "Buy" o "Sell"
    qty: float
    reason: Optional[str] = "Decisione del workflow n8n"

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Bybit Executor Agent è attivo."}

@app.get("/balance")
def get_balance_endpoint(coin: str = "USDT"):
    balance = get_wallet_balance(coin)
    if balance is None:
        raise HTTPException(status_code=500, detail="Errore nel contattare l'API di Bybit.")
    return balance

@app.post("/place_order")
def place_order_endpoint(order: OrderInput):
    """
    Endpoint per ricevere una richiesta di piazzare un ordine e registrarlo.
    """
    if order.side.lower() not in ['buy', 'sell']:
        raise HTTPException(status_code=400, detail="Il campo 'side' deve essere 'Buy' o 'Sell'")
    
    result = place_order(
        symbol=order.symbol,
        side=order.side,
        qty=order.qty,
        reason=order.reason
    )
    
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])
        
    return result