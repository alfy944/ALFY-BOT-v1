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
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "default_leverage": 5,
    "size_pct": 0.15,
    "reverse_threshold": 2.0,
    "atr_multiplier_sl": 2.0,
    "atr_multiplier_tp": 3.0,
    "min_rsi_for_long": 40,
    "max_rsi_for_short": 60,
    "min_score_trade": 0.6,
    "trend_score_threshold": 0.6,
    "range_score_threshold": 0.55,
    "countertrend_score_threshold": 0.7,
    "atr_sl_factor": 1.2,
    "trailing_atr_factor": 1.0,
    "breakeven_R": 1.0,
    "reverse_enabled": False,
    "max_daily_trades": 3,
    "max_open_positions": 3,
}

DEFAULT_CONTROLS = {
    "disable_symbols": [],
    "disable_regimes": [],
    "max_trades_per_hour": 0,
    "cooldown_minutes": 0,
    "safe_mode": False,
    "max_trades_per_day": None,
    "size_cap": None,
    "max_open_positions": None,
}

EVOLVED_PARAMS_FILE = "/data/evolved_params.json"
API_COSTS_FILE = "/data/api_costs.json"
AI_DECISIONS_FILE = "/data/ai_decisions.json"
MASTER_STATE_FILE = "/data/master_state.json"
MIN_SYMBOL_COOLDOWN_MINUTES = 45


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
    score: Optional[float] = None
    rationale: str

    # Validator permissivi
    @field_validator("leverage")
    def clamp_lev(cls, v): return max(1.0, min(v, 10.0))

    @model_validator(mode="after")
    def normalize_size(cls, values):
        if values.action in ("HOLD", "CLOSE"):
            values.size_pct = 0.0
        else:
            values.size_pct = max(0.05, min(values.size_pct, 0.25))
        return values


def is_open_action(action: str) -> bool:
    return action in ("OPEN_LONG", "OPEN_SHORT")


def count_recent_actions(decisions: list, minutes: int, action_filter=None) -> int:
    cutoff = datetime.utcnow().timestamp() - minutes * 60
    count = 0
    for d in decisions:
        ts = d.get('timestamp')
        try:
            ts_val = datetime.fromisoformat(ts).timestamp()
        except Exception:
            continue
        if ts_val < cutoff:
            continue
        if action_filter and d.get('action') not in action_filter:
            continue
        count += 1
    return count

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
Sei un TRADER ALGORITMICO AGGRESSIVO ma DISCIPLINATO.
Il tuo compito è analizzare e poi AGIRE solo se i segnali sono solidi.

LINEE GUIDA CHIAVE:
- Se i segnali tecnici sono chiari e coerenti con il trend -> apri la posizione (OPEN_LONG/OPEN_SHORT).
- Se i segnali sono deboli o misti -> scegli esplicitamente HOLD.
- Se esistono posizioni aperte valuta la coerenza prima di aprire nuove operazioni.
- Non superare mai 3 posizioni aperte contemporaneamente: se ci sono già 3 trade aperti, apri solo se prima chiudi qualcosa o resta in HOLD.
- Usa leva e size in base alla qualità del setup (non default fissi).
- Usa RSI come conferma del setup, non come vincolo assoluto: in trend guarda i pullback (long 40–55, short 45–60), in range usa valori estremi (long <35, short >65).
- Regole per regime: trend = trend-following; range = mean reversion con RSI + supporti/resistenze; transition = mercato che parte → trade ammessi con size ridotta (≈50% della size normale), NON hold automatico.
- Aggiungi counter-trend scalp in trend bearish: RSI <25, prezzo distante ≥1.5 ATR da EMA20, prima candela di rifiuto, size 25–30%, TP corto, vietato pyramiding.
- Score minimi per tipo: trend ≥0.60, range ≥0.55, counter-trend ≥0.70 (size ridotta) — non usare soglia unica.
- Logica LONG e SHORT separate: short in trend può partire con RSI 50–55, long in trend può partire con RSI 45–50. Non attendere sempre 30/70.
- Pesa i segnali con priorità esplicite: trend TF alto = driver (50%, priorità alta), momentum/MACD = conferma (30%, non veto), RSI = timing (20%). Se trend domina consenti il trade; se momentum domina riduci size ma non bloccare; HOLD solo con segnali tutti contrari.
- Ogni HOLD deve spiegare rejected_by = (RSI | regime | score | momentum | risk_control) nel rationale per rendere l’azione chiara.
- Gestione SL/TP per evitare chiusure premature: stop basato su ATR (usa atr_sl_factor rispetto all’ATR e oltre l’ultimo swing, non sotto il rumore), TP minimo 2R–3R coerente con atr_multiplier_tp; quando il prezzo raggiunge almeno 1R (breakeven_R) porta lo SL a breakeven e poi trail con trailing_atr_factor. Non chiudere anticipatamente senza un motivo contrario forte.
- No scalping: entra solo se il potenziale movimento offre spazio (≥1–1.5 ATR fino al primo target) e R/R atteso ≥2 al netto delle commissioni; evita TP ravvicinati o trade che coprono a malapena le fee. Non stringere gli stop in anticipo: porta a breakeven solo dopo 1R pieno, attiva il trailing oltre ~1.2–1.5R, e mantieni la posizione finché non scatta SL/TP o emergono segnali contrari forti.

