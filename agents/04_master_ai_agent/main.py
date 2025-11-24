import os
import json
from typing import Dict, Any, List, Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

app = FastAPI(title="Master AI Agent (ITA)")

# --- CONFIGURAZIONE INTELLIGENTE ---
deepseek_key = os.getenv("DEEPSEEK_API_KEY")
openai_key = os.getenv("OPENAI_API_KEY")

if deepseek_key:
    print("🔹 Using DeepSeek AI Model")
    client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
    MODEL_NAME = "deepseek-chat"
elif openai_key:
    print("🔹 Using Standard OpenAI (GPT-4) Model")
    client = OpenAI(api_key=openai_key)
    MODEL_NAME = "gpt-4-turbo-preview"
else:
    client = None
    MODEL_NAME = "none"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELLI ---
class AnalysisPayload(BaseModel):
    symbol: str
    user_config: Dict[str, Any] = {} 
    tech_data: Dict[str, Any]
    fib_data: Dict[str, Any]
    gann_data: Dict[str, Any]
    sentiment_data: Dict[str, Any]

class DecisionResponse(BaseModel):
    decision: str
    trade_setup: Optional[Dict[str, Any]]
    logic_log: List[str]

# --- ENDPOINTS ---

# *** QUESTA È LA PARTE CHE MANCAVA ***
@app.get("/health")
def health_check():
    if not client:
        return {"status": "error", "message": "No API Key configured"}
    return {"status": "ok", "model": MODEL_NAME}

@app.post("/decide", response_model=DecisionResponse)
async def decide(payload: AnalysisPayload):
    if not client:
        return {"decision": "WAIT", "trade_setup": None, "logic_log": ["ERRORE: API Key mancante"]}

    strategy = payload.user_config.get("strategy", "intraday")
    risk_pct = payload.user_config.get("risk_per_trade", 1.0)
    current_price = payload.fib_data.get("current_price", 0.0)

    # PROMPT IN ITALIANO
    system_prompt = f"""
    Sei un Trader AI esperto. Il tuo obiettivo è fare PROFITTO, non restare a guardare.
    Parla SOLO in ITALIANO.
    
    STRATEGIA ATTUALE: {strategy.upper()}
    
    REGOLE OPERATIVE:
    1. INTRADAY: Dai priorità ai segnali 15m. Usa 4H solo come conferma. Cerca ingressi rapidi.
    2. SWING: Dai priorità ai segnali 4H. Ignora il rumore sul 15m.
    
    LOGICA DI DECISIONE:
    - OPEN_LONG: Se c'è slancio rialzista (Prezzo sopra EMA, RSI non in ipercomprato, News positive).
    - OPEN_SHORT: Se c'è pressione ribassista (Prezzo sotto EMA, RSI non in ipervenduto).
    - WAIT: Solo se il mercato è completamente piatto o ci sono segnali fortemente contrastanti.
    
    FORMATO OUTPUT JSON:
    {{
      "decision": "OPEN_LONG" | "OPEN_SHORT" | "WAIT",
      "trade_setup": {{
        "entry_price": {current_price},
        "stop_loss": <prezzo_calcolato>,
        "take_profit": <prezzo_calcolato>,
        "size_pct": {risk_pct}
      }},
      "logic_log": ["Analisi dettagliata in Italiano punto 1", "Analisi punto 2"]
    }}
    """

    user_prompt = f"""
    Analizza {payload.symbol}. Prezzo Attuale: {current_price}.
    
    [TECNICA]: {json.dumps(payload.tech_data)}
    [FIBONACCI]: {json.dumps(payload.fib_data)}
    [GANN]: {json.dumps(payload.gann_data)}
    [SENTIMENT]: {json.dumps(payload.sentiment_data)}
    
    Prendi una decisione decisa per la strategia {strategy.upper()}. Spiega in Italiano.
    """

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=600,
            response_format={ 'type': 'json_object' }
        )
        
        data = json.loads(response.choices[0].message.content)
        # Validazione di sicurezza
        if data.get('decision') not in ["OPEN_LONG", "OPEN_SHORT", "WAIT"]:
            data['decision'] = "WAIT"
            
        return data

    except Exception as e:
        return {
            "decision": "WAIT", 
            "trade_setup": None, 
            "logic_log": [f"Errore AI: {str(e)}"]
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
