import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import time

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Mitragliere Terminal", layout="wide", page_icon="💣")

# URLs (INTERNAL DOCKER DNS) - QUESTI FUNZIONANO SEMPRE NELLA RETE BRIDGE
URLS = {
    "manager": "http://position-manager-agent:8000",
    "sentiment": "http://news-sentiment-agent:8000",
    "technical": "http://technical-analyzer-agent:8000"
}

# --- CSS STYLE ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #1c1f26; border: 1px solid #2d3436; padding: 15px; border-radius: 5px; }
    .metric-label { font-size: 0.8rem; color: #b2bec3; }
    .metric-value { font-size: 1.8rem; font-weight: bold; color: #ffffff; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNZIONI ---
def fetch(url, endpoint, default=None):
    try:
        r = requests.get(f"{url}{endpoint}", timeout=2)
        if r.status_code == 200: return r.json()
    except Exception as e:
        # Debug log nascosto nel terminale del container
        print(f"Connection Error to {url}: {e}")
        pass
    return default

def close_pos_req(symbol):
    try:
        requests.post(f"{URLS['manager']}/close_position", json={"symbol": symbol}, timeout=3)
        st.toast(f"Sent close order for {symbol}", icon="💣")
    except: st.error("Failed to close position")

# --- LOAD DATA ---
wallet = fetch(URLS['manager'], "/get_wallet_balance", {})
positions = fetch(URLS['manager'], "/get_open_positions", [])
logs = fetch(URLS['manager'], "/management_logs", [])
sent_data = fetch(URLS['sentiment'], "/global_sentiment", {})
equity_hist = fetch(URLS['manager'], "/equity_history", [])

# Se il wallet è vuoto, mostriamo un errore chiaro invece di crashare
if not wallet and not logs:
    st.error("⚠️ ERRORE DI CONNESSIONE: La Dashboard non raggiunge il Position Manager.")
    st.stop()

# --- DISPLAY ---
balance = wallet.get("balance", 0.0)
active_pnl = sum(p.get('pnl', 0) for p in positions) if positions else 0
equity = balance + active_pnl

st.title("💣 Mitragliere AI Hedge Fund")

# KPI
k1, k2, k3 = st.columns(3)
k1.metric("Wallet Balance", f"${balance:,.2f}")
k2.metric("Live Equity", f"${equity:,.2f}", delta=f"{active_pnl:.2f}")
k3.metric("Active Trades", len(positions) if positions else 0)

st.divider()

c1, c2 = st.columns([2, 1])

with c1:
    st.subheader("⚡ Active Positions")
    if positions:
        df = pd.DataFrame(positions)
        st.dataframe(df[['symbol', 'side', 'size', 'entry_price', 'pnl', 'stop_loss']], use_container_width=True)
        
        # Close buttons
        for p in positions:
            if st.button(f"CLOSE {p['symbol']}", key=p['symbol']):
                close_pos_req(p['symbol'])
    else:
        st.info("No active positions. Waiting for signals.")

with c2:
    st.subheader("📜 Mission Logs")
    if logs:
        log_txt = ""
        for l in logs[:20]:
             log_txt += f"{l.get('time','')} | {l.get('action','')}\n"
        st.text_area("Logs", log_txt, height=400)
    else:
        st.warning("No logs available yet.")

time.sleep(10)
st.rerun()
