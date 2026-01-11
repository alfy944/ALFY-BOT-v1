import os
import json
import logging
import httpx
from datetime import datetime
from fastapi import FastAPI
from pydantic import BaseModel, field_validator, model_validator
from typing import Dict, Any, Literal, Optional
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MasterAI")

app = FastAPI()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
BB_MIN_WIDTH = float(os.getenv("BB_MIN_WIDTH", "0.001"))
BB_BREACH_PCT = float(os.getenv("BB_BREACH_PCT", "0.002"))
TREND_ALIGNMENT_REQUIRED = os.getenv("TREND_ALIGNMENT_REQUIRED", "false").lower() == "true"
BB_ONLY_STRATEGY = os.getenv("BB_ONLY_STRATEGY", "true").lower() == "true"

# Agent URLs for reverse analysis
AGENT_URLS = {
    "technical": "http://01_technical_analyzer:8000",
    "fibonacci": "http://03_fibonacci_agent:8000",
    "gann": "http://05_gann_analyzer_agent:8000",
    "news": "http://06_news_sentiment_agent:8000",
    "forecaster": "http://08_forecaster_agent:8000"
}

# Default parameters (fallback)
DEFAULT_PARAMS = {
    "default_leverage": 3,
    "size_pct": 0.15,
    "reverse_threshold": 2.0,
    "atr_multiplier_sl": 2.0,
    "atr_multiplier_tp": 3.0,
    "atr_sl_factor": 1.2,
    "trailing_atr_factor": 1.0,
    "breakeven_R": 1.0,
    "reverse_enabled": True,
    "max_daily_trades": 3,
}

DEFAULT_CONTROLS = {
    "disable_symbols": [],
    "disable_regimes": [],
    "max_trades_per_hour": 1,
    "cooldown_minutes": 45,
    "safe_mode": False,
    "max_trades_per_day": None,
    "size_cap": None,
}

EVOLVED_PARAMS_FILE = "/data/evolved_params.json"
API_COSTS_FILE = "/data/api_costs.json"
AI_DECISIONS_FILE = "/data/ai_decisions.json"
MASTER_STATE_FILE = "/data/master_state.json"


def log_api_call(tokens_in: int, tokens_out: int):
    """
    Logga una chiamata API per il tracking dei costi DeepSeek.
    
    Args:
        tokens_in: Token input della richiesta
        tokens_out: Token output della risposta
    """
    try:
        # Carica i dati esistenti
        if os.path.exists(API_COSTS_FILE):
            with open(API_COSTS_FILE, 'r') as f:
                data = json.load(f)
        else:
            data = {'calls': []}
        
        # Aggiungi la nuova chiamata
        data['calls'].append({
            'timestamp': datetime.now().isoformat(),
            'tokens_in': tokens_in,
            'tokens_out': tokens_out
        })
        
        # Salva i dati aggiornati
        os.makedirs(os.path.dirname(API_COSTS_FILE), exist_ok=True)
        with open(API_COSTS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"API call logged: {tokens_in} in, {tokens_out} out")
    except Exception as e:
        logger.error(f"Error logging API call: {e}")


