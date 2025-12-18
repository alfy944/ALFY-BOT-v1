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
    "reverse_threshold": 1.2,
    "atr_multiplier_sl": 2.0,
    "atr_multiplier_tp": 3.0,
    "min_rsi_for_long": 40,
    "max_rsi_for_short": 50,
    "min_score_trade": 0.35,
    "trend_score_threshold": 0.35,
    "range_score_threshold": 0.55,
    "transition_score_threshold": 0.35,
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
MIN_SYMBOL_COOLDOWN_MINUTES = 15


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
    hold_quality: Optional[Literal["strong", "weak"]] = None
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
        if values.action == "HOLD" and values.hold_quality not in ("strong", "weak"):
            values.hold_quality = "strong"
        return values


def is_open_action(action: str) -> bool:
    return action in ("OPEN_LONG", "OPEN_SHORT")


def weighted_score(action: str, tech: dict) -> Optional[float]:
    """
    Calcola uno score pesato (trend 50%, momentum 30%, RSI 20%)
    per evitare medie secche che penalizzano trend chiari con momentum neutro.
    """
    try:
        trend_score = 0.5
        momentum_score = 0.5
        rsi_score = 0.5

        trend_15m = (tech.get("trend_15m") or tech.get("trend") or "").upper()
        trend_1h = (tech.get("trend_1h") or "").upper()
        action_is_long = action == "OPEN_LONG"

        if trend_15m and trend_1h:
            same = trend_15m == trend_1h
            if action_is_long and trend_15m == "BULLISH" and same:
                trend_score = 1.0
            elif (not action_is_long) and trend_15m == "BEARISH" and same:
                trend_score = 1.0
            elif (action_is_long and trend_15m == "BULLISH") or ((not action_is_long) and trend_15m == "BEARISH"):
                trend_score = 0.7
            else:
                trend_score = 0.4

        macd_hist = tech.get("macd_hist")
        atr_val = tech.get("atr") or 0
        if macd_hist is not None:
            # momentum è neutro salvo forte opposizione (>0.25*ATR)
            if action_is_long:
                if macd_hist > 0:
                    momentum_score = 0.7
                elif macd_hist < -0.25 * atr_val:
                    momentum_score = 0.3
                else:
                    momentum_score = 0.5
            else:
                if macd_hist < 0:
                    momentum_score = 0.7
                elif macd_hist > 0.25 * atr_val:
                    momentum_score = 0.3
                else:
                    momentum_score = 0.5

        rsi_val = tech.get("rsi") or tech.get("rsi_7")
        if rsi_val is not None:
            if action_is_long:
                if 45 <= rsi_val <= 60:
                    rsi_score = 1.0
                elif 40 <= rsi_val <= 70:
                    rsi_score = 0.7
                else:
                    rsi_score = 0.4
            else:
                if 55 <= rsi_val <= 70:
                    rsi_score = 1.0
                elif 50 <= rsi_val <= 75:
                    rsi_score = 0.7
                else:
                    rsi_score = 0.4

        return round(0.5 * trend_score + 0.3 * momentum_score + 0.2 * rsi_score, 4)
    except Exception:
        return None


def clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


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
            assets_summary[k] = {
                "price": t.get('price'),
                "rsi_7": t.get('details', {}).get('rsi_7') or t.get('rsi_7'),
                "trend": t.get('trend'),
                "trend_15m": t.get('trend_15m') or t.get('trend'),
                "trend_1h": t.get('trend_1h'),
                "regime": t.get('regime'),
                "macd": t.get('macd'),
                "macd_hist": t.get('macd_hist'),
                "ema_20": (t.get('details') or {}).get('ema_20'),
                "atr": (t.get('details') or {}).get('atr'),
                "breakout": t.get('breakout') or {},
                "volume_ratio": (t.get('details') or {}).get('volume_ratio'),
                "volume_avg_20": (t.get('details') or {}).get('volume_avg_20'),
                "rsi": t.get('rsi'),
                "structure_break": t.get('structure_break') or {},
                "high_20": t.get('high_20'),
                "low_20": t.get('low_20'),
                "last_high_15m": t.get("last_high_15m"),
                "last_low_15m": t.get("last_low_15m"),
                "macd_hist_prev": t.get("macd_hist_prev"),
                "macd_hist_prev2": t.get("macd_hist_prev2"),
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
- Soglia reverse: {params.get('reverse_threshold', 1.2)}%
- Min RSI per long: {params.get('min_rsi_for_long', 40)}
    - Max RSI per short: {params.get('max_rsi_for_short', 50)}
    - Score minimi: trend {params.get('trend_score_threshold', 0.35)} | range {params.get('range_score_threshold', 0.55)} | counter-trend {params.get('countertrend_score_threshold', 0.7)}
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
            computed_score = weighted_score(d.get('action', ''), tech) if is_open_action(d.get('action', '')) else None
            if computed_score is not None:
                score_val = computed_score
                d['score'] = computed_score
            trend_15m = (tech.get("trend_15m") or "").upper()
            trend_1h = (tech.get("trend_1h") or "").upper()
            price = tech.get("price")
            ema20 = tech.get("ema_20")
            atr_val = tech.get("atr")
            structure_break = tech.get("structure_break") or {}
            rsi_val = tech.get("rsi") or tech.get("rsi_7") or 0
            rsi_extreme_long = rsi_val < 35
            rsi_extreme_short = rsi_val > 65

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
            price = tech.get("price")
            ema20 = tech.get("ema_20")
            atr_val = tech.get("atr")
            if (
                is_open_action(d.get('action', ''))
                and trend_15m
                and trend_1h
                and trend_15m != trend_1h
                and not rsi_extreme_long
                and not rsi_extreme_short
            ):
                d['action'] = 'HOLD'
                rationale_suffix.append('mtf_trend_mismatch')

            # Volume filter
            vol_ratio = tech.get("volume_ratio")
            if is_open_action(d.get('action', '')) and vol_ratio is not None and vol_ratio < 1.3:
                d['size_pct'] = d.get('size_pct', 0.1) * 0.7
                rationale_suffix.append('low_volume_soft')

            # MACD momentum filter (only strong positive blocks shorts)
            macd_hist = tech.get("macd_hist")
            macd_prev = tech.get("macd_hist_prev")
            macd_prev2 = tech.get("macd_hist_prev2")
            if (
                is_open_action(d.get('action', ''))
                and d.get('action') == "OPEN_SHORT"
                and macd_hist is not None
                and atr_val
                and macd_hist > atr_val * 0.25
            ):
                d['size_pct'] = d.get('size_pct', 0.1) * 0.7
                rationale_suffix.append('macd_positive_soft')
            # MACD veto only on strong opposite momentum
            if (
                is_open_action(d.get('action', ''))
                and d.get('action') == "OPEN_LONG"
                and macd_hist is not None
                and atr_val
                and macd_hist < -0.25 * atr_val
            ):
                d['size_pct'] = d.get('size_pct', 0.1) * 0.7
                rationale_suffix.append('macd_negative_soft')
            # Momentum improvement: allow negative MACD if improving or small magnitude
            macd_prev = tech.get("macd_hist_prev")
            if (
                is_open_action(d.get('action', ''))
                and macd_hist is not None
                and atr_val
            ):
                improving = macd_prev is not None and macd_hist > macd_prev
                small_mag = abs(macd_hist) < (0.25 * atr_val)
                if improving or small_mag:
                    rationale_suffix = [r for r in rationale_suffix if r != 'macd_positive_strong']

            # Breakout requirement
            breakout = tech.get("breakout") or {}
            breakout_long = breakout.get("long")
            breakout_short = breakout.get("short")
            high_20 = tech.get("high_20")
            low_20 = tech.get("low_20")
            if is_open_action(d.get('action', '')):
                if d.get('action') == "OPEN_LONG" and breakout_long is not None and not breakout_long:
                    d['action'] = 'HOLD'
                    rationale_suffix.append('no_breakout_long')
                if d.get('action') == "OPEN_SHORT" and breakout_short is not None and not breakout_short:
                    d['action'] = 'HOLD'
                    rationale_suffix.append('no_breakout_short')

            # Transition regime gating
            regime_val = (tech.get("regime") or "").lower()
            if score_val is not None and regime_val == "range":
                score_val *= 0.8
                d['score'] = score_val
                if is_open_action(d.get('action', '')):
                    d['size_pct'] = d.get('size_pct', 0.1) * 0.7
            if (
                is_open_action(d.get('action', ''))
                and regime_val == "transition"
            ):
                allow_transition = False
                if (
                    trend_15m == "BULLISH"
                    and trend_1h == "BULLISH"
                    and breakout_long
                    and vol_ratio is not None
                    and vol_ratio >= 1.3
                    and high_20 is not None
                    and price is not None
                    and price > high_20
                    and (score_val or 0) >= params.get("transition_score_threshold", 0.35)
                ):
                    allow_transition = True
                if (
                    trend_15m == "BEARISH"
                    and trend_1h == "BEARISH"
                    and breakout_short
                    and vol_ratio is not None
                    and vol_ratio >= 1.3
                    and low_20 is not None
                    and price is not None
                    and price < low_20
                    and (score_val or 0) >= params.get("transition_score_threshold", 0.35)
                ):
                    allow_transition = True

                if not (
                    allow_transition
                    or (
                        (score_val or 0) >= params.get("transition_score_threshold", 0.35)
                        and vol_ratio is not None
                        and vol_ratio >= 1.3
                        and (
                            (d.get('action') == "OPEN_LONG" and breakout_long)
                            or (d.get('action') == "OPEN_SHORT" and breakout_short)
                        )
                    )
                ):
                    d['action'] = 'HOLD'
                    rationale_suffix.append('transition_guard')
                else:
                    if is_open_action(d.get('action', '')):
                        d['size_pct'] = min(d.get('size_pct', 0.0), 0.5)
                        rationale_suffix.append('transition_risk')

            # RSI windows (more permissive dead-zone handling)
            rsi_val = tech.get("rsi") or tech.get("rsi_7") or 0
            if (
                is_open_action(d.get('action', ''))
                and d.get('action') == "OPEN_SHORT"
                and (trend_1h == "BEARISH" or trend_15m == "BEARISH")
                and rsi_val < params.get("max_rsi_for_short", 50)
            ):
                rationale_suffix.append('rsi_soft_short')

            # Distance from EMA20 (adaptive R/R filter) — only for counter-trend entries
            if is_open_action(d.get('action', '')) and price and ema20 and atr_val:
                main_trend = trend_1h or trend_15m
                counter_trend = (
                    (d.get('action') == "OPEN_LONG" and main_trend == "BEARISH")
                    or (d.get('action') == "OPEN_SHORT" and main_trend == "BULLISH")
                )
                if counter_trend:
                    dist_atr = abs(price - ema20) / atr_val if atr_val else 999
                    vol_ratio = tech.get("volume_ratio")
                    vol_boost = clamp(((vol_ratio - 1.0) / 2.0), 0, 1) if vol_ratio is not None else 0
                    rejection_long = bool((tech.get("structure_break") or {}).get("long") or breakout_long)
                    rejection_short = bool((tech.get("structure_break") or {}).get("short") or breakout_short)
                    rejection = rejection_long if d.get('action') == "OPEN_LONG" else rejection_short
                    trend_align = 1 if ((d.get('action') == "OPEN_LONG" and trend_15m == "BULLISH" and trend_1h == "BULLISH") or (d.get('action') == "OPEN_SHORT" and trend_15m == "BEARISH" and trend_1h == "BEARISH")) else 0
                    quality = 0.5 * (1 if rejection else 0) + 0.3 * vol_boost + 0.2 * trend_align
                    min_dist_required = clamp(1.5 - 0.2 * quality, 1.3, 1.5)
                    if dist_atr < min_dist_required:
                        d['action'] = 'HOLD'
                        rationale_suffix.append(f'distance_filter<{min_dist_required:.2f}ATR')

            # Pullback filter (long only)
            if is_open_action(d.get('action', '')) and d.get('action') == "OPEN_LONG" and price and ema20 and atr_val:
                near_ema = abs(price - ema20) <= atr_val
                rsi_val = tech.get("rsi") or tech.get("rsi_7") or 0
                if not (trend_15m == "BULLISH" and near_ema and rsi_val > 38):
                    rationale_suffix.append('pullback_filter_fail')
                    d['action'] = 'HOLD'

            # Trend pullback short (allows neutral momentum)
            trend_pullback_short = False
            if (
                is_open_action(d.get('action', ''))
                and d.get('action') == "OPEN_SHORT"
                and regime_val == "trend_bear"
                and trend_1h == "BEARISH"
                and trend_15m == "BEARISH"
                and price
                and ema20
                and price < ema20  # sotto EMA20/50 area
                and 35 <= (tech.get("rsi") or tech.get("rsi_7") or 0) <= 55
                and ((tech.get("structure_break") or {}).get("short") or (last_low_15m and price < last_low_15m))
                and (score_val or 0) >= params.get("trend_score_threshold", 0.56)
            ):
                trend_pullback_short = True
                d['path'] = "bear_pullback_short"
                d['leverage'] = min(d.get('leverage', params.get("default_leverage", 5)), 5)
                d['size_pct'] = d.get('size_pct', 0.15)

            # Bear continuation short (RSI 25–45, tighter risk)
            bear_continuation_short = False
            if (
                is_open_action(d.get('action', ''))
                and d.get('action') == "OPEN_SHORT"
                and regime_val == "trend_bear"
                and trend_1h == "BEARISH"
                and trend_15m == "BEARISH"
                and price
                and ema20
                and price < ema20
                and 25 <= (tech.get("rsi") or tech.get("rsi_7") or 0) <= 45
                and (
                    (last_low_15m and price < (last_low_15m - (0.10 * atr_val if atr_val else 0)))
                    or (low_20 is not None and price < low_20)
                )
                and ((vol_ratio is not None and vol_ratio >= 1.2) or breakout_short)
                and (score_val or 0) >= params.get("trend_score_threshold", 0.35)
            ):
                bear_continuation_short = True
                d['path'] = "bear_continuation_short"
                d['leverage'] = min(d.get('leverage', 3), 3)
                d['size_pct'] = min(d.get('size_pct', 0.15) * 0.7, 0.15)

            # Counter-trend long in bear (small size)
            counter_trend_long = False
            if (
                is_open_action(d.get('action', ''))
                and d.get('action') == "OPEN_LONG"
                and regime_val == "trend_bear"
                and (tech.get("rsi") or tech.get("rsi_7") or 0) < 30
                and price
                and ema20
                and atr_val
                and abs(price - ema20) >= 1.8 * atr_val
                and (
                    (macd_prev is not None and macd_prev2 is not None and macd_hist is not None and macd_hist > macd_prev > macd_prev2)
                    or (last_high_15m and price > (last_high_15m + 0.10 * atr_val))
                )
                and vol_ratio is not None
                and vol_ratio >= 1.5
                and (score_val or 0) >= params.get("countertrend_score_threshold", 0.7)
            ):
                counter_trend_long = True
                d['path'] = "counter_trend_long"
                d['leverage'] = min(max(d.get('leverage', 2), 2), 3)
                d['size_pct'] = min(max(d.get('size_pct', 0.08), 0.05), 0.10)

            macd_improving = macd_prev is not None and macd_hist is not None and macd_prev2 is not None and ((d.get('action') == "OPEN_LONG" and macd_hist > macd_prev > macd_prev2) or (d.get('action') == "OPEN_SHORT" and macd_hist < macd_prev < macd_prev2))
            macd_small = macd_hist is not None and atr_val and abs(macd_hist) < 0.25 * atr_val
            if macd_hist is not None:
                if d.get('action') == "OPEN_LONG":
                    score_val = (score_val or 0) + (0.1 if macd_hist > 0 else -0.1)
                elif d.get('action') == "OPEN_SHORT":
                    score_val = (score_val or 0) + (0.1 if macd_hist < 0 else -0.1)
            if is_open_action(d.get('action', '')):
                if d.get('action') == "OPEN_LONG":
                    if rsi_extreme_long:
                        score_val = (score_val or 0) + 0.1
                    elif rsi_val >= 55:
                        score_val = (score_val or 0) - 0.1
                elif d.get('action') == "OPEN_SHORT":
                    if rsi_extreme_short:
                        score_val = (score_val or 0) + 0.1
                    elif rsi_val <= 45:
                        score_val = (score_val or 0) - 0.1
            d['score'] = score_val

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
            if breakout_long and breakout_long is True and d.get('action') == "OPEN_LONG":
                conditions_true += 1
            if breakout_short and breakout_short is True and d.get('action') == "OPEN_SHORT":
                conditions_true += 1
            if vol_ratio is not None and vol_ratio >= 1.3:
                conditions_true += 1
            if price and ema20 and atr_val and abs(price - ema20) <= atr_val:
                conditions_true += 1
            if trend_pullback_short:
                conditions_true = max(conditions_true, 3)

            if is_open_action(d.get('action', '')):
                if (score_val or 0) < params.get("min_score_trade", 0.35):
                    d['action'] = 'HOLD'
                    rationale_suffix.append('score_below_min')
                else:
                    path_score_ok = False
                    if counter_trend and (score_val or 0) >= params.get("countertrend_score_threshold", 0.7):
                        path_score_ok = True
                    elif regime_val == "transition" and (score_val or 0) >= params.get("transition_score_threshold", 0.35):
                        path_score_ok = True
                    elif rsi_extreme_long and d.get('action') == "OPEN_LONG":
                        path_score_ok = True
                    elif rsi_extreme_short and d.get('action') == "OPEN_SHORT":
                        path_score_ok = True
                    elif not counter_trend and (score_val or 0) >= params.get("trend_score_threshold", 0.35):
                        path_score_ok = True

                    if not path_score_ok or conditions_true < 1:
                        d['action'] = 'HOLD'
                        rationale_suffix.append('quality_score_low')

            # Hold quality flag
            if d.get('action') == 'HOLD':
                if conditions_true >= 2 or (vol_ratio is not None and vol_ratio >= 1.2):
                    d['hold_quality'] = "weak"
                else:
                    d['hold_quality'] = "strong"
            else:
                d['hold_quality'] = None

            # Entry triggers (need at least one)
            if is_open_action(d.get('action', '')) and d['action'] != 'HOLD':
                trigger_price = False
                trigger_momentum = False
                trigger_time = False  # placeholder
                last_high_15m = tech.get("last_high_15m")
                last_low_15m = tech.get("last_low_15m")
                if last_high_15m and price and d.get('action') == "OPEN_LONG" and price > last_high_15m:
                    trigger_price = True
                if last_low_15m and price and d.get('action') == "OPEN_SHORT" and price < last_low_15m:
                    trigger_price = True
                if macd_improving or macd_small:
                    trigger_momentum = True
                if not (trigger_price or trigger_momentum or trigger_time):
                    d['action'] = 'HOLD'
                    rationale_suffix.append('no_entry_trigger')

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
