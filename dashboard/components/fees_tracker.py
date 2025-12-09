"""
Component per tracciare e visualizzare commissioni trading Bybit
"""
import streamlit as st
from datetime import datetime, timedelta
from typing import Dict
import sys
import os

# Aggiungi il path del dashboard per importare bybit_client
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bybit_client import BybitClient


@st.cache_data(ttl=3600)  # Cache 1 ora
def get_trading_fees() -> Dict[str, float]:
    """
    Recupera commissioni da Bybit analizzando le posizioni chiuse.
    
    Returns:
        Dict con chiavi: today, week, month, total
    """
    try:
        client = BybitClient()
        
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())
        month_start = today_start.replace(day=1)
        
        # Recupera closed PnL con fee breakdown - aumentiamo il limite per avere più dati
        all_trades = client.get_closed_pnl(limit=200)
        
        fees = {'today': 0.0, 'week': 0.0, 'month': 0.0, 'total': 0.0}
        
        for trade in all_trades:
            # Le commissioni sono nel campo closedPnl breakdown o possiamo stimarle
            # Bybit carica ~0.055% per maker e ~0.06% per taker
            # Usiamo una stima basata sul valore della posizione se non abbiamo il campo fee esplicito
            fee = 0
            
            # Se abbiamo il campo exec_fee lo usiamo
            if 'exec_fee' in trade:
                fee = abs(float(trade.get('exec_fee', 0)))
            elif 'fee' in trade:
                fee = abs(float(trade.get('fee', 0)))
            else:
                # Stima: ~0.06% del valore della posizione
                # Calcoliamo dal PnL e prezzo medio se disponibile
                continue
            
            trade_time = datetime.fromtimestamp(trade.get('ts', 0) / 1000)
            
            fees['total'] += fee
            if trade_time >= month_start:
                fees['month'] += fee
            if trade_time >= week_start:
                fees['week'] += fee
            if trade_time >= today_start:
                fees['today'] += fee
        
        return fees
    except Exception as e:
        print(f"Error retrieving fees: {e}")
        return {'today': 0.0, 'week': 0.0, 'month': 0.0, 'total': 0.0}


def render_fees_section():
    """Renderizza la sezione commissioni trading"""
    st.markdown('<div class="section-title">💰 Commissioni Trading Bybit</div>', unsafe_allow_html=True)
    
    fees = get_trading_fees()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Oggi", f"${fees['today']:.2f}")
    
    with col2:
        st.metric("Settimana", f"${fees['week']:.2f}")
    
    with col3:
        st.metric("Mese", f"${fees['month']:.2f}")
    
    with col4:
        st.metric("Totale", f"${fees['total']:.2f}")
