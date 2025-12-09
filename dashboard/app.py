"""
Dashboard Trading con Design Minimal Modern
Redesign completo con nuove funzionalità professionali
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import time
from datetime import datetime
from bybit_client import BybitClient
from components.fees_tracker import render_fees_section, get_trading_fees
from components.api_costs import render_api_costs_section, calculate_api_costs

# --- CONFIGURAZIONE ---
st.set_page_config(
    layout="wide", 
    page_title="Trading Dashboard", 
    page_icon="📈",
    initial_sidebar_state="expanded"
)

# --- CSS MINIMAL MODERN ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    /* Base */
    .stApp {
        background-color: #f8f9fa;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Cards */
    .metric-card {
        background: white;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        border: 1px solid #e5e7eb;
        margin-bottom: 16px;
    }
    
    .metric-value {
        font-size: 28px;
        font-weight: 700;
        color: #111827;
        margin: 8px 0;
    }
    
    .metric-label {
        font-size: 14px;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-weight: 500;
    }
    
    .profit { color: #10b981; }
    .loss { color: #ef4444; }
    
    /* Section headers */
    .section-title {
        font-size: 18px;
        font-weight: 600;
        color: #374151;
        margin-bottom: 16px;
        padding-bottom: 8px;
        border-bottom: 2px solid #e5e7eb;
    }
    
    /* Header */
    .dashboard-header {
        background: white;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        border: 1px solid #e5e7eb;
    }
    
    .status-online {
        color: #10b981;
        font-weight: 600;
    }
    
    .status-offline {
        color: #ef4444;
        font-weight: 600;
    }
    
    /* Metrics override */
    div[data-testid="stMetric"] {
        background-color: white;
        border: 1px solid #e5e7eb;
        padding: 16px;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    
    div[data-testid="stMetric"] label {
        color: #6b7280 !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #111827 !important;
        font-size: 24px !important;
        font-weight: 700 !important;
    }
    
    /* Tables */
    .dataframe {
        border: none !important;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: white;
        border-radius: 8px;
        padding: 8px 16px;
        border: 1px solid #e5e7eb;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #3b82f6;
        color: white !important;
    }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display: none;}
    
    /* Info boxes */
    .info-box {
        background: #eff6ff;
        border-left: 4px solid #3b82f6;
        padding: 12px;
        border-radius: 8px;
        margin: 16px 0;
        color: #1e40af;
    }
    
    .success-box {
        background: #f0fdf4;
        border-left: 4px solid #10b981;
        padding: 12px;
        border-radius: 8px;
        margin: 16px 0;
        color: #065f46;
    }
    
    .warning-box {
        background: #fef3c7;
        border-left: 4px solid #f59e0b;
        padding: 12px;
        border-radius: 8px;
        margin: 16px 0;
        color: #92400e;
    }
</style>
""", unsafe_allow_html=True)

# --- HEADER ---
st.markdown('<div class="dashboard-header">', unsafe_allow_html=True)
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown("# 📈 Trading Dashboard")
    st.caption("Sistema di trading automatico con AI")
