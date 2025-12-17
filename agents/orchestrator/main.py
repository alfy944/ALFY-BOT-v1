import asyncio, httpx, json, os
from datetime import datetime

URLS = {
    "tech": "http://01_technical_analyzer:8000",
    "pos": "http://07_position_manager:8000",
    "ai": "http://04_master_ai_agent:8000"
}
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# --- CONFIGURAZIONE OTTIMIZZAZIONE ---
MAX_POSITIONS = 3  # Numero massimo posizioni contemporanee
REVERSE_THRESHOLD = 2.0  # Percentuale perdita per trigger reverse analysis
CYCLE_INTERVAL = 60  # Secondi tra ogni ciclo di controllo (era 900)
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

AI_DECISIONS_FILE = "/data/ai_decisions.json"
BYBIT_TICKERS_URL = "https://api.bybit.com/v5/market/tickers"
USE_TRENDING = os.getenv("USE_TRENDING_SYMBOLS", "true").lower() == "true"
TRENDING_LIMIT = int(os.getenv("TRENDING_SYMBOLS_LIMIT", "10"))

def save_monitoring_decision(positions_count: int, max_positions: int, positions_details: list, reason: str):
    """Salva la decisione di monitoraggio per la dashboard"""
    try:
        decisions = []
        if os.path.exists(AI_DECISIONS_FILE):
            with open(AI_DECISIONS_FILE, 'r') as f:
                decisions = json.load(f)
        
        # Crea un summary delle posizioni
        positions_summary = []
        for p in positions_details:
            pnl_pct = (p.get('pnl', 0) / (p.get('entry_price', 1) * p.get('size', 1))) * 100 if p.get('entry_price') else 0
            positions_summary.append({
                'symbol': p.get('symbol'),
                'side': p.get('side'),
                'pnl': p.get('pnl'),
                'pnl_pct': round(pnl_pct, 2)
            })
        
        decisions.append({
            'timestamp': datetime.now().isoformat(),
            'symbol': 'PORTFOLIO',
            'action': 'HOLD',
            'leverage': 0,
            'size_pct': 0,
            'rationale': reason,
            'analysis_summary': f"Monitoraggio: {positions_count}/{max_positions} posizioni attive",
            'positions': positions_summary
        })
        
        # Mantieni solo le ultime 100 decisioni
        decisions = decisions[-100:]
        
        os.makedirs(os.path.dirname(AI_DECISIONS_FILE), exist_ok=True)
        with open(AI_DECISIONS_FILE, 'w') as f:
            json.dump(decisions, f, indent=2)
            
    except Exception as e:
        print(f"⚠️ Error saving monitoring decision: {e}")

async def manage_cycle():
    async with httpx.AsyncClient() as c:
        try: await c.post(f"{URLS['pos']}/manage_active_positions", timeout=5)
        except: pass


