import os
import sqlite3
import json
from fastapi import FastAPI
from datetime import datetime, timedelta
from typing import Dict, List, Any

app = FastAPI()

DB_PATH = os.getenv('DB_PATH', './data/trading_history.db')

class TradingLearningAgent:
    """
    Agent that analyzes historical trades to provide insights
    and improve future trading decisions
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def analyze_symbol_performance(self, symbol: str, days: int = 30) -> Dict[str, Any]:
        """Analyze performance for a specific symbol"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        cursor.execute('''
            SELECT COUNT(*) as total_trades,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                   SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                   AVG(pnl) as avg_pnl,
                   SUM(pnl) as total_pnl,
                   AVG(pnl_percentage) as avg_pnl_pct,
                   MAX(pnl) as best_trade,
                   MIN(pnl) as worst_trade,
                   AVG(duration_seconds) as avg_duration,
                   SUM(CASE WHEN was_reversed THEN 1 ELSE 0 END) as reversed_count
            FROM closed_positions
            WHERE symbol = ? AND close_time > ?
        ''', (symbol, cutoff_date))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row or row[0] == 0:
            return {
                "symbol": symbol,
                "has_data": False,
                "recommendation": "No historical data available"
            }
        
        total_trades = row[0]
        winning = row[1] or 0
        losing = row[2] or 0
        avg_pnl = row[3] or 0
        total_pnl = row[4] or 0
        avg_pnl_pct = row[5] or 0
        best_trade = row[6] or 0
        worst_trade = row[7] or 0
        avg_duration = row[8] or 0
        reversed_count = row[9] or 0
        
        win_rate = (winning / total_trades * 100) if total_trades > 0 else 0
        
        # Generate recommendation
        recommendation = self._generate_recommendation(
            win_rate, avg_pnl, total_pnl, avg_pnl_pct, reversed_count
        )
        
        return {
            "symbol": symbol,
            "has_data": True,
            "period_days": days,
            "total_trades": total_trades,
            "winning_trades": winning,
            "losing_trades": losing,
            "win_rate": round(win_rate, 2),
            "avg_pnl": round(avg_pnl, 2),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl_percentage": round(avg_pnl_pct, 2),
            "best_trade": round(best_trade, 2),
            "worst_trade": round(worst_trade, 2),
            "avg_duration_seconds": int(avg_duration),
            "reversed_count": reversed_count,
            "recommendation": recommendation
        }
    
    def _generate_recommendation(self, win_rate: float, avg_pnl: float, 
                                 total_pnl: float, avg_pnl_pct: float, 
                                 reversed_count: int) -> str:
        """Generate trading recommendation based on historical performance"""
        
        if win_rate >= 60 and avg_pnl > 0:
            if avg_pnl_pct > 2.0:
                return "STRONG_BUY - Excellent historical performance"
            return "BUY - Good win rate and positive returns"
        elif win_rate >= 50 and total_pnl > 0:
            return "MODERATE_BUY - Profitable but inconsistent"
        elif win_rate < 40 or total_pnl < -50:
            return "AVOID - Poor historical performance"
        elif reversed_count > 5:
            return "CAUTION - High reversal rate indicates volatility"
        else:
            return "NEUTRAL - Insufficient data for strong recommendation"
    
    def analyze_side_preference(self, symbol: str, days: int = 30) -> Dict[str, Any]:
        """Analyze which side (LONG/SHORT) performs better for a symbol"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        cursor.execute('''
            SELECT side,
                   COUNT(*) as trades,
                   AVG(pnl) as avg_pnl,
                   SUM(pnl) as total_pnl,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins
            FROM closed_positions
            WHERE symbol = ? AND close_time > ?
            GROUP BY side
        ''', (symbol, cutoff_date))
        
        rows = cursor.fetchall()
        conn.close()
        
        results = {}
        for row in rows:
            side = row[0]
            trades = row[1]
            avg_pnl = row[2] or 0
            total_pnl = row[3] or 0
            wins = row[4] or 0
            win_rate = (wins / trades * 100) if trades > 0 else 0
            
            results[side] = {
                "trades": trades,
                "avg_pnl": round(avg_pnl, 2),
                "total_pnl": round(total_pnl, 2),
                "win_rate": round(win_rate, 2)
            }
        
        # Determine preferred side
        preferred_side = None
        if results:
            sorted_sides = sorted(results.items(), key=lambda x: x[1]['total_pnl'], reverse=True)
            if sorted_sides:
                preferred_side = sorted_sides[0][0]
        
        return {
            "symbol": symbol,
            "side_analysis": results,
            "preferred_side": preferred_side
        }
    
    def get_common_mistakes(self, days: int = 30) -> List[Dict[str, Any]]:
        """Identify common trading mistakes from history"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        mistakes = []
        
        # 1. Symbols with high loss rate
        cursor.execute('''
            SELECT symbol,
                   COUNT(*) as total,
                   SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                   AVG(pnl) as avg_pnl
            FROM closed_positions
            WHERE close_time > ?
            GROUP BY symbol
            HAVING COUNT(*) >= 3 AND (losses * 1.0 / total) > 0.6
        ''', (cutoff_date,))
        
        for row in cursor.fetchall():
            mistakes.append({
                "type": "HIGH_LOSS_RATE",
                "symbol": row[0],
                "details": f"Lost {row[2]}/{row[1]} trades, avg PnL: ${row[3]:.2f}",
                "recommendation": f"Avoid or reduce exposure to {row[0]}"
            })
        
        # 2. Frequently reversed positions (indicates bad entries)
        cursor.execute('''
            SELECT symbol, COUNT(*) as reverse_count, AVG(pnl) as avg_loss
            FROM closed_positions
            WHERE close_time > ? AND was_reversed = 1
            GROUP BY symbol
            HAVING COUNT(*) >= 3
        ''', (cutoff_date,))
        
        for row in cursor.fetchall():
            mistakes.append({
                "type": "HIGH_REVERSAL_RATE",
                "symbol": row[0],
                "details": f"Reversed {row[1]} times, avg loss: ${row[2]:.2f}",
                "recommendation": f"Improve entry timing for {row[0]}"
            })
        
        # 3. Quick losses (closed in < 5 minutes with loss)
        cursor.execute('''
            SELECT symbol, COUNT(*) as quick_losses, AVG(pnl) as avg_loss
            FROM closed_positions
            WHERE close_time > ? AND duration_seconds < 300 AND pnl < 0
            GROUP BY symbol
            HAVING COUNT(*) >= 2
        ''', (cutoff_date,))
        
        for row in cursor.fetchall():
            mistakes.append({
                "type": "QUICK_LOSSES",
                "symbol": row[0],
                "details": f"{row[1]} quick losses (<5min), avg: ${row[2]:.2f}",
                "recommendation": f"Wait for better confirmation before entering {row[0]}"
            })
        
        conn.close()
        return mistakes
    
    def get_best_performing_patterns(self, days: int = 30) -> List[Dict[str, Any]]:
        """Identify patterns that led to successful trades"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        patterns = []
        
        # 1. Best performing symbols
        cursor.execute('''
            SELECT symbol, 
                   COUNT(*) as trades,
                   SUM(pnl) as total_pnl,
                   AVG(pnl_percentage) as avg_pnl_pct,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins
            FROM closed_positions
            WHERE close_time > ? AND pnl > 0
            GROUP BY symbol
            HAVING COUNT(*) >= 3 AND SUM(pnl) > 50
            ORDER BY total_pnl DESC
            LIMIT 5
        ''', (cutoff_date,))
        
        for row in cursor.fetchall():
            symbol = row[0]
            trades = row[1]
            total_pnl = row[2]
            avg_pnl_pct = row[3]
            wins = row[4]
            win_rate = (wins / trades * 100) if trades > 0 else 0
            
            patterns.append({
                "type": "PROFITABLE_SYMBOL",
                "symbol": symbol,
                "trades": trades,
                "total_pnl": round(total_pnl, 2),
                "avg_pnl_percentage": round(avg_pnl_pct, 2),
                "win_rate": round(win_rate, 2),
                "recommendation": f"Continue trading {symbol} with current strategy"
            })
        
        conn.close()
        return patterns
    
    def generate_insights(self, symbols: List[str]) -> Dict[str, Any]:
        """Generate comprehensive insights for given symbols"""
        insights = {
            "timestamp": datetime.now().isoformat(),
            "symbols_analysis": {},
            "common_mistakes": self.get_common_mistakes(),
            "best_patterns": self.get_best_performing_patterns(),
            "overall_recommendation": ""
        }
        
        for symbol in symbols:
            perf = self.analyze_symbol_performance(symbol)
            side_pref = self.analyze_side_preference(symbol)
            
            insights["symbols_analysis"][symbol] = {
                "performance": perf,
                "side_preference": side_pref
            }
        
        # Generate overall recommendation
        total_mistakes = len(insights["common_mistakes"])
        total_patterns = len(insights["best_patterns"])
        
        if total_patterns > total_mistakes:
            insights["overall_recommendation"] = "System is learning and improving. Continue with current strategy."
        elif total_mistakes > 5:
            insights["overall_recommendation"] = "High number of mistakes detected. Consider reducing position sizes."
        else:
            insights["overall_recommendation"] = "Balanced performance. Monitor closely."
        
        return insights

# Initialize agent
learning_agent = TradingLearningAgent(DB_PATH)

@app.post("/analyze_symbols")
def analyze_symbols(payload: Dict[str, Any]):
    """Analyze performance for specific symbols"""
    symbols = payload.get('symbols', [])
    days = payload.get('days', 30)
    
    if not symbols:
        return {"error": "No symbols provided"}
    
    insights = learning_agent.generate_insights(symbols)
    return insights

@app.get("/get_insights")
def get_insights():
    """Get general trading insights"""
    # Analyze common symbols
    default_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    insights = learning_agent.generate_insights(default_symbols)
    return insights

@app.get("/common_mistakes")
def get_common_mistakes():
    """Get list of common trading mistakes"""
    mistakes = learning_agent.get_common_mistakes(days=30)
    return {"mistakes": mistakes, "count": len(mistakes)}

@app.get("/best_patterns")
def get_best_patterns():
    """Get best performing trading patterns"""
    patterns = learning_agent.get_best_performing_patterns(days=30)
    return {"patterns": patterns, "count": len(patterns)}

@app.get("/health")
def health():
    return {"status": "active", "agent": "learning"}