with col2:
    st.markdown(f'<p style="text-align: right; margin-top: 20px;">⏱️ {datetime.now().strftime("%H:%M:%S")}</p>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# --- CARICAMENTO DATI ---
try:
    client = BybitClient()
    wallet = client.get_wallet_balance()
    system_online = True
except Exception as e:
    st.error(f"⚠️ Sistema OFFLINE: {e}")
    system_online = False
    wallet = None
    st.stop()

# --- KPI PRINCIPALI ---
if wallet:
    st.markdown('<div class="section-title">📊 Key Performance Indicators</div>', unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    
    equity = wallet.get('equity', 0)
    balance = wallet.get('wallet_balance', 0)
    available = wallet.get('available', 0)
    pnl = wallet.get('unrealized_pnl', 0)
    
    with col1:
        st.metric("Total Equity", f"${equity:.2f}")
    
    with col2:
        st.metric("Wallet Balance", f"${balance:.2f}")
    
    with col3:
        st.metric("Available", f"${available:.2f}")
    
    with col4:
        pnl_color = "normal" if pnl >= 0 else "inverse"
        st.metric("PnL Aperto", f"${pnl:.2f}", delta=f"{pnl:.2f}", delta_color=pnl_color)
    
    st.markdown("---")

# --- COMMISSIONI BYBIT ---
try:
    render_fees_section()
    st.markdown("---")
except Exception as e:
    st.warning(f"⚠️ Impossibile caricare commissioni: {e}")

# --- COSTI API DEEPSEEK ---
try:
    render_api_costs_section()
    st.markdown("---")
except Exception as e:
    st.warning(f"⚠️ Impossibile caricare costi API: {e}")

# --- TABS PRINCIPALI ---
tab1, tab2, tab3 = st.tabs(["⚡ Posizioni Aperte", "📊 Performance & Grafici", "📜 Storico Trading"])

with tab1:
    st.markdown('<div class="section-title">Posizioni Attive</div>', unsafe_allow_html=True)
    
    positions = client.get_open_positions()
    
    if positions:
        df_pos = pd.DataFrame(positions)
        
        # Aggiungi colori alle celle PnL
        st.dataframe(
            df_pos, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Unrealized PnL": st.column_config.NumberColumn(
                    format="$%.2f",
                ),
                "PnL %": st.column_config.NumberColumn(
                    format="%.2f%%",
                ),
                "Entry Price": st.column_config.NumberColumn(
                    format="$%.2f",
                ),
            }
        )
        
        # Grafici per ogni posizione
        st.markdown('<div class="section-title">📈 Grafici Posizioni</div>', unsafe_allow_html=True)
        
        for idx, pos in enumerate(positions):
            with st.expander(f"{pos['Symbol']} - {pos['Side']} - PnL: ${pos['Unrealized PnL']:.2f}"):
                # Gauge meter per PnL %
                pnl_pct = pos['PnL %']
                
                fig_gauge = go.Figure(go.Indicator(
                    mode="gauge+number+delta",
                    value=pnl_pct,
                    title={'text': f"PnL % - {pos['Symbol']}"},
                    delta={'reference': 0},
                    gauge={
                        'axis': {'range': [-10, 10]},
                        'bar': {'color': "#10b981" if pnl_pct >= 0 else "#ef4444"},
                        'steps': [
                            {'range': [-10, -5], 'color': "#fee2e2"},
                            {'range': [-5, 0], 'color': "#fef3c7"},
                            {'range': [0, 5], 'color': "#d1fae5"},
                            {'range': [5, 10], 'color': "#a7f3d0"}
                        ],
                        'threshold': {
                            'line': {'color': "black", 'width': 4},
                            'thickness': 0.75,
                            'value': pnl_pct
                        }
                    }
                ))
                
                fig_gauge.update_layout(
                    height=250,
                    margin=dict(l=20, r=20, t=40, b=20),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font={'color': '#374151'}
                )
                
                st.plotly_chart(fig_gauge, use_container_width=True)
    else:
        st.markdown('<div class="success-box">🟢 Nessuna posizione attiva al momento</div>', unsafe_allow_html=True)

