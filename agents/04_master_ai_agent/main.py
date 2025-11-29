import os
import json
import time
import requests
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, Any, List
from openai import OpenAI
# from forecaster import get_crypto_forecasts # DISABILITATO TEMP

app = FastAPI()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
client = OpenAI(api_key=OPENAI_API_KEY)

AGENTS = {
    "technical": "http://technical-analyzer-agent:8000/analyze_multi_tf",
    "fibonacci": "http://fibonacci-cyclical-agent:8000/analyze_fib",
    "sentiment": "http://news-sentiment-agent:8000/analyze_sentiment",
    "gann": "http://gann-analyzer-agent:8000/analyze_gann"
}

class BatchTradeRequest(BaseModel):
    symbols: List[str]
    portfolio: Dict[str, Any]

def get_agent_data(name, url, payload):
    try:
        response = requests.post(url, json=payload, timeout=4)
        if response.status_code == 200:
            return response.json()
        return {"error": "N/A"}
    except:
        return {"error": "Timeout"}

def load_system_prompt():
    try:
        with open("formatted_system_prompt.txt", "r") as f: return f.read()
    except: return "You are a crypto AI. Output JSON."

def call_gpt_batch(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-5.1",
            messages=[{"role": "user", "content": prompt}],
            # Niente extra_body per evitare errori
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "portfolio_decision",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "trades": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "symbol": {"type": "string", "enum": ["BTC", "ETH", "SOL"]},
                                        "operation": {"type": "string", "enum": ["open", "close", "hold"]},
                                        "direction": {"type": "string", "enum": ["long", "short"]},
                                        "target_portion_of_balance": {"type": "number"},
                                        "leverage": {"type": "number"},
                                        "reason": {"type": "string"}
                                    },
                                    "required": ["symbol", "operation", "direction", "target_portion_of_balance", "leverage", "reason"],
                                    "additionalProperties": False
                                }
                            }
                        },
                        "required": ["trades"],
                        "additionalProperties": False
                    }
                }
            }
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"GPT Error: {e}")
        return {"trades": [], "error": str(e)}

@app.post("/execute_batch_strategy")
def execute_batch(req: BatchTradeRequest):
    print(f"🧠 RIZZO MASTER: Safe Mode Analysis for {req.symbols}...")
    
    indicators_txt = ""
    for sym in req.symbols:
        clean_sym = sym.replace("USDT", "")
        payload = {"symbol": clean_sym + "USDT"}
        
        # Raccolta Dati Tecnici (Leggeri)
        tech = get_agent_data("Technical", AGENTS["technical"], payload)
        fib = get_agent_data("Fibonacci", AGENTS["fibonacci"], payload)
        gann = get_agent_data("Gann", AGENTS["gann"], payload)
        
        indicators_txt += f"""
        === {clean_sym} DATA ===
        TECHNICAL: {json.dumps(tech)}
        FIBONACCI: {json.dumps(fib)}
        GANN: {json.dumps(gann)}
        ------------------------
        """
    
    sent_payload = {"symbol": "BTCUSDT"} 
    sentiment_json = get_agent_data("Sentiment", AGENTS["sentiment"], sent_payload)
    
    # MOCK FORECAST (Per evitare crash Prophet)
    forecasts_txt = "Forecast data temporarily unavailable. Focus on Technicals."

    msg_info = f"""<indicatori>\n{indicators_txt}\n</indicatori>\n\n
    <sentiment>\n{json.dumps(sentiment_json)}\n</sentiment>\n\n
    <forecast>\n{forecasts_txt}\n</forecast>\n\n"""

    final_prompt = f"""
    {load_system_prompt()}
    
    INSTRUCTIONS:
    1. Analyze the technical data for ALL assets.
    2. THINK DEEPLY about the setup.
    3. Output a JSON list of decisions.
    
    PORTFOLIO: {json.dumps(req.portfolio)}
    
    {msg_info}
    """

    print("🚀 Sending Signal to GPT-5.1 (Safe Mode)...")
    return call_gpt_batch(final_prompt)

@app.get("/health")
def health(): return {"status": "active"}

# Endpoint fantasma per zittire i 404 della Dashboard
@app.get("/latest_reasoning")
def reason(): return {"status": "ok"}
