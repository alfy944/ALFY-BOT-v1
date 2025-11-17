from fastapi import FastAPI
from pydantic import BaseModel
import os
from pybit.unified_trading import HTTP

# Modello dell'ordine completo che riceviamo dal Trade Guardian
class FinalOrder(BaseModel):
    symbol: str
    side: str
    qty: float

app = FastAPI()

# --- INIZIALIZZAZIONE DEL CLIENT BYBIT ---
try:
    session = HTTP(
        testnet=True, # FONDAMENTALE: SEMPRE TESTNET PER I TEST!
        api_key=os.environ.get("BYBIT_API_KEY"),
        api_secret=os.environ.get("BYBIT_API_SECRET"),
    )
    print("BYBIT EXECUTOR: Connessione a Bybit (Testnet) stabilita.")
except Exception as e:
    print(f"BYBIT EXECUTOR - ERRORE CRITICO: Impossibile inizializzare sessione Bybit. Errore: {e}")
    session = None

# Endpoint che viene chiamato dal Trade Guardian
@app.post("/place_order")
def place_order(order: FinalOrder):
    if not session:
        return {"status": "error", "message": "Sessione Bybit non inizializzata."}

    print(f"--- BYBIT EXECUTOR: Ordine finale ricevuto ---")
    print(f"Dettagli: {order.symbol}, {order.side}, Qty: {order.qty}")

    # Siccome i calcoli di rischio sono già stati fatti, qui definiamo solo
    # la strategia di SL/TP in base a percentuali fisse.
    symbol_for_api = order.symbol.replace("/", "")
    try:
        ticker_info = session.get_tickers(category="spot", symbol=symbol_for_api)
        mark_price = float(ticker_info['result']['list'][0]['markPrice'])
    except Exception as e:
        return {"status": "error", "message": f"Impossibile ottenere il prezzo di mercato: {e}"}

    TAKE_PROFIT_PERCENTAGE = 0.02  # 2%
    STOP_LOSS_PERCENTAGE = 0.01   # 1%

    if order.side.lower() == 'buy':
        take_profit_price = round(mark_price * (1 + TAKE_PROFIT_PERCENTAGE), 2)
        stop_loss_price = round(mark_price * (1 - STOP_LOSS_PERCENTAGE), 2)
    else: # Sell
        take_profit_price = round(mark_price * (1 - TAKE_PROFIT_PERCENTAGE), 2)
        stop_loss_price = round(mark_price * (1 + STOP_LOSS_PERCENTAGE), 2)
    
    # --- ESECUZIONE ORDINE ---
    try:
        print(f">>> Inviando ordine a Bybit: {order.qty} {symbol_for_api} @ Mkt, TP:{take_profit_price}, SL:{stop_loss_price}")
        response = session.place_order(
            category="spot",
            symbol=symbol_for_api,
            side=order.side,
            orderType="Market",
            qty=str(order.qty),
            takeProfit=str(take_profit_price),
            stopLoss=str(stop_loss_price),
        )
        print("<<< Risposta da Bybit:")
        print(response)
        return {"status": "success", "response": response}
    except Exception as e:
        print(f"!!! ERRORE CRITICO ESECUZIONE ORDINE: {e}")
        return {"status": "error", "message": str(e)}