FORMATO RISPOSTA JSON OBBLIGATORIO:
{
  "analysis_summary": "Breve sintesi del perché",
  "decisions": [
    {
      "symbol": "ETHUSDT",
      "action": "OPEN_LONG" | "OPEN_SHORT" | "HOLD" | "CLOSE",
      "leverage": 5.0,
      "size_pct": 0.15,
      "score": 0.82,
      "rationale": "RSI basso su supporto"
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

        if controls.get('safe_mode'):
            controls.setdefault('max_trades_per_day', 1)
            controls.setdefault('size_cap', 0.05)
        logger.info(f"🤝 Using controls: {controls} (confidence={confidence})")
        
        # Semplificazione dati per prompt
        active_positions = payload.global_data.get('already_open', []) or []
        assets_summary = {}
        for k, v in payload.assets_data.items():
            t = v.get('tech', {})
            if k.upper() != "BTC" and t.get("regime") == "range":
                logger.info(f"⏳ Skip {k} per regime range")
                continue
            assets_summary[k] = {
                "price": t.get('price'),
                "rsi_7": t.get('details', {}).get('rsi_7') or t.get('rsi_7'),
                "trend": t.get('trend'),
                "trend_15m": t.get('trend_15m') or t.get('trend'),
                "trend_1h": t.get('trend_1h'),
                "regime": t.get('regime'),
                "macd_hist": t.get('macd_hist'),
                "macd": t.get('macd'),
                "ema_20": (t.get('details') or {}).get('ema_20'),
                "atr": (t.get('details') or {}).get('atr'),
                "breakout": t.get('breakout') or {},
                "volume_ratio": (t.get('details') or {}).get('volume_ratio'),
                "volume_avg_20": (t.get('details') or {}).get('volume_avg_20'),
                "rsi": t.get('rsi'),
            }
            
        prompt_data = {
            "wallet_equity": payload.global_data.get('portfolio', {}).get('equity'),
            "active_positions": active_positions,
            "market_data": assets_summary
        }
        
        # Enhanced system prompt with evolved parameters
        enhanced_system_prompt = SYSTEM_PROMPT + f"""

PARAMETRI OTTIMIZZATI (dall'evoluzione automatica):
- RSI Overbought (per short): {params.get('rsi_overbought', 70)}
- RSI Oversold (per long): {params.get('rsi_oversold', 30)}
- Leverage suggerito: {params.get('default_leverage', 5)}x
- Size per trade: {params.get('size_pct', 0.15)*100:.0f}% del wallet
- Soglia reverse: {params.get('reverse_threshold', 2.0)}%
- Min RSI per long: {params.get('min_rsi_for_long', 40)}
- Max RSI per short: {params.get('max_rsi_for_short', 60)}
- Score minimi: trend {params.get('trend_score_threshold', 0.6)} | range {params.get('range_score_threshold', 0.55)} | counter-trend {params.get('countertrend_score_threshold', 0.7)}
- ATR SL factor: {params.get('atr_sl_factor', 1.2)} | trailing ATR: {params.get('trailing_atr_factor', 1.0)} | breakeven R: {params.get('breakeven_R', 1.0)}
- Reverse abilitato: {params.get('reverse_enabled', True)} | Max daily trades: {params.get('max_daily_trades', 3)} | Max posizioni aperte: {params.get('max_open_positions', 3)}

CONTROLLI DI RISCHIO ATTIVI (da Learning Agent):
- Disable symbols: {controls.get('disable_symbols')}
- Disable regimes: {controls.get('disable_regimes')}
- Max trades/hour: {controls.get('max_trades_per_hour')} | cooldown minutes: {controls.get('cooldown_minutes')}
- Safe mode: {controls.get('safe_mode')} | max trades/day: {controls.get('max_trades_per_day')} | size cap: {controls.get('size_cap')}
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
            temperature=0.7, # Più creatività = più trade
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

        state = load_master_state()
        open_hour_count = count_recent_actions(state.get('decisions', []), 60, action_filter=["OPEN_LONG", "OPEN_SHORT"])
        open_day_count = count_recent_actions(state.get('decisions', []), 24 * 60, action_filter=["OPEN_LONG", "OPEN_SHORT"])
        symbol_cooldowns = state.get('symbol_cooldowns', {}) or {}
        now_ts = datetime.utcnow().timestamp()
        max_open_positions = controls.get('max_open_positions') if controls.get('max_open_positions') is not None else params.get('max_open_positions', 3)
        open_positions_count = len(active_positions)

        valid_decisions = []
        for d in decision_json.get("decisions", []):
            symbol_key = (d.get('symbol') or '').upper()
            rationale_suffix = []
            score_val = d.get("score")
            tech = assets_summary.get(symbol_key, {})

            # Dynamic sizing by score
            if is_open_action(d.get('action', '')) and score_val is not None:
                try:
                    s = float(score_val)
                    if s < 0.70:
                        d['size_pct'] = 0.05
                    elif s < 0.80:
                        d['size_pct'] = 0.10
                    else:
                        d['size_pct'] = 0.15
                    d['score'] = s
                except Exception:
                    pass

            # Multi-timeframe confirmation (15m vs 1h)
            trend_15m = (tech.get("trend_15m") or "").upper()
            trend_1h = (tech.get("trend_1h") or "").upper()
            if is_open_action(d.get('action', '')) and trend_15m and trend_1h and trend_15m != trend_1h:
                d['action'] = 'HOLD'
                rationale_suffix.append('mtf_trend_mismatch')

            # Volume filter
            vol_ratio = tech.get("volume_ratio")
            if is_open_action(d.get('action', '')) and vol_ratio is not None and vol_ratio < 1.3:
                d['action'] = 'HOLD'
                rationale_suffix.append('low_volume')

            # Breakout requirement
            breakout = tech.get("breakout") or {}
            if is_open_action(d.get('action', '')):
                if d.get('action') == "OPEN_LONG" and not breakout.get("long", False):
                    d['action'] = 'HOLD'
                    rationale_suffix.append('no_breakout_long')
                if d.get('action') == "OPEN_SHORT" and not breakout.get("short", False):
                    d['action'] = 'HOLD'
                    rationale_suffix.append('no_breakout_short')

            # Distance from EMA20 (avoid late entries)
            price = tech.get("price")
            ema20 = tech.get("ema_20")
            atr_val = tech.get("atr")
            if is_open_action(d.get('action', '')) and price and ema20 and atr_val:
                if abs(price - ema20) > atr_val * 1.8:
                    d['action'] = 'HOLD'
                    rationale_suffix.append('late_move')

            # Pullback filter (long only)
            if is_open_action(d.get('action', '')) and d.get('action') == "OPEN_LONG" and price and ema20 and atr_val:
                near_ema = abs(price - ema20) <= atr_val
                rsi_val = tech.get("rsi") or tech.get("rsi_7") or 0
                if not (trend_15m == "BULLISH" and near_ema and rsi_val > 45):
                    rationale_suffix.append('pullback_filter_fail')
                    d['action'] = 'HOLD'

            # Altcoin depends on BTC context
            if is_open_action(d.get('action', '')) and symbol_key not in ("BTC", "BTCUSDT"):
                btc = assets_summary.get("BTCUSDT") or assets_summary.get("BTC") or {}
                btc_trend = (btc.get("trend") or "").upper()
                btc_rsi = float(btc.get("rsi") or 0)
                if btc_trend == "BEARISH" or btc_rsi <= 45:
                    d['action'] = 'HOLD'
                    rationale_suffix.append('btc_correlation_block')

            # Quality score: count strong conditions
            conditions_true = 0
            if trend_15m and trend_1h and trend_15m == trend_1h:
                conditions_true += 1
            if breakout.get("long") and d.get('action') == "OPEN_LONG":
                conditions_true += 1
            if breakout.get("short") and d.get('action') == "OPEN_SHORT":
                conditions_true += 1
            if vol_ratio is not None and vol_ratio >= 1.3:
                conditions_true += 1
            if price and ema20 and atr_val and abs(price - ema20) <= atr_val:
                conditions_true += 1
            if is_open_action(d.get('action', '')) and conditions_true < 3:
                d['action'] = 'HOLD'
                rationale_suffix.append('quality_score_low')

            # Disable lists
            if symbol_key in [s.upper() for s in controls.get('disable_symbols', [])]:
                d['action'] = 'HOLD'
                rationale_suffix.append('blocked by disable_symbols')

            regime = assets_summary.get(symbol_key, {}).get('regime') if assets_summary else None
            if regime and regime.lower() in [str(r).lower() for r in controls.get('disable_regimes', [])]:
                d['action'] = 'HOLD'
                rationale_suffix.append('blocked by regime filter')

            # Cooldown per symbol
            cd_minutes = max(controls.get('cooldown_minutes') or 0, MIN_SYMBOL_COOLDOWN_MINUTES)
            if cd_minutes > 0:
                last_ts = symbol_cooldowns.get(symbol_key, 0)
                if last_ts and (now_ts - last_ts) < cd_minutes * 60 and is_open_action(d.get('action', '')):
                    d['action'] = 'HOLD'
                    rationale_suffix.append('cooldown active')

            # Trade frequency limits
            if is_open_action(d.get('action', '')):
                limit_hour = controls.get('max_trades_per_hour') or 0
                limit_day = controls.get('max_trades_per_day') or params.get('max_daily_trades')

                if limit_hour and open_hour_count >= limit_hour:
                    d['action'] = 'HOLD'
                    rationale_suffix.append('max trades/hour reached')
                if limit_day and open_day_count >= limit_day:
                    d['action'] = 'HOLD'
                    rationale_suffix.append('max trades/day reached')
                if max_open_positions and open_positions_count >= max_open_positions:
                    d['action'] = 'HOLD'
                    rationale_suffix.append('max open positions reached')

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
                # Update counters if we will place an open trade
                if is_open_action(valid_dec.action):
                    open_hour_count += 1
                    open_day_count += 1
                    open_positions_count += 1
                    symbol_cooldowns[symbol_key] = now_ts

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

        # Persist updated cooldowns
        state['symbol_cooldowns'] = symbol_cooldowns
        save_master_state(state)

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
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Technical Analysis
            try:
                resp = await client.post(
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
                resp = await client.post(
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
                resp = await client.post(
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
                resp = await client.post(
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
                resp = await client.post(
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
