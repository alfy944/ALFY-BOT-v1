"""
Master AI Agent v2.2 - Con Learning Integration
================================================
Usa i dati storici dal Learning Agent per migliorare le decisioni.
"""

import os
import json
import httpx
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

app = FastAPI(title="Master AI Agent - Learning Enhanced", version="2.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
MIN_CONFIDENCE = int(os.getenv("MIN_CONFIDENCE", "60"))
LEVERAGE_SCALP = int(os.getenv("LEVERAGE_SCALP", "5"))
LEVERAGE_SWING = int(os.getenv("LEVERAGE_SWING", "3"))
SIZE_PCT = float(os.getenv("SIZE_PCT", "0.15"))
LEARNING_AGENT_URL = os.getenv("LEARNING_AGENT_URL", "http://learning-agent:8000")

client = OpenAI(api_key=OPENAI_API_KEY)

DATA_DIR = "/app/data"
os.makedirs(DATA_DIR, exist_ok=True)
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.json")

latest_decisions: Dict[str, Any] = {}

def log_print(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {"INFO": "i", "WARN": "!", "ERROR": "X", "SUCCESS": "OK", "AI": "AI"}.get(level, "-")
    print("[{}] [{}] {}".format(ts, prefix, msg), flush=True)

class AnalysisRequest(BaseModel):
    symbol: str
    technical: Dict[str, Any]
    fibonacci: Dict[str, Any]
    gann: Dict[str, Any]
    sentiment: Dict[str, Any]
    open_positions: list = []

class DecisionResponse(BaseModel):
    decision: str
    confidence_score: int
    reasoning: str
    trade_setup: Optional[Dict[str, Any]] = None

async def get_learning_context() -> str:
    """Recupera il contesto dal Learning Agent."""
    try:
        async with httpx.AsyncClient(timeout=10) as client_http:
            r = await client_http.get("{}/ai_context".format(LEARNING_AGENT_URL))
            if r.status_code == 200:
                data = r.json()
                context = data.get("context", "")
                if context:
                    log_print("Learning context loaded", "SUCCESS")
                    return context
    except Exception as e:
        log_print("Could not fetch learning context: {}".format(e), "WARN")
    return ""

async def get_symbol_stats(symbol: str) -> Dict:
    """Recupera statistiche specifiche per un symbol."""
    try:
        async with httpx.AsyncClient(timeout=10) as client_http:
            r = await client_http.get("{}/stats".format(LEARNING_AGENT_URL))
            if r.status_code == 200:
                data = r.json()
                symbol_stats = data.get("by_symbol", {}).get(symbol, {})
                return symbol_stats
    except:
        pass
    return {}

def build_prompt(data: AnalysisRequest, learning_context: str, symbol_stats: Dict) -> str:
    """Costruisce il prompt per GPT con contesto di apprendimento."""
    
    # Header con dati storici
    historical_section = ""
    if learning_context:
        historical_section = """
{}

""".format(learning_context)
    
    # Stats specifiche del symbol
    symbol_warning = ""
    if symbol_stats:
        wr = symbol_stats.get("win_rate", 0)
        trades = symbol_stats.get("trades", 0)
        pnl = symbol_stats.get("pnl", 0)
        if trades >= 3:
            if wr >= 70:
                symbol_warning = "NOTE: {} has EXCELLENT historical performance ({}% win rate, {} trades, ${} PnL). Consider being more aggressive.\n".format(data.symbol, wr, trades, pnl)
            elif wr <= 40:
                symbol_warning = "WARNING: {} has POOR historical performance ({}% win rate, {} trades, ${} PnL). Be extra cautious or consider skipping.\n".format(data.symbol, wr, trades, pnl)
            elif pnl < -10:
                symbol_warning = "WARNING: {} is losing money historically (${} PnL despite {}% win rate). Losses are too big - use TIGHTER stop losses.\n".format(data.symbol, pnl, wr)

    prompt = """You are an elite trading AI analyzing {symbol}.

{historical}{symbol_warning}
=== CURRENT MARKET DATA ===

TECHNICAL ANALYSIS:
{technical}

FIBONACCI LEVELS:
{fibonacci}

GANN ANALYSIS:
{gann}

SENTIMENT:
{sentiment}

OPEN POSITIONS: {positions}

=== TRADING RULES ===
1. Single Timeframe Conviction: Need ONE clear timeframe signal + supporting factor
2. SCALP (M15/H1): SL 0.8-1.5%, TP min 1:1 R:R, Leverage {lev_scalp}x
3. SWING (H4): SL 1.5-3%, TP min 1.3:1 R:R, Leverage {lev_swing}x
4. Confidence must be >= {min_conf} to trade
5. If symbol has poor historical performance, require higher confidence (70+)
6. If historical data shows losses are too big, use TIGHTER stop losses (reduce by 20-30%)

=== RESPONSE FORMAT (JSON only) ===
{{
    "decision": "OPEN_LONG" | "OPEN_SHORT" | "HOLD",
    "confidence_score": 0-100,
    "reasoning": "detailed explanation including historical context if relevant",
    "trade_setup": {{
        "entry": price,
        "stop_loss": price,
        "take_profit": price,
        "leverage": {lev_scalp} or {lev_swing},
        "size_pct": {size},
        "trade_type": "SCALP" or "SWING",
        "target_timeframe": "M15" | "H1" | "H4"
    }}
}}

If HOLD, trade_setup can be null.
Respond with valid JSON only, no markdown.""".format(
        symbol=data.symbol,
        historical=historical_section,
        symbol_warning=symbol_warning,
        technical=json.dumps(data.technical, indent=2),
        fibonacci=json.dumps(data.fibonacci, indent=2),
        gann=json.dumps(data.gann, indent=2),
        sentiment=json.dumps(data.sentiment, indent=2),
        positions=data.open_positions if data.open_positions else "None",
        lev_scalp=LEVERAGE_SCALP,
        lev_swing=LEVERAGE_SWING,
        min_conf=MIN_CONFIDENCE,
        size=SIZE_PCT
    )
    
    return prompt

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "master-ai-agent",
        "version": "2.2.0",
        "model": OPENAI_MODEL,
        "learning_enabled": True
    }

@app.post("/analyze", response_model=DecisionResponse)
async def analyze(data: AnalysisRequest):
    """Analizza i dati e genera decisione di trading."""
    
    if data.symbol in [p.get("symbol") for p in data.open_positions if isinstance(p, dict)]:
        return DecisionResponse(
            decision="HOLD",
            confidence_score=0,
            reasoning="Position already open for {}".format(data.symbol)
        )
    
    # Recupera contesto dal Learning Agent
    learning_context = await get_learning_context()
    symbol_stats = await get_symbol_stats(data.symbol)
    
    # Costruisci prompt con contesto storico
    prompt = build_prompt(data, learning_context, symbol_stats)
    
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a professional trading AI. Always respond with valid JSON only. Use historical performance data to improve decisions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        content = response.choices[0].message.content.strip()
        
        # Pulisci eventuale markdown
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()
        
        result = json.loads(content)
        
        decision = DecisionResponse(
            decision=result.get("decision", "HOLD"),
            confidence_score=result.get("confidence_score", 0),
            reasoning=result.get("reasoning", ""),
            trade_setup=result.get("trade_setup")
        )
        
        # Salva decisione
        latest_decisions[data.symbol] = {
            "decision": decision.decision,
            "confidence_score": decision.confidence_score,
            "reasoning": decision.reasoning[:200] + "..." if len(decision.reasoning) > 200 else decision.reasoning,
            "trade_setup": decision.trade_setup,
            "model": OPENAI_MODEL,
            "learning_context_used": bool(learning_context),
            "symbol_stats": symbol_stats,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Salva su file
        try:
            with open(DECISIONS_FILE, "w") as f:
                json.dump(latest_decisions, f, indent=2)
        except:
            pass
        
        log_print("{}: {} (conf: {}, learning: {})".format(
            data.symbol, 
            decision.decision, 
            decision.confidence_score,
            "YES" if learning_context else "NO"
        ), "AI")
        
        return decision
        
    except json.JSONDecodeError as e:
        log_print("JSON parse error: {}".format(e), "ERROR")
        return DecisionResponse(decision="HOLD", confidence_score=0, reasoning="Failed to parse AI response")
    except Exception as e:
        log_print("OpenAI error: {}".format(e), "ERROR")
        return DecisionResponse(decision="HOLD", confidence_score=0, reasoning="AI error: {}".format(str(e)))

@app.get("/latest_decisions")
def get_latest_decisions():
    return latest_decisions

@app.get("/learning_status")
async def learning_status():
    """Mostra lo stato dell'integrazione con Learning Agent."""
    context = await get_learning_context()
    return {
        "learning_agent_url": LEARNING_AGENT_URL,
        "context_available": bool(context),
        "context_preview": context[:500] if context else None
    }

@app.on_event("startup")
async def startup():
    log_print("Master AI v2.2 starting - Model: {}".format(OPENAI_MODEL), "INFO")
    log_print("Learning Agent URL: {}".format(LEARNING_AGENT_URL), "INFO")
    
    # Test connessione Learning Agent
    context = await get_learning_context()
    if context:
        log_print("Learning Agent connected - Historical data available", "SUCCESS")
    else:
        log_print("Learning Agent not available - Will retry on each request", "WARN")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