def load_master_state() -> Dict[str, Any]:
    try:
        if os.path.exists(MASTER_STATE_FILE):
            with open(MASTER_STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {"symbol_cooldowns": {}, "decisions": []}


def save_master_state(state: Dict[str, Any]):
    try:
        os.makedirs(os.path.dirname(MASTER_STATE_FILE), exist_ok=True)
        with open(MASTER_STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.warning(f"⚠️ Failed to persist master state: {e}")


def save_ai_decision(decision_data):
    """Salva la decisione AI per visualizzarla nella dashboard"""
    try:
        decisions = []
        if os.path.exists(AI_DECISIONS_FILE):
            with open(AI_DECISIONS_FILE, 'r') as f:
                decisions = json.load(f)
        
        # Aggiungi nuova decisione
        decisions.append({
            'timestamp': datetime.now().isoformat(),
            'symbol': decision_data.get('symbol'),
            'action': decision_data.get('action'),  # OPEN_LONG, OPEN_SHORT, HOLD, CLOSE
            'leverage': decision_data.get('leverage', 1),
            'size_pct': decision_data.get('size_pct', 0),
            'rationale': decision_data.get('rationale', ''),
            'analysis_summary': decision_data.get('analysis_summary', '')
        })
        
        # Mantieni solo le ultime 100 decisioni
        decisions = decisions[-100:]
        
        os.makedirs(os.path.dirname(AI_DECISIONS_FILE), exist_ok=True)
        with open(AI_DECISIONS_FILE, 'w') as f:
            json.dump(decisions, f, indent=2)

        logger.info(f"AI decision saved: {decision_data.get('action')} on {decision_data.get('symbol')}")

        # Persist lightweight state for gating
        state = load_master_state()
        state.setdefault('decisions', []).append({
            'timestamp': datetime.now().isoformat(),
            'symbol': decision_data.get('symbol'),
            'action': decision_data.get('action'),
        })
        state['decisions'] = state['decisions'][-500:]
        save_master_state(state)
    except Exception as e:
        logger.error(f"Error saving AI decision: {e}")


class Decision(BaseModel):
    symbol: str
    action: Literal["OPEN_LONG", "OPEN_SHORT", "HOLD", "CLOSE"]
    leverage: float = 1.0
    size_pct: float = 0.0
    rationale: str

    # Validator permissivi
    @field_validator("leverage")
    def clamp_lev(cls, v): return max(1.0, min(v, 3.0))

    @model_validator(mode="after")
    def normalize_size(cls, values):
        if values.action in ("HOLD", "CLOSE"):
            values.size_pct = 0.0
        else:
            values.size_pct = max(0.05, min(values.size_pct, 0.25))
        return values


def is_open_action(action: str) -> bool:
    return action in ("OPEN_LONG", "OPEN_SHORT")


class AnalysisPayload(BaseModel):
    global_data: Dict[str, Any]
    assets_data: Dict[str, Any]

class ReverseAnalysisRequest(BaseModel):
    symbol: str
    current_position: Dict[str, Any]


def load_evolved_config() -> Dict[str, Any]:
    """Load evolved parameters/controls and confidence or use defaults"""
    try:
        if os.path.exists(EVOLVED_PARAMS_FILE):
            with open(EVOLVED_PARAMS_FILE, 'r') as f:
                data = json.load(f) or {}
                version = data.get('version', 'unknown')
                logger.info(f"📚 Using evolved params {version}")
                params = data.get("params", DEFAULT_PARAMS.copy())
                controls = DEFAULT_CONTROLS.copy()
                controls.update(data.get("controls", {}))
                confidence = float(data.get("agent_confidence", 0.0))
                reward = data.get("reward", {})
                return {
                    "params": params,
                    "controls": controls,
                    "agent_confidence": confidence,
                    "reward": reward,
                }
        else:
            logger.info("📚 No evolved params found, using defaults")
            return {
                "params": DEFAULT_PARAMS.copy(),
                "controls": DEFAULT_CONTROLS.copy(),
                "agent_confidence": 0.0,
                "reward": {},
            }
    except Exception as e:
        logger.warning(f"⚠️ Error loading evolved params: {e}")
        return {
            "params": DEFAULT_PARAMS.copy(),
            "controls": DEFAULT_CONTROLS.copy(),
            "agent_confidence": 0.0,
            "reward": {},
        }


SYSTEM_PROMPT = """
Sei un TRADER ALGORITMICO DISCIPLINATO e PRUDENTE.
Il tuo compito è analizzare e AGIRE solo quando i segnali sono chiari e concordi.

LINEE GUIDA CHIAVE:
- Se i segnali tecnici sono forti e coerenti con il trend -> apri la posizione (OPEN_LONG/OPEN_SHORT).
- Se i segnali sono deboli, misti o rumorosi -> scegli esplicitamente HOLD.
- Se esistono posizioni aperte valuta la coerenza prima di aprire nuove operazioni.
- Usa leva e size in base alla qualità del setup (non default fissi) e privilegia la conservazione del capitale.

FORMATO RISPOSTA JSON OBBLIGATORIO:
{
  "analysis_summary": "Breve sintesi del perché",
  "decisions": [
    {
      "symbol": "ETHUSDT",
      "action": "OPEN_LONG" | "OPEN_SHORT" | "HOLD" | "CLOSE",
      "leverage": 5.0,
      "size_pct": 0.15,
      "rationale": "trend chiaro con momentum favorevole"
    }
  ]
}
"""

@app.post("/decide_batch")
def decide_batch(payload: AnalysisPayload):
    try:
        # Load evolved parameters (hot-reload on each request)
        config = load_evolved_config()
        confidence = config.get('agent_confidence', 0.0)
        params = config.get('params', DEFAULT_PARAMS.copy()) if confidence >= 0.4 else DEFAULT_PARAMS.copy()
        controls = config.get('controls', DEFAULT_CONTROLS.copy()) if confidence >= 0.4 else DEFAULT_CONTROLS.copy()
        negative_performance = False
        if controls.get('safe_mode'):
            controls.setdefault('max_trades_per_day', 1)
            controls.setdefault('size_cap', 0.05)
        if negative_performance:
            controls['max_trades_per_hour'] = min(controls.get('max_trades_per_hour') or 1, 1)
            controls['cooldown_minutes'] = max(int(controls.get('cooldown_minutes') or 0), 60)
            controls['max_trades_per_day'] = min(controls.get('max_trades_per_day') or params.get('max_daily_trades', 3), 1)
        logger.info(f"🤝 Using controls: {controls} (confidence={confidence})")
        
        # Semplificazione dati per prompt
        assets_summary = {}
        for k, v in payload.assets_data.items():
            t = v.get('tech', {})
            scalp_setup = t.get('scalp_setup', {}) if isinstance(t, dict) else {}
            timeframes = scalp_setup.get('timeframes', {}) if isinstance(scalp_setup, dict) else {}
            tf_1m = timeframes.get('1m', {}) if isinstance(timeframes, dict) else {}
            regime = scalp_setup.get('regime', {}) if isinstance(scalp_setup, dict) else {}
            trend_scalp = scalp_setup.get('trend_scalp', {}) if isinstance(scalp_setup, dict) else {}
            reversal_scalp = scalp_setup.get('reversal_scalp', {}) if isinstance(scalp_setup, dict) else {}
            extreme_reversal_scalp = scalp_setup.get('extreme_reversal_scalp', {}) if isinstance(scalp_setup, dict) else {}
            assets_summary[k] = {
                "price": t.get('price'),
                "trend": t.get('trend'),
                "trend_1h": t.get('trend_1h'),
                "macd_hist": t.get('macd_hist'),
                "macd": t.get('macd'),
                "rsi": t.get('rsi'),
                "rsi_7": t.get('rsi_7'),
                "bb_upper": t.get('bb_upper'),
                "bb_middle": t.get('bb_middle'),
                "bb_lower": t.get('bb_lower'),
                "bb_width": t.get('bb_width'),
                "atr_pct": tf_1m.get('atr_pct'),
                "ema_dist": tf_1m.get('ema_dist'),
                "regime": regime.get('mode'),
                "trend_scalp": {
                    "long": trend_scalp.get('long'),
                    "short": trend_scalp.get('short'),
                },
                "reversal_scalp": {
                    "long": reversal_scalp.get('long'),
                    "short": reversal_scalp.get('short'),
                },
                "extreme_reversal_scalp": {
                    "long": extreme_reversal_scalp.get('long'),
                    "short": extreme_reversal_scalp.get('short'),
                },
            }
            
        prompt_data = {
            "wallet_equity": payload.global_data.get('portfolio', {}).get('equity'),
            "active_positions": payload.global_data.get('already_open', []),
            "market_data": assets_summary
        }

        if BB_ONLY_STRATEGY:
            decisions = []
            for symbol, view in assets_summary.items():
                price = view.get("price")
                bb_upper = view.get("bb_upper")
                bb_lower = view.get("bb_lower")
                bb_width = view.get("bb_width")
                action = "HOLD"
                if (
                    price is not None
                    and bb_upper is not None
                    and bb_lower is not None
                    and (bb_width is None or bb_width >= BB_MIN_WIDTH)
                ):
                    if price > bb_upper:
                        action = "OPEN_SHORT"
                    elif price < bb_lower:
                        action = "OPEN_LONG"
                decisions.append({
                    "symbol": symbol,
                    "action": action,
                    "leverage": params.get("default_leverage", DEFAULT_PARAMS["default_leverage"]),
                    "size_pct": params.get("size_pct", DEFAULT_PARAMS["size_pct"]),
                    "rationale": "BB-only strategy: entry on band break; exit at mid-band",
                })
            return {
                "analysis": "BB-only strategy active",
                "decisions": [Decision(**d).model_dump() for d in decisions],
            }
        
        # Enhanced system prompt with evolved parameters
        enhanced_system_prompt = SYSTEM_PROMPT + f"""

PARAMETRI OTTIMIZZATI (dall'evoluzione automatica):
- Leverage suggerito: {params.get('default_leverage', 5)}x
- Size per trade: {params.get('size_pct', 0.15)*100:.0f}% del wallet
- Soglia reverse: {params.get('reverse_threshold', 2.0)}%
- ATR SL factor: {params.get('atr_sl_factor', 1.2)} | trailing ATR: {params.get('trailing_atr_factor', 1.0)} | breakeven R: {params.get('breakeven_R', 1.0)}
- Reverse abilitato: {params.get('reverse_enabled', True)} | Max daily trades: {params.get('max_daily_trades', 3)}

CONTROLLI DI RISCHIO ATTIVI (da Learning Agent):
- Disable symbols: {controls.get('disable_symbols')}
- Disable regimes: {controls.get('disable_regimes')}
- Safe mode: {controls.get('safe_mode')} | size cap: {controls.get('size_cap')}
Confidence del modello: {confidence}

USA QUESTI PARAMETRI EVOLUTI nelle tue decisioni.
"""

        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": enhanced_system_prompt},
                {"role": "user", "content": f"ANALIZZA E AGISCI: {json.dumps(prompt_data)}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        
        # Logga i costi API per tracking DeepSeek
        if hasattr(response, 'usage') and response.usage:
            log_api_call(
                tokens_in=response.usage.prompt_tokens,
                tokens_out=response.usage.completion_tokens
            )

        content = response.choices[0].message.content
        logger.info(f"AI Raw Response: {content}") # Debug nel log
        
        decision_json = json.loads(content)

        valid_decisions = []
        for d in decision_json.get("decisions", []):
            symbol_key = (d.get('symbol') or '').upper()
            rationale_suffix = []

            # Disable lists
            if symbol_key in [s.upper() for s in controls.get('disable_symbols', [])]:
                d['action'] = 'HOLD'
                rationale_suffix.append('blocked by disable_symbols')

            regime = assets_summary.get(symbol_key, {}).get('trend') if assets_summary else None
            if regime and regime.lower() in [str(r).lower() for r in controls.get('disable_regimes', [])]:
                d['action'] = 'HOLD'
                rationale_suffix.append('blocked by regime filter')

            # Bollinger guards (anti-fomo and compression filter)
            if is_open_action(d.get('action', '')):
                asset_view = assets_summary.get(symbol_key, {})
                price = asset_view.get("price")
                bb_upper = asset_view.get("bb_upper")
                bb_lower = asset_view.get("bb_lower")
                bb_width = asset_view.get("bb_width")
                if bb_width is not None and bb_width < BB_MIN_WIDTH:
                    d['action'] = 'HOLD'
                    rationale_suffix.append('bb_width too low')
                if price is not None and bb_upper is not None and d.get('action') == "OPEN_LONG":
                    if price > (bb_upper * (1 + BB_BREACH_PCT)):
                        d['action'] = 'HOLD'
                        rationale_suffix.append('price above bb_upper')
                if price is not None and bb_lower is not None and d.get('action') == "OPEN_SHORT":
                    if price < (bb_lower * (1 - BB_BREACH_PCT)):
                        d['action'] = 'HOLD'
                        rationale_suffix.append('price below bb_lower')

            # Higher timeframe alignment (15m + 1h trend)
            if TREND_ALIGNMENT_REQUIRED and is_open_action(d.get('action', '')):
                asset_view = assets_summary.get(symbol_key, {})
                trend_15m = (asset_view.get("trend") or "").upper()
                trend_1h = (asset_view.get("trend_1h") or "").upper()
                if trend_15m and trend_1h:
                    if d.get('action') == "OPEN_LONG" and not (trend_15m == "BULLISH" and trend_1h == "BULLISH"):
                        d['action'] = 'HOLD'
                        rationale_suffix.append('trend 15m/1h not aligned')
                    if d.get('action') == "OPEN_SHORT" and not (trend_15m == "BEARISH" and trend_1h == "BEARISH"):
                        d['action'] = 'HOLD'
                        rationale_suffix.append('trend 15m/1h not aligned')

            # Safe mode sizing
            if controls.get('safe_mode') and is_open_action(d.get('action', '')):
                if controls.get('size_cap') is not None:
                    d['size_pct'] = min(d.get('size_pct', 0.0), controls['size_cap'])
                d['leverage'] = min(d.get('leverage', 1.0), 3.0)
                rationale_suffix.append('safe_mode')
            elif controls.get('size_cap') is not None and is_open_action(d.get('action', '')):
                d['size_pct'] = min(d.get('size_pct', 0.0), controls['size_cap'])

            if rationale_suffix:
                d['rationale'] = f"{d.get('rationale','')} | {'; '.join(rationale_suffix)}".strip()

            try:
                valid_dec = Decision(**d)
                valid_decisions.append(valid_dec)

                # Salva la decisione per la dashboard
                save_ai_decision({
                    'symbol': valid_dec.symbol,
                    'action': valid_dec.action,
                    'leverage': valid_dec.leverage,
                    'size_pct': valid_dec.size_pct,
                    'rationale': valid_dec.rationale,
                    'analysis_summary': decision_json.get("analysis_summary", "")
                })
            except Exception as e:
                logger.warning(f"Invalid decision: {e}")

        return {
            "analysis": decision_json.get("analysis_summary", "No analysis"),
            "decisions": [d.model_dump() for d in valid_decisions]
        }

    except Exception as e:
        logger.error(f"AI Critical Error: {e}")
        return {"analysis": "Error", "decisions": []}


@app.post("/analyze_reverse")
async def analyze_reverse(payload: ReverseAnalysisRequest):
    """
    Analizza posizione in perdita e decide: HOLD, CLOSE o REVERSE
    Raccoglie dati da tutti gli agenti per decisione informata
    """
    try:
        symbol = payload.symbol
        position = payload.current_position
        
        logger.info(f"🔍 Analyzing reverse for {symbol}: ROI={position.get('roi_pct', 0)*100:.2f}%")
        
        # Raccolta dati da tutti gli agenti
        agents_data = {}
        
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            # Technical Analysis
            try:
                resp = await http_client.post(
                    f"{AGENT_URLS['technical']}/analyze_multi_tf",
                    json={"symbol": symbol}
                )
                if resp.status_code == 200:
                    agents_data['technical'] = resp.json()
                    logger.info(f"✅ Technical data received for {symbol}")
            except Exception as e:
                logger.warning(f"⚠️ Technical analyzer failed: {e}")
                agents_data['technical'] = {}
            
            # Fibonacci Analysis
            try:
                resp = await http_client.post(
                    f"{AGENT_URLS['fibonacci']}/analyze_fib",
                    json={"symbol": symbol}
                )
                if resp.status_code == 200:
                    agents_data['fibonacci'] = resp.json()
                    logger.info(f"✅ Fibonacci data received for {symbol}")
            except Exception as e:
                logger.warning(f"⚠️ Fibonacci analyzer failed: {e}")
                agents_data['fibonacci'] = {}
            
            # Gann Analysis
            try:
                resp = await http_client.post(
                    f"{AGENT_URLS['gann']}/analyze_gann",
                    json={"symbol": symbol}
                )
                if resp.status_code == 200:
                    agents_data['gann'] = resp.json()
                    logger.info(f"✅ Gann data received for {symbol}")
            except Exception as e:
                logger.warning(f"⚠️ Gann analyzer failed: {e}")
                agents_data['gann'] = {}
            
            # News Sentiment
            try:
                resp = await http_client.post(
                    f"{AGENT_URLS['news']}/analyze_sentiment",
                    json={"symbol": symbol}
                )
                if resp.status_code == 200:
                    agents_data['news'] = resp.json()
                    logger.info(f"✅ News sentiment received for {symbol}")
            except Exception as e:
                logger.warning(f"⚠️ News analyzer failed: {e}")
                agents_data['news'] = {}
            
            # Forecaster
            try:
                resp = await http_client.post(
                    f"{AGENT_URLS['forecaster']}/forecast",
                    json={"symbol": symbol}
                )
                if resp.status_code == 200:
                    agents_data['forecaster'] = resp.json()
                    logger.info(f"✅ Forecast data received for {symbol}")
            except Exception as e:
                logger.warning(f"⚠️ Forecaster failed: {e}")
                agents_data['forecaster'] = {}
        
        # Calcola recovery size usando la formula specificata
        pnl_dollars = position.get('pnl_dollars', 0)
        wallet_balance = position.get('wallet_balance', 0)
        
        # Se non abbiamo wallet_balance, usa una stima conservativa
        if wallet_balance == 0:
            wallet_balance = abs(pnl_dollars) * 3
        
        base_size_pct = 0.15
        loss_amount = abs(pnl_dollars)
        recovery_extra = (loss_amount / max(wallet_balance, 100)) / 0.02
        recovery_size_pct = min(base_size_pct + recovery_extra, 0.25)
        
        # Prepara prompt per DeepSeek
        prompt_data = {
            "symbol": symbol,
            "current_position": {
                "side": position.get('side'),
                "entry_price": position.get('entry_price'),
                "mark_price": position.get('mark_price'),
                "roi_pct": position.get('roi_pct', 0) * 100,  # Converti in percentuale
                "pnl_dollars": pnl_dollars,
                "leverage": position.get('leverage', 1)
            },
            "technical_analysis": agents_data.get('technical', {}),
            "fibonacci_analysis": agents_data.get('fibonacci', {}),
            "gann_analysis": agents_data.get('gann', {}),
            "news_sentiment": agents_data.get('news', {}),
            "forecast": agents_data.get('forecaster', {})
        }
        
        system_prompt = """Sei un TRADER ESPERTO che analizza posizioni in perdita.

DECISIONI POSSIBILI:
1. HOLD = È solo una correzione temporanea, il trend principale rimane valido. Mantieni la posizione.
2. CLOSE = Il trend è incerto, meglio chiudere e aspettare chiarezza. Non aprire nuove posizioni.
3. REVERSE = CHIARA INVERSIONE DI TREND confermata da MULTIPLI INDICATORI. Chiudi e apri posizione opposta.

CRITERI PER REVERSE (TUTTI devono essere soddisfatti):
- Almeno 3 indicatori tecnici confermano inversione
- RSI mostra chiaro over/undersold nella direzione opposta
- Fibonacci/Gann mostrano supporto/resistenza forte
- News/sentiment supportano la nuova direzione
- Forecast prevede movimento nella direzione opposta

CRITERI PER CLOSE:
- Indicatori contrastanti, no chiara direzione
- Alta volatilità o incertezza di mercato
- News negative o sentiment molto negativo

CRITERI PER HOLD:
- Trend principale ancora valido
- Solo correzione temporanea
- Supporti/resistenze tengono
- Indicatori mostrano possibile rimbalzo

FORMATO RISPOSTA JSON OBBLIGATORIO:
{
  "action": "HOLD" | "CLOSE" | "REVERSE",
  "confidence": 85,
  "rationale": "Spiegazione dettagliata basata sugli indicatori",
  "recovery_size_pct": 0.18
}

Usa recovery_size_pct fornito nel contesto per recuperare le perdite."""
        
        user_prompt = f"""ANALIZZA QUESTA POSIZIONE IN PERDITA E DECIDI:

{json.dumps(prompt_data, indent=2)}

Recovery size calcolato: {recovery_size_pct:.2f} ({recovery_size_pct*100:.1f}%)

Analizza TUTTI gli indicatori e decidi: HOLD, CLOSE o REVERSE."""
        
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3  # Più conservativo per decisioni di risk management
        )
        
        # Log API costs
        if hasattr(response, 'usage') and response.usage:
            log_api_call(
                tokens_in=response.usage.prompt_tokens,
                tokens_out=response.usage.completion_tokens
            )
        
        content = response.choices[0].message.content
        logger.info(f"AI Reverse Analysis Response: {content}")
        
        decision = json.loads(content)
        
        # Valida e normalizza la risposta
        action = decision.get("action", "HOLD").upper()
        if action not in ["HOLD", "CLOSE", "REVERSE"]:
            action = "HOLD"
        
        confidence = max(0, min(100, decision.get("confidence", 50)))
        rationale = decision.get("rationale", "No rationale provided")
        
        # Usa recovery_size_pct dal decision se presente, altrimenti quello calcolato
        final_recovery_size = decision.get("recovery_size_pct", recovery_size_pct)
        final_recovery_size = max(0.05, min(0.25, final_recovery_size))
        
        result = {
            "action": action,
            "confidence": confidence,
            "rationale": rationale,
            "recovery_size_pct": final_recovery_size,
            "agents_data_summary": {
                "technical_available": bool(agents_data.get('technical')),
                "fibonacci_available": bool(agents_data.get('fibonacci')),
                "gann_available": bool(agents_data.get('gann')),
                "news_available": bool(agents_data.get('news')),
                "forecast_available": bool(agents_data.get('forecaster'))
            }
        }
        
        logger.info(f"✅ Reverse analysis complete for {symbol}: {action} (confidence: {confidence}%)")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Reverse analysis error: {e}")
        # Default safe response
        return {
            "action": "HOLD",
            "confidence": 0,
            "rationale": f"Error during analysis: {str(e)}. Defaulting to HOLD for safety.",
            "recovery_size_pct": 0.15,
            "agents_data_summary": {}
        }


@app.get("/health")
def health(): return {"status": "active"}
