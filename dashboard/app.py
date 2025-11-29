import streamlit as st
import pandas as pd
import requests
import time
import plotly.graph_objects as go
from datetime import datetime

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Rizzo AI Hedge Fund", layout="wide", page_icon="🚀")

# URLs dei Microservizi (Docker DNS)
URLS = {
    "technical": "http://technical-analyzer-agent:8000",
    "sentiment": "http://news-sentiment-agent:8000",
    "manager": "http://position-manager-agent:8000",
    "master": "http://master-ai-agent:8000"
}

# --- STILE CSS ---
st.markdown("""
    <style>
    .stMetric {
        background-color: #1E1E1E;
        padding: 10px;
        border-radius: 5px;
        border: 1px solid #333;
    }
    </style>
    """, unsafe_allow_html=True)

# --- FUNZIONI ---
def get_data(url, endpoint):
    try:
        r = requests.get(f"{url}{endpoint}", timeout=3)
        if r.status_code == 200:
            return r.json()
    except:
        return None

def close_position(symbol):
    try:
        url = f"{URLS['manager']}/close_position"
        r = requests.post(url, json={"symbol": symbol}, timeout=5)
        if r.status_code == 200:
            st.toast(f"Order sent to close {symbol}!", icon="✅")
            time.sleep(1)
            st.rerun()
        else:
            st.error(f"Error: {r.text}")
    except Exception as e:
        st.error(f"Connection Error: {e}")

# --- LAYOUT ---
st.title("🧠 Rizzo AI: Autonomous Hedge Fund")

# 1. STATUS CHECK
c1, c2, c3, c4 = st.columns(4)
services = [("Technical", "technical"), ("Sentiment", "sentiment"), ("Manager", "manager"), ("Brain", "master")]

for col, (label, key) in zip([c1,c2,c3,c4], services):
    res = get_data(URLS[key], "/health")
    status = "🟢 ONLINE" if res else "🔴 OFFLINE"
    col.markdown(f"**{label}**: {status}")

st.markdown("---")

# 2. WALLET & PNL
wallet = get_data(URLS['manager'], "/get_wallet_balance")
positions = get_data(URLS['manager'], "/get_open_positions") or []
equity_hist = get_data(URLS['manager'], "/equity_history") or []

bal = wallet.get("balance", 0) if wallet else 0
total_pnl = sum(p.get('pnl', 0) for p in positions)

k1, k2, k3 = st.columns(3)
k1.metric("Wallet Balance", f"${bal:,.2f}")
k2.metric("Open PnL", f"${total_pnl:,.2f}", delta=total_pnl)
k3.metric("Active Trades", len(positions))

# 3. POSITIONS TABLE
st.subheader(f"Active Positions ({len(positions)})")

if not positions:
    st.info("😴 No active trades. Waiting for Rizzo's signal...")
else:
    # Intestazione tabella
    h1, h2, h3, h4, h5, h6 = st.columns([1,1,1,1,1,1])
    h1.markdown("**Symbol**")
    h2.markdown("**Side**")
    h3.markdown("**Size**")
    h4.markdown("**Entry**")
    h5.markdown("**PnL**")
    h6.markdown("**Action**")
    
    for p in positions:
        r1, r2, r3, r4, r5, r6 = st.columns([1,1,1,1,1,1])
        
        color = "green" if p['side'] == "Buy" else "red"
        pnl_val = p.get('pnl', 0)
        pnl_color = "green" if pnl_val >= 0 else "red"
        
        r1.markdown(f"**{p['symbol']}**")
        r2.markdown(f":{color}[{p['side']} x{p.get('leverage',1)}]")
        r3.text(f"{p['size']}")
        r4.text(f"${p['entry_price']:,.2f}")
        r5.markdown(f":{pnl_color}[${pnl_val:.2f}]")
        
        if r6.button("🛑 CLOSE", key=f"btn_{p['symbol']}"):
            close_position(p['symbol'])

st.markdown("---")

# 4. MARKET SENTIMENT & LOGS
c_left, c_right = st.columns([1, 2])

with c_left:
    st.subheader("Market Mood")
    sent = get_data(URLS['sentiment'], "/global_sentiment")
    if sent:
        val = sent.get("score", 50)
        label = sent.get("label", "Neutral")
        
        fig = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = val,
            title = {'text': f"{label}"},
            gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "white"}}
        ))
        fig.update_layout(height=250, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Sentiment Data Unavailable")

with c_right:
    st.subheader("📜 Rizzo's Diary (Latest Logs)")
    logs = get_data(URLS['manager'], "/management_logs")
    
    if st.button("🔄 Refresh Logs"):
        st.rerun()

    if logs:
        log_df = pd.DataFrame(logs)
        st.dataframe(
            log_df[['time', 'pair', 'action', 'status']], 
            hide_index=True, 
            use_container_width=True,
            height=300
        )
    else:
        st.write("Waiting for logs...")

# Auto-refresh ogni 60 secondi
time.sleep(60)
st.rerun()