with tab2:
    st.markdown('<div class="section-title">Equity Curve</div>', unsafe_allow_html=True)
    
    hist = client.get_closed_pnl(limit=100)
    
    if hist:
        df_hist = pd.DataFrame(hist)
        
        # Equity curve
        df_chart = df_hist.iloc[::-1].copy()
        df_chart['CumPnL'] = df_chart['Closed PnL'].cumsum()
        
        fig_equity = go.Figure()
        
        # Area chart per equity
        fig_equity.add_trace(go.Scatter(
            x=list(range(len(df_chart))),
            y=df_chart['CumPnL'],
            mode='lines',
            name='Profitto Cumulativo',
            line=dict(color='#10b981', width=3),
            fill='tozeroy',
            fillcolor='rgba(16, 185, 129, 0.1)'
        ))
        
        fig_equity.update_layout(
            title="Curva dei Profitti (Cumulative PnL)",
            template="plotly_white",
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='white',
            height=400,
            margin=dict(l=20, r=20, t=40, b=20),
            xaxis_title="Trade #",
            yaxis_title="PnL Cumulativo ($)",
            font={'color': '#374151'}
        )
        
        st.plotly_chart(fig_equity, use_container_width=True)
        
        # Statistiche performance
        st.markdown('<div class="section-title">📊 Statistiche Performance</div>', unsafe_allow_html=True)
        
        total_trades = len(df_hist)
        winning_trades = len(df_hist[df_hist['Closed PnL'] > 0])
        losing_trades = len(df_hist[df_hist['Closed PnL'] < 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        total_pnl = df_hist['Closed PnL'].sum()
        avg_win = df_hist[df_hist['Closed PnL'] > 0]['Closed PnL'].mean() if winning_trades > 0 else 0
        avg_loss = df_hist[df_hist['Closed PnL'] < 0]['Closed PnL'].mean() if losing_trades > 0 else 0
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Trades", total_trades)
        
        with col2:
            st.metric("Win Rate", f"{win_rate:.1f}%")
        
        with col3:
            st.metric("Total PnL", f"${total_pnl:.2f}")
        
        with col4:
            profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0
            st.metric("Profit Factor", f"{profit_factor:.2f}")
        
        # Pie chart distribuzione wins/losses
        st.markdown('<div class="section-title">🥧 Distribuzione Win/Loss</div>', unsafe_allow_html=True)
        
        fig_pie = go.Figure(data=[go.Pie(
            labels=['Winning Trades', 'Losing Trades'],
            values=[winning_trades, losing_trades],
            marker=dict(colors=['#10b981', '#ef4444']),
            hole=0.4
        )])
        
        fig_pie.update_layout(
            height=300,
            margin=dict(l=20, r=20, t=20, b=20),
            paper_bgcolor='rgba(0,0,0,0)',
            font={'color': '#374151'}
        )
        
        st.plotly_chart(fig_pie, use_container_width=True)
        
    else:
        st.markdown('<div class="info-box">ℹ️ Nessuno storico disponibile</div>', unsafe_allow_html=True)

with tab3:
    st.markdown('<div class="section-title">Storico Posizioni Chiuse</div>', unsafe_allow_html=True)
    
    hist = client.get_closed_pnl(limit=50)
    
    if hist:
        df_hist = pd.DataFrame(hist)
        
        # Rimuovi colonne non necessarie per la visualizzazione
        display_cols = ['Symbol', 'Side', 'Closed PnL', 'Exit Time']
        if 'exec_fee' in df_hist.columns:
            display_cols.insert(3, 'exec_fee')
            df_hist = df_hist.rename(columns={'exec_fee': 'Fee'})
        
        df_display = df_hist[[col for col in display_cols if col in df_hist.columns or col == 'Fee']]
        
        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Closed PnL": st.column_config.NumberColumn(format="$%.2f"),
                "Fee": st.column_config.NumberColumn(format="$%.4f"),
            }
        )
    else:
        st.markdown('<div class="info-box">ℹ️ Nessuno storico disponibile</div>', unsafe_allow_html=True)

# --- AI REVIEW STATUS (Placeholder per future integration) ---
st.markdown("---")
st.markdown('<div class="section-title">🤖 AI Review Status</div>', unsafe_allow_html=True)
st.markdown('<div class="info-box">ℹ️ Funzionalità in fase di integrazione - Mostrerà le ultime decisioni AI (HOLD/CLOSE/REVERSE)</div>', unsafe_allow_html=True)

# --- FOOTER ---
st.markdown("---")
col1, col2, col3 = st.columns(3)
with col1:
    st.caption("🟢 Sistema Online" if system_online else "🔴 Sistema Offline")
with col2:
    st.caption(f"Ultimo aggiornamento: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
with col3:
    st.caption("Auto-refresh: 5 secondi")

# --- AUTO REFRESH ---
time.sleep(5)
st.rerun()
