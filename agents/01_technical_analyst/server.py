# server.py

# 1. Importiamo le librerie necessarie
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel, conlist

# Importiamo la nostra logica di analisi dal file main.py
from .main import analyze

# 2. Creiamo un'istanza dell'applicazione FastAPI
app = FastAPI(
    title="Technical Analyst Agent",
    description="Un agente che esegue analisi tecnica sui dati di mercato.",
    version="1.0.0",
)

# 3. Definiamo i modelli dei dati di input e output con Pydantic
# Questo garantisce che i dati che riceviamo abbiano la forma corretta.
class MarketDataItem(BaseModel):
    timestamp: int  # Usiamo timestamp UNIX per semplicità
    open: float
    high: float
    low: float
    close: float
    volume: float

# Il nostro input sarà una lista di questi item, con almeno 20 elementi per i calcoli
class AnalysisInput(BaseModel):
    market_data: conlist(MarketDataItem, min_length=20)


# 4. Definiamo l'endpoint della nostra API
@app.post("/analyze/")
async def run_analysis(input_data: AnalysisInput):
    """
    Esegue l'analisi tecnica e restituisce gli indicatori più recenti.

    Per usare questo endpoint, invia una richiesta POST con un JSON contenente
    la chiave "market_data" e una lista di candele.
    """
    # Convertiamo i dati ricevuti (una lista di oggetti) in un DataFrame pandas
    df = pd.DataFrame([item.dict() for item in input_data.market_data])
    
    # Convertiamo il timestamp da UNIX a formato datetime, necessario per Pandas
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')

    # Chiamiamo la nostra funzione di analisi dal file main.py
    analysis_result = analyze(df)

    # Restituiamo il risultato. FastAPI lo convertirà in JSON automaticamente.
    return analysis_result

# Endpoint di base per controllare se il server è attivo
@app.get("/")
def health_check():
    return {"status": "Technical Analyst Agent is running"}
