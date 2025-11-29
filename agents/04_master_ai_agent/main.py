import os
import json
import time
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI

app = FastAPI()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Memoria volatile dell'ultima analisi
LAST_ANALYSIS = {
    "timestamp": 0,
    "decisions": {}
}

class MarketData(BaseModel):
    raw_data: dict

@app.post("/analyze")
def analyze_market(data: MarketData):
    global LAST_ANALYSIS
    try:
        prompt = f"""
        You are 'Mitragliere', an elite crypto sniper AI.
        MARKET DATA: {json.dumps(data.raw_data, indent=2)}
        
        DECIDE FOR BTC, ETH, SOL.
        OUTPUT JSON ONLY:
        {{
            "BTCUSDT": {{ "decision": "OPEN_LONG" or "HOLD", "leverage": 5, "size_pct": 0.1, "reasoning": "Brief explanation why..." }},
            ...
        }}
        """
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "You are a JSON trading engine."}, {"role": "user", "content": prompt}],
            temperature=0.1
        )
        content = response.choices[0].message.content
        if "```json" in content: content = content.split("```json")[1].split("```")[0]
        
        decisions = json.loads(content)
        
        # Aggiorna la memoria globale
        LAST_ANALYSIS = {
            "timestamp": int(time.time()),
            "decisions": decisions
        }
        return decisions

    except Exception as e:
        print(f"AI Error: {e}")
        return {}

@app.get("/latest_reasoning")
def get_latest():
    return LAST_ANALYSIS

@app.get("/health")
def health(): return {"status": "ok"}
