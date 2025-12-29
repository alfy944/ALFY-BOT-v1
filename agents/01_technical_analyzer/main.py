from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import traceback
from indicators import CryptoTechnicalAnalysisBybit

app = FastAPI()
analyzer = CryptoTechnicalAnalysisBybit()

class TechRequest(BaseModel):
    symbol: str

class BacktestRequest(BaseModel):
    symbol: str
    limit: int = 2000
    train_split: float = 0.7
    sl_atr_mult: float = 1.0
    max_bars: int = 10
    fee_pct: float = 0.0006
    slippage_pct: float = 0.0002
    hard_stop_pct: float = 0.03

@app.post("/analyze_multi_tf")
def analyze_endpoint(req: TechRequest):
    try:
        data = analyzer.get_complete_analysis(req.symbol)
        if not data:
            return {"symbol": req.symbol, "error": "Analysis Failed", "price": 0, "rsi": 50}
        return data
    except Exception as e:
        print(f"Error analyzing {req.symbol}: {e}\n{traceback.format_exc()}")
        return JSONResponse(
            status_code=200,
            content={"symbol": req.symbol, "error": f"Exception: {e}", "price": 0, "rsi": 50},
        )

@app.post("/backtest_mean_reversion")
def backtest_endpoint(req: BacktestRequest):
    try:
        data = analyzer.backtest_mean_reversion(
            req.symbol,
            limit=req.limit,
            sl_atr_mult=req.sl_atr_mult,
            max_bars=req.max_bars,
            fee_pct=req.fee_pct,
            slippage_pct=req.slippage_pct,
            train_split=req.train_split,
            hard_stop_pct=req.hard_stop_pct,
        )
        return data
    except Exception as e:
        print(f"Error backtesting {req.symbol}: {e}\n{traceback.format_exc()}")
        return JSONResponse(
            status_code=200,
            content={"symbol": req.symbol, "error": f"Exception: {e}"},
        )

@app.get("/health")
def health(): return {"status": "active"}
