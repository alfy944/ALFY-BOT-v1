from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import logging

# --- QUESTA È LA RIGA CORRETTA ---
from main import run_analysis as perform_technical_analysis

class IndicatorConfig(BaseModel):
    name: str
    length: int = 14

class AnalysisInput(BaseModel):
    symbol: str
    interval: str
    indicator_configs: List[IndicatorConfig]

app = FastAPI()

@app.post("/analyze")
async def analyze_endpoint(data: AnalysisInput):
    try:
        analysis_results = perform_technical_analysis(
            symbol=data.symbol,
            interval=data.interval,
            indicator_configs=[config.dict() for config in data.indicator_configs]
        )
        return analysis_results
    except Exception as e:
        # Questo cattura l'errore rilanciato da run_analysis
        raise HTTPException(status_code=500, detail=f"Errore interno all'agente: {str(e)}")

@app.get("/")
def read_root():
    return {"message": "Technical Analyzer Agent (Versione Finale) è attivo."}