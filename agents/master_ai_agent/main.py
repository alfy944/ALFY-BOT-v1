import os
import json
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

# Carica variabili d'ambiente
load_dotenv()

app = FastAPI()

# CONFIGURAZIONE
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
client = OpenAI(api_key=OPENAI_API_KEY)
# Modello di punta
MODEL_NAME = "gpt-5.1"  

# --- LA TUA FUNZIONE OTTIMIZZATA (BATCH) ---
def previsione_trading_agent_batch(prompt):
    """
    Versione ottimizzata che richiede decisioni per MULTIPLI asset in una sola chiamata.
    """
    try:
        # Schema JSON modificato per accettare una LISTA di operazioni
        json_schema = {
            "type": "object",
            "properties": {
                "decisions": {
                    "type": "array",
                    "description": "List of trading decisions for all analyzed symbols",
                    "items": {
                        "type": "object",
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": ["open", "close", "hold"]
                            },
                            "symbol": {
                                "type": "string",
                                "enum": ["BTC", "ETH", "SOL"]
                            },
                            "direction": {
                                "type": "string",
                                "enum": ["long", "short"]
                            },
                            "target_portion_of_balance": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1
                            },
                            "leverage": {
                                "type": "number",
                                "minimum": 1,
                                "maximum": 10
                            },
                            "reason": {
                                "type": "string",
                                "maxLength": 300
                            }
                        },
                        "required": ["operation", "symbol", "direction", "target_portion_of_balance", "leverage", "reason"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["decisions"],
            "additionalProperties": False
        }

        # Tenta di usare la sintassi avanzata 'responses.create'
        try:
            response = client.responses.create(
                model=MODEL_NAME,
                input=prompt,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "batch_trade_decisions",
                        "strict": True,
                        "schema": json_schema
                    }
                },
                reasoning={"effort": "medium"},
                store=True
            )
            return json.loads(response.output_text)
        
        except AttributeError:
            # FALLBACK STANDARD
            print(f">>> Fallback: uso chat.completions standard con {MODEL_NAME}")
            completion = client.chat.completions.create(
                model=MODEL_NAME, 
                messages=[
                    {"role": "system", "content": "You are a trading AI. Analyze all assets and return a JSON with a list of decisions under the key 'decisions'."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            return json.loads(completion.choices[0].message.content)

    except Exception as e:
        print(f">>> AI ERROR: {e}")
        return {"decisions": []}

# --- API ENDPOINTS ---

class MarketData(BaseModel):
    raw_data: dict

LATEST_REASONING = {}

@app.post("/analyze")
def analyze_market(data: MarketData):
    global LATEST_REASONING
    print(">>> AVVIO ANALISI BATCH (1 Chiamata per 3 Asset)...")
    
    # 1. Filtriamo solo i dati che ci interessano
    relevant_data = {k: v for k, v in data.raw_data.items() if k in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]}
    
    prompt = f"""
    Analyze the following cryptocurrency market data for BTC, ETH, and SOL.
    
    MARKET DATA:
    {json.dumps(relevant_data, indent=2)}
    
    TASK:
    For EACH symbol (BTC, ETH, SOL), decide whether to OPEN (Long/Short), CLOSE, or HOLD.
    Apply the 'Rizzo' strategy: look for trend continuation and strong volume.
    
    Output a strictly formatted JSON object containing a list of decisions.
    """
    
    # 2. Chiamata AI (Una sola volta!)
    ai_result = previsione_trading_agent_batch(prompt)
    
    # 3. Parsing e Adattamento
    final_decisions = {}
    decision_list = ai_result.get("decisions", [])
    
    # Fallback strutturale
    if not decision_list and isinstance(ai_result, list): 
        decision_list = ai_result
    
    for dec in decision_list:
        sym = dec.get("symbol")
        if not sym: continue
        
        # Mappiamo BTC -> BTCUSDT
        bybit_symbol = f"{sym}USDT"
        
        op = dec.get("operation", "hold").lower()
        direction = dec.get("direction", "long").lower()
        
        decision_code = "HOLD"
        if op == "open":
            decision_code = "OPEN_LONG" if direction == "long" else "OPEN_SHORT"
        elif op == "close":
            decision_code = "CLOSE"
            
        final_decisions[bybit_symbol] = {
            "decision": decision_code,
            "leverage": dec.get("leverage", 5),
            "size_pct": dec.get("target_portion_of_balance", 0.1),
            "reasoning": dec.get("reason", "Global Analysis")
        }
    
    # Aggiorna memoria
    LATEST_REASONING["decisions"] = final_decisions
    
    print(f">>> ANALISI BATCH COMPLETATA. Simboli analizzati: {len(final_decisions)}")
    return final_decisions

@app.get("/latest_reasoning")
def get_reasoning():
    return LATEST_REASONING
