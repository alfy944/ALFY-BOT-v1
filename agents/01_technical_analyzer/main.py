from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import traceback
from indicators import CryptoTechnicalAnalysisBybit

app = FastAPI()
analyzer = CryptoTechnicalAnalysisBybit()

class TechRequest(BaseModel):
    symbol: str

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

@app.get("/health")
def health(): return {"status": "active"}
