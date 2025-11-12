def manage_trade(current_price: float, entry_price: float, direction: str, tech_analysis: dict) -> dict:
    """
    Analizza una posizione aperta e decide come aggiornare SL e TP.

    Args:
        current_price: Il prezzo attuale del mercato.
        entry_price: Il prezzo a cui siamo entrati nell'operazione.
        direction: 'LONG' o 'SHORT'.
        tech_analysis: L'output completo e aggiornato dell'agente tecnico.

    Returns:
        Un dizionario con le azioni da intraprendere.
    """
    
    # Estraiamo i dati chiave dalla nuova analisi
    rsi = tech_analysis.get('rsi')
    macd = tech_analysis.get('macd')
    macd_signal = tech_analysis.get('macd_signal')
    trend = tech_analysis.get('trend_strength')

    # Calcoliamo il profitto/perdita attuale (P/L)
    if direction == 'LONG':
        p_l_ratio = (current_price - entry_price) / entry_price
    else: # SHORT
        p_l_ratio = (entry_price - current_price) / entry_price

    # --- LOGICA DI GESTIONE ---
    action = "HOLD" # Azione di default
    comment = "Le condizioni non richiedono un intervento."
    new_stop_loss = None # Lascia invariato di default

    # 1. Regola di Chiusura Anticipata (Protezione Capitale)
    # Se il trend si è invertito con forza, chiudiamo prima di toccare lo SL.
    is_long_and_reversing = direction == 'LONG' and macd < macd_signal and trend < -0.3
    is_short_and_reversing = direction == 'SHORT' and macd > macd_signal and trend > 0.3

    if p_l_ratio < 0 and (is_long_and_reversing or is_short_and_reversing):
        action = "CLOSE_NOW"
        comment = f"Chiusura anticipata: il trend si è invertito con forza (Trend: {trend:.2f})."
        return {"action": action, "comment": comment}

    # 2. Trailing Stop (Protezione Profitto)
    # Se siamo in profitto, spostiamo lo stop loss a breakeven o più su.
    if p_l_ratio > 0.005: # Se siamo in profitto di almeno lo 0.5%
        if direction == 'LONG':
            # Sposta lo SL leggermente sopra il prezzo di ingresso
            new_stop_loss = entry_price * 1.001 
            action = "UPDATE_SL"
            comment = f"Profitto rilevato. Spostamento SL a breakeven ({new_stop_loss:.2f}) per proteggere l'investimento."
        elif direction == 'SHORT':
            # Sposta lo SL leggermente sotto il prezzo di ingresso
            new_stop_loss = entry_price * 0.999
            action = "UPDATE_SL"
            comment = f"Profitto rilevato. Spostamento SL a breakeven ({new_stop_loss:.2f}) per proteggere l'investimento."

    # In futuro qui potremmo aggiungere la logica per il take profit parziale

    return {
        "action": action,
        "new_stop_loss": new_stop_loss,
        "comment": comment,
        "current_p_l_ratio": p_l_ratio
    }
