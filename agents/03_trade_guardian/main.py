from fastapi import FastAPI
from pydantic import BaseModel
import httpx
import os

# Modello dei dati che riceviamo da n8n (solo il simbolo e la direzione)
class TradeSignal(BaseModel):
    symbol: str
    side: str # "Buy" o "Sell"
    current_price: float # Aggiungiamo il prezzo attuale per i calcoli

app = FastAPI()

# URL dell'agente esecutore (il prossimo nella catena)
EXECUTOR_URL = "http://bybit-executor:8000/place_order"

RISK_PER_TRADE_USD = 10.00  # Rischio massimo per operazione (es. 10 USD)
STOP_LOSS_PERCENTAGE = 0.01 # 1% (lo stesso che userà l'esecutore)

@app.post("/validate_and_size")
async def validate_and_size(signal: TradeSignal):
    print(f"--- TRADE GUARDIAN: Segnale ricevuto per {signal.symbol} ---")

    # --- LOGICA DI POSITION SIZING ---
    # Calcoliamo la dimensione della posizione per non rischiare più di 10 USD
    
    # 1. Calcola a quanto corrisponde l'1% di stop loss in USD
    stop_loss_price_diff = signal.current_price * STOP_LOSS_PERCENTAGE
    if stop_loss_price_diff == 0:
        return {"status": "error", "message": "Differenza di prezzo per SL è zero, impossibile calcolare la quantità."}
        
    # 2. Calcola la quantità (qty) di asset da acquistare/vendere
    # Formula: Rischio in USD / (Prezzo di SL in USD per unità)
    quantity = RISK_PER_TRADE_USD / stop_loss_price_diff
    
    print(f"Prezzo attuale: {signal.current_price}")
    print(f"Rischio per trade: ${RISK_PER_TRADE_USD}")
    print(f"Stop Loss (1%): {stop_loss_price_diff} USD per unità")
    print(f"Quantità calcolata: {quantity:.6f} {signal.symbol.split('/')[0]}")
    
    # 3. Prepara l'ordine completo da inviare all'esecutore
    final_order = {
        "symbol": signal.symbol,
        "side": signal.side,
        "qty": round(quantity, 6) # Arrotondiamo per evitare problemi con l'API
    }

    # 4. Inoltra l'ordine all'agente esecutore
    print(f">>> Inoltrando ordine validato a Bybit Executor...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(EXECUTOR_URL, json=final_order, timeout=30.0)
            response.raise_for_status() # Lancia un errore se la risposta è 4xx o 5xx
            
            print(f"<<< Risposta ricevuta da Bybit Executor.")
            return response.json()
            
    except httpx.RequestError as e:
        print(f"!!! ERRORE CRITICO: Impossibile comunicare con Bybit Executor a {EXECUTOR_URL}. Dettagli: {e}")
        return {"status": "error", "message": f"Impossibile contattare l'esecutore: {e}"}
    except Exception as e:
        print(f"!!! ERRORE SCONOSCIUTO: {e}")
        return {"status": "error", "message": str(e)}