async def post_with_retries(client: httpx.AsyncClient, url: str, **kwargs):
    """Simple retry helper to reduce transient connection errors."""
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await client.post(url, **kwargs)
        except Exception as e:
            last_error = e
            print(f"        ⚠️ Tentativo {attempt}/{MAX_RETRIES} fallito verso {url}: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)
    raise last_error

async def fetch_trending_symbols(client: httpx.AsyncClient) -> list:
    """Fetch trending symbols from Bybit using 24h turnover as a proxy."""
    try:
        resp = await client.get(BYBIT_TICKERS_URL, params={"category": "linear"})
        data = resp.json()

        if data.get("retCode") != 0:
            print(f"⚠️ Trending fetch failed: {data.get('retMsg')}")
            return []

        rows = data.get("result", {}).get("list", []) if isinstance(data.get("result"), dict) else []
        ranked = sorted(rows, key=lambda r: float(r.get("turnover24h") or 0), reverse=True)

        symbols = []
        for row in ranked:
            sym = row.get("symbol")
            if sym and sym.endswith("USDT"):
                symbols.append(sym)
            if len(symbols) >= TRENDING_LIMIT:
                break

        return symbols
    except Exception as e:
        print(f"⚠️ Error fetching trending symbols: {e}")
        return []

async def get_symbol_universe(client: httpx.AsyncClient) -> list:
    """Return the list of symbols to scan, preferring Bybit trending if enabled."""
    if not USE_TRENDING:
        return DEFAULT_SYMBOLS

    trending = await fetch_trending_symbols(client)
    if trending:
        print(f"🔥 Trending Bybit symbols: {trending}")
        return trending

    print("⚠️ Nessun trending disponibile, uso lista di default")
    return DEFAULT_SYMBOLS

async def analysis_cycle():
    async with httpx.AsyncClient(timeout=60) as c:
        
        # 1. DATA COLLECTION
        portfolio = {}
        position_details = []
        active_symbols = []
        try:
            # Fetch parallelo
            r_bal, r_pos = await asyncio.gather(
                c.get(f"{URLS['pos']}/get_wallet_balance"),
                c.get(f"{URLS['pos']}/get_open_positions"),
                return_exceptions=True
            )
            if hasattr(r_bal, 'json'): portfolio = r_bal.json()
            if hasattr(r_pos, 'json'): 
                d = r_pos.json()
                active_symbols = d.get('active', []) if isinstance(d, dict) else []
                position_details = d.get('details', []) if isinstance(d, dict) else []

        except Exception as e:
            print(f"⚠️ Data Error: {e}")
            return

        num_positions = len(active_symbols)
        print(f"\n[{datetime.now().strftime('%H:%M')}] 📊 Position check: {num_positions}/{MAX_POSITIONS} posizioni aperte")
        
        # 2. LOGICA OTTIMIZZAZIONE
        positions_losing = []
        
        # Controlla posizioni in perdita oltre la soglia
        for pos in position_details:
            entry = pos.get('entry_price', 0)
            mark = pos.get('mark_price', 0)
            side = pos.get('side', '').lower()
            symbol = pos.get('symbol', '')
            leverage = float(pos.get('leverage', 1))
            
            if entry > 0 and mark > 0:
                # Calcola perdita % CON LEVA (come mostrato su Bybit)
                if side in ['long', 'buy']:
                    loss_pct = ((mark - entry) / entry) * leverage * 100
                else:  # short - loss when mark > entry, profit when mark < entry
                    loss_pct = -((mark - entry) / entry) * leverage * 100  # Negative sign because direction is reversed
                
                if loss_pct < -REVERSE_THRESHOLD:
                    positions_losing.append({
                        'symbol': symbol,
                        'loss_pct': loss_pct,
                        'side': side
                    })

        # CASO 1: Tutte le posizioni occupate (3/3)
        if num_positions >= MAX_POSITIONS:
            if positions_losing:
                # Ci sono posizioni in perdita oltre la soglia
                for pos_loss in positions_losing:
                    print(f"        ⚠️ {pos_loss['symbol']} perde {pos_loss['loss_pct']:.2f}%")
                
                # TODO: Implementare logica reverse per chiudere/invertire posizioni in perdita
                # Opzioni possibili:
                # 1. Chiudere la posizione in perdita
                # 2. Chiamare DeepSeek per analisi reverse (chiudere + aprire posizione opposta)
                # 3. Ridurre leverage o size della posizione
                # Per ora monitoriamo solo, il trailing stop gestirà l'uscita automatica
                print(f"        ⚠️ {len(positions_losing)} posizione(i) in perdita critica rilevata(e)")
            else:
                # Controlla se tutte le posizioni sono realmente in profitto o se ci sono perdite minori
                all_positions_status = []
                all_in_profit = True
                
                for pos in position_details:
                    entry = pos.get('entry_price', 0)
                    mark = pos.get('mark_price', 0)
                    side = pos.get('side', '').lower()
                    symbol = pos.get('symbol', '').replace('USDT', '')
                    leverage = float(pos.get('leverage', 1))
                    
                    if entry > 0 and mark > 0:
                        # Calcola P&L % con leva
                        if side in ['long', 'buy']:
                            pnl_pct = ((mark - entry) / entry) * leverage * 100
                        else:  # short
                            pnl_pct = -((mark - entry) / entry) * leverage * 100
                        
                        all_positions_status.append(f"{symbol}: {pnl_pct:+.2f}%")
                        if pnl_pct < 0:
                            all_in_profit = False
                
                # Genera rationale in base allo stato reale
                positions_str = " | ".join(all_positions_status)
                if all_in_profit:
                    rationale = f"Tutte le posizioni in profitto. {positions_str}. Nessuna azione richiesta. Continuo monitoraggio trailing stop."
                else:
                    rationale = f"Posizioni miste. {positions_str}. Nessuna in perdita critica. Continuo monitoraggio trailing stop."
                
                print(f"        ✅ Nessun allarme perdita - Skip analisi DeepSeek")
                save_monitoring_decision(
                    positions_count=len(position_details),
                    max_positions=MAX_POSITIONS,
                    positions_details=position_details,
                    reason=rationale
                )
            return

        # CASO 2: Almeno uno slot libero (< 3 posizioni)
        print(f"        🔍 Slot libero - Chiamo DeepSeek per nuove opportunità")
        
        # 3. FILTER - Solo asset senza posizione aperta
        symbols_universe = await get_symbol_universe(c)
        scan_list = [s for s in symbols_universe if s not in active_symbols]
        if not scan_list:
            print("        ⚠️ Nessun asset disponibile per scan")
            return

        # 4. TECH ANALYSIS
        assets_data = {}
        for s in scan_list:
            try:
                resp = await post_with_retries(
                    c,
                    f"{URLS['tech']}/analyze_multi_tf",
                    json={"symbol": s},
                    timeout=30,
                )

                if resp.status_code != 200:
                    print(f"        ❌ Tech analyzer {s} status {resp.status_code}: {resp.text}")
                    continue

                t = resp.json()
                if not t:
                    print(f"        ⚠️ Dati tecnici vuoti per {s}")
                    continue

                if isinstance(t, dict) and t.get("error"):
                    print(f"        ⚠️ Tech analyzer {s} error: {t.get('error')}")
                    continue

                assets_data[s] = {"tech": t}
            except Exception as e:
                print(f"        ❌ Errore nel chiamare il technical analyzer per {s}: {e}")
        
        if not assets_data: 
            print("        ⚠️ Nessun dato tecnico disponibile")
            save_monitoring_decision(
                positions_count=0,
                max_positions=MAX_POSITIONS,
                positions_details=[],
                reason="Impossibile ottenere dati tecnici dagli analizzatori. Riprovo al prossimo ciclo."
            )
            return

        # 5. AI DECISION
        print(f"        🤖 DeepSeek: Analizzando {list(assets_data.keys())}...")
        try:
            resp = await post_with_retries(
                c,
                f"{URLS['ai']}/decide_batch",
                json={
                    "global_data": {"portfolio": portfolio, "already_open": active_symbols},
                    "assets_data": assets_data
                },
                timeout=120
            )
            
            dec_data = resp.json()
            analysis_text = dec_data.get('analysis', 'No text')
            decisions_list = dec_data.get('decisions', [])

            print(f"        📝 AI Says: {analysis_text}")

            if not decisions_list:
                print("        ℹ️ AI non ha generato ordini")
                return

            # 6. EXECUTION
            for d in decisions_list:
                sym = d['symbol']
                action = d['action']
                
                if action == "CLOSE":
                    print(f"        🛡️ Ignorato CLOSE su {sym} (Auto-Close Disabled)")
                    continue

                if action in ["OPEN_LONG", "OPEN_SHORT"]:
                    print(f"        🔥 EXECUTING {action} on {sym}...")
                    res = await c.post(f"{URLS['pos']}/open_position", json={
                        "symbol": sym,
                        "side": action,
                        "leverage": d.get('leverage', 5),
                        "size_pct": d.get('size_pct', 0.15),
                        "score": d.get('score')
                    })
                    print(f"        ✅ Result: {res.json()}")

        except Exception as e: 
            print(f"        ❌ AI/Exec Error: {e}")

async def main_loop():
    while True:
        await manage_cycle()
        await analysis_cycle()
        await asyncio.sleep(CYCLE_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main_loop